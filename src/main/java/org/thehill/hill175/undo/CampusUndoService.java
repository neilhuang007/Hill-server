package org.thehill.hill175.undo;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.Bisected;
import org.bukkit.block.data.Directional;
import org.bukkit.block.data.Openable;
import org.bukkit.block.data.Powerable;
import org.bukkit.block.data.type.Bed;
import org.bukkit.block.data.type.Door;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.*;
import org.bukkit.event.entity.EntityChangeBlockEvent;
import org.bukkit.event.entity.EntityExplodeEvent;
import org.bukkit.event.player.*;
import org.bukkit.event.world.StructureGrowEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.BiPredicate;
import java.util.function.LongSupplier;
import java.util.function.Predicate;

/** Best effort local building undo. It never rolls back a world, inventory, or another actor. */
public final class CampusUndoService implements Listener, AutoCloseable {
    private static final int maximumPending = 2048;
    private static final int maximumBatchBlocks = 16;
    private static final String exclusions = "Fluids, waterlogged or falling blocks, containers, other block entities, "
            + "and item interactions are not included in Undo.";
    private final JavaPlugin plugin;
    private final BiPredicate<Player, Location> mayBuild;
    private final Predicate<World> sharedCampus;
    private final LongSupplier clock;
    private final UndoHistory<BlockSnapshot> history;
    private final List<Pending> pending = new ArrayList<>();
    private final Map<UUID, Player> requests = new LinkedHashMap<>();
    private final Map<UUID, Job> jobs = new LinkedHashMap<>();
    private final Map<UUID, Long> unsupported = new HashMap<>();
    private final BukkitTask ticker;
    private boolean replaying;
    private boolean closed;
    private int ticks;

    public CampusUndoService(JavaPlugin plugin, BiPredicate<Player, Location> mayBuild, Predicate<World> sharedCampus) {
        this(plugin, mayBuild, sharedCampus, System::currentTimeMillis);
    }

    CampusUndoService(JavaPlugin plugin, BiPredicate<Player, Location> mayBuild,
                      Predicate<World> sharedCampus, LongSupplier clock) {
        this.plugin = Objects.requireNonNull(plugin);
        this.mayBuild = Objects.requireNonNull(mayBuild);
        this.sharedCampus = Objects.requireNonNull(sharedCampus);
        this.clock = Objects.requireNonNull(clock);
        this.history = new UndoHistory<>(clock);
        this.ticker = plugin.getServer().getScheduler().runTaskTimer(plugin, this::tick, 1L, 1L);
    }

