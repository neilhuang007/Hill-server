package org.thehill.hill175.ui;

import io.papermc.paper.datacomponent.DataComponentTypes;
import io.papermc.paper.datacomponent.item.Consumable;
import io.papermc.paper.datacomponent.item.consumable.ItemUseAnimation;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.title.Title;
import org.bukkit.GameMode;
import org.bukkit.Input;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.player.PlayerDropItemEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.player.PlayerSwapHandItemsEvent;
import org.bukkit.event.player.PlayerTeleportEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.PlayerInventory;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.bukkit.util.BoundingBox;
import org.bukkit.util.Vector;
import org.thehill.hill175.blueprint.BlockChange;
import org.thehill.hill175.blueprint.BlockPosition;
import org.thehill.hill175.blueprint.BlueprintOutlines;
import org.thehill.hill175.blueprint.BlueprintOutlines.Tone;
import org.thehill.hill175.blueprint.BlueprintRepository;
import org.thehill.hill175.blueprint.BlueprintReview;
import org.thehill.hill175.blueprint.BlueprintService;
import org.thehill.hill175.blueprint.BlueprintService.CampusConflict;
import org.thehill.hill175.blueprint.ChangeAreas;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Entry;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Hotbar modes for the blueprint. Each mode replaces the hotbar with two or three items, lets the player
 * fly and pass through walls, and puts everything back afterwards.
 * <ul>
 *   <li>Box: right-click Box Corner twice to box a build, then Send.</li>
 *   <li>Fix: Keep Mine or Use Blueprint's where an update overlapped the student's edits.</li>
 *   <li>Review (staff): Accept or Reject each waiting build.</li>
 * </ul>
 */
final class BlueprintStaging implements Listener, AutoCloseable, BlueprintService.PlayerScreens {
    private static final Duration BOX_TIME = Duration.ofMinutes(10);
    private static final long CLICK_GAP = 250_000_000L;
    private static final double PUSH = 0.35;
    private static final String REJECT_REASON = "Not ready yet.";

    private enum Mode { BOX, FIX, REVIEW, VISIT, ROLLBACK }

    private enum Tool {
        CORNER(Mode.BOX, 0, Material.LIME_CONCRETE, "Box Corner", NamedTextColor.GREEN,
                "Fly to one corner of your build and right-click, then fly to the opposite corner and right-click."),
        SEND(Mode.BOX, 1, Material.LIME_DYE, "Send", NamedTextColor.GREEN, "Right-click: send what is inside your box for approval."),
        CANCEL(Mode.BOX, 8, Material.BARRIER, "Cancel", NamedTextColor.RED, "Right-click: stop without sending anything."),
        KEEP(Mode.FIX, 0, Material.LIME_DYE, "Keep Mine", NamedTextColor.GREEN, "Right-click: keep your blocks in the pink box."),
        TAKE(Mode.FIX, 1, Material.LIGHT_BLUE_DYE, "Use Blueprint's", NamedTextColor.AQUA, "Right-click: switch them to the shared blueprint's blocks."),
        LATER(Mode.FIX, 8, Material.BARRIER, "Finish Later", NamedTextColor.RED, "Right-click: stop for now."),
        ACCEPT(Mode.REVIEW, 0, Material.LIME_DYE, "Accept", NamedTextColor.GREEN, "Right-click: add this build to the shared blueprint."),
        REJECT(Mode.REVIEW, 1, Material.RED_DYE, "Reject", NamedTextColor.RED, "Right-click: send it back so the student can improve it."),
        LEAVE(Mode.VISIT, 8, Material.BARRIER, "Leave the Blueprint", NamedTextColor.RED, "Right-click: go back to where you were."),
        ROLL_BACK(Mode.ROLLBACK, 0, Material.LIME_DYE, "Roll Back to This", NamedTextColor.GREEN,
                "Right-click: make the shared blueprint look like this version again."),
        KEEP_CURRENT(Mode.ROLLBACK, 1, Material.BARRIER, "Cancel", NamedTextColor.RED, "Right-click: leave without changing anything.");

        final Mode mode;
        final int slot;
        final Material material;
        final String label;
        final NamedTextColor color;
        final String hint;

