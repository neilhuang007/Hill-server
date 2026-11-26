package org.thehill.hill175.replay;

import com.destroystokyo.paper.event.player.PlayerPickupExperienceEvent;
import com.destroystokyo.paper.event.player.PlayerStartSpectatingEntityEvent;
import io.papermc.paper.event.player.AsyncPlayerSpawnLocationEvent;
import io.papermc.paper.event.player.PlayerArmSwingEvent;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.EntityMountEvent;
import org.bukkit.event.entity.EntityPickupItemEvent;
import org.bukkit.event.entity.FoodLevelChangeEvent;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.inventory.InventoryOpenEvent;
import org.bukkit.event.player.*;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.inventory.ItemStack;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.IllegalPluginAccessException;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.backup.RecoveryPlayerState;
import org.thehill.hill175.competition.CompetitionModule;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Predicate;
import java.util.logging.Level;

/** Owns staff replay visits, with the displaced player state journaled before any replay tools are issued. */
public final class BuildReplayViewer implements Listener, AutoCloseable {
    private static final int MAX_VISITS = 3;
    private static final int PREPARE_TIMEOUT_TICKS = 20 * 30;
    private static final int[] INTERVALS = {5, 15, 30, 60, 120};
    private static final double[] SPEEDS = {0.25, 0.5, 1, 2, 4, 8};
    private static final String STATE_IDENTITY = "replay-identity";
    private static final String STATE_RESTORE_TOKEN = "replay-restore-token";

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final Predicate<Player> allowed;
    private final BuildRecorder recorder;
    private final Path stateDirectory;
    private final NamespacedKey controlKey;
    private final NamespacedKey restoreKey;
    private final Map<UUID, Request> loading = new HashMap<>();
    private final Map<UUID, Visit> visits = new HashMap<>();
    private final Set<UUID> recovering = new HashSet<>();
    private final Set<UUID> restoredInMemory = new HashSet<>();
    private volatile Location loginFallback;
    private volatile boolean closed;
    private BukkitTask ticker;

    public BuildReplayViewer(JavaPlugin plugin, CompetitionModule competition, Predicate<Player> allowed, BuildRecorder recorder) {
        this.plugin = plugin;
        this.competition = competition;
        this.allowed = allowed;
        this.recorder = recorder;
        this.stateDirectory = plugin.getDataFolder().toPath().resolve("build-replay-players");
        this.controlKey = new NamespacedKey(plugin, "build-replay-control");
        this.restoreKey = new NamespacedKey(plugin, "build-replay-restored");
    }