    /** Queues a main thread undo, allowing the current vanilla placement to finish first. */
    public void undo(Player player) {
        requireMainThread();
        if (closed || !eligible(player, player.getLocation())) {
            tell(player, "Undo is available while building in the shared campus in Creative mode.");
            return;
        }
        UUID actor = player.getUniqueId();
        if (requests.containsKey(actor) || jobs.containsKey(actor)) {
            tell(player, "Your building undo is already running.");
            return;
        }
        requests.put(actor, player);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlace(BlockPlaceEvent event) {
        if (event.isCancelled() || event instanceof BlockMultiPlaceEvent) return;
        record(event.getPlayer(), List.of(event.getBlockReplacedState()), false);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onMultiPlace(BlockMultiPlaceEvent event) {
        if (!event.isCancelled()) record(event.getPlayer(), event.getReplacedBlockStates(), false);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent event) {
        if (!event.isCancelled()) record(event.getPlayer(), related(event.getBlock()), true);
    }

    private void record(Player player, List<BlockState> states, boolean breaking) {
        if (closed || replaying || states.isEmpty() || !sharedCampus.test(states.getFirst().getWorld())) return;
        requireMainThread();
        List<UndoHistory.Point> points = states.stream().map(state -> point(state.getLocation())).toList();
        Map<UndoHistory.Point, UndoHistory.Revision> reserved = history.reserve(points);
        if (states.stream().anyMatch(state -> !eligible(player, state.getLocation()))) return;
        if (states.size() > maximumBatchBlocks || pending.size() >= maximumPending) {
            excluded(player);
            return;
        }
        Map<UndoHistory.Point, BlockSnapshot> before = snapshots(states);
        if (before == null) { excluded(player); return; }
        Map<UndoHistory.Point, String> expected = new LinkedHashMap<>();
        for (BlockState state : states) {
            String data = breaking ? "minecraft:air" : state.getBlock().getBlockData().getAsString();
            expected.put(point(state.getLocation()), data);
        }
        pending.add(new Pending(player.getUniqueId(), clock.getAsLong(), before, expected, reserved));
    }

    private void finish(Pending change) {
        Map<UndoHistory.Point, BlockSnapshot> after = new LinkedHashMap<>();
        for (UndoHistory.Point point : change.before.keySet()) {
            BlockSnapshot snapshot = current(point);
            if (snapshot == null || !snapshot.blockData().equals(change.expected.get(point))) {
                unsupported.put(change.actor, clock.getAsLong());
                return;
            }
            after.put(point, snapshot);
        }
        history.record(change.actor, change.at, change.before, after, change.reserved);
    }

    private void tick() {
        if (closed) return;
        pending.removeIf(change -> { if (--change.remainingTicks > 0) return false; finish(change); return true; });
        requests.entrySet().removeIf(entry -> start(entry.getKey(), entry.getValue()));
        long deadline = System.nanoTime() + 5_000_000;
        for (Job job : List.copyOf(jobs.values())) {
            process(job, deadline);
            if (System.nanoTime() >= deadline) break;
        }
        if (++ticks % 20 == 0) {
            history.prune();
            unsupported.values().removeIf(at -> at < clock.getAsLong() - UndoHistory.windowMillis);
        }
    }

    private boolean start(UUID actor, Player player) {
        if (pending.stream().anyMatch(change -> change.actor.equals(actor))) return false;
        jobs.put(actor, new Job(player, history.beginUndo(actor)));
        return true;
    }

    private void process(Job job, long deadline) {
        int count = 0;
        while (job.session.hasNext() && count++ < 64 && System.nanoTime() < deadline) {
            UndoHistory.Batch<BlockSnapshot> batch = job.session.next();
            if (canRestore(job, batch) && restore(batch, true)) {
                job.session.applied(batch);
                job.restored += batch.edits().size();
            } else job.skipped += batch.edits().size();
        }
        if (!job.session.hasNext()) complete(job);
    }

    private boolean canRestore(Job job, UndoHistory.Batch<BlockSnapshot> batch) {
        if (!job.player.isOnline() || !eligible(job.player, job.player.getLocation())) return false;
        return batch.edits().stream().allMatch(edit -> {
            Location location = location(edit.point());
            return location != null && job.player.getWorld().equals(location.getWorld()) && eligible(job.player, location);
        }) && job.session.canApply(batch, this::current);
    }

    private boolean restore(UndoHistory.Batch<BlockSnapshot> batch, boolean before) {
        replaying = true;
        try {
            for (UndoHistory.Edit<BlockSnapshot> edit : batch.edits()) {
                if (!(before ? edit.before() : edit.after()).restore(location(edit.point()))) {
                    throw new IllegalStateException("Block snapshot could not be restored");
                }
            }
            if (before && batch.edits().stream().anyMatch(edit -> !edit.before().equals(current(edit.point())))) {
                throw new IllegalStateException("Restored block did not match its snapshot");
            }
            return true;
        } catch (RuntimeException exception) {
            if (before) restore(batch, false);
            history.invalidate(batch.edits().stream().map(UndoHistory.Edit::point).toList());
            plugin.getLogger().warning("Campus undo could not restore a block group: " + exception.getMessage());
            return false;
        } finally { replaying = false; }
    }

    private void complete(Job job) {
        UUID actor = job.player.getUniqueId();
        jobs.remove(actor);
        String message = job.restored == 0 ? "No safe building edits to undo from the last 15 seconds."
                : "Undid " + job.restored + " block changes from your last 15 seconds of building.";
        if (job.skipped > 0) message += " Skipped " + job.skipped + " changes that were edited again or are no longer safe.";
        if (job.player.isOnline()) {
            tell(job.player, message);
            Long at = unsupported.remove(actor);
            if (at != null && at >= clock.getAsLong() - UndoHistory.windowMillis) tell(job.player, exclusions);
        }
    }

    private List<BlockState> related(Block block) {
        List<BlockState> states = new ArrayList<>();
        states.add(block.getState());
        BlockFace face = null;
        if (block.getBlockData() instanceof Door door) {
            face = door.getHalf() == Bisected.Half.BOTTOM ? BlockFace.UP : BlockFace.DOWN;
        } else if (block.getBlockData() instanceof Bed bed) {
            face = bed.getPart() == Bed.Part.FOOT ? bed.getFacing() : bed.getFacing().getOppositeFace();
        }
        if (face != null && block.getRelative(face).getType() == block.getType()) states.add(block.getRelative(face).getState());
        return states;
    }

    private Map<UndoHistory.Point, BlockSnapshot> snapshots(List<BlockState> states) {
        Map<UndoHistory.Point, BlockSnapshot> result = new LinkedHashMap<>();
        for (BlockState state : states) {
            BlockSnapshot snapshot = BlockSnapshot.capture(state);
            if (snapshot == null) return null;
            result.put(point(state.getLocation()), snapshot);
        }
        return result;
    }

    private boolean eligible(Player player, Location location) {
        return player.getGameMode() == GameMode.CREATIVE && location.getWorld() != null
                && sharedCampus.test(location.getWorld()) && mayBuild.test(player, location);
    }

    private Location location(UndoHistory.Point point) {
        World world = plugin.getServer().getWorld(point.world());
        if (world == null || !world.isChunkLoaded(point.x() >> 4, point.z() >> 4)) return null;
        return new Location(world, point.x(), point.y(), point.z());
    }

    private BlockSnapshot current(UndoHistory.Point point) {
        Location location = location(point);
        return location == null ? null : BlockSnapshot.capture(location.getBlock().getState());
    }

    private UndoHistory.Point point(Location location) {
        return new UndoHistory.Point(location.getWorld().getUID(), location.getBlockX(), location.getBlockY(), location.getBlockZ());
    }

    private void excluded(Player player) { unsupported.put(player.getUniqueId(), clock.getAsLong()); }
    private void tell(Player player, String message) { player.sendMessage(Component.text(message, NamedTextColor.YELLOW)); }
    private void requireMainThread() {
        if (!plugin.getServer().isPrimaryThread()) throw new IllegalStateException("Campus undo must run on the server thread");
    }

    private void invalidate(Collection<Block> blocks) {
        if (closed || replaying) return;
        history.invalidate(blocks.stream().filter(block -> sharedCampus.test(block.getWorld()))
                .map(block -> point(block.getLocation())).toList());
    }

    private void invalidateStates(Collection<BlockState> states) {
        invalidate(states.stream().map(BlockState::getBlock).toList());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBucketEmpty(PlayerBucketEmptyEvent event) { bucket(event); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBucketFill(PlayerBucketFillEvent event) { bucket(event); }
    private void bucket(PlayerBucketEvent event) {
        if (event.isCancelled()) return;
        invalidate(List.of(event.getBlock(), event.getBlockClicked()));
        if (eligible(event.getPlayer(), event.getBlock().getLocation())) excluded(event.getPlayer());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onInteraction(PlayerInteractEvent event) {
        Block block = event.getClickedBlock();
        if (event.useInteractedBlock() == org.bukkit.event.Event.Result.DENY || block == null
                || event.getAction() != Action.RIGHT_CLICK_BLOCK) return;
        String held = event.getMaterial().name();
        boolean tool = held.endsWith("_AXE") || held.endsWith("_HOE") || held.endsWith("_SHOVEL") || held.equals("HONEYCOMB");
        if (!(block.getBlockData() instanceof Openable) && !(block.getBlockData() instanceof Powerable)
                && !(block.getBlockData() instanceof Bed) && !tool) return;
        invalidateStates(related(block));
        if (eligible(event.getPlayer(), block.getLocation())) excluded(event.getPlayer());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onFlow(BlockFromToEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock(), event.getToBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onForm(BlockFormEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onGrow(BlockGrowEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onFade(BlockFadeEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBurn(BlockBurnEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onDecay(LeavesDecayEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onIgnite(BlockIgniteEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onHarvest(PlayerHarvestBlockEvent event) {
        if (!event.isCancelled()) invalidate(List.of(event.getHarvestedBlock()));
    }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onDispense(BlockDispenseEvent event) {
        if (event.isCancelled()) return;
        Block dispenser = event.getBlock();
        if (dispenser.getBlockData() instanceof Directional facing) {
            invalidate(List.of(dispenser, dispenser.getRelative(facing.getFacing())));
        }
    }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onEntityChange(EntityChangeBlockEvent event) { if (!event.isCancelled()) invalidate(List.of(event.getBlock())); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onFertilize(BlockFertilizeEvent event) { if (!event.isCancelled()) invalidateStates(event.getBlocks()); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onStructure(StructureGrowEvent event) { if (!event.isCancelled()) invalidateStates(event.getBlocks()); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onSponge(SpongeAbsorbEvent event) { if (!event.isCancelled()) invalidateStates(event.getBlocks()); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onExplosion(BlockExplodeEvent event) { if (!event.isCancelled()) invalidate(event.blockList()); }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onEntityExplosion(EntityExplodeEvent event) { if (!event.isCancelled()) invalidate(event.blockList()); }
    @EventHandler(priority = EventPriority.MONITOR)
    public void onRedstone(BlockRedstoneEvent event) {
        if (event.getOldCurrent() != event.getNewCurrent()) invalidate(List.of(event.getBlock()));
    }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onExtend(BlockPistonExtendEvent event) {
        if (!event.isCancelled()) piston(event.getBlock(), event.getBlocks(), event.getDirection());
    }
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onRetract(BlockPistonRetractEvent event) {
        if (!event.isCancelled()) piston(event.getBlock(), event.getBlocks(), event.getDirection());
    }
    private void piston(Block piston, List<Block> moved, BlockFace direction) {
        List<Block> affected = new ArrayList<>(moved);
        affected.add(piston);
        affected.add(piston.getRelative(direction));
        moved.forEach(block -> { affected.add(block.getRelative(direction)); affected.add(block.getRelative(direction.getOppositeFace())); });
        invalidate(affected);
    }

    @EventHandler public void onQuit(PlayerQuitEvent event) {
        UUID actor = event.getPlayer().getUniqueId();
        pending.removeIf(change -> change.actor.equals(actor));
        requests.remove(actor);
        jobs.remove(actor);
        unsupported.remove(actor);
        history.forget(actor);
    }

    @Override public void close() {
        requireMainThread();
        closed = true;
        ticker.cancel();
        pending.clear();
        requests.clear();
        jobs.clear();
        unsupported.clear();
        history.clear();
    }

    private static final class Pending {
        private final UUID actor;
        private final long at;
        private final Map<UndoHistory.Point, BlockSnapshot> before;
        private final Map<UndoHistory.Point, String> expected;
        private final Map<UndoHistory.Point, UndoHistory.Revision> reserved;
        private int remainingTicks = 2;
        private Pending(UUID actor, long at, Map<UndoHistory.Point, BlockSnapshot> before,
                        Map<UndoHistory.Point, String> expected, Map<UndoHistory.Point, UndoHistory.Revision> reserved) {
            this.actor = actor; this.at = at; this.before = before; this.expected = expected; this.reserved = reserved;
        }
    }

    private final class Job {
        private final Player player;
        private final UndoHistory<BlockSnapshot>.Session session;
        private int restored;
        private int skipped;
        private Job(Player player, UndoHistory<BlockSnapshot>.Session session) { this.player = player; this.session = session; }
    }
}