        Tool(Mode mode, int slot, Material material, String label, NamedTextColor color, String hint) {
            this.mode = mode;
            this.slot = slot;
            this.material = material;
            this.label = label;
            this.color = color;
            this.hint = hint;
        }
    }

    private static final class Session {
        final Mode mode;
        final String identity;
        final ItemStack[] inventory;
        final int heldSlot;
        final GameMode gameMode;
        final boolean allowFlight;
        final boolean flying;
        final boolean invulnerable;
        final Location start;
        World world;
        BlueprintService.Snapshot snapshot;
        BlockPosition first;
        BlockPosition second;
        Map<BlockPosition, CampusConflict> conflicts = Map.of();
        List<ChangeAreas.Area> areas = List.of();
        int area;
        BlueprintReview.Shown shown;
        long revision;

        Session(Player player, Mode mode, String identity) {
            this.mode = mode;
            this.identity = identity;
            PlayerInventory items = player.getInventory();
            inventory = Arrays.stream(items.getContents()).map(item -> item == null ? null : item.clone()).toArray(ItemStack[]::new);
            heldSlot = items.getHeldItemSlot();
            gameMode = player.getGameMode();
            allowFlight = player.getAllowFlight();
            flying = player.isFlying();
            invulnerable = player.isInvulnerable();
            start = player.getLocation();
        }
    }

    private final JavaPlugin plugin;
    private final BlueprintService blueprint;
    private final CompetitionModule competition;
    private final BlueprintOutlines outlines;
    private final NamespacedKey key;
    private final Map<UUID, Session> sessions = new HashMap<>();
    private final Map<UUID, Long> lastClick = new HashMap<>();
    private final BukkitTask ticker;
    private final BukkitTask phaser;
    private int ticks;

    BlueprintStaging(JavaPlugin plugin, BlueprintService blueprint, CompetitionModule competition) {
        this.plugin = plugin;
        this.blueprint = blueprint;
        this.competition = competition;
        this.outlines = blueprint.outlines();
        key = new NamespacedKey(plugin, "blueprint-tool");
        plugin.getServer().getPluginManager().registerEvents(this, plugin);
        competition.sendingBuild(this::active);
        ticker = plugin.getServer().getScheduler().runTaskTimer(plugin, this::tick, 10L, 10L);
        phaser = plugin.getServer().getScheduler().runTaskTimer(plugin, this::noclip, 2L, 2L);
    }

    boolean active(Player player) { return sessions.containsKey(player.getUniqueId()); }

    // ---------------------------------------------------------------- box and send

    void box(Player p) {
        if (active(p)) { p.sendActionBar(Component.text("Finish what you are doing first.", NamedTextColor.YELLOW)); return; }
        String identity = competition.participantKey(p);
        java.util.concurrent.CompletableFuture<BlueprintService.Snapshot> taking;
        try { taking = blueprint.snapshot(p); }
        catch (RuntimeException exception) {
            if (exception.getMessage() != null && exception.getMessage().startsWith("First choose what to keep")) {
                say(p, NamedTextColor.LIGHT_PURPLE, "The shared blueprint changed some blocks that you also changed. Choose what to keep first.");
                fix(p);
            } else say(p, NamedTextColor.RED, exception.getMessage());
            return;
        }
        taking.whenComplete((snapshot, error) -> {
            if (!p.isOnline() || !competition.isAuthenticated(p) || !competition.participantKey(p).equals(identity) || active(p)) return;
            if (error != null) { say(p, NamedTextColor.RED, error.getMessage()); return; }
            if (snapshot.changes().isEmpty()) { say(p, NamedTextColor.YELLOW, "Nothing new to send. Build something in your campus first."); return; }
            safely(p, () -> {
                World world = campus(p, snapshot.areas().getFirst().center());
                Session s = new Session(p, Mode.BOX, identity);
                s.world = world;
                s.snapshot = snapshot;
                apply(p, s);
                draw(p, s);
                title(p, "Box Your Build", "Fly to a corner and right-click the Box Corner");
                say(p, NamedTextColor.GREEN, "Gray boxes show what you changed. You can fly through walls. Fly to one corner of your build "
                        + "and right-click the Box Corner, then fly to the opposite corner and right-click again.");
            });
        });
    }

