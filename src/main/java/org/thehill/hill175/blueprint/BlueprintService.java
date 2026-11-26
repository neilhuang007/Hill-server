package org.thehill.hill175.blueprint;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.world.WorldModule;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Properties;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.function.Predicate;
import java.util.logging.Level;

/**
 * Git-like campus workflow. Each personal campus is a branch of the shared blueprint. Students take a
 * snapshot of their build and send it for approval without pausing their campus. Every approval is
 * stored as an update packet; personal campuses merge updates automatically, and blocks changed on
 * both sides become conflicts that the owner resolves.
 */
public final class BlueprintService implements AutoCloseable {
    private static final Duration SNAPSHOT_LIFETIME = Duration.ofMinutes(20);
    private static final int CONFLICT_LIMIT = 262_144;
    private final JavaPlugin plugin;
    private final CompetitionStore store;
    private final CompetitionModule competition;
    private final WorldModule worlds;
    private final Path folder;
    private final BlueprintRepository submissions;
    private final BlueprintBackups backups;
    private final BlueprintOutlines outlines;
    private final BlueprintReview reviews;
    private final Map<UUID, Branch> branches = new HashMap<>();
    private final Map<String, UUID> branchByWorld = new HashMap<>();
    private final Map<Long, Approval> approvals = new HashMap<>();
    private final Map<Long, List<BlockChange>> packets = new LinkedHashMap<>(16, 0.75f, true) {
        @Override protected boolean removeEldestEntry(Map.Entry<Long, List<BlockChange>> eldest) { return size() > 8; }
    };
    private final Set<UUID> staging = new HashSet<>();
    private final Set<UUID> resetting = new HashSet<>();
    /** Staff edits of the live blueprint: each touched chunk as it was before its first edit. */
    private final Map<Long, BlueprintStage.Side> draft = new HashMap<>();
    private final Map<BlockPosition, BlockSnapshot> draftOverrides = new HashMap<>();
    private final Map<UUID, String> editors = new LinkedHashMap<>();
    private final Set<String> previews = new HashSet<>();
    private boolean committingDraft;
    private long lastDraftEdit;
    private static final long DRAFT_IDLE_NANOS = Duration.ofMinutes(2).toNanos();
    private final Set<String> failedWorlds = new HashSet<>();
    private final LinkedHashSet<UUID> syncQueue = new LinkedHashSet<>();
    private Predicate<String> textAllowed = text -> false;
    private PlayerScreens screens;
    private World blueprint;
    private long editSequence;
    private boolean initialized;
    private boolean merging;
    private boolean saving;
    private boolean closing;
    private boolean failed;

    /** Player screens live in the UI package; commands and notices open them through this hook. */
    public interface PlayerScreens {
        void menu(Player player);
        void send(Player player);
        void conflicts(Player player);
        void review(Player player);
        void visit(Player player);
    }

    /** Staff edits and rollbacks are recorded as updates of this reserved entry; no campus has it. */
    static final UUID STAFF_ENTRY = UUID.nameUUIDFromBytes("hill175:blueprint-staff".getBytes(java.nio.charset.StandardCharsets.UTF_8));

    public record Revision(long number, String title, String author, Instant when, boolean staff) { }

    public enum ConflictChoice { REFUSE, KEEP_BLUEPRINT, USE_PROPOSAL }

    /** A point-in-time snapshot of a campus compared with the blueprint revision it is based on. */
    public record Snapshot(UUID entryId, String author, long revision, Instant takenAt,
                           List<BlockChange> changes, List<ChangeAreas.Area> areas) {
        public Snapshot {
            changes = List.copyOf(changes);
            areas = List.copyOf(areas);
        }
    }

    public record Overview(Entry entry, boolean updating, long revision, int conflicts,
                           BlueprintRepository.Summary waiting, BlueprintRepository.Summary lastDecision) { }

    public record CampusConflict(BlockPosition position, BlockSnapshot mine, BlockSnapshot blueprint) { }

    private record Approval(UUID submission, UUID entryId) { }

    static final class Branch {
        final UUID entryId;
        final String owner;
        final String world;
        final UUID worldId;
        final String bounds;
        final String legacyBaseline;
        long syncedThrough;
        long notifiedThrough;
        String seenDecision = "";
        final Set<String> chunks = new HashSet<>();
        final Map<String, Long> lastEdit = new HashMap<>();
        final Map<BlockPosition, BlockChange> conflicts = new TreeMap<>();
        boolean conflictsChanged;
        String conflictFile;
        String conflictDigest;

        Branch(UUID entryId, String owner, String world, UUID worldId, String bounds, String legacyBaseline) {
            this.entryId = entryId;
            this.owner = owner;
            this.world = world;
            this.worldId = worldId;
            this.bounds = bounds;
            this.legacyBaseline = legacyBaseline;
        }
    }

    public BlueprintService(JavaPlugin plugin, CompetitionStore store, CompetitionModule competition, WorldModule worlds) {
        this.plugin = plugin;
        this.store = store;
        this.competition = competition;
        this.worlds = worlds;
        folder = plugin.getDataFolder().toPath().resolve("blueprint");
        try {
            submissions = new BlueprintRepository(folder.resolve("submissions"));
            backups = new BlueprintBackups(plugin);
        } catch (IOException exception) { throw new UncheckedIOException(exception); }
        outlines = new BlueprintOutlines(plugin);
        reviews = new BlueprintReview(plugin, this, competition, outlines);
    }

    public static Path prepareTemplate(JavaPlugin plugin) {
        try { return BlueprintWorldFiles.prepareTemplate(plugin); }
        catch (IOException exception) { throw new UncheckedIOException("Cannot prepare the accepted blueprint.", exception); }
    }

    public void textAllowed(Predicate<String> predicate) { textAllowed = java.util.Objects.requireNonNull(predicate); }
    public void playerScreens(PlayerScreens screens) { this.screens = java.util.Objects.requireNonNull(screens); }

    public void initialize() {
        requireMainThread();
        try {
            blueprint = BlueprintWorldFiles.load(plugin, "hill_blueprint", false);
            recoverMerge();
            withdrawInterruptedStaffChanges();
            deleteLeftoverPreviews();
            loadApprovals();
            loadBranches();
            prepareTemplate(plugin);
            initialized = true;
            for (World world : Bukkit.getWorlds()) worldLoaded(world);
            enqueueBehind();
            plugin.getServer().getScheduler().runTaskTimer(plugin, this::autoSync, 20L, 10L);
        } catch (Exception exception) { failClosed("Blueprint initialization/recovery failed; editing and approval are blocked.", exception); }
        outlines.start();
        reviews.start();
    }

    public BlueprintListener listener() { return new BlueprintListener(this); }
    public BlueprintCommands commands() { return new BlueprintCommands(this); }
    public BlueprintRepository repository() { return submissions; }
    public BlueprintBackups backups() { return backups; }
    public BlueprintReview reviewControls() { return reviews; }
    public BlueprintOutlines outlines() { return outlines; }
    World acceptedWorld() { requireMainThread(); requireReady(); return blueprint; }
    public void openReview(Player player) { requireReviewer(player); screens().review(player); }
    public PlayerScreens screens() {
        if (screens == null) throw new IllegalStateException("Blueprint menus are not ready yet.");
        return screens;
    }

    // ---------------------------------------------------------------- branches