    public void start() {
        if (closed || ticker != null) return;
        loginFallback = plugin.getServer().getRespawnWorld().getSpawnLocation();
        ReplayStage.cleanup(plugin);
        for (Player player : Bukkit.getOnlinePlayers()) detectRecovery(player, false);
        Bukkit.getPluginManager().registerEvents(this, plugin);
        ticker = Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 1L, 1L);
    }

    /** Pending disk loads do not yet own or protect a replay inventory. */
    public boolean contains(Player player) {
        return visits.containsKey(player.getUniqueId());
    }

    public void open(Player viewer, UUID profile) {
        if (closed || recorder == null || !hasAccess(viewer)) {
            tell(viewer, "Only signed-in replay staff can open build recordings.", NamedTextColor.RED);
            return;
        }
        UUID id = viewer.getUniqueId();
        if (contains(viewer)) {
            tell(viewer, "Exit the current replay before starting another.", NamedTextColor.YELLOW);
            return;
        }
        if (!canOpenHere(viewer)) {
            tell(viewer, "Open Replays from the hub or a campus after finishing your current preview or edit.", NamedTextColor.YELLOW);
            return;
        }
        if (loading.containsKey(id)) {
            tell(viewer, "A recording is already loading for you.", NamedTextColor.YELLOW);
            return;
        }
        if (visits.size() + loading.size() >= MAX_VISITS) {
            tell(viewer, "The replay viewers are busy. Try again after one closes.", NamedTextColor.YELLOW);
            return;
        }
        viewer.closeInventory();
        if (!viewer.getItemOnCursor().getType().isAir()) {
            tell(viewer, "Put away the item on your cursor before opening a replay.", NamedTextColor.YELLOW);
            return;
        }
        Request request = new Request(viewer, profile, competition.participantKey(viewer), viewer.getLocation());
        loading.put(id, request);
        tell(viewer, "Loading the build recording. Stay in this spot while it opens.", NamedTextColor.AQUA);
        try {
            recorder.pin(profile);
            request.pinned = true;
            recorder.load(profile, 0).whenComplete((tape, error) -> {
                if (closed) return;
                try {
                    Bukkit.getScheduler().runTask(plugin, () -> loaded(request, tape, error));
                } catch (IllegalPluginAccessException disabled) { }
            });
        } catch (RuntimeException failure) {
            loading.remove(id, request);
            releaseRequest(request);
            loadFailed(viewer, failure);
        }
    }

    private void loaded(Request request, BuildTape tape, Throwable error) {
        Player viewer = request.viewer;
        UUID id = viewer.getUniqueId();
        if (!loading.remove(id, request)) return;
        try {
            if (closed || !hasAccess(viewer) || Bukkit.getPlayer(id) != viewer
                    || !sameIdentity(viewer, request.identity) || !sameBlock(request.origin, viewer.getLocation())
                    || !canOpenHere(viewer)) return;
            if (error != null) {
                loadFailed(viewer, error);
                return;
            }
            if (tape == null || tape.segments().isEmpty()) {
                tell(viewer, "There is no saved build recording for that player yet.", NamedTextColor.YELLOW);
                return;
            }
            viewer.closeInventory();
            if (!viewer.getItemOnCursor().getType().isAir()) {
                tell(viewer, "Put away the item on your cursor and try again.", NamedTextColor.YELLOW);
                return;
            }
            RecoveryPlayerState state = RecoveryPlayerState.capture(viewer);
            state.values().setProperty(STATE_IDENTITY, request.identity);
            state.values().setProperty(STATE_RESTORE_TOKEN, UUID.randomUUID().toString());
            ReplayStage stage = new ReplayStage(plugin, id, tape);
            try {
                state.save(stateFile(viewer));
            } catch (IOException | RuntimeException failure) {
                stage.close();
                throw failure;
            }
            restoredInMemory.remove(id);
            Visit visit = new Visit(request.profile, request.identity, tape, stage, state);
            visits.put(id, visit);
            request.pinned = false;
            try {
                clearInventory(viewer);
                setReplayMode(viewer);
                controls(viewer, visit);
                viewer.getInventory().setHeldItemSlot(2);
                show(viewer, visit, 0L);
                if (!visit.stage.owns(viewer.getWorld())) throw new IOException("The replay world could not be entered.");
                plugin.getLogger().info("Build replay opened: staff=" + id + " profile=" + visit.profile);
                tell(viewer, "Playing at 1×. Left-click Pause or Play Backward; right-click either skip arrow to change the interval.", NamedTextColor.AQUA);
                if (tape.windowCount() > 1) {
                    tell(viewer, "This recording has multiple parts. Hold Replay Info and left-click for the previous part or right-click for the next.", NamedTextColor.AQUA);
                }
                status(viewer, visit);
            } catch (IOException | RuntimeException failure) {
                loadFailed(viewer, failure);
                leave(viewer, visit, true, false);
            }
        } catch (IOException | RuntimeException failure) {
            loadFailed(viewer, failure);
        } finally {
            releaseRequest(request);
        }
    }

    private boolean canOpenHere(Player viewer) {
        UUID id = viewer.getUniqueId();
        return !isReplayWorld(viewer.getWorld()) && !recovering.contains(id)
                && (restoredInMemory.contains(id) || !Files.exists(stateFile(viewer), LinkOption.NOFOLLOW_LINKS))
                && !viewer.isInsideVehicle() && viewer.getPassengers().isEmpty()
                && (viewer.getGameMode() != GameMode.SPECTATOR || viewer.getSpectatorTarget() == null)
                && competition.canStartBuildReplay(viewer);
    }

    private boolean hasAccess(Player player) {
        try { return player.isOnline() && competition.isAuthenticated(player) && allowed.test(player); }
        catch (RuntimeException unavailable) { return false; }
    }

    private boolean sameIdentity(Player player, String identity) {
        return competition.isAuthenticated(player) && identity.equals(competition.participantKey(player));
    }

    private boolean canWatch(Player player, Visit visit) {
        return hasAccess(player) && sameIdentity(player, visit.identity);
    }

    private void show(Player player, Visit visit, long time) throws IOException {
        show(player, visit, visit.stage, time);
        visit.time = time;
    }

    private void show(Player player, Visit visit, ReplayStage stage, long time) throws IOException {
        visit.presenting = stage;
        try {
            stage.show(player, time);
        } finally {
            visit.presenting = null;
        }
    }

    private boolean moveChapter(Player player, Visit visit, int step, ChapterMove move, long remaining) {
        if (visit.chapter != null) return false;
        int index = visit.tape.windowIndex() + step;
        if (index < 0 || index >= visit.tape.windowCount()) {
            if (move == ChapterMove.PLAY) {
                visit.direction = 0;
                visit.halfMillis = 0;
            } else if (move == ChapterMove.SELECT) {
                tell(player, step < 0 ? "This is the first part." : "This is the last part.", NamedTextColor.YELLOW);
            }
            return false;
        }
        requestChapter(player, visit, new Chapter(index, Bukkit.getCurrentTick(), move, step, remaining));
        return true;
    }

    private void requestChapter(Player player, Visit visit, Chapter chapter) {
        visit.chapter = chapter;
        status(player, visit);
        try {
            recorder.load(visit.profile, chapter.index()).whenComplete((tape, error) -> {
                if (closed) return;
                try {
                    Bukkit.getScheduler().runTask(plugin, () -> chapterLoaded(player, visit, chapter, tape, error));
                } catch (IllegalPluginAccessException disabled) { }
            });
        } catch (RuntimeException failure) {
            chapterFailed(player, visit, failure);
        }
    }

    private void chapterLoaded(Player player, Visit visit, Chapter chapter, BuildTape tape, Throwable error) {
        UUID id = player.getUniqueId();
        if (closed || visits.get(id) != visit || visit.leaving || visit.chapter != chapter || Bukkit.getPlayer(id) != player
                || !canWatch(player, visit) || !visit.stage.owns(player.getWorld())) return;
        if (error != null || tape == null || tape.segments().isEmpty() || tape.windowIndex() != chapter.index()) {
            chapterFailed(player, visit, error != null ? error : new IOException("The requested replay part is unavailable."));
            return;
        }
        long edge = chapter.step() < 0 && chapter.move() != ChapterMove.SELECT ? tape.duration() : 0L;
        long consumed = Math.clamp(chapter.remaining(), -edge, tape.duration() - edge);
        long remaining = chapter.remaining() - consumed;
        if (remaining != 0) {
            int nextIndex = chapter.index() + chapter.step();
            if (nextIndex >= 0 && nextIndex < tape.windowCount()) {
                requestChapter(player, visit, new Chapter(nextIndex, Bukkit.getCurrentTick(), ChapterMove.SEEK, chapter.step(), remaining));
                return;
            }
        }
        long time = edge + consumed;
        try {
            ReplayStage previous = visit.stage;
            ReplayStage next = new ReplayStage(plugin, id, tape);
            visit.incoming = next;
            previous.withdrawActor();
            show(player, visit, next, time);
            if (visits.get(id) != visit || visit.leaving) return;
            if (!next.owns(player.getWorld())) throw new IOException("The replay part could not be entered.");
            visit.stage = next;
            visit.incoming = null;
            visit.tape = tape;
            visit.time = time;
            visit.halfMillis = 0;
            visit.chapter = null;
            closeStage(previous);
            controls(player, visit);
            status(player, visit);
        } catch (IOException | RuntimeException failure) {
            loadFailed(player, failure);
            leave(player, visit, true, false);
        }
    }

    private void chapterFailed(Player player, Visit visit, Throwable failure) {
        visit.chapter = null;
        visit.direction = 0;
        visit.halfMillis = 0;
        plugin.getLogger().log(Level.WARNING, "Could not load a build replay part.", failure);
        tell(player, "Could not load that replay part. The current part is paused; try Replay Info again.", NamedTextColor.RED);
        status(player, visit);
    }

    private void tick() {
        int tick = Bukkit.getCurrentTick();
        for (Request request : List.copyOf(loading.values())) {
            if (tick - request.started >= PREPARE_TIMEOUT_TICKS || !hasAccess(request.viewer)
                    || !sameIdentity(request.viewer, request.identity) || !canOpenHere(request.viewer)) cancel(request, true);
        }
        for (UUID id : List.copyOf(recovering)) {
            Player player = Bukkit.getPlayer(id);
            if (player != null && competition.isAuthenticated(player)) recover(player);
        }
        for (var entry : List.copyOf(visits.entrySet())) {
            Player player = Bukkit.getPlayer(entry.getKey());
            Visit visit = entry.getValue();
            if (player == null || !canWatch(player, visit)) {
                if (player != null) {
                    tell(player, "Replay access ended. Returning you to Hill.", NamedTextColor.YELLOW);
                    leave(player, visit, true, false);
                } else if (visits.remove(entry.getKey(), visit)) {
                    dispose(visit);
                }
                continue;
            }
            if (!visit.stage.owns(player.getWorld())) {
                leave(player, visit, false, false);
                continue;
            }
            try {
                visit.stage.finishFrame();
            } catch (IOException | RuntimeException failure) {
                loadFailed(player, failure);
                leave(player, visit, true, false);
                continue;
            }
            if (visit.chapter != null) {
                if (tick - visit.chapter.started() >= PREPARE_TIMEOUT_TICKS) {
                    chapterFailed(player, visit, new IOException("Timed out loading a replay part."));
                } else if (tick % 5 == 0) status(player, visit);
                continue;
            }
            if (!visit.stage.ready()) {
                if (tick % 5 == 0) status(player, visit);
                continue;
            }
            long duration = visit.tape.duration();
            int halfMillis = (int) (100 * SPEEDS[visit.speed]) * visit.direction + visit.halfMillis;
            long elapsed = Math.floorDiv(halfMillis, 2);
            long bounded = Math.clamp(elapsed, -visit.time, duration - visit.time);
            long next = visit.time + bounded;
            visit.halfMillis = elapsed == bounded ? Math.floorMod(halfMillis, 2) : 0;
            if (next != visit.time) {
                try {
                    show(player, visit, next);
                } catch (IOException | RuntimeException failure) {
                    loadFailed(player, failure);
                    leave(player, visit, true, false);
                    continue;
                }
            }
            if (visit.stage.ready()) {
                if (visit.direction < 0 && next == 0 && visit.halfMillis == 0) moveChapter(player, visit, -1, ChapterMove.PLAY, 0L);
                else if (visit.direction > 0 && next == duration) moveChapter(player, visit, 1, ChapterMove.PLAY, 0L);
            }
            if (tick % 5 == 0) status(player, visit);
        }
    }

    private void cancel(Request request, boolean notify) {
        if (!loading.remove(request.viewer.getUniqueId(), request)) return;
        releaseRequest(request);
        if (notify && request.viewer.isOnline()) tell(request.viewer, "Replay loading was canceled. Open it again when you're ready.", NamedTextColor.YELLOW);
    }

    private void releaseRequest(Request request) {
        if (!request.pinned) return;
        request.pinned = false;
        recorder.unpin(request.profile);
    }

    private void returnToHill(Player player, RecoveryPlayerState state, boolean exact) {
        if (exact) {
            Location origin = null;
            try {
                origin = state.location();
            } catch (IllegalStateException unavailable) { }
            if (origin != null && !isReplayWorld(origin.getWorld()) && competition.safeBuildReplayReturn(origin)
                    && player.teleport(origin) && origin.getWorld().equals(player.getWorld())) return;
        }
        if (!player.teleport(competition.buildReplayFallback(player)) || isReplayWorld(player.getWorld())) {
            throw new IllegalStateException("Could not return the viewer to Hill.");
        }
    }

    private void leave(Player player, Visit visit, boolean returnLocation, boolean quitting) {
        UUID id = player.getUniqueId();
        if (visits.get(id) != visit || visit.leaving) return;
        visit.leaving = true;
        boolean originalViewer = sameIdentity(player, visit.identity);
        boolean restored = false;
        try {
            withdrawActor(visit.incoming);
            withdrawActor(visit.stage);
            if (returnLocation && isReplayWorld(player.getWorld())) {
                try {
                    returnToHill(player, visit.state, originalViewer);
                } catch (RuntimeException failure) {
                    if (!quitting) plugin.getLogger().log(Level.WARNING, "Could not move a replay viewer to Hill.", failure);
                }
            }
            if (originalViewer) visit.state.apply(player);
            else clearInventory(player);
            if (!competition.isAuthenticated(player)) setLockedMode(player);
            visits.remove(id, visit);
            if (originalViewer && !quitting && !isReplayWorld(player.getWorld())) {
                competition.refreshMovementMode(player, player.getLocation());
            }
            if (originalViewer && !isReplayWorld(player.getWorld())) {
                acknowledgeRestore(player, visit.state);
                restored = true;
            } else player.saveData();
        } catch (RuntimeException failure) {
            plugin.getLogger().log(Level.SEVERE, "Replay player state was preserved for recovery.", failure);
        } finally {
            visits.remove(id, visit);
            if (!restored && !quitting) recovering.add(id);
            dispose(visit);
        }
        if (quitting) return;
        if (isReplayWorld(player.getWorld())) {
            player.kick(Component.text("Could not return from the replay safely. Your original inventory is saved; reconnect to recover it."));
        } else if (restored) {
            player.sendActionBar(Component.empty());
        }
    }

    private void dispose(Visit visit) {
        visit.chapter = null;
        closeStage(visit.incoming);
        closeStage(visit.stage);
        recorder.unpin(visit.profile);
    }

    private void withdrawActor(ReplayStage stage) {
        if (stage == null) return;
        try {
            stage.withdrawActor();
        } catch (RuntimeException failure) {
            plugin.getLogger().log(Level.WARNING, "The replay figure could not be removed.", failure);
        }
    }

    private void closeStage(ReplayStage stage) {
        if (stage == null) return;
        try {
            stage.close();
        } catch (RuntimeException failure) {
            plugin.getLogger().log(Level.WARNING, "The temporary replay stage could not be released.", failure);
        }
    }

    private Path stateFile(Player player) { return stateDirectory.resolve(player.getUniqueId() + ".properties"); }

    private void detectRecovery(Player player, boolean joined) {
        UUID id = player.getUniqueId();
        Path file = stateFile(player);
        var data = player.getPersistentDataContainer();
        if (!Files.exists(file, LinkOption.NOFOLLOW_LINKS)) {
            if (joined) data.remove(restoreKey);
            return;
        }
        String acknowledged = data.get(restoreKey, PersistentDataType.STRING);
        if (acknowledged != null && Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            try {
                if (acknowledged.equals(RecoveryPlayerState.read(file).values().getProperty(STATE_RESTORE_TOKEN))) {
                    restoredInMemory.add(id);
                    if (joined) {
                        Files.delete(file);
                        data.remove(restoreKey);
                    }
                    return;
                }
            } catch (IOException | RuntimeException failure) {
                plugin.getLogger().log(Level.WARNING, "Could not check or clear a build replay recovery record for " + id, failure);
                if (restoredInMemory.contains(id)) return;
            }
        }
        recovering.add(id);
        var inventory = player.getInventory();
        for (int slot = 0; slot < inventory.getSize(); slot++) {
            ItemStack item = inventory.getItem(slot);
            if (item != null && item.hasItemMeta() && item.getItemMeta().getPersistentDataContainer().has(controlKey)) {
                inventory.setItem(slot, null);
            }
        }
    }

    private void recover(Player player) {
        UUID id = player.getUniqueId();
        Path file = stateFile(player);
        try {
            if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Missing or invalid recovery record.");
            RecoveryPlayerState state = RecoveryPlayerState.read(file);
            if (!sameIdentity(player, state.values().getProperty(STATE_IDENTITY, ""))) {
                player.kick(Component.text("Sign in with the same Hill account you used for replays to recover your saved inventory."));
                return;
            }
            if (state.values().getProperty(STATE_RESTORE_TOKEN) == null) {
                state.values().setProperty(STATE_RESTORE_TOKEN, UUID.randomUUID().toString());
                state.save(file);
            }
            returnToHill(player, state, true);
            state.apply(player);
            competition.refreshMovementMode(player, player.getLocation());
            acknowledgeRestore(player, state);
            tell(player, "Your inventory was recovered from a previous build replay.", NamedTextColor.GREEN);
        } catch (IOException | RuntimeException failure) {
            plugin.getLogger().log(Level.SEVERE, "Cannot recover the saved build replay inventory for " + id, failure);
            player.kick(Component.text("Your saved replay inventory needs operator recovery."));
        }
    }

    private void acknowledgeRestore(Player player, RecoveryPlayerState state) {
        UUID id = player.getUniqueId();
        player.getPersistentDataContainer().set(restoreKey, PersistentDataType.STRING, state.values().getProperty(STATE_RESTORE_TOKEN));
        restoredInMemory.add(id);
        recovering.remove(id);
        try {
            player.saveData();
        } catch (RuntimeException failure) {
            plugin.getLogger().log(Level.WARNING, "Could not save restored player data for " + id + "; recovery record retained.", failure);
        }
    }

    private static void setReplayMode(Player player) {
        player.setGameMode(GameMode.ADVENTURE);
        player.setGravity(false);
        player.setAllowFlight(true);
        player.setFlying(true);
        player.setFallDistance(0);
    }

    private static void setLockedMode(Player player) {
        player.setGameMode(GameMode.ADVENTURE);
        player.setFlying(false);
        player.setAllowFlight(false);
        player.setGravity(false);
        player.setFallDistance(0);
    }

    private static void clearInventory(Player player) {
        player.getInventory().setContents(new ItemStack[player.getInventory().getSize()]);
    }

    private void controls(Player player, Visit visit) {
        int seconds = INTERVALS[visit.interval];
        String rate = speed(visit);
        var inv = player.getInventory();
        inv.setItem(0, control(visit, Material.SPECTRAL_ARROW, "Skip Back " + seconds + "s", "Left-click to jump back. Right-click to change interval.", Control.SKIP_BACK));
        inv.setItem(1, control(visit, Material.REDSTONE_TORCH, "Play Backward", "Left-click to play in reverse.", Control.REVERSE));
        inv.setItem(2, control(visit, Material.REDSTONE_BLOCK, "Pause", "Left-click to pause the recording.", Control.PAUSE));
        inv.setItem(3, control(visit, Material.LIME_DYE, "Play Forward", "Left-click to play at " + rate + ".", Control.FORWARD));
        inv.setItem(4, control(visit, Material.ARROW, "Skip Ahead " + seconds + "s", "Left-click to jump ahead. Right-click to change interval.", Control.SKIP_AHEAD));
        inv.setItem(5, control(visit, Material.FEATHER, "Slower · " + rate, "Left-click to lower playback speed.", Control.SLOWER));
        inv.setItem(6, control(visit, Material.SUGAR, "Faster · " + rate, "Left-click to raise playback speed.", Control.FASTER));
        inv.setItem(7, visit.tape.windowCount() > 1
                ? control(visit, Material.CLOCK, "Replay Info · " + part(visit.tape),
                        "Left-click: Previous part\nRight-click: Next part", Control.INFO)
                : control(visit, Material.CLOCK, "Replay Info", "Click for controls and playback time.", Control.INFO));
        inv.setItem(8, control(visit, Material.BARRIER, "Exit Replay", "Return to Hill with your original inventory.", Control.EXIT));
    }

    private ItemStack control(Visit visit, Material material, String label, String hint, Control control) {
        ItemStack item = new ItemStack(material);
        var meta = item.getItemMeta();
        meta.displayName(Component.text(label, NamedTextColor.GREEN));
        meta.lore(hint.lines().<Component>map(line -> Component.text(line, NamedTextColor.GRAY)).toList());
        meta.getPersistentDataContainer().set(controlKey, PersistentDataType.STRING, visit.token + ":" + control.name());
        item.setItemMeta(meta);
        return item;
    }

    private void use(Player player, ItemStack item, boolean right, boolean swing) {
        Visit visit = visits.get(player.getUniqueId());
        if (visit == null || visit.leaving || !canWatch(player, visit) || !visit.stage.owns(player.getWorld())
                || item == null || !item.hasItemMeta()) return;
        String action = item.getItemMeta().getPersistentDataContainer().get(controlKey, PersistentDataType.STRING);
        if (action == null || !action.startsWith(visit.token + ":")) return;
        Control control;
        try { control = Control.valueOf(action.substring(visit.token.length() + 1)); }
        catch (IllegalArgumentException invalid) { return; }
        int tick = Bukkit.getCurrentTick();
        if (right) {
            if (tick == visit.lastRightTick) return;
            visit.lastRightTick = tick;
        } else {
            if (tick - visit.lastLeftTick <= 1 || swing && tick - visit.lastRightTick <= 1) return;
            visit.lastLeftTick = tick;
        }
        if (Bukkit.isTickingWorlds()) Bukkit.getScheduler().runTask(plugin, () -> operate(player, visit, control, right));
        else operate(player, visit, control, right);
    }

    private void operate(Player player, Visit visit, Control control, boolean right) {
        if (visits.get(player.getUniqueId()) != visit || visit.leaving || !canWatch(player, visit) || !visit.stage.owns(player.getWorld())) return;
        try {
            switch (control) {
                case SKIP_BACK, SKIP_AHEAD -> {
                    if (right) {
                        visit.interval = (visit.interval + 1) % INTERVALS.length;
                        controls(player, visit);
                    } else {
                        long delta = INTERVALS[visit.interval] * 1000L * (control == Control.SKIP_AHEAD ? 1 : -1);
                        seek(player, visit, delta);
                    }
                }
                case REVERSE -> { if (!right) direction(visit, -1); }
                case FORWARD -> { if (!right) direction(visit, 1); }
                case PAUSE -> { if (!right) visit.direction = 0; }
                case SLOWER, FASTER -> {
                    if (!right) {
                        visit.speed = Math.clamp(visit.speed + (control == Control.FASTER ? 1 : -1), 0, SPEEDS.length - 1);
                        controls(player, visit);
                    }
                }
                case INFO -> {
                    if (visit.tape.windowCount() > 1) moveChapter(player, visit, right ? 1 : -1, ChapterMove.SELECT, 0L);
                    else tell(player, "Left-click to play, pause, seek, or change speed. Right-click a skip arrow to choose how far to jump. Recorded time skips offline gaps.", NamedTextColor.AQUA);
                }
                case EXIT -> { leave(player, visit, true, false); return; }
            }
            status(player, visit);
        } catch (IOException | RuntimeException failure) {
            loadFailed(player, failure);
            leave(player, visit, true, false);
        }
    }

    private void seek(Player player, Visit visit, long delta) throws IOException {
        long consumed = Math.clamp(delta, -visit.time, visit.tape.duration() - visit.time);
        long remaining = delta - consumed;
        visit.halfMillis = 0;
        visit.chapter = null;
        if (remaining != 0 && moveChapter(player, visit, Long.signum(remaining), ChapterMove.SEEK, remaining)) return;
        if (consumed != 0) show(player, visit, visit.time + consumed);
    }

    private static void direction(Visit visit, int direction) {
        if (visit.chapter != null && visit.chapter.move() == ChapterMove.PLAY && visit.chapter.step() != direction) visit.chapter = null;
        visit.direction = direction;
    }

    private static String speed(Visit visit) {
        double value = SPEEDS[visit.speed];
        return (value == (int) value ? Integer.toString((int) value) : Double.toString(value)) + "×";
    }

    private void status(Player player, Visit visit) {
        String phase;
        if (visit.chapter != null) phase = "Loading part " + (visit.chapter.index() + 1) + "…";
        else if (!visit.stage.ready()) phase = "Rendering…";
        else phase = (visit.direction > 0 ? "Playing" : visit.direction < 0 ? "Reversing" : "Paused") + " " + speed(visit);
        String part = visit.tape.windowCount() > 1 ? "  •  " + part(visit.tape) : "";
        player.sendActionBar(Component.text(visit.tape.name() + part + "  •  " + timestamp(visit.time) + " / "
                + timestamp(visit.tape.duration()) + "  •  " + phase + "  •  Skip " + INTERVALS[visit.interval] + "s", NamedTextColor.AQUA));
    }

    private static String part(BuildTape tape) { return "Part " + (tape.windowIndex() + 1) + "/" + tape.windowCount(); }

    private static String timestamp(long millis) {
        long seconds = millis / 1000L;
        return seconds >= 3600 ? String.format(Locale.ROOT, "%d:%02d:%02d", seconds / 3600, seconds / 60 % 60, seconds % 60)
                : String.format(Locale.ROOT, "%d:%02d", seconds / 60, seconds % 60);
    }

    private static void tell(Player player, String text, NamedTextColor color) { player.sendMessage(Component.text(text, color)); }

    private void loadFailed(Player player, Throwable failure) {
        plugin.getLogger().log(Level.WARNING, "Could not open or play a build replay.", failure);
        tell(player, failure instanceof ReplayStorage.Full ? failure.getMessage() : "The build replay could not be opened or played. Please try again.", NamedTextColor.RED);
    }

    private static boolean isReplayWorld(World world) { return world != null && world.getName().startsWith(ReplayStage.PREFIX); }

    private static boolean sameBlock(Location a, Location b) {
        return b != null && a.getWorld().equals(b.getWorld()) && a.getBlockX() == b.getBlockX()
                && a.getBlockY() == b.getBlockY() && a.getBlockZ() == b.getBlockZ();
    }

    private boolean protectedInventory(Player player) {
        return contains(player) || isReplayWorld(player.getWorld())
                || recovering.contains(player.getUniqueId()) && competition.isAuthenticated(player);
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void interact(PlayerInteractEvent event) {
        Player player = event.getPlayer();
        if (!protectedInventory(player)) return;
        event.setCancelled(true);
        if (event.getHand() == EquipmentSlot.HAND && (event.getAction().isLeftClick() || event.getAction().isRightClick())) {
            use(player, event.getItem(), event.getAction().isRightClick(), false);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void swing(PlayerArmSwingEvent event) {
        Player player = event.getPlayer();
        Visit visit = visits.get(player.getUniqueId());
        if (event.getHand() != EquipmentSlot.HAND || visit == null) return;
        event.setCancelled(true);
        if (visit.swingQueued) return;
        visit.swingQueued = true;
        int slot = player.getInventory().getHeldItemSlot();
        int tick = Bukkit.getCurrentTick();
        Bukkit.getScheduler().runTask(plugin, () -> {
            visit.swingQueued = false;
            if (visits.get(player.getUniqueId()) != visit || player.getInventory().getHeldItemSlot() != slot
                    || tick - visit.lastLeftTick <= 1 || tick - visit.lastRightTick <= 1) return;
            use(player, player.getInventory().getItemInMainHand(), false, true);
        });
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void interactEntity(PlayerInteractEntityEvent event) {
        if (!protectedInventory(event.getPlayer()) && !isReplayWorld(event.getRightClicked().getWorld())) return;
        event.setCancelled(true);
        if (event.getHand() == EquipmentSlot.HAND) use(event.getPlayer(), event.getPlayer().getInventory().getItemInMainHand(), true, false);
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void interactAtEntity(PlayerInteractAtEntityEvent event) { interactEntity(event); }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void manipulateArmorStand(PlayerArmorStandManipulateEvent event) { interactEntity(event); }

    @EventHandler(priority = EventPriority.LOWEST)
    public void command(PlayerCommandPreprocessEvent event) {
        Player player = event.getPlayer();
        Visit visit = visits.get(player.getUniqueId());
        if (visit == null) return;
        String command = event.getMessage().strip();
        boolean exit = command.equalsIgnoreCase("/hub") || command.equalsIgnoreCase("/lobby") || command.equalsIgnoreCase("/replayexit");
        event.setCancelled(true);
        if (exit) leave(player, visit, true, false);
        else tell(player, "Use Exit Replay or /hub before running other commands.", NamedTextColor.YELLOW);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void teleport(PlayerTeleportEvent event) {
        Player player = event.getPlayer();
        Location to = event.getTo();
        Visit visit = visits.get(player.getUniqueId());
        if (to == null) return;
        if (isReplayWorld(to.getWorld())) {
            if (visit == null || visit.presenting == null || visit.leaving || !visit.presenting.owns(to.getWorld()) || !canWatch(player, visit)) {
                event.setCancelled(true);
            }
        } else if (visit != null && !visit.leaving) {
            if (competition.isAuthenticated(player) || !sameBlock(competition.buildReplayFallback(player), to)) {
                event.setCancelled(true);
            }
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void portal(PlayerPortalEvent event) {
        if (protectedInventory(event.getPlayer())) event.setCancelled(true);
        else teleport(event);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void limitTravel(PlayerMoveEvent event) {
        Visit visit = visits.get(event.getPlayer().getUniqueId());
        if (visit != null && !visit.leaving && visit.stage.owns(event.getFrom().getWorld())
                && event.getTo() != null && event.hasChangedPosition() && !visit.stage.allowsMovement(event.getTo())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void moved(PlayerMoveEvent event) {
        Request request = loading.get(event.getPlayer().getUniqueId());
        if (request != null && !sameBlock(request.origin, event.getTo())) cancel(request, true);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void teleported(PlayerTeleportEvent event) {
        Request request = loading.get(event.getPlayer().getUniqueId());
        if (request != null) cancel(request, true);
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void changedWorld(PlayerChangedWorldEvent event) {
        Player player = event.getPlayer();
        Request request = loading.get(player.getUniqueId());
        if (request != null) cancel(request, true);
        Visit visit = visits.get(player.getUniqueId());
        if (visit != null && !visit.leaving && !visit.owns(player.getWorld())) leave(player, visit, false, false);
        else if (visit == null && isReplayWorld(player.getWorld())) {
            Bukkit.getScheduler().runTask(plugin, () -> {
                if (player.isOnline() && isReplayWorld(player.getWorld()) && !contains(player)
                        && !player.teleport(competition.buildReplayFallback(player))) {
                    player.kick(Component.text("This build replay is private."));
                }
            });
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void spawn(AsyncPlayerSpawnLocationEvent event) {
        Location fallback = loginFallback;
        if (fallback != null && isReplayWorld(event.getSpawnLocation().getWorld())) event.setSpawnLocation(fallback);
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void join(PlayerJoinEvent event) { detectRecovery(event.getPlayer(), true); }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void respawn(PlayerRespawnEvent event) {
        if (isReplayWorld(event.getRespawnLocation().getWorld())) event.setRespawnLocation(competition.buildReplayFallback(event.getPlayer()));
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void quit(PlayerQuitEvent event) {
        Player player = event.getPlayer();
        UUID id = player.getUniqueId();
        Request request = loading.get(id);
        if (request != null) cancel(request, false);
        Visit visit = visits.get(id);
        if (visit != null) leave(player, visit, true, true);
        recovering.remove(id);
        restoredInMemory.remove(id);
    }

    @EventHandler(priority = EventPriority.HIGHEST) public void spectate(PlayerStartSpectatingEntityEvent e) {
        if (protectedInventory(e.getPlayer()) || isReplayWorld(e.getNewSpectatorTarget().getWorld())) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void gameMode(PlayerGameModeChangeEvent e) {
        Visit visit = visits.get(e.getPlayer().getUniqueId());
        if (visit != null && !visit.leaving && e.getNewGameMode() != GameMode.ADVENTURE) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void click(InventoryClickEvent e) {
        if (e.getWhoClicked() instanceof Player p && protectedInventory(p)) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void drag(InventoryDragEvent e) {
        if (e.getWhoClicked() instanceof Player p && protectedInventory(p)) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void inventory(InventoryOpenEvent e) {
        if (e.getPlayer() instanceof Player p && protectedInventory(p)) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void drop(PlayerDropItemEvent e) { if (protectedInventory(e.getPlayer())) e.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void swap(PlayerSwapHandItemsEvent e) { if (protectedInventory(e.getPlayer())) e.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void pickup(EntityPickupItemEvent e) { if (e.getEntity() instanceof Player p && protectedInventory(p)) e.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void experience(PlayerPickupExperienceEvent e) { if (protectedInventory(e.getPlayer())) e.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void hunger(FoodLevelChangeEvent e) {
        if (e.getEntity() instanceof Player p && contains(p)) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void damage(EntityDamageEvent e) {
        if (isReplayWorld(e.getEntity().getWorld()) || e instanceof EntityDamageByEntityEvent by && by.getDamager() instanceof Player p && contains(p)) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void mount(EntityMountEvent e) {
        if (e.getEntity() instanceof Player p && protectedInventory(p)) e.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void breakBlock(BlockBreakEvent e) { if (protectedInventory(e.getPlayer())) e.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void placeBlock(BlockPlaceEvent e) { if (protectedInventory(e.getPlayer())) e.setCancelled(true); }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        if (ticker != null) ticker.cancel();
        for (Request request : List.copyOf(loading.values())) cancel(request, false);
        for (var entry : List.copyOf(visits.entrySet())) {
            Player player = Bukkit.getPlayer(entry.getKey());
            if (player != null) leave(player, entry.getValue(), true, false);
            else if (visits.remove(entry.getKey(), entry.getValue())) dispose(entry.getValue());
        }
        recovering.clear();
        restoredInMemory.clear();
        HandlerList.unregisterAll(this);
    }

    private enum Control { SKIP_BACK, REVERSE, PAUSE, FORWARD, SKIP_AHEAD, SLOWER, FASTER, INFO, EXIT }

    private static final class Request {
        final Player viewer;
        final UUID profile;
        final String identity;
        final Location origin;
        final int started = Bukkit.getCurrentTick();
        boolean pinned;

        Request(Player viewer, UUID profile, String identity, Location origin) {
            this.viewer = viewer;
            this.profile = profile;
            this.identity = identity;
            this.origin = origin;
        }
    }

    private enum ChapterMove { PLAY, SELECT, SEEK }

    private record Chapter(int index, int started, ChapterMove move, int step, long remaining) { }

    private static final class Visit {
        final UUID profile;
        final String identity;
        BuildTape tape;
        ReplayStage stage;
        ReplayStage incoming;
        ReplayStage presenting;
        Chapter chapter;
        final RecoveryPlayerState state;
        final String token = UUID.randomUUID().toString();
        int interval = 1;
        int speed = 2;
        int direction = 1;
        int halfMillis;
        int lastLeftTick = Bukkit.getCurrentTick() - 2;
        int lastRightTick = Bukkit.getCurrentTick() - 2;
        long time;
        boolean swingQueued;
        boolean leaving;

        boolean owns(World world) { return stage.owns(world) || incoming != null && incoming.owns(world); }

        Visit(UUID profile, String identity, BuildTape tape, ReplayStage stage, RecoveryPlayerState state) {
            this.profile = profile;
            this.identity = identity;
            this.tape = tape;
            this.stage = stage;
            this.state = state;
        }
    }
}