    /** Marks the block the player is in, so a corner can be set anywhere, including inside walls. */
    private void corner(Player p, Session s) {
        BlockPosition at = here(p);
        if (s.first == null || s.second != null) {
            s.first = at;
            s.second = null;
            draw(p, s);
            title(p, "First Corner Set", "Fly to the opposite corner and right-click again");
            return;
        }
        s.second = at;
        draw(p, s);
        int inside = inside(s).size();
        title(p, "Box Ready", inside == 0 ? "Nothing you changed is inside. Right-click again to start over" : blocks(inside) + " inside. Right-click Send");
    }

    private static BlockPosition here(Player p) {
        Location feet = p.getLocation();
        return new BlockPosition(feet.getBlockX(), feet.getBlockY(), feet.getBlockZ());
    }

    private void send(Player p, Session s) throws IOException {
        if (s.first == null || s.second == null) { p.sendActionBar(Component.text("Right-click the Box Corner twice first.", NamedTextColor.YELLOW)); return; }
        List<BlockPosition> inside = inside(s);
        if (inside.isEmpty()) { p.sendActionBar(Component.text("Nothing you changed is inside your box.", NamedTextColor.YELLOW)); return; }
        BlueprintService.Snapshot snapshot = s.snapshot;
        ChangeAreas.Area box = box(s, inside);
        BlueprintService.Snapshot boxed = new BlueprintService.Snapshot(snapshot.entryId(), snapshot.author(), snapshot.revision(), snapshot.takenAt(),
                snapshot.changes(), List.of(box));
        String name = "";
        Entry entry = blueprint.overview(p).entry();
        if (entry != null) name = entry.title();
        if (name.isBlank()) name = p.getName() + "'s build";
        try {
            var sent = blueprint.send(p, boxed, Set.of(0), name);
            exit(p, true);
            say(p, NamedTextColor.GREEN, "Sent! \"" + sent.title() + "\" (" + blocks(sent.changes().size()) + ") is waiting for a moderator. Keep building!");
        } catch (IllegalStateException exception) {
            if (exception.getMessage() != null && exception.getMessage().contains("updated after your snapshot")) {
                exit(p, true);
                say(p, NamedTextColor.YELLOW, "The shared blueprint was just updated. Right-click Send My Build again.");
                return;
            }
            throw exception;
        }
    }

    private List<BlockPosition> inside(Session s) {
        int minX = Math.min(s.first.blockX(), s.second.blockX()), maxX = Math.max(s.first.blockX(), s.second.blockX());
        int minY = Math.min(s.first.blockY(), s.second.blockY()), maxY = Math.max(s.first.blockY(), s.second.blockY());
        int minZ = Math.min(s.first.blockZ(), s.second.blockZ()), maxZ = Math.max(s.first.blockZ(), s.second.blockZ());
        return s.snapshot.changes().stream().map(BlockChange::position)
                .filter(at -> at.blockX() >= minX && at.blockX() <= maxX && at.blockY() >= minY && at.blockY() <= maxY && at.blockZ() >= minZ && at.blockZ() <= maxZ)
                .toList();
    }

    private static ChangeAreas.Area box(Session s, List<BlockPosition> inside) {
        return new ChangeAreas.Area(Math.min(s.first.blockX(), s.second.blockX()), Math.min(s.first.blockY(), s.second.blockY()),
                Math.min(s.first.blockZ(), s.second.blockZ()), Math.max(s.first.blockX(), s.second.blockX()),
                Math.max(s.first.blockY(), s.second.blockY()), Math.max(s.first.blockZ(), s.second.blockZ()), inside);
    }

    // ---------------------------------------------------------------- conflicts

    void fix(Player p) {
        if (active(p)) { p.sendActionBar(Component.text("Finish what you are doing first.", NamedTextColor.YELLOW)); return; }
        safely(p, () -> {
            List<CampusConflict> found = blueprint.conflicts(p);
            if (found.isEmpty()) { say(p, NamedTextColor.GREEN, "Nothing to decide. Your campus has no conflicts with the shared blueprint."); return; }
            World world = campus(p, found.getFirst().position());
            Session s = new Session(p, Mode.FIX, competition.participantKey(p));
            s.world = world;
            load(s, found);
            apply(p, s);
            showConflict(p, s);
            say(p, NamedTextColor.LIGHT_PURPLE, "The shared blueprint changed blocks that you also changed. For each pink box, "
                    + "right-click Keep Mine or Use Blueprint's.");
        });
    }