    public void registerBranch(Entry entry) {
        requireMainThread();
        ensureCanCreateBranch();
        if (branches.containsKey(entry.id())) throw new IllegalStateException("This campus is already connected to the blueprint.");
        requireCanonicalOwner(entry, soleOwner(entry));
        if (!entry.worldName().matches("hill_(people|place)_[a-f0-9]{12}")) throw new IllegalArgumentException("Blueprint branches require a private campus copy.");
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) throw new IllegalStateException("The new campus copy is not ready.");
        try {
            long latest = latestRevision();
            long copied = BlueprintWorldFiles.revisionMarker(world.getWorldFolder().toPath()).orElse(latest);
            if (copied < 0 || copied > latest) throw new IOException("The new campus records an unknown blueprint revision.");
            Branch branch = new Branch(entry.id(), soleOwner(entry), entry.worldName(), world.getUID(), bounds(entry), null);
            branch.syncedThrough = copied;
            branch.notifiedThrough = copied;
            saveBranch(branch);
            index(branch);
            quiet(world);
            if (copied < latest) syncQueue.add(entry.id());
        } catch (Exception exception) {
            failedWorlds.add(entry.worldName());
            failClosed("Cannot record the new campus branch; editing was stopped.", exception);
            throw new IllegalStateException("The campus could not be connected to the blueprint. Staff must check the server log.", exception);
        }
    }

    public boolean isRegistered(Entry entry) { return entry != null && branches.containsKey(entry.id()); }

    public void ensureCanCreateBranch() {
        requireMainThread();
        requireReady();
        if (merging || saving) throw new IllegalStateException("The blueprint is being saved. Try again in a moment.");
    }

    /** Campuses never pause for review; they only stop when recovery is required. */
    public boolean isFrozen(Entry entry) {
        if (entry == null) return true;
        if (!initialized || failed || closing || failedWorlds.contains(entry.worldName()) || resetting.contains(entry.id())) return true;
        Branch branch = branches.get(entry.id());
        return branch != null && !validBranch(entry, branch);
    }

    /**
     * Campuses are compared block by block with the blueprint, which has no random ticks. A campus with
     * random ticks would decay grass and leaves on its own, and those changes would look like student edits.
     */
    public void worldLoaded(World world) {
        if (branchByWorld.containsKey(world.getName())) quiet(world);
    }

    private static void quiet(World world) {
        world.setGameRule(org.bukkit.GameRules.RANDOM_TICK_SPEED, 0);
    }

    public boolean isCampus(World world) { return world != null && branchByWorld.containsKey(world.getName()); }

    /** Natural block changes (decay, spread, fading) never happen in campuses or the blueprint. */
    public boolean stopsNaturalChanges(World world) {
        return world != null && (branchByWorld.containsKey(world.getName()) || isBlueprint(world) || protects(world));
    }

    public boolean isBlueprint(World world) { return world != null && blueprint != null && world.equals(blueprint); }

    /** The shared blueprint can only change while staff are editing it. Saved versions and previews never change. */
    public boolean protects(World world) {
        if (world == null) return false;
        String name = world.getName();
        if (isBlueprint(world)) return editors.isEmpty() || committingDraft || failed || closing || !initialized || merging || saving;
        if (name.equals("hill_blueprint") || name.startsWith("hill_bp_") || name.startsWith("hill_replay_") || failedWorlds.contains(name)) return true;
        UUID entryId = branchByWorld.get(name);
        if (entryId == null) return false;
        Branch branch = branches.get(entryId);
        return failed || closing || !initialized || resetting.contains(entryId) || store.entry(entryId).filter(entry -> validBranch(entry, branch)).isEmpty();
    }

    /** Whether this player may change blocks or containers in this world, as far as the blueprint is concerned. */
    public boolean mayChange(Player player, World world) {
        return !protects(world) && (!isBlueprint(world) || editor(player));
    }

    /** Journals the edited chunk and its neighbors before a block changes. */
    public boolean changed(World world, int blockX, int blockZ) {
        requireMainThread();
        if (world == null) return true;
        if (isBlueprint(world)) return !protects(world) && captureDraft(blockX, blockZ);
        if (protects(world)) return false;
        UUID entryId = branchByWorld.get(world.getName());
        if (entryId == null) return true;
        Branch branch = branches.get(entryId);
        if (!world.getUID().equals(branch.worldId)) {
            failedWorlds.add(world.getName());
            failClosed("Campus world identity no longer matches its branch.", new IOException(world.getName()));
            return false;
        }
        long sequence = ++editSequence;
        boolean added = false;
        for (int chunkX = (blockX >> 4) - 1; chunkX <= (blockX >> 4) + 1; chunkX++) {
            for (int chunkZ = (blockZ >> 4) - 1; chunkZ <= (blockZ >> 4) + 1; chunkZ++) {
                String key = chunkX + "," + chunkZ;
                branch.lastEdit.put(key, sequence);
                added |= branch.chunks.add(key);
            }
        }
        if (!added) return true;
        try { saveBranch(branch); return true; }
        catch (IOException exception) {
            failedWorlds.add(world.getName());
            failClosed("Campus editing was stopped because the changed-area journal could not be saved.", exception);
            return false;
        }
    }

    // ---------------------------------------------------------------- player workflow

    public void openMenu(Player player) { screens().menu(player); }

    public void visit(Player player) { requireAuthenticated(player); requireReady(); screens().visit(player); }

    /** The shared blueprint, for visiting. */
    public World blueprintWorld() { requireMainThread(); requireReady(); return blueprint; }

    // ---------------------------------------------------------------- staff editing of the shared blueprint

    public boolean editor(Player player) {
        return player != null && editors.containsKey(player.getUniqueId()) && isBlueprint(player.getWorld());
    }

    /** Whether staff edits of the shared blueprint are waiting to be saved. */
    public boolean drafting() { return !draft.isEmpty() || committingDraft; }

    /** Takes a staff member into the shared blueprint to build. Their edits become one update when saved. */
    public void startEditing(Player player) {
        requireMainThread();
        requireReviewer(player);
        ensureCanCreateBranch();
        if (committingDraft) throw new IllegalStateException("The last blueprint edits are still being saved. Try again in a moment.");
        editors.put(player.getUniqueId(), competition.participantKey(player));
        if (!isBlueprint(player.getWorld()) && !player.teleport(blueprint.getSpawnLocation().clone().add(0.5, 1, 0.5))) {
            editors.remove(player.getUniqueId());
            throw new IllegalStateException("Could not open the shared blueprint. Try again.");
        }
        competition.refreshMovementMode(player, player.getLocation());
        player.sendMessage(Component.text("You are editing the shared blueprint. When you leave it, or use /blueprint save, your changes "
                + "become one update and reach every student's campus.", NamedTextColor.GOLD));
    }

    /** Records how each chunk looked before staff first changed it; called before the change happens. */
    private boolean captureDraft(int blockX, int blockZ) {
        try {
            boolean first = draft.isEmpty();
            lastDraftEdit = System.nanoTime();
            BlueprintStage.Bounds bounds = wholeBlueprint();
            for (int chunkX = (blockX >> 4) - 1; chunkX <= (blockX >> 4) + 1; chunkX++) {
                for (int chunkZ = (blockZ >> 4) - 1; chunkZ <= (blockZ >> 4) + 1; chunkZ++) {
                    long key = org.bukkit.Chunk.getChunkKey(chunkX, chunkZ);
                    if (draft.containsKey(key)) continue;
                    org.bukkit.Chunk chunk = blueprint.getChunkAt(chunkX, chunkZ);
                    chunk.addPluginChunkTicket(plugin);
                    draft.put(key, BlueprintStage.side(chunk, bounds, new long[]{0}));
                }
            }
            // Unsaved edits must not reach disk; a crash then simply loses them and the blueprint matches its last update.
            if (first) blueprint.setAutoSave(false);
            return true;
        } catch (IOException | RuntimeException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not record a staff blueprint edit; it was cancelled.", exception);
            return false;
        }
    }

    /** Placement changes the world before its event; the replaced block is the true "before" of a freshly recorded chunk. */
    public boolean uncaptured(org.bukkit.block.Block block) {
        return isBlueprint(block.getWorld()) && !draft.containsKey(org.bukkit.Chunk.getChunkKey(block.getX() >> 4, block.getZ() >> 4));
    }

    public void replaced(org.bukkit.block.BlockState state) {
        if (!isBlueprint(state.getWorld()) || !draft.containsKey(org.bukkit.Chunk.getChunkKey(state.getX() >> 4, state.getZ() >> 4))) return;
        draftOverrides.putIfAbsent(new BlockPosition(state.getX(), state.getY(), state.getZ()), new BlockSnapshot(state.getBlockData().getAsString(), null));
    }

    public void saveEdits(CommandSender actor) {
        requireMainThread();
        requireReviewer(actor);
        if (draft.isEmpty()) { actor.sendMessage(committingDraft ? "Saving..." : "There are no blueprint edits to save."); return; }
        commitDraft(false);
    }

    /** Saves automatically when the last editor leaves the shared blueprint. */
    public void editorLeft(Player player) {
        if (editors.remove(player.getUniqueId()) == null) return;
        if (editors.isEmpty() && !draft.isEmpty() && !committingDraft && initialized && !failed && !closing) commitDraft(false);
    }

    private void commitDraft(boolean synchronous) {
        committingDraft = true;
        String author = editors.isEmpty() ? "staff" : editors.values().iterator().next();
        List<BlueprintStage.Pair> pairs = new ArrayList<>();
        BlueprintStage.Bounds bounds = wholeBlueprint();
        try {
            for (var entry : draft.entrySet()) {
                int chunkX = (int) (long) entry.getKey(), chunkZ = (int) (entry.getKey() >> 32);
                pairs.add(new BlueprintStage.Pair(chunkX, chunkZ, entry.getValue(), BlueprintStage.side(blueprint.getChunkAt(chunkX, chunkZ), bounds, new long[]{0})));
            }
            if (synchronous) finishDraft(author, BlueprintStage.compare(pairs, bounds, BlueprintRepository.MAXIMUM_CHANGES, 0).changes());
            else BlueprintStage.compareLater(plugin, pairs, bounds, BlueprintRepository.MAXIMUM_CHANGES, 0).whenComplete((result, error) -> {
                if (error != null) failDraft(error);
                else finishDraft(author, result.changes());
            });
        } catch (IOException | RuntimeException exception) { failDraft(exception); }
    }

    private void finishDraft(String author, List<BlockChange> compared) {
        try {
            Map<BlockPosition, BlockChange> changes = new LinkedHashMap<>();
            for (BlockChange change : compared) changes.put(change.position(), change);
            var live = new BukkitBlueprintBlocks(blueprint);
            for (var override : draftOverrides.entrySet()) {
                BlockSnapshot now = live.read(override.getKey());
                if (now.equals(override.getValue())) changes.remove(override.getKey());
                else changes.put(override.getKey(), new BlockChange(override.getKey(), override.getValue(), now));
            }
            if (changes.isEmpty()) tellEditors("No blueprint changes to save.");
            else {
                String number = commit(author, "Staff edit by " + displayName(author), List.copyOf(changes.values()), false, false);
                tellEditors("Saved your blueprint edits as update #" + number + ". Every student's campus gets them automatically.");
            }
        } catch (IOException | RuntimeException exception) {
            plugin.getLogger().log(Level.SEVERE, "Staff blueprint edits could not be saved.", exception);
            tellEditors("The blueprint edits could not be saved: " + exception.getMessage());
        } finally { endDraft(); }
    }

    private void failDraft(Throwable error) {
        plugin.getLogger().log(Level.SEVERE, "Staff blueprint edits could not be compared.", error);
        tellEditors("The blueprint edits could not be saved: " + error.getMessage());
        endDraft();
    }

    private void endDraft() {
        for (long key : draft.keySet()) blueprint.removePluginChunkTicket((int) key, (int) (key >> 32), plugin);
        draft.clear();
        draftOverrides.clear();
        committingDraft = false;
        blueprint.setAutoSave(true);
    }

    private void tellEditors(String message) {
        for (UUID id : editors.keySet()) {
            Player player = Bukkit.getPlayer(id);
            if (player != null) player.sendMessage(Component.text(message, NamedTextColor.GOLD));
        }
        plugin.getLogger().info(message);
    }

    private BlueprintStage.Bounds wholeBlueprint() {
        return BlueprintStage.Bounds.of(blueprint, List.of(new BuildRegion(blueprint.getName(), -30_000_000, blueprint.getMinHeight(), -30_000_000,
                30_000_000, blueprint.getMaxHeight() - 1, 30_000_000)));
    }

    private String displayName(String author) {
        return author.equals("staff") || author.equals("console") ? "staff" : competition.displayName(author);
    }

    // ---------------------------------------------------------------- saved versions and rollback

    /** Every blueprint version, newest first. Version 0 is the original campus. */
    public List<Revision> revisions() throws IOException {
        requireReady();
        Map<UUID, BlueprintRepository.Summary> byId = new HashMap<>();
        for (var summary : submissions.summaries()) byId.put(summary.id(), summary);
        List<Revision> result = new ArrayList<>();
        for (long number = approvals.size(); number >= 1; number--) {
            Approval approval = approvals.get(number);
            var summary = byId.get(approval.submission());
            if (summary == null) continue;
            result.add(new Revision(number, summary.title(), displayName(summary.author()), summary.createdAt(), approval.entryId().equals(STAFF_ENTRY)));
        }
        result.add(new Revision(0, "Original campus", "", null, true));
        return List.copyOf(result);
    }

    public long latestUpdate() { return approvals.size(); }

    public boolean ready() { return initialized && !failed && !closing; }

    /** Copies a saved version into a temporary look-only world, off the server thread. */
    public CompletableFuture<World> openPreview(Player staff, long number) {
        requireMainThread();
        requireReviewer(staff);
        requireReady();
        if (drafting()) throw new IllegalStateException("Staff blueprint edits are not saved yet. Save them first.");
        if (number < 0 || number > approvals.size()) throw new IllegalArgumentException("Choose a saved version.");
        Path export;
        try { export = exportOf(number); }
        catch (IOException exception) { throw new IllegalStateException("That version's saved copy could not be found.", exception); }
        String name = "hill_bp_preview_" + UUID.randomUUID().toString().replace("-", "");
        Path target = BlueprintWorldFiles.worldFolder(plugin, name);
        CompletableFuture<World> result = new CompletableFuture<>();
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                BlueprintWorldFiles.copyWorld(export, target);
                Bukkit.getScheduler().runTask(plugin, () -> {
                    try {
                        World world = BlueprintWorldFiles.load(plugin, name, true);
                        previews.add(name);
                        result.complete(world);
                    } catch (Exception exception) { result.completeExceptionally(exception); }
                });
            } catch (Exception exception) { Bukkit.getScheduler().runTask(plugin, () -> result.completeExceptionally(exception)); }
        });
        return result;
    }

    /** Unloads and deletes a preview once nobody is in it. */
    public void closePreview(World world) {
        if (world == null || !previews.contains(world.getName()) || !plugin.isEnabled()) return;
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (!world.getPlayers().isEmpty()) return;
            Path folder = world.getWorldFolder().toPath();
            previews.remove(world.getName());
            if (!Bukkit.unloadWorld(world, false)) return;
            Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
                try { BlueprintWorldFiles.deletePreview(folder); }
                catch (IOException exception) { plugin.getLogger().log(Level.WARNING, "Could not delete a blueprint preview copy.", exception); }
            });
        }, 2L);
    }

    private Path exportOf(long number) throws IOException {
        Path exports = folder.resolve("exports");
        if (number == 0) return BlueprintFiles.child(exports, "revision-0");
        Approval approval = approvals.get(number);
        String recorded = BlueprintFiles.readProperties(folder.resolve("merge-complete-" + approval.submission() + ".properties")).getProperty("export");
        if (recorded != null) return BlueprintFiles.child(exports, recorded);
        try (var names = Files.list(exports)) {
            List<Path> matches = names.filter(path -> path.getFileName().toString().startsWith("revision-" + number + "-")).toList();
            if (matches.size() != 1) throw new IOException("Saved copy of update " + number + " is missing or ambiguous.");
            return matches.getFirst();
        }
    }

    /**
     * Makes the shared blueprint look like version {@code target} again, as a new update. Each block touched
     * since then takes its state from just before the first later update changed it.
     */
    public String rollback(CommandSender staff, long target) throws IOException {
        requireMainThread();
        requireReviewer(staff);
        ensureCanCreateBranch();
        if (drafting()) throw new IllegalStateException("Staff blueprint edits are not saved yet. Save them first.");
        long latest = approvals.size();
        if (target < 0 || target >= latest) throw new IllegalArgumentException("Choose an older version to roll back to.");
        List<List<BlockChange>> later = new ArrayList<>();
        for (long number = target + 1; number <= latest; number++) later.add(packet(number));
        List<BlockChange> changes = BlueprintMerge.revert(later, new BukkitBlueprintBlocks(blueprint));
        if (changes.isEmpty()) throw new IllegalStateException("The shared blueprint already looks like update #" + target + ".");
        String number = commit(actor(staff), "Rolled back to update #" + target, changes, true, true);
        staff.sendMessage(Component.text("Rolled the shared blueprint back to update #" + target + " as update #" + number
                + ". Every student's campus gets it automatically.", NamedTextColor.GOLD));
        return number;
    }

    /** Records staff changes as a new update. {@code apply} is false when the blocks are already in the blueprint. */
    private String commit(String author, String title, List<BlockChange> changes, boolean apply, boolean backupFirst) throws IOException {
        if (changes.size() > BlueprintRepository.MAXIMUM_CHANGES) {
            throw new IllegalStateException("That changes " + changes.size() + " blocks; one update can hold " + BlueprintRepository.MAXIMUM_CHANGES + ".");
        }
        String backup = "";
        if (backupFirst) {
            try { backup = backups.capture(blueprint, "Before " + title); }
            catch (IOException exception) {
                failClosed("Mandatory recovery snapshot failed; nothing was changed and further editing is blocked.", exception);
                throw exception;
            }
        }
        var submission = new BlueprintRepository.Submission(UUID.randomUUID(), STAFF_ENTRY, author, title, Long.toString(latestRevision()),
                Instant.now(), BlueprintRepository.Status.PENDING, "", "", changes);
        submissions.create(submission);
        merging = true;
        try { return publish(author, submission, changes, apply, backup, number -> title + " (update #" + number + ")"); }
        finally { merging = false; }
    }

    private void withdrawInterruptedStaffChanges() throws IOException {
        for (var summary : submissions.summaries()) {
            if (summary.status() != BlueprintRepository.Status.PENDING || !summary.entryId().equals(STAFF_ENTRY)) continue;
            submissions.saveDecision(submissions.read(summary.id()).decide(BlueprintRepository.Status.WITHDRAWN, "server", "Interrupted staff change; rolled back"));
        }
    }

    private void deleteLeftoverPreviews() throws IOException {
        for (Path parent : List.of(plugin.getServer().getWorldContainer().toPath(), BlueprintWorldFiles.dimensionFolder(plugin))) {
            if (!Files.isDirectory(parent)) continue;
            try (var paths = Files.list(parent)) {
                for (Path path : paths.filter(path -> path.getFileName().toString().matches("hill_bp_preview_[a-f0-9]{32}")).toList()) {
                    BlueprintWorldFiles.deletePreview(path);
                }
            }
        }
    }

    // ---------------------------------------------------------------- resetting a campus

    /** Makes the owner's campus match the shared blueprint again. Building pauses while it runs. */
    public CompletableFuture<Integer> reset(Player player) {
        requireMainThread();
        requireAuthenticated(player);
        ensureCanCreateBranch();
        if (drafting()) throw new IllegalStateException("Staff are editing the shared blueprint right now. Try again in a minute.");
        Branch branch = ownBranch(player).orElseThrow(() -> new IllegalStateException("You do not have a campus yet."));
        Entry entry = store.entry(branch.entryId).orElseThrow(() -> new IllegalStateException("Your campus record is unavailable. Ask staff for help."));
        requireOwner(player, entry);
        if (isFrozen(entry)) throw new IllegalStateException("Your campus is busy. Try again in a moment.");
        try {
            if (branch.syncedThrough < latestRevision()) {
                syncQueue.addFirst(branch.entryId);
                throw new IllegalStateException("Your campus is getting the newest blueprint update. Try again in a few seconds.");
            }
        } catch (IOException exception) { throw new UncheckedIOException(exception); }
        List<String> chunks = branch.chunks.stream().filter(chunk -> overlaps(entry.editableRegions(), chunk)).sorted().toList();
        World source;
        try { source = openCampus(branch); }
        catch (IOException exception) { throw new UncheckedIOException(exception); }
        resetting.add(entry.id());
        refreshWorldPlayers(branch.world);
        CompletableFuture<Integer> result = new CompletableFuture<>();
        if (chunks.isEmpty()) { finishReset(branch, source, chunks, 0, result); return result; }
        BlueprintStage.run(plugin, source, blueprint, chunks, entry.editableRegions(), BlueprintRepository.MAXIMUM_CHANGES, () -> editSequence)
                .whenComplete((stage, error) -> {
                    if (error != null) { stopReset(branch, result, error instanceof CompletionException ? error.getCause() : error); return; }
                    List<BlockChange> changes = stage.changes();
                    new org.bukkit.scheduler.BukkitRunnable() {
                        int next;
                        @Override public void run() {
                            try {
                                if (closing || failed) throw new IllegalStateException("The server is stopping.");
                                Map<BlockPosition, BlockSnapshot> batch = new LinkedHashMap<>();
                                for (int end = Math.min(changes.size(), next + 2048); next < end; next++) batch.put(changes.get(next).position(), changes.get(next).before());
                                if (!batch.isEmpty()) new BukkitBlueprintBlocks(source).write(batch);
                                if (next < changes.size()) return;
                                cancel();
                                finishReset(branch, source, chunks, changes.size(), result);
                            } catch (IOException | RuntimeException exception) {
                                cancel();
                                stopReset(branch, result, exception);
                            }
                        }
                    }.runTaskTimer(plugin, 1L, 1L);
                });
        return result;
    }

    private void finishReset(Branch branch, World source, List<String> chunks, int count, CompletableFuture<Integer> result) {
        try {
            source.save(true);
            chunks.forEach(chunk -> { branch.chunks.remove(chunk); branch.lastEdit.remove(chunk); });
            branch.conflicts.clear();
            branch.conflictsChanged = true;
            saveBranch(branch);
            resetting.remove(branch.entryId);
            refreshWorldPlayers(branch.world);
            result.complete(count);
        } catch (IOException | RuntimeException exception) { stopReset(branch, result, exception); }
    }

    private void stopReset(Branch branch, CompletableFuture<Integer> result, Throwable error) {
        resetting.remove(branch.entryId);
        refreshWorldPlayers(branch.world);
        plugin.getLogger().log(Level.WARNING, "Campus reset stopped for " + branch.entryId, error);
        result.completeExceptionally(error);
    }

    public Overview overview(Player player) throws IOException {
        requireAuthenticated(player);
        requireReady();
        long latest = latestRevision();
        Branch branch = ownBranch(player).orElse(null);
        if (branch == null) return new Overview(null, false, latest, 0, null, null);
        Entry entry = store.entry(branch.entryId).orElse(null);
        BlueprintRepository.Summary waiting = null;
        BlueprintRepository.Summary decided = null;
        for (var summary : submissions.summaries()) {
            if (!summary.entryId().equals(branch.entryId)) continue;
            if (waiting == null && summary.status() == BlueprintRepository.Status.PENDING) waiting = summary;
            if (decided == null && (summary.status() == BlueprintRepository.Status.APPROVED || summary.status() == BlueprintRepository.Status.REJECTED)) decided = summary;
        }
        return new Overview(entry, branch.syncedThrough < latest, latest, branch.conflicts.size(), waiting, decided);
    }

    /**
     * Captures the owner's campus as it is right now and compares it with the blueprint. The campus stays
     * editable; later edits are not part of this snapshot.
     */
    public CompletableFuture<Snapshot> snapshot(Player player) {
        requireMainThread();
        requireAuthenticated(player);
        ensureCanCreateBranch();
        Branch branch = ownBranch(player).orElseThrow(() -> new IllegalStateException("You need your own campus first. Choose My Campus to make one."));
        Entry entry = store.entry(branch.entryId).orElseThrow(() -> new IllegalStateException("Your campus record is unavailable. Ask staff for help."));
        requireOwner(player, entry);
        if (isFrozen(entry)) throw new IllegalStateException("Your campus needs staff help before it can be sent.");
        if (drafting()) throw new IllegalStateException("Staff are editing the shared blueprint right now. Try again in a minute.");
        long revision;
        try { revision = latestRevision(); }
        catch (IOException exception) { throw new UncheckedIOException(exception); }
        if (branch.syncedThrough < revision) {
            syncQueue.addFirst(branch.entryId);
            throw new IllegalStateException("Your campus is getting the newest blueprint update. Try again in a few seconds.");
        }
        if (!branch.conflicts.isEmpty()) throw new IllegalStateException("First choose what to keep where the blueprint changed ("
                + branch.conflicts.size() + " blocks).");
        List<BuildRegion> regions = entry.editableRegions();
        if (!staging.add(entry.id())) throw new IllegalStateException("Your snapshot is already being taken.");
        String author = competition.participantKey(player);
        List<String> chunks = branch.chunks.stream().filter(chunk -> overlaps(regions, chunk)).sorted().toList();
        if (chunks.isEmpty()) {
            staging.remove(entry.id());
            return CompletableFuture.completedFuture(new Snapshot(entry.id(), author, revision, Instant.now(), List.of(), List.of()));
        }
        if (chunks.size() > maximumSnapshotChunks()) {
            staging.remove(entry.id());
            throw new IllegalStateException("Your changes are spread over too much of the campus to check at once. Ask a moderator for help.");
        }
        World source;
        try {
            worlds.ensureEntryWorld(entry);
            source = Bukkit.getWorld(branch.world);
            if (source == null || !source.getUID().equals(branch.worldId)) throw new IllegalStateException("Your campus could not be opened.");
        } catch (RuntimeException exception) {
            staging.remove(entry.id());
            throw exception;
        }
        CompletableFuture<Snapshot> result = new CompletableFuture<>();
        CompletableFuture<BlueprintStage.Result> running;
        try { running = BlueprintStage.run(plugin, source, blueprint, chunks, regions, maximumChanges() * 4, () -> editSequence); }
        catch (RuntimeException exception) { staging.remove(entry.id()); throw exception; }
        running.whenComplete((stage, error) -> {
            staging.remove(entry.id());
            if (error != null) { result.completeExceptionally(error instanceof CompletionException ? error.getCause() : error); return; }
            try {
                prune(branch, entry, stage);
                List<BlockPosition> positions = stage.changes().stream().map(BlockChange::position).toList();
                result.complete(new Snapshot(entry.id(), author, revision, Instant.now(), stage.changes(), ChangeAreas.of(positions)));
            } catch (Exception exception) { result.completeExceptionally(exception); }
        });
        return result;
    }

    /** Forgets chunks that matched the blueprint in the snapshot and were not edited since it was taken. */
    private void prune(Branch branch, Entry entry, BlueprintStage.Result stage) throws IOException {
        if (branches.get(branch.entryId) != branch) return;
        boolean changed = false;
        for (String chunk : List.copyOf(branch.chunks)) {
            boolean outside = !overlaps(entry.editableRegions(), chunk);
            boolean clean = stage.cleanChunks().contains(chunk) && branch.lastEdit.getOrDefault(chunk, 0L) <= stage.sequence();
            if (outside || clean) {
                branch.chunks.remove(chunk);
                branch.lastEdit.remove(chunk);
                changed = true;
            }
        }
        if (changed) saveBranch(branch);
    }

    /** Sends the chosen areas of a snapshot for review, replacing any request that is still waiting. */
    public BlueprintRepository.Submission send(Player player, Snapshot snapshot, Set<Integer> areaIndexes, String title) throws IOException {
        requireMainThread();
        requireAuthenticated(player);
        ensureCanCreateBranch();
        Branch branch = branches.get(snapshot.entryId());
        Entry entry = store.entry(snapshot.entryId()).orElseThrow(() -> new IllegalStateException("Your campus record is unavailable."));
        requireOwner(player, entry);
        if (branch == null || !competition.participantKey(player).equals(snapshot.author())) throw new SecurityException("Only the campus owner can send this snapshot.");
        if (isFrozen(entry)) throw new IllegalStateException("Your campus needs staff help before it can be sent.");
        if (snapshot.takenAt().plus(SNAPSHOT_LIFETIME).isBefore(Instant.now())) throw new IllegalStateException("That snapshot is too old. Take a new one.");
        if (snapshot.revision() != latestRevision() || branch.syncedThrough != snapshot.revision()) {
            throw new IllegalStateException("The blueprint was updated after your snapshot. Take a new snapshot so it includes the update.");
        }
        if (!branch.conflicts.isEmpty()) throw new IllegalStateException("First choose what to keep where the blueprint changed.");
        Set<BlockPosition> chosen = new HashSet<>();
        for (int index : areaIndexes) {
            if (index < 0 || index >= snapshot.areas().size()) throw new IllegalArgumentException("Choose areas from your snapshot.");
            chosen.addAll(snapshot.areas().get(index).positions());
        }
        List<BlockChange> changes = snapshot.changes().stream().filter(change -> chosen.contains(change.position())).toList();
        if (changes.isEmpty()) throw new IllegalArgumentException("Choose at least one area to send.");
        if (changes.size() > maximumChanges()) {
            throw new IllegalArgumentException("That is " + changes.size() + " changed blocks; one request can hold " + maximumChanges() + ". Choose fewer areas.");
        }
        String name = title == null || title.isBlank() ? (entry.title().isBlank() ? "My campus build" : entry.title()) : title;
        var submission = new BlueprintRepository.Submission(UUID.randomUUID(), entry.id(), snapshot.author(), cleanText(name, Entry.MAX_TITLE_LENGTH),
                Long.toString(snapshot.revision()), Instant.now(), BlueprintRepository.Status.PENDING, "", "", changes);
        List<BlueprintRepository.Summary> replaced = submissions.summaries().stream()
                .filter(summary -> summary.entryId().equals(entry.id()) && summary.status() == BlueprintRepository.Status.PENDING).toList();
        submissions.create(submission);
        for (var old : replaced) decide(submissions.read(old.id()), BlueprintRepository.Status.WITHDRAWN, snapshot.author(), "Replaced by a newer snapshot");
        return submission;
    }

    public boolean cancel(Player player) throws IOException {
        requireMainThread();
        requireAuthenticated(player);
        Branch branch = ownBranch(player).orElseThrow(() -> new IllegalStateException("You need your own campus first."));
        return withdraw(player, store.entry(branch.entryId).orElseThrow());
    }

    public boolean withdraw(Player player, Entry entry) throws IOException {
        requireMainThread();
        requireOwner(player, entry);
        ensureCanCreateBranch();
        boolean any = false;
        for (var summary : submissions.summaries()) {
            if (!summary.entryId().equals(entry.id()) || summary.status() != BlueprintRepository.Status.PENDING) continue;
            decide(submissions.read(summary.id()), BlueprintRepository.Status.WITHDRAWN, competition.participantKey(player), "Cancelled by the owner");
            any = true;
        }
        return any;
    }

    /** Lists unresolved conflicts with the owner's current block; conflicts the owner already matched are cleared. */
    public List<CampusConflict> conflicts(Player player) throws IOException {
        requireMainThread();
        requireAuthenticated(player);
        requireReady();
        Branch branch = ownBranch(player).orElse(null);
        if (branch == null || branch.conflicts.isEmpty()) return List.of();
        var campus = new BukkitBlueprintBlocks(openCampus(branch));
        List<CampusConflict> result = new ArrayList<>();
        boolean cleared = false;
        for (var conflict : List.copyOf(branch.conflicts.values())) {
            BlockSnapshot mine = campus.read(conflict.position());
            if (mine.equals(conflict.after())) { branch.conflicts.remove(conflict.position()); branch.conflictsChanged = cleared = true; continue; }
            result.add(new CampusConflict(conflict.position(), mine, conflict.after()));
        }
        if (cleared) saveBranch(branch);
        return List.copyOf(result);
    }

    /** Keeps the owner's blocks, or replaces them with the blueprint's, at the chosen conflicts. */
    public int resolve(Player player, Collection<BlockPosition> positions, boolean keepMine) throws IOException {
        requireMainThread();
        requireAuthenticated(player);
        ensureCanCreateBranch();
        Branch branch = ownBranch(player).orElseThrow(() -> new IllegalStateException("You need your own campus first."));
        requireOwner(player, store.entry(branch.entryId).orElseThrow());
        World world = openCampus(branch);
        var campus = new BukkitBlueprintBlocks(world);
        List<BlockChange> writes = new ArrayList<>();
        List<BlockPosition> resolved = new ArrayList<>();
        for (BlockPosition position : positions) {
            BlockChange conflict = branch.conflicts.get(position);
            if (conflict == null) continue;
            resolved.add(position);
            if (keepMine) continue;
            BlockSnapshot mine = campus.read(position);
            if (!mine.equals(conflict.after())) writes.add(new BlockChange(position, mine, conflict.after()));
        }
        BlueprintMerge.apply(writes, campus);
        if (!writes.isEmpty()) world.save(true);
        resolved.forEach(branch.conflicts::remove);
        branch.conflictsChanged |= !resolved.isEmpty();
        saveBranch(branch);
        return resolved.size();
    }

    /** Moves the owner into their campus, next to a block. */
    public void goTo(Player player, BlockPosition position) {
        requireAuthenticated(player);
        Branch branch = ownBranch(player).orElseThrow(() -> new IllegalStateException("You need your own campus first."));
        if (!player.getWorld().getName().equals(branch.world)) competition.home(player);
        if (!player.getWorld().getName().equals(branch.world)) throw new IllegalStateException("Your campus is opening. Try again in a moment.");
        competition.visitChangedBlock(player, position);
    }

    /** The owner's campus world when the player is standing in it. */
    public Optional<World> campusWorld(Player player) {
        return ownBranch(player).map(branch -> Bukkit.getWorld(branch.world)).filter(world -> world.equals(player.getWorld()));
    }

    public void visitChanges(Player player, Long requested) throws IOException {
        requireReady();
        requireAuthenticated(player);
        Branch branch = ownBranch(player).orElseThrow(() -> new IllegalStateException("You need your own campus first."));
        Entry entry = store.entry(branch.entryId).orElseThrow();
        long number = requested == null ? branch.syncedThrough : requested;
        if (number < 1 || number > branch.syncedThrough || !approvals.containsKey(number)) throw new IllegalArgumentException("There is no blueprint update to show yet.");
        List<BlockPosition> positions = packet(number).stream().map(BlockChange::position).filter(position -> editable(entry, position)).toList();
        if (positions.isEmpty()) { player.sendMessage("Blueprint update #" + number + " did not change anything inside your campus."); return; }
        List<ChangeAreas.Area> areas = ChangeAreas.of(positions);
        goTo(player, areas.getFirst().center());
        List<BlueprintOutlines.Box> boxes = areas.stream().map(area -> BlueprintOutlines.Box.around(area, BlueprintOutlines.Tone.UPDATE)).toList();
        outlines.show(player, player.getWorld(), boxes, Duration.ofMinutes(2));
        player.sendMessage(Component.text("Blue boxes show what blueprint update #" + number + " changed in your campus ("
                + positions.size() + " blocks in " + areas.size() + (areas.size() == 1 ? " area)." : " areas)."), NamedTextColor.AQUA));
    }

    // ---------------------------------------------------------------- automatic updates

    private void enqueueBehind() {
        long latest = approvals.size();
        List<UUID> loaded = new ArrayList<>();
        List<UUID> unloaded = new ArrayList<>();
        for (Branch branch : branches.values()) {
            if (branch.syncedThrough >= latest) continue;
            (Bukkit.getWorld(branch.world) != null ? loaded : unloaded).add(branch.entryId);
        }
        syncQueue.addAll(loaded);
        syncQueue.addAll(unloaded);
    }

    private void autoSync() {
        // Students cannot send while staff edits are unsaved, so idle edits save themselves.
        if (!draft.isEmpty() && !committingDraft && !merging && !saving && initialized && !failed && !closing
                && System.nanoTime() - lastDraftEdit > DRAFT_IDLE_NANOS) commitDraft(false);
        if (!initialized || failed || closing || merging || saving || syncQueue.isEmpty()) return;
        UUID id = syncQueue.removeFirst();
        Branch branch = branches.get(id);
        Entry entry = store.entry(id).orElse(null);
        long latest = approvals.size();
        if (entry == null || branch == null || branch.syncedThrough >= latest || isFrozen(entry)) return;
        boolean opened = Bukkit.getWorld(branch.world) == null;
        try {
            requireCanonicalOwner(entry, branch.owner);
            World world = openCampus(branch);
            long number = branch.syncedThrough + 1;
            Approval approval = approvals.get(number);
            if (approval == null) throw new IOException("Missing blueprint update " + number);
            List<BlockChange> packet = packet(number);
            var campus = new BukkitBlueprintBlocks(world);
            var update = BlueprintMerge.update(packet, campus, approval.entryId().equals(branch.entryId), position -> editable(entry, position));
            BlueprintMerge.apply(update.writes(), campus);
            Set<BlockPosition> added = new HashSet<>();
            for (BlockChange conflict : update.conflicts()) added.add(conflict.position());
            for (BlockChange change : packet) if (!added.contains(change.position())) branch.conflicts.remove(change.position());
            for (BlockChange conflict : update.conflicts()) branch.conflicts.put(conflict.position(), conflict);
            branch.conflictsChanged = true;
            Set<BlockPosition> written = new HashSet<>();
            for (BlockChange change : update.writes()) written.add(change.position());
            long sequence = ++editSequence;
            for (BlockChange change : packet) {
                if (written.contains(change.position()) || !editable(entry, change.position()) || campus.read(change.position()).equals(change.after())) continue;
                String chunk = (change.position().blockX() >> 4) + "," + (change.position().blockZ() >> 4);
                branch.chunks.add(chunk);
                branch.lastEdit.put(chunk, sequence);
            }
            world.save(true);
            branch.syncedThrough = number;
            saveBranch(branch);
            if (number < latest) syncQueue.add(id);
            for (Player player : Bukkit.getOnlinePlayers()) {
                if (!isOwnerOnline(player, branch)) continue;
                if (!added.isEmpty()) conflictNotice(player, branch.conflicts.size());
                else if (number == latest) deliverNotices(player, branch);
            }
        } catch (IOException | RuntimeException exception) {
            plugin.getLogger().log(Level.WARNING, "Automatic blueprint update stopped for campus " + id + "; it is retried at the next update or sign in.", exception);
        } finally {
            if (opened) unloadIfEmpty(branch.world);
        }
    }

    private World openCampus(Branch branch) throws IOException {
        Entry entry = store.entry(branch.entryId).orElseThrow(() -> new IOException("Campus entry is missing."));
        if (Bukkit.getWorld(branch.world) == null) {
            BlueprintWorldFiles.validateWorld(BlueprintWorldFiles.worldFolder(plugin, branch.world));
            worlds.ensureEntryWorld(entry);
        }
        World world = Bukkit.getWorld(branch.world);
        if (world == null || !world.getUID().equals(branch.worldId)) throw new IOException("Saved campus world identity mismatch.");
        return world;
    }

    private static void unloadIfEmpty(String name) {
        World world = Bukkit.getWorld(name);
        if (world != null && world.getPlayers().isEmpty()) Bukkit.unloadWorld(world, true);
    }

    private boolean isOwnerOnline(Player player, Branch branch) {
        return competition.isAuthenticated(player) && competition.participantKey(player).equals(branch.owner);
    }

    private void conflictNotice(Player player, int count) {
        player.sendMessage(Component.text("The shared blueprint changed " + count + (count == 1 ? " block" : " blocks")
                        + " that you also changed. You decide which version stays. ", NamedTextColor.LIGHT_PURPLE)
                .append(Component.text("[Choose What to Keep]", NamedTextColor.GOLD).decorate(TextDecoration.UNDERLINED)
                        .clickEvent(ClickEvent.runCommand("/blueprint fix"))));
    }

    public void onAdmission(Player player) {
        if (!initialized || failed || closing) return;
        for (Branch branch : branches.values()) {
            if (!isOwnerOnline(player, branch)) continue;
            try {
                deliverNotices(player, branch);
                decisionNotice(player, branch);
            } catch (IOException exception) { plugin.getLogger().log(Level.WARNING, "Could not save a blueprint notice receipt.", exception); }
            if (!branch.conflicts.isEmpty()) conflictNotice(player, branch.conflicts.size());
            if (branch.syncedThrough < approvals.size()) syncQueue.add(branch.entryId);
        }
    }

    private void deliverNotices(Player player, Branch branch) throws IOException {
        if (branch.notifiedThrough >= branch.syncedThrough) return;
        long updates = branch.syncedThrough - branch.notifiedThrough;
        player.sendMessage(Component.text((updates == 1 ? "The shared blueprint was updated" : "The shared blueprint got " + updates + " updates")
                        + " and your campus already has the changes. ", NamedTextColor.AQUA)
                .append(Component.text("[Show Me]", NamedTextColor.GREEN).decorate(TextDecoration.UNDERLINED)
                        .clickEvent(ClickEvent.runCommand("/blueprint news"))));
        branch.notifiedThrough = branch.syncedThrough;
        saveBranch(branch);
    }

    private void decisionNotice(Player player, Branch branch) throws IOException {
        var latest = submissions.summaries().stream().filter(summary -> summary.entryId().equals(branch.entryId)
                && (summary.status() == BlueprintRepository.Status.APPROVED || summary.status() == BlueprintRepository.Status.REJECTED)).findFirst();
        if (latest.isEmpty() || latest.get().id().toString().equals(branch.seenDecision)) return;
        player.sendMessage(decisionText(latest.get().title(), latest.get().status(), latest.get().reason()));
        branch.seenDecision = latest.get().id().toString();
        saveBranch(branch);
    }

    private static Component decisionText(String title, BlueprintRepository.Status status, String reason) {
        if (status == BlueprintRepository.Status.APPROVED) {
            return Component.text("Your build \"" + title + "\" was approved and is now part of the shared blueprint!", NamedTextColor.GREEN);
        }
        return Component.text("A moderator sent back \"" + title + "\": " + reason
                + " Keep building and send it again when you are ready.", NamedTextColor.YELLOW);
    }

    // ---------------------------------------------------------------- review and approval

    public void approve(CommandSender reviewer, UUID submissionId, ConflictChoice choice) throws IOException {
        requireMainThread();
        requireReviewer(reviewer);
        ensureCanCreateBranch();
        if (drafting()) throw new IllegalStateException("Staff blueprint edits are not saved yet. Save them first.");
        var submission = submissions.read(submissionId);
        requirePending(submission);
        merging = true;
        try { merge(reviewer, submission, choice); }
        finally { merging = false; }
    }

    private void merge(CommandSender reviewer, BlueprintRepository.Submission submission, ConflictChoice choice) throws IOException {
        var target = new BukkitBlueprintBlocks(blueprint);
        var plan = BlueprintMerge.plan(submission.changes(), target);
        int conflicts = plan.conflicts().size();
        if (conflicts > 0 && choice == ConflictChoice.REFUSE) {
            throw new IllegalStateException(conflicts + " blocks conflict with the current blueprint. Choose whether the blueprint or the student's blocks win there.");
        }
        List<BlockChange> writes = plan.writes(choice == ConflictChoice.USE_PROPOSAL);
        if (writes.isEmpty()) throw new IllegalStateException("Nothing would change: the blueprint already matches this request. Deny it instead.");
        String backup;
        try { backup = backups.capture(blueprint, "Before blueprint approval " + submission.id()); }
        catch (IOException exception) {
            failClosed("Mandatory premerge recovery snapshot failed; no merge was started and further editing/approval is blocked.", exception);
            throw exception;
        }
        String number = publish(actor(reviewer), submission, writes, true, backup, revision -> {
            String detail = "Added as blueprint update #" + revision;
            if (conflicts > 0) detail += choice == ConflictChoice.USE_PROPOSAL ? "; the student's blocks replaced " + conflicts + " conflicting blocks"
                    : "; " + conflicts + " conflicting blocks kept the blueprint version";
            return detail;
        });
        reviewer.sendMessage("Approved \"" + submission.title() + "\" as blueprint update #" + number + ". Recovery snapshot " + backup + ".");
        notifyAuthor(submission, decisionText(submission.title(), BlueprintRepository.Status.APPROVED, ""));
    }

    /**
     * Records {@code writes} as the next blueprint update: the journal is written first, then the blocks are
     * applied (unless already in place), the blueprint is saved and exported, and the decision is committed.
     * Restart recovery rolls back an update whose decision was not committed.
     */
    private String publish(String actor, BlueprintRepository.Submission submission, List<BlockChange> writes, boolean apply,
                           String backup, java.util.function.Function<String, String> detail) throws IOException {
        Path transaction = folder.resolve("merge.properties");
        Properties journal = new Properties();
        try {
            journal.setProperty("submission", submission.id().toString());
            journal.setProperty("reviewer", actor);
            journal.setProperty("backup", backup);
            journal.setProperty("previousRevision", Long.toString(latestRevision()));
            journal.setProperty("newRevision", Long.toString(Math.addExact(latestRevision(), 1)));
            journal.setProperty("previousExport", BlueprintFiles.readProperties(folder.resolve("current.properties")).getProperty("export"));
            BlueprintFiles.atomicWrite(folder.resolve("merge-rollback.bin"), BlueprintRepository.encode(writes));
            journal.setProperty("rollbackSha256", BlueprintFiles.digest(folder.resolve("merge-rollback.bin")));
            BlueprintFiles.writeProperties(transaction, journal);
        } catch (IOException exception) {
            failClosed("Premerge journal could not be saved. No merge was started; further editing/approval is blocked.", exception);
            throw exception;
        }
        reviews.clearAll();
        String number = journal.getProperty("newRevision");
        try {
            if (apply) BlueprintMerge.apply(writes, new BukkitBlueprintBlocks(blueprint));
            blueprint.save(true);
            journal.setProperty("export", publishExport(number));
            BlueprintFiles.writeProperties(transaction, journal);
            submissions.saveDecision(submission.decide(BlueprintRepository.Status.APPROVED, actor, detail.apply(number)));
            completeMergeJournal(transaction, submission);
        } catch (Exception exception) {
            failClosed("Blueprint update interrupted. Further editing and merges are blocked until successful restart recovery.", exception);
            throw new IOException("Update interrupted. Its rollback journal is retained; restart for recovery before further edits.", exception);
        }
        return number;
    }

    private String publishExport(String revision) throws IOException {
        String exportName = "revision-" + revision + "-" + UUID.randomUUID().toString().substring(0, 8);
        Path export = folder.resolve("exports").resolve(exportName);
        BlueprintWorldFiles.copyWorld(blueprint.getWorldFolder().toPath(), export);
        BlueprintWorldFiles.writeRevisionMarker(export, Long.parseLong(revision));
        Properties current = BlueprintFiles.readProperties(folder.resolve("current.properties"));
        current.setProperty("revision", revision);
        current.setProperty("export", exportName);
        BlueprintFiles.writeProperties(folder.resolve("current.properties"), current);
        prepareTemplate(plugin);
        return exportName;
    }

    private void recoverMerge() throws IOException {
        Path transaction = folder.resolve("merge.properties");
        if (!Files.exists(transaction)) return;
        Properties journal = BlueprintFiles.readProperties(transaction);
        UUID submissionId = UUID.fromString(journal.getProperty("submission"));
        var submission = submissions.read(submissionId);
        if (submission.status() == BlueprintRepository.Status.APPROVED) {
            if (latestRevision() != Long.parseLong(journal.getProperty("newRevision"))) throw new IOException("Approved revision does not match its transaction.");
            prepareTemplate(plugin);
            completeMergeJournal(transaction, submission);
            return;
        }
        if (submission.status() != BlueprintRepository.Status.PENDING) throw new IOException("Ambiguous interrupted merge decision.");
        Path rollback = folder.resolve("merge-rollback.bin");
        if (!BlueprintFiles.digest(rollback).equals(journal.getProperty("rollbackSha256"))) throw new IOException("Merge rollback checksum mismatch.");
        BlueprintMerge.rollback(BlueprintRepository.decode(Files.readAllBytes(rollback)), new BukkitBlueprintBlocks(blueprint));
        blueprint.save(true);
        Properties current = BlueprintFiles.readProperties(folder.resolve("current.properties"));
        current.setProperty("revision", journal.getProperty("previousRevision"));
        current.setProperty("export", journal.getProperty("previousExport"));
        BlueprintFiles.writeProperties(folder.resolve("current.properties"), current);
        prepareTemplate(plugin);
        String retained = "merge-recovered-" + submissionId + "-" + UUID.randomUUID();
        BlueprintFiles.atomicWrite(folder.resolve(retained + ".bin"), Files.readAllBytes(rollback));
        BlueprintFiles.move(transaction, folder.resolve(retained + ".properties"));
        plugin.getLogger().warning("Rolled back interrupted blueprint merge " + submissionId + "; the request is still waiting for review.");
    }

    /** The retained applied-change file is the update packet that personal campuses merge. */
    private void completeMergeJournal(Path transaction, BlueprintRepository.Submission submission) throws IOException {
        Path rollback = folder.resolve("merge-rollback.bin");
        if (Files.exists(rollback)) BlueprintFiles.atomicWrite(folder.resolve("merge-complete-" + submission.id() + ".bin"), Files.readAllBytes(rollback));
        long number = Long.parseLong(BlueprintFiles.readProperties(transaction).getProperty("newRevision"));
        BlueprintFiles.move(transaction, folder.resolve("merge-complete-" + submission.id() + ".properties"));
        if (initialized) {
            approvals.put(number, new Approval(submission.id(), submission.entryId()));
            enqueueBehind();
        }
    }

    private void loadApprovals() throws IOException {
        for (var summary : submissions.summaries()) {
            if (summary.status() != BlueprintRepository.Status.APPROVED) continue;
            var journal = BlueprintFiles.readProperties(folder.resolve("merge-complete-" + summary.id() + ".properties"));
            long number = Long.parseLong(journal.getProperty("newRevision"));
            if (!summary.id().toString().equals(journal.getProperty("submission")) || number < 1
                    || approvals.put(number, new Approval(summary.id(), summary.entryId())) != null) throw new IOException("Invalid approval history.");
        }
        if (approvals.size() != latestRevision()) throw new IOException("Incomplete approval history.");
    }

    private List<BlockChange> packet(long number) throws IOException {
        List<BlockChange> cached = packets.get(number);
        if (cached != null) return cached;
        Approval approval = approvals.get(number);
        if (approval == null) throw new IOException("Missing blueprint update " + number);
        Properties journal = BlueprintFiles.readProperties(folder.resolve("merge-complete-" + approval.submission() + ".properties"));
        Path file = folder.resolve("merge-complete-" + approval.submission() + ".bin");
        if (!BlueprintFiles.digest(file).equals(journal.getProperty("rollbackSha256"))) throw new IOException("Blueprint update " + number + " checksum mismatch.");
        List<BlockChange> changes = BlueprintRepository.decode(Files.readAllBytes(file));
        packets.put(number, changes);
        return changes;
    }

    public void reject(CommandSender reviewer, UUID submissionId, String reason) throws IOException {
        requireMainThread();
        requireReviewer(reviewer);
        ensureCanCreateBranch();
        String cleaned = cleanText(reason, 500);
        var submission = submissions.read(submissionId);
        requirePending(submission);
        decide(submission, BlueprintRepository.Status.REJECTED, actor(reviewer), cleaned);
        notifyAuthor(submission, decisionText(submission.title(), BlueprintRepository.Status.REJECTED, cleaned));
    }

    private void decide(BlueprintRepository.Submission submission, BlueprintRepository.Status status, String actor, String reason) throws IOException {
        submissions.saveDecision(submission.decide(status, actor, reason));
        reviews.proposalDecided(submission.id());
    }

    private void requirePending(BlueprintRepository.Submission submission) {
        if (submission.status() != BlueprintRepository.Status.PENDING) throw new IllegalStateException("This request is already decided.");
        Entry entry = store.entry(submission.entryId()).orElseThrow(() -> new IllegalStateException("The campus that sent this request no longer exists."));
        for (BlockChange change : submission.changes()) {
            if (!editable(entry, change.position())) throw new IllegalStateException("This request changes blocks outside its campus bounds.");
        }
    }

    // ---------------------------------------------------------------- access

    public void requireAuthenticated(CommandSender sender) {
        if (sender instanceof Player player && !competition.isAuthenticated(player)) throw new SecurityException("Sign in before using the blueprint.");
    }

    public void requireReviewer(CommandSender sender) {
        requireAuthenticated(sender);
        if (!sender.hasPermission(reviewPermission())) throw new SecurityException("You do not have permission to review blueprint requests.");
    }

    public void requireBackupOperator(CommandSender sender) {
        requireAuthenticated(sender);
        if (!sender.hasPermission(plugin.getConfig().getString("blueprint.backup-permission", "hill175.blueprint.backup"))) {
            throw new SecurityException("You do not have permission for blueprint recovery snapshots.");
        }
    }

    public void requireOwner(Player player, Entry entry) {
        requireAuthenticated(player);
        String author = competition.participantKey(player);
        requireCanonicalOwner(entry, author);
        Branch branch = branches.get(entry.id());
        if (branch != null && !branch.owner.equals(author)) throw new SecurityException("This campus belongs to another owner.");
    }

    private void requireCanonicalOwner(Entry entry, String author) {
        if (entry == null || store.entry(entry.id()).orElse(null) != entry || !entry.members().equals(Set.of(author))) {
            throw new SecurityException("Only the campus owner can do this. Guests can help build, and the owner sends the build.");
        }
    }

    private Optional<Branch> ownBranch(Player player) {
        if (!competition.isAuthenticated(player)) return Optional.empty();
        String key = competition.participantKey(player);
        return branches.values().stream().filter(branch -> branch.owner.equals(key)
                && store.entry(branch.entryId).filter(entry -> validBranch(entry, branch)).isPresent()).findFirst();
    }

    public boolean maySee(CommandSender sender, BlueprintRepository.Summary summary) {
        if (sender instanceof Player player) {
            if (!competition.isAuthenticated(player)) return false;
            if (sender.hasPermission(reviewPermission())) return true;
            String author = competition.participantKey(player);
            return author.equals(summary.author()) && store.entry(summary.entryId()).map(entry -> entry.members().equals(Set.of(author))).orElse(false);
        }
        return sender.hasPermission(reviewPermission());
    }

    public List<String> allowedActions(CommandSender sender) {
        if (sender instanceof Player player && !competition.isAuthenticated(player)) return List.of();
        List<String> actions = new ArrayList<>(List.of("menu", "visit", "news", "history", "help"));
        if (sender instanceof Player player && ownBranch(player).isPresent()) actions.addAll(List.of("send", "fix", "cancel"));
        if (sender.hasPermission(reviewPermission())) actions.addAll(List.of("review", "edit", "save", "approve", "reject"));
        if (sender.hasPermission(plugin.getConfig().getString("blueprint.backup-permission", "hill175.blueprint.backup"))) actions.addAll(List.of("backup", "backups"));
        return List.copyOf(actions);
    }

    public String captureBackup(String reason) throws IOException {
        ensureCanCreateBranch();
        saving = true;
        try { return backups.capture(blueprint, reason); }
        catch (IOException exception) { failClosed("Blueprint recovery snapshot failed; further editing/approval is blocked.", exception); throw exception; }
        finally { saving = false; }
    }

    private String actor(CommandSender sender) {
        requireAuthenticated(sender);
        return sender instanceof Player player ? competition.participantKey(player) : "console";
    }

    private void notifyAuthor(BlueprintRepository.Submission submission, Component message) {
        Branch branch = branches.get(submission.entryId());
        for (Player online : Bukkit.getOnlinePlayers()) {
            if (!competition.isAuthenticated(online) || !submission.author().equals(competition.participantKey(online))) continue;
            online.sendMessage(message);
            if (branch == null) continue;
            branch.seenDecision = submission.id().toString();
            try { saveBranch(branch); }
            catch (IOException exception) { plugin.getLogger().log(Level.WARNING, "Could not save a blueprint notice receipt.", exception); }
        }
    }

    private String cleanText(String text, int maximumLength) {
        if (text == null || text.isBlank() || text.length() > maximumLength || text.codePoints().anyMatch(Character::isISOControl)
                || text.indexOf('§') >= 0 || !textAllowed.test(text)) throw new IllegalArgumentException("Use clean plain text of 1–" + maximumLength + " characters.");
        return text.trim();
    }

    // ---------------------------------------------------------------- persistence

    private void saveBranch(Branch branch) throws IOException {
        Properties values = new Properties();
        values.setProperty("entry", branch.entryId.toString());
        values.setProperty("owner", branch.owner);
        values.setProperty("world", branch.world);
        values.setProperty("worldId", branch.worldId.toString());
        values.setProperty("bounds", branch.bounds);
        if (branch.legacyBaseline != null) values.setProperty("baseline", branch.legacyBaseline);
        values.setProperty("notifiedThrough", Long.toString(branch.notifiedThrough));
        values.setProperty("syncedThrough", Long.toString(branch.syncedThrough));
        values.setProperty("seenDecision", branch.seenDecision);
        values.setProperty("chunks", String.join(";", branch.chunks.stream().sorted().toList()));
        values.setProperty("conflicts", Integer.toString(branch.conflicts.size()));
        boolean rewrite = branch.conflictsChanged;
        String file = branch.conflictFile;
        String digest = branch.conflictDigest;
        if (rewrite) {
            file = null;
            digest = null;
            if (!branch.conflicts.isEmpty()) {
                file = branch.entryId + ".conflicts-" + UUID.randomUUID() + ".bin";
                Path written = folder.resolve("branches").resolve(file);
                BlueprintFiles.atomicWrite(written, BlueprintRepository.encode(List.copyOf(branch.conflicts.values()), CONFLICT_LIMIT));
                digest = BlueprintFiles.digest(written);
            }
        }
        if (file != null) {
            values.setProperty("conflictsFile", file);
            values.setProperty("conflictsSha256", digest);
        }
        BlueprintFiles.writeProperties(branchFile(branch.entryId), values);
        if (!rewrite) return;
        String previous = branch.conflictFile;
        branch.conflictFile = file;
        branch.conflictDigest = digest;
        branch.conflictsChanged = false;
        if (previous != null && !previous.equals(file)) Files.deleteIfExists(folder.resolve("branches").resolve(previous));
    }

    private void loadBranches() throws IOException {
        Path directory = folder.resolve("branches");
        Files.createDirectories(directory);
        long latest = latestRevision();
        try (var paths = Files.list(directory)) {
            for (Path file : paths.filter(path -> path.toString().endsWith(".properties")).toList()) {
                Properties values = BlueprintFiles.readProperties(file);
                UUID entryId = UUID.fromString(values.getProperty("entry"));
                if (!file.equals(branchFile(entryId))) throw new IOException("Branch filename identity mismatch.");
                Branch branch = new Branch(entryId, values.getProperty("owner"), values.getProperty("world"),
                        UUID.fromString(values.getProperty("worldId")), values.getProperty("bounds"), values.getProperty("baseline"));
                branch.syncedThrough = Long.parseLong(values.getProperty("syncedThrough", "0"));
                branch.notifiedThrough = Long.parseLong(values.getProperty("notifiedThrough", Long.toString(branch.syncedThrough)));
                branch.seenDecision = values.getProperty("seenDecision", "");
                if (branch.notifiedThrough < 0 || branch.notifiedThrough > branch.syncedThrough) throw new IOException("Invalid update notice revision.");
                if (branch.syncedThrough < 0 || branch.syncedThrough > latest) throw new IOException("Invalid sync revision.");
                if (!branch.world.matches("hill_(people|place)_[a-f0-9]{12}")) throw new IOException("Invalid branch world reference.");
                Entry entry = store.entry(entryId).orElseThrow(() -> new IOException("Branch campus entry is missing."));
                String chunks = values.getProperty("chunks", "");
                if (!chunks.isEmpty()) {
                    for (String chunk : chunks.split(";")) {
                        if (!chunk.matches("-?\\d{1,7},-?\\d{1,7}")) throw new IOException("Invalid changed-area journal.");
                        branch.chunks.add(chunk);
                    }
                }
                int conflicts = Integer.parseInt(values.getProperty("conflicts", "0"));
                if (conflicts > 0) {
                    String name = values.getProperty("conflictsFile", "");
                    if (!name.matches(java.util.regex.Pattern.quote(entryId.toString()) + "\\.conflicts-[0-9a-f-]{36}\\.bin")) throw new IOException("Invalid conflict journal reference.");
                    Path conflictFile = directory.resolve(name);
                    String digest = values.getProperty("conflictsSha256");
                    if (!BlueprintFiles.digest(conflictFile).equals(digest)) throw new IOException("Conflict journal checksum mismatch.");
                    for (BlockChange change : BlueprintRepository.decode(Files.readAllBytes(conflictFile), CONFLICT_LIMIT)) branch.conflicts.put(change.position(), change);
                    if (branch.conflicts.size() != conflicts) throw new IOException("Conflict journal count mismatch.");
                    branch.conflictFile = name;
                    branch.conflictDigest = digest;
                }
                index(branch);
                if (!validBranch(entry, branch)) throw new IOException("Campus branch ownership or bounds no longer match: " + entryId);
            }
        }
    }

    private void index(Branch branch) {
        branches.put(branch.entryId, branch);
        branchByWorld.put(branch.world, branch.entryId);
    }

    private boolean validBranch(Entry entry, Branch branch) {
        World loaded = Bukkit.getWorld(branch.world);
        return store.entry(entry.id()).orElse(null) == entry && entry.id().equals(branch.entryId)
                && entry.worldName().equals(branch.world) && entry.members().equals(Set.of(branch.owner))
                && bounds(entry).equals(branch.bounds) && (loaded == null || loaded.getUID().equals(branch.worldId));
    }

    private static boolean editable(Entry entry, BlockPosition position) {
        for (BuildRegion region : entry.editableRegions()) if (region.contains(position.blockX(), position.blockY(), position.blockZ())) return true;
        return false;
    }

    private static boolean overlaps(List<BuildRegion> regions, String chunk) {
        String[] parts = chunk.split(",");
        int minX = Integer.parseInt(parts[0]) << 4;
        int minZ = Integer.parseInt(parts[1]) << 4;
        return regions.stream().anyMatch(region -> region.minX() <= minX + 15 && region.maxX() >= minX
                && region.minZ() <= minZ + 15 && region.maxZ() >= minZ);
    }


    private static String soleOwner(Entry entry) {
        if (entry == null || entry.members().size() != 1) throw new SecurityException("A blueprint campus must have exactly one owner; guests are stored separately.");
        return entry.members().iterator().next();
    }

    private int maximumChanges() { return Math.clamp(plugin.getConfig().getInt("blueprint.maximum-changed-blocks", 4096), 1, 8192); }
    private int maximumSnapshotChunks() { return Math.clamp(plugin.getConfig().getInt("blueprint.maximum-snapshot-chunks", 512), 16, 4096); }
    private String reviewPermission() { return plugin.getConfig().getString("blueprint.review-permission", "hill175.blueprint.review"); }
    long latestRevision() throws IOException { return Long.parseLong(BlueprintFiles.readProperties(folder.resolve("current.properties")).getProperty("revision")); }
    private Path branchFile(UUID entryId) { return folder.resolve("branches").resolve(entryId + ".properties"); }
    private static String bounds(Entry entry) { return entry.region() + "|" + entry.editableRegions(); }
    private static void requireMainThread() { if (!Bukkit.isPrimaryThread()) throw new IllegalStateException("Blueprint actions require the server thread."); }
    private void requireReady() { if (!initialized || failed || closing) throw new IllegalStateException("The blueprint is unavailable until staff finish recovery and restart."); }

    private void refreshWorldPlayers(String worldName) {
        World world = Bukkit.getWorld(worldName);
        if (world == null) return;
        for (Player player : List.copyOf(world.getPlayers())) {
            if (!competition.isAuthenticated(player)) continue;
            player.closeInventory();
            competition.refreshMovementMode(player, player.getLocation());
        }
    }

    private void failClosed(String message, Exception exception) {
        failed = true;
        reviews.clearAll();
        plugin.getLogger().log(Level.SEVERE, message, exception);
        branches.values().stream().map(branch -> branch.world).distinct().forEach(this::refreshWorldPlayers);
    }

    @Override
    public void close() {
        requireMainThread();
        if (!draft.isEmpty() && !committingDraft && initialized && !failed) commitDraft(true);
        closing = true;
        reviews.close();
        outlines.close();
        for (String name : List.copyOf(previews)) {
            World world = Bukkit.getWorld(name);
            if (world == null || !Bukkit.unloadWorld(world, false)) continue;
            try { BlueprintWorldFiles.deletePreview(world.getWorldFolder().toPath()); }
            catch (IOException exception) { plugin.getLogger().log(Level.WARNING, "Could not delete a blueprint preview copy.", exception); }
        }
    }
}