    private void load(Session s, List<CampusConflict> found) {
        s.conflicts = found.stream().collect(Collectors.toMap(CampusConflict::position, conflict -> conflict));
        s.areas = ChangeAreas.of(s.conflicts.keySet());
        s.area = Math.clamp(s.area, 0, s.areas.size() - 1);
    }

    private void showConflict(Player p, Session s) {
        ChangeAreas.Area area = s.areas.get(s.area);
        p.teleport(viewpoint(s.world, area, p.getLocation()));
        p.setFlying(true);
        draw(p, s);
        title(p, "Choose What to Keep", (s.areas.size() == 1 ? "" : (s.area + 1) + " of " + s.areas.size() + " · ") + blocks(area.size()) + " in the pink box");
    }

    private void decide(Player p, Session s, boolean keepMine) throws IOException {
        blueprint.resolve(p, s.areas.get(s.area).positions(), keepMine);
        List<CampusConflict> found = blueprint.conflicts(p);
        if (found.isEmpty()) {
            exit(p, true);
            say(p, NamedTextColor.GREEN, "All decided! Right-click Send My Build whenever you are ready.");
            return;
        }
        load(s, found);
        showConflict(p, s);
    }

    // ---------------------------------------------------------------- staff review

    // ---------------------------------------------------------------- visiting and rolling back

    /** Everyone can fly through the shared blueprint to look at it; nobody can change it this way. */
    @Override
    public void visit(Player p) {
        if (active(p)) exit(p, true);
        safely(p, () -> {
            World world = blueprint.blueprintWorld();
            Session s = new Session(p, Mode.VISIT, competition.participantKey(p));
            s.world = world;
            if (!p.getWorld().equals(world) && !p.teleport(world.getSpawnLocation().clone().add(0.5, 1, 0.5))) {
                throw new IllegalStateException("Could not open the shared blueprint. Try again.");
            }
            apply(p, s);
            title(p, "Shared Blueprint", "Look around · the barrier takes you back");
            say(p, NamedTextColor.AQUA, "This is the shared Hill blueprint that every campus copies. You can fly through it, but not change it.");
        });
    }

    /** Opens a saved version in a temporary world, with Roll Back to This and Cancel in the hotbar. */
    void preview(Player p, long number) {
        if (active(p)) exit(p, true);
        String identity = competition.participantKey(p);
        Session s = new Session(p, Mode.ROLLBACK, identity);
        s.revision = number;
        java.util.concurrent.CompletableFuture<World> opening;
        try { opening = blueprint.openPreview(p, number); }
        catch (RuntimeException exception) { say(p, NamedTextColor.RED, exception.getMessage()); return; }
        say(p, NamedTextColor.GOLD, "Opening " + (number == 0 ? "the original campus" : "update #" + number) + "...");
        opening.whenComplete((world, error) -> {
            if (error != null) { say(p, NamedTextColor.RED, "That version could not be opened: " + error.getMessage()); return; }
            if (!p.isOnline() || active(p) || !competition.isAuthenticated(p) || !competition.participantKey(p).equals(identity)) {
                blueprint.closePreview(world);
                return;
            }
            s.world = world;
            Location at = p.getLocation().clone();
            if (!blueprint.isBlueprint(p.getWorld())) at = world.getSpawnLocation().clone().add(0.5, 1, 0.5);
            at.setWorld(world);
            if (!p.teleport(at)) { blueprint.closePreview(world); say(p, NamedTextColor.RED, "Could not open that version."); return; }
            apply(p, s);
            title(p, number == 0 ? "Original Campus" : "Update #" + number, "Roll back to this version, or cancel");
            say(p, NamedTextColor.GOLD, "You are looking at a saved copy. Nothing here can change. Right-click Roll Back to This to make the "
                    + "shared blueprint look like this again, or Cancel.");
        });
    }

    /** Ends any hotbar mode and returns the player to where they started. */
    void leave(Player p) { exit(p, true); }

    @Override public void menu(Player p) { box(p); }
    @Override public void send(Player p) { box(p); }
    @Override public void conflicts(Player p) { fix(p); }

    @Override
    public void review(Player p) {
        Session current = sessions.get(p.getUniqueId());
        if (current != null && current.mode == Mode.REVIEW) {
            exit(p, true);
            say(p, NamedTextColor.YELLOW, "Review stopped.");
            return;
        }
        if (current != null) exit(p, true);
        safely(p, () -> {
            UUID next = next(null);
            if (next == null) { say(p, NamedTextColor.GREEN, "No builds are waiting for review."); return; }
            Session s = new Session(p, Mode.REVIEW, competition.participantKey(p));
            showRequest(p, s, next);
        });
    }

    private void showRequest(Player p, Session s, UUID request) throws IOException {
        try { s.shown = blueprint.reviewControls().show(p, request); }
        catch (IOException | RuntimeException exception) {
            if (active(p)) exit(p, true);
            throw exception;
        }
        s.world = p.getWorld();
        apply(p, s);
        title(p, s.shown.title(), "by " + s.shown.author() + " · " + blocks(s.shown.blocks())
                + (s.shown.conflicts() > 0 ? " · " + s.shown.conflicts() + " conflicts" : ""));
    }

    private void decideRequest(Player p, Session s, boolean accept) throws IOException {
        UUID request = s.shown.request();
        if (accept) blueprint.approve(p, request, BlueprintService.ConflictChoice.USE_PROPOSAL);
        else {
            blueprint.reject(p, request, REJECT_REASON);
            say(p, NamedTextColor.YELLOW, "Rejected \"" + s.shown.title() + "\". The student can improve it and send it again.");
        }
        advance(p, s, request);
    }

    private void advance(Player p, Session s, UUID after) throws IOException {
        UUID next = next(after);
        if (next == null) {
            exit(p, true);
            say(p, NamedTextColor.GREEN, "That was the last build waiting for review.");
            return;
        }
        showRequest(p, s, next);
    }

    private UUID next(UUID after) throws IOException {
        List<BlueprintRepository.Summary> pending = new ArrayList<>(blueprint.repository().summaries().stream()
                .filter(summary -> summary.status() == BlueprintRepository.Status.PENDING && !summary.id().equals(after)).toList());
        if (pending.isEmpty()) return null;
        return pending.getLast().id();
    }

    // ---------------------------------------------------------------- shared

    /** Saves nothing new; puts the session's items in the hotbar and switches to flying look-only mode. */
    private void apply(Player p, Session s) {
        sessions.put(p.getUniqueId(), s);
        p.closeInventory();
        PlayerInventory inventory = p.getInventory();
        inventory.clear();
        for (Tool tool : Tool.values()) if (tool.mode == s.mode) inventory.setItem(tool.slot, item(tool));
        inventory.setHeldItemSlot(0);
        p.setGameMode(GameMode.ADVENTURE);
        p.setAllowFlight(true);
        p.setFlying(true);
        p.setInvulnerable(true);
    }

    private World campus(Player p, BlockPosition near) {
        if (blueprint.campusWorld(p).isEmpty()) blueprint.goTo(p, near);
        return blueprint.campusWorld(p).orElseThrow(() -> new IllegalStateException("Open your campus first."));
    }

    private void draw(Player p, Session s) {
        List<BlueprintOutlines.Box> drawn = new ArrayList<>();
        switch (s.mode) {
            case BOX -> {
                if (s.first != null) drawn.add(BlueprintOutlines.Box.block(s.first, Tone.CHANGE));
                if (s.second != null) {
                    drawn.add(BlueprintOutlines.Box.block(s.second, Tone.CHANGE));
                    drawn.add(BlueprintOutlines.Box.around(box(s, List.of()), Tone.CHANGE));
                }
                for (ChangeAreas.Area area : s.snapshot.areas()) drawn.add(BlueprintOutlines.Box.around(area, Tone.MUTED));
            }
            case FIX -> {
                ChangeAreas.Area area = s.areas.get(s.area);
                area.positions().stream().limit(24).forEach(position -> drawn.add(BlueprintOutlines.Box.block(position, Tone.CONFLICT)));
                drawn.addFirst(BlueprintOutlines.Box.around(area, Tone.CONFLICT));
                for (int index = 0; index < s.areas.size(); index++) if (index != s.area) drawn.add(BlueprintOutlines.Box.around(s.areas.get(index), Tone.MUTED));
            }
            case REVIEW, VISIT, ROLLBACK -> { return; }
        }
        outlines.show(p, s.world, drawn, BOX_TIME);
    }

    private void use(Player p, Tool tool) throws IOException {
        Session s = sessions.get(p.getUniqueId());
        if (s == null || tool.mode != s.mode || !competition.isAuthenticated(p) || !s.identity.equals(competition.participantKey(p))) {
            stripTools(p);
            return;
        }
        switch (tool) {
            case CORNER -> corner(p, s);
            case SEND -> send(p, s);
            case CANCEL -> { exit(p, true); say(p, NamedTextColor.YELLOW, "Nothing was sent. Your campus is unchanged."); }
            case KEEP -> decide(p, s, true);
            case TAKE -> decide(p, s, false);
            case LATER -> { exit(p, true); say(p, NamedTextColor.YELLOW, "Stopped. Open the Blueprint menu to finish later."); }
            case ACCEPT -> decideRequest(p, s, true);
            case REJECT -> decideRequest(p, s, false);
            case LEAVE -> exit(p, true);
            case ROLL_BACK -> { blueprint.rollback(p, s.revision); exit(p, true); }
            case KEEP_CURRENT -> { exit(p, true); say(p, NamedTextColor.YELLOW, "Nothing was changed."); }
        }
    }

    /** Restores the player's own inventory, game mode and flight, optionally returning them to where they started. */
    void exit(Player p, boolean returnToStart) {
        Session s = sessions.remove(p.getUniqueId());
        if (s == null) return;
        outlines.clear(p);
        if (s.mode == Mode.REVIEW) blueprint.reviewControls().end(p);
        PlayerInventory inventory = p.getInventory();
        inventory.setContents(s.inventory);
        inventory.setHeldItemSlot(s.heldSlot);
        p.setGameMode(s.gameMode);
        p.setAllowFlight(s.allowFlight);
        p.setFlying(s.allowFlight && s.flying);
        p.setInvulnerable(s.invulnerable);
        if (returnToStart) {
            if (s.start.getWorld() != null && plugin.getServer().getWorld(s.start.getWorld().getUID()) != null) p.teleport(s.start);
            competition.refreshMovementMode(p, p.getLocation());
        }
        if (s.mode == Mode.ROLLBACK) blueprint.closePreview(s.world);
    }

    // ---------------------------------------------------------------- flying through walls

    /**
     * Spectator mode passes through blocks but hides the hotbar. Players are switched to spectator while they
     * are inside blocks or pushing into them, and back to flying adventure in open air, where the hotbar works.
     */
    private void noclip() {
        ticks++;
        for (Map.Entry<UUID, Session> entry : List.copyOf(sessions.entrySet())) {
            Player p = plugin.getServer().getPlayer(entry.getKey());
            Session s = entry.getValue();
            if (p == null || s.world == null || !p.getWorld().equals(s.world)) continue;
            BoundingBox body = p.getBoundingBox();
            boolean blocked = s.world.hasCollisionsIn(body) || s.world.hasCollisionsIn(body.clone().shift(push(p)));
            if (blocked && p.getGameMode() != GameMode.SPECTATOR) p.setGameMode(GameMode.SPECTATOR);
            else if (!blocked && p.getGameMode() == GameMode.SPECTATOR) {
                p.setGameMode(GameMode.ADVENTURE);
                p.setAllowFlight(true);
                p.setFlying(true);
            }
            if (s.mode == Mode.BOX && s.first != null && s.second == null && ticks % 2 == 0) {
                BlockPosition at = here(p);
                outlines.sketch(p, new BlueprintOutlines.Box(Math.min(s.first.blockX(), at.blockX()), Math.min(s.first.blockY(), at.blockY()),
                        Math.min(s.first.blockZ(), at.blockZ()), Math.max(s.first.blockX(), at.blockX()), Math.max(s.first.blockY(), at.blockY()),
                        Math.max(s.first.blockZ(), at.blockZ()), Tone.CHANGE));
            }
        }
    }

    /** The direction the player is trying to move, from their movement keys. */
    private static Vector push(Player p) {
        Input input = p.getCurrentInput();
        double yaw = Math.toRadians(p.getLocation().getYaw());
        double forward = (input.isForward() ? 1 : 0) - (input.isBackward() ? 1 : 0);
        double left = (input.isLeft() ? 1 : 0) - (input.isRight() ? 1 : 0);
        Vector move = new Vector(-Math.sin(yaw) * forward + Math.cos(yaw) * left, 0, Math.cos(yaw) * forward + Math.sin(yaw) * left);
        if (move.lengthSquared() > 0) move.normalize().multiply(PUSH);
        if (input.isJump()) move.setY(PUSH);
        else if (input.isSneak()) move.setY(-PUSH);
        return move;
    }

    // ---------------------------------------------------------------- events

    @EventHandler(priority = EventPriority.LOW)
    public void onUse(PlayerInteractEvent event) {
        Tool tool = tool(event.getItem());
        if (tool == null) return;
        event.setCancelled(true);
        if (event.getHand() != EquipmentSlot.HAND || !event.getAction().isRightClick()) return;
        Player p = event.getPlayer();
        long now = System.nanoTime();
        Long last = lastClick.put(p.getUniqueId(), now);
        if (last != null && now - last < CLICK_GAP) return;
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            if (p.isOnline()) safely(p, () -> use(p, tool));
        });
    }

    @EventHandler(priority = EventPriority.LOW)
    public void onPlace(BlockPlaceEvent event) {
        if (tool(event.getItemInHand()) != null) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.LOW)
    public void onDrop(PlayerDropItemEvent event) {
        if (active(event.getPlayer()) || tool(event.getItemDrop().getItemStack()) != null) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.LOW)
    public void onInventoryClick(InventoryClickEvent event) {
        if (event.getWhoClicked() instanceof Player p && active(p)) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.LOW)
    public void onInventoryDrag(InventoryDragEvent event) {
        if (event.getWhoClicked() instanceof Player p && active(p)) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.LOW)
    public void onSwap(PlayerSwapHandItemsEvent event) {
        if (active(event.getPlayer())) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onTeleport(PlayerTeleportEvent event) {
        Session s = sessions.get(event.getPlayer().getUniqueId());
        if (s != null && s.world != null && event.getTo() != null && !s.world.equals(event.getTo().getWorld())) exit(event.getPlayer(), false);
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onQuit(PlayerQuitEvent event) {
        exit(event.getPlayer(), false);
        lastClick.remove(event.getPlayer().getUniqueId());
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) { stripTools(event.getPlayer()); }

    private void tick() {
        for (Map.Entry<UUID, Session> entry : List.copyOf(sessions.entrySet())) {
            Player p = plugin.getServer().getPlayer(entry.getKey());
            if (p == null) { sessions.remove(entry.getKey()); continue; }
            Session s = entry.getValue();
            switch (s.mode) {
                case BOX -> {
                    p.sendActionBar(Component.text(s.first == null ? "Fly to one corner of your build and right-click the Box Corner"
                            : s.second == null ? "Fly to the opposite corner and right-click the Box Corner"
                            : "Box ready · right-click Send · or the Box Corner again to start over", NamedTextColor.GREEN));
                    if (!outlines.showing(p)) draw(p, s);
                }
                case FIX -> {
                    p.sendActionBar(Component.text("Keep Mine or Use Blueprint's for the pink box", NamedTextColor.LIGHT_PURPLE));
                    if (!outlines.showing(p)) draw(p, s);
                }
                case VISIT -> p.sendActionBar(Component.text("Shared blueprint · look only · the barrier takes you back", NamedTextColor.AQUA));
                case ROLLBACK -> p.sendActionBar(Component.text((s.revision == 0 ? "Original campus" : "Update #" + s.revision)
                        + " · lime dye: roll back to this · barrier: cancel", NamedTextColor.GOLD));
                case REVIEW -> {
                    if (s.shown != null && !blueprint.reviewControls().reviewing(p, s.shown.request())) {
                        safely(p, () -> advance(p, s, s.shown.request()));
                        continue;
                    }
                    p.sendActionBar(Component.text("\"" + s.shown.title() + "\" by " + s.shown.author()
                            + (s.shown.areas() > 1 ? " · " + s.shown.areas() + " green boxes" : "") + " · Accept or Reject · /review to stop", NamedTextColor.GOLD));
                }
            }
        }
    }

    // ---------------------------------------------------------------- helpers

    private static void title(Player p, String heading, String detail) {
        p.showTitle(Title.title(Component.text(heading, NamedTextColor.GREEN), Component.text(detail, NamedTextColor.WHITE),
                Title.Times.times(Duration.ofMillis(150), Duration.ofMillis(2500), Duration.ofMillis(400))));
    }

    private static void say(Player p, NamedTextColor color, String message) { p.sendMessage(Component.text(message, color)); }

    private static Location viewpoint(World world, ChangeAreas.Area area, Location from) {
        Vector center = new Vector((area.minX() + area.maxX() + 1) / 2.0, (area.minY() + area.maxY() + 1) / 2.0, (area.minZ() + area.maxZ() + 1) / 2.0);
        double reach = Math.max(area.maxX() - area.minX(), Math.max(area.maxY() - area.minY(), area.maxZ() - area.minZ())) / 2.0 + 2;
        Vector offset = new Vector(from.getX() - center.getX(), 0, from.getZ() - center.getZ());
        if (offset.lengthSquared() < 1) offset = new Vector(0.6, 0, 0.8);
        offset.normalize().multiply(reach + 5);
        Location spot = new Location(world, center.getX() + offset.getX(),
                Math.min(world.getMaxHeight() - 3, center.getY() + reach * 0.5 + 2), center.getZ() + offset.getZ());
        for (int lift = 0; lift < 48 && spot.getY() < world.getMaxHeight() - 3
                && !(spot.getBlock().isPassable() && spot.clone().add(0, 1, 0).getBlock().isPassable()); lift++) spot.add(0, 1, 0);
        spot.setDirection(center.clone().subtract(spot.toVector().add(new Vector(0, 1.62, 0))));
        return spot;
    }

    private ItemStack item(Tool tool) {
        ItemStack item = new ItemStack(tool.material);
        ItemMeta meta = item.getItemMeta();
        meta.displayName(Component.text(tool.label, tool.color).decoration(TextDecoration.ITALIC, false));
        meta.lore(List.of(Component.text(tool.hint, NamedTextColor.GRAY).decoration(TextDecoration.ITALIC, false)));
        meta.getPersistentDataContainer().set(key, PersistentDataType.STRING, tool.name());
        if (tool == Tool.CORNER) meta.setEnchantmentGlintOverride(true);
        item.setItemMeta(meta);
        // Minecraft 26.2 only reports right-clicks in empty air for items with a use behavior; onUse cancels it.
        item.setData(DataComponentTypes.CONSUMABLE, Consumable.consumable()
                .consumeSeconds(60.0F).animation(ItemUseAnimation.NONE).hasConsumeParticles(false));
        return item;
    }

    private Tool tool(ItemStack item) {
        if (item == null || item.getType().isAir() || !item.hasItemMeta()) return null;
        String value = item.getItemMeta().getPersistentDataContainer().get(key, PersistentDataType.STRING);
        if (value == null) return null;
        try { return Tool.valueOf(value); }
        catch (IllegalArgumentException ignored) { return null; }
    }

    private void stripTools(Player p) {
        if (active(p)) return;
        PlayerInventory inventory = p.getInventory();
        for (int slot = 0; slot < inventory.getSize(); slot++) if (tool(inventory.getItem(slot)) != null) inventory.setItem(slot, null);
    }

    private static String blocks(int count) { return count + (count == 1 ? " block" : " blocks"); }

    @FunctionalInterface private interface Action { void run() throws IOException; }

    private static void safely(Player p, Action action) {
        try { action.run(); }
        catch (IOException | RuntimeException exception) {
            String message = exception.getMessage() == null ? "Something went wrong. Try again." : exception.getMessage();
            p.sendMessage(Component.text("Blueprint: " + message, NamedTextColor.RED));
        }
    }

    @Override
    public void close() {
        ticker.cancel();
        phaser.cancel();
        for (UUID id : List.copyOf(sessions.keySet())) {
            Player p = plugin.getServer().getPlayer(id);
            if (p != null) exit(p, true);
        }
        sessions.clear();
        HandlerList.unregisterAll(this);
    }
}
