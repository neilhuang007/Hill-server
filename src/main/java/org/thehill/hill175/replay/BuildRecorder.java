package org.thehill.hill175.replay;

import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.Bisected;
import org.bukkit.block.data.BlockData;
import org.bukkit.block.data.type.Bed;
import org.bukkit.block.data.type.Door;
import org.bukkit.block.data.type.Fence;
import org.bukkit.block.data.type.Stairs;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockMultiPlaceEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.player.PlayerBucketEmptyEvent;
import org.bukkit.event.player.PlayerBucketEvent;
import org.bukkit.event.player.PlayerBucketFillEvent;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.competition.CompetitionModule;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Predicate;
import java.util.logging.Level;

/** Records authenticated gameplay on the server thread and journals immutable batches off-thread. */
public final class BuildRecorder implements Listener, AutoCloseable {
    private static final int SAMPLE_TICKS = 10;
    private static final int FLUSH_TICKS = 40;
    private static final int PRUNE_TICKS = 20 * 60 * 60;
    private static final int WRITER_QUEUE_SIZE = 32;
    private static final long HEARTBEAT_MILLIS = 2_000;
    private static final int BATCH_RECORDS = 2_048;
    private static final int SCENE_RECORDS = 32_768;
    private static final long SCENE_BYTES = 4L * 1024 * 1024;
    private static final long SCENE_MILLIS = Duration.ofHours(2).toMillis();
    private static final int CONTEXT_RADIUS = 48;
    private static final int MAX_SHAPE_NEIGHBORS = 8;
    private static final List<BlockFace> HORIZONTAL = List.of(BlockFace.NORTH, BlockFace.EAST, BlockFace.SOUTH, BlockFace.WEST);

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final Predicate<World> recordWorld;
    private final ReplayStorage storage;
    private final ReplayTerrain terrain;
    private final BuildJournal journal;
    private final ThreadPoolExecutor writer = executor("Hill build replay journal", WRITER_QUEUE_SIZE);
    private final ThreadPoolExecutor reader = executor("Hill build replay reader", 8);
    private final long retentionMillis;
    private final Map<UUID, Active> active = new HashMap<>();
    private final Map<BuildJournal.Scene, Staged> staged = new LinkedHashMap<>();
    private final List<Pending> pending = new ArrayList<>();
    private final Map<UUID, Integer> pins = new ConcurrentHashMap<>();
    private final Set<UUID> protectedScenes = ConcurrentHashMap.newKeySet();
    private final Set<UUID> retiring = new HashSet<>();
    private final AtomicBoolean maintaining = new AtomicBoolean();
    private final AtomicBoolean stopped = new AtomicBoolean();
    private volatile boolean initialized;
    private boolean storageGap;
    private volatile boolean writeFailed;
    private volatile boolean closed;
    private boolean overloaded;
    private BukkitTask ticker;
    private int ticks;
    private int stagedRecords;
    private long sequence;
    private long lastSceneStart;

    public BuildRecorder(JavaPlugin plugin, CompetitionModule competition, Predicate<World> recordWorld) {
        this.plugin = plugin;
        this.competition = competition;
        this.recordWorld = recordWorld;
        this.storage = new ReplayStorage(plugin);
        this.terrain = new ReplayTerrain(plugin, storage);
        this.journal = new BuildJournal(plugin, storage);
        this.retentionMillis = Duration.ofDays(Math.max(1, plugin.getConfig().getInt("build-replay.retention-days", 7))).toMillis();
    }

    public void start() {
        if (closed || ticker != null) throw new IllegalStateException("Build recorder already started or closed");
        writer.execute(() -> {
            try {
                journal.initialize();
                storage.initialize();
                maintain(true, true);
                initialized = true;
            } catch (IOException | RuntimeException exception) { diskFailure(exception); }
        });
        plugin.getServer().getPluginManager().registerEvents(this, plugin);
        ticker = plugin.getServer().getScheduler().runTaskTimer(plugin, this::tick, 1L, 1L);
    }

    /** No disk access: populated once on startup and updated by durable journal writes. */
    public List<BuildTape.Profile> profiles() { return journal.profiles(); }

    /** Keep the scenery of an open or loading replay from being pruned. Balance with {@link #unpin}. */
    public void pin(UUID id) { pins.merge(id, 1, Integer::sum); }

    public void unpin(UUID id) { pins.computeIfPresent(id, (key, count) -> count == 1 ? null : count - 1); }

    public CompletableFuture<BuildTape> load(UUID id) { return load(id, -1); }

    /** Called on the server thread. Window indices are chronological and -1 selects the latest window. */
    public CompletableFuture<BuildTape> load(UUID id, int window) {
        if (window < -1) return CompletableFuture.failedFuture(new IllegalArgumentException("Invalid build replay window"));
        if (closed || ticker == null) return CompletableFuture.failedFuture(new IllegalStateException("Build replays are not running"));
        finishPending(List.of());
        long now = System.nanoTime();
        for (Active scene : active.values()) if (scene.scene.profile().equals(id)) stage(scene, elapsed(scene, now));
        flushBatch();
        pin(id);
        CompletableFuture<BuildJournal.ReadPoint> point = new CompletableFuture<>();
        CompletableFuture<Void> scenery = terrain.flush();
        try {
            writer.execute(() -> {
                try { point.complete(journal.point(id, window)); }
                catch (IOException | RuntimeException exception) { point.completeExceptionally(exception); }
            });
        } catch (RejectedExecutionException exception) {
            point.completeExceptionally(exception);
        }
        return point.thenCombine(scenery, (filePoint, ignored) -> filePoint).thenCompose(filePoint -> {
            CompletableFuture<BuildTape> tape = new CompletableFuture<>();
            try {
                reader.execute(() -> {
                    try { tape.complete(journal.read(filePoint)); }
                    catch (IOException | RuntimeException exception) { tape.completeExceptionally(exception); }
                });
            } catch (RejectedExecutionException exception) {
                tape.completeExceptionally(exception);
            }
            return tape;
        }).whenComplete((tape, failure) -> unpin(id)).copy();
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onJoin(PlayerJoinEvent event) { sync(event.getPlayer()); }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onQuit(PlayerQuitEvent event) {
        finishPending(List.of());
        end(active.remove(event.getPlayer().getUniqueId()));
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onWorldChange(PlayerChangedWorldEvent event) {
        finishPending(List.of());
        sync(event.getPlayer());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlace(BlockPlaceEvent event) {
        List<BlockState> before = event instanceof BlockMultiPlaceEvent multi ? multi.getReplacedBlockStates()
                : List.of(event.getBlockReplacedState());
        finishPending(before);
        if (!event.canBuild()) return;
        EditCapture edit = prepare(event.getPlayer(), event.getBlockPlaced().getWorld());
        if (edit == null) return;
        Map<Block, Boolean> sources = new LinkedHashMap<>();
        for (BlockState state : before) {
            Block block = state.getBlock();
            BlockData replaced = state.getBlockData();
            defer(edit, block, replaced, null);
            sources.put(block, replaced instanceof Stairs || block.getBlockData() instanceof Stairs);
        }
        deferConnections(edit, sources);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent event) {
        finishPending(List.of());
        Block block = event.getBlock();
        EditCapture edit = prepare(event.getPlayer(), block.getWorld());
        if (edit == null) return;
        BlockData data = block.getBlockData();
        defer(edit, block, data, null);
        Map<Block, Boolean> sources = new LinkedHashMap<>();
        sources.put(block, data instanceof Stairs);
        BlockFace face = null;
        if (data instanceof Door door) face = door.getHalf() == Bisected.Half.BOTTOM ? BlockFace.UP : BlockFace.DOWN;
        if (data instanceof Bed bed) face = bed.getPart() == Bed.Part.FOOT ? bed.getFacing() : bed.getFacing().getOppositeFace();
        if (face != null) {
            Block partner = block.getRelative(face);
            if (loaded(partner) && partner.getType() == block.getType()) {
                defer(edit, partner, partner.getBlockData(), null);
                sources.put(partner, false);
            }
        }
        deferConnections(edit, sources);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBucketEmpty(PlayerBucketEmptyEvent event) { bucket(event); }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBucketFill(PlayerBucketFillEvent event) { bucket(event); }

    private void bucket(PlayerBucketEvent event) {
        finishPending(List.of());
        Block block = event.getBlock();
        EditCapture edit = prepare(event.getPlayer(), block.getWorld());
        if (edit == null) return;
        if (loaded(block)) defer(edit, block, block.getBlockData(), null);
        Block clicked = event.getBlockClicked();
        if (!clicked.equals(block) && loaded(clicked)) defer(edit, clicked, clicked.getBlockData(), null);
    }

    /** Called by the campus WorldEdit guard, only for its already-authorized, synchronous edit scope. */
    public EditCapture prepareWorldEdit(Player actor, World world) {
        finishPending(List.of());
        return prepare(actor, world);
    }

    /** Record a successful campus undo or another trusted direct write. The first old state is the baseline. */
    public void changed(Player actor, Block block, String before, String after) {
        EditCapture edit = prepareWorldEdit(actor, block.getWorld());
        if (edit == null) return;
        edit.beforeWrite(block.getX(), block.getZ());
        edit.successful(block.getX(), block.getY(), block.getZ(), before, after);
    }

    private EditCapture prepare(Player actor, World world) {
        Active own = sync(actor);
        if (own == null || !own.world.equals(world)) return null;
        List<Observer> observers = new ArrayList<>();
        observers.add(new Observer(own, true, 0, 0));
        for (Active other : active.values()) {
            if (other == own || !other.world.equals(world) || !other.player.getWorld().equals(world)
                    || !competition.isAuthenticated(other.player)) continue;
            Location position = other.player.getLocation();
            observers.add(new Observer(other, false, position.getX(), position.getZ()));
        }
        return new EditCapture(world, observers);
    }

    /** A short-lived observer set for a Bukkit mutation or one synchronous WorldEdit command. */
    public final class EditCapture {
        private final World world;
        private final List<Observer> observers;
        private final long started = System.nanoTime();
        private final Map<UUID, Set<Long>> captured = new HashMap<>();

        private EditCapture(World world, List<Observer> observers) {
            this.world = world;
            this.observers = observers;
        }

        public void beforeWrite(int x, int z) { beforeWrite(x, z, System.nanoTime()); }

        private void beforeWrite(int x, int z, long now) {
            if (overloaded || stopped.get() || closed) return;
            int cx = x >> 4, cz = z >> 4;
            boolean loaded = world.isChunkLoaded(cx, cz);
            long key = ((long) cx << 32) | Integer.toUnsignedLong(cz);
            for (Observer observer : observers) {
                Active subject = observer.active;
                if (!observer.includes(x, z) || !current(subject)) continue;
                if (rotateIfNeeded(subject, now) && (overloaded || stopped.get())) return;
                UUID scene = subject.scene.id();
                if (loaded && captured.computeIfAbsent(scene, ignored -> new HashSet<>()).add(key)) {
                    terrain.capture(scene, world.getChunkAt(cx, cz, false));
                }
            }
        }

        public void successful(int x, int y, int z, String before, String after) {
            successful(System.nanoTime(), x, y, z, before, after);
        }

        private void successful(long at, int x, int y, int z, String before, String after) {
            if (overloaded || stopped.get() || closed || before.equals(after)) return;
            for (Observer observer : observers) {
                Active scene = observer.active;
                if (observer.includes(x, z) && current(scene)) {
                    long time = elapsed(scene, at);
                    Staged update = stage(scene, time);
                    update.edits.add(new BuildTape.Edit(time, x, y, z, before, after, observer.subject));
                    countRecord(scene, 25L + 3L * (before.length() + after.length()));
                    if (overloaded || stopped.get()) return;
                }
            }
        }
    }

    private void defer(EditCapture edit, Block block, BlockData before, Set<BlockFace> shapeFaces) {
        edit.beforeWrite(block.getX(), block.getZ(), edit.started);
        pending.add(new Pending(edit, block, before, shapeFaces));
    }

    private void deferConnections(EditCapture edit, Map<Block, Boolean> sources) {
        Map<Block, Connection> neighbors = new LinkedHashMap<>();
        sources.forEach((source, staircase) -> {
            for (BlockFace side : HORIZONTAL) {
                Block neighbor = source.getRelative(side);
                if (sources.containsKey(neighbor) || !loaded(neighbor)) continue;
                Connection connection = neighbors.get(neighbor);
                if (connection == null) {
                    if (neighbors.size() >= MAX_SHAPE_NEIGHBORS) continue;
                    BlockData before = neighbor.getBlockData();
                    if (!(before instanceof Fence) && !(staircase && before instanceof Stairs)) continue;
                    connection = new Connection(before, EnumSet.noneOf(BlockFace.class));
                    neighbors.put(neighbor, connection);
                }
                if (connection.before instanceof Fence || staircase) connection.faces.add(side.getOppositeFace());
            }
        });
        neighbors.forEach((block, connection) -> defer(edit, block, connection.before, connection.faces));
    }

    private void finishPending(List<BlockState> replacedByNextPlacement) {
        boolean directChange = false;
        for (Pending change : pending) {
            Block block = change.block;
            if (!loaded(block)) continue;
            BlockData after = null;
            for (BlockState replaced : replacedByNextPlacement) {
                if (block.equals(replaced.getBlock())) {
                    after = replaced.getBlockData();
                    break;
                }
            }
            if (after == null) after = block.getBlockData();
            String beforeState = change.before.getAsString(), afterState = after.getAsString();
            if (beforeState.equals(afterState)) continue;
            if (change.shapeFaces == null) directChange = true;
            else if (!directChange || !connectionOnly(change.before, after, change.shapeFaces)) continue;
            change.edit.successful(change.edit.started, block.getX(), block.getY(), block.getZ(), beforeState, afterState);
        }
        pending.clear();
    }

    private static boolean connectionOnly(BlockData before, BlockData after, Set<BlockFace> faces) {
        if (before.getMaterial() != after.getMaterial()) return false;
        BlockData expected = before.clone();
        if (expected instanceof Fence fence && after instanceof Fence result) {
            for (BlockFace face : faces) fence.setFace(face, result.hasFace(face));
        } else if (!faces.isEmpty() && expected instanceof Stairs stairs && after instanceof Stairs result) {
            stairs.setShape(result.getShape());
        } else return false;
        return expected.getAsString().equals(after.getAsString());
    }

    private static boolean loaded(Block block) {
        return block.getWorld().isChunkLoaded(block.getX() >> 4, block.getZ() >> 4);
    }

    private void tick() {
        boolean newGap = false;
        if (initialized && storage.paused() && !storageGap) {
            storageGap = true;
            newGap = true;
            pending.clear();
            staged.clear();
            stagedRecords = 0;
            endAll();
            flushBatch();
            plugin.getLogger().warning("Build replay capture paused to protect disk space. No active recording or staff viewing session will be pruned.");
        } else if (storageGap && !storage.paused()) {
            storageGap = false;
            plugin.getLogger().info("Build replay storage recovered; recording resumes in new scenes.");
        }
        finishPending(List.of());
        if (++ticks % SAMPLE_TICKS == 0) {
            if (stopped.get()) endAll();
            else {
                if (overloaded && writer.getQueue().remainingCapacity() >= WRITER_QUEUE_SIZE / 2) {
                    overloaded = false;
                    plugin.getLogger().info("Build replay journal recovered; recording is resuming in new scenes.");
                }
                for (Player player : plugin.getServer().getOnlinePlayers()) {
                    Active scene = sync(player);
                    long now = System.nanoTime();
                    if (scene != null && !rotateIfNeeded(scene, now)) sample(scene, player.getLocation(), elapsed(scene, now));
                }
            }
        }
        if (ticks % FLUSH_TICKS == 0) flushBatch();
        if (initialized && (newGap || ticks % 1200 == 0)) scheduleMaintenance(ticks == PRUNE_TICKS, storageGap);
        if (ticks == PRUNE_TICKS) ticks = 0;
    }

    private Active sync(Player player) {
        if (ticker == null || closed || !initialized || storageGap || storage.paused() || overloaded || stopped.get()) return null;
        UUID connection = player.getUniqueId();
        Active scene = active.get(connection);
        World world = player.getWorld();
        if (!recordWorld.test(world) || !competition.isAuthenticated(player)) {
            if (scene != null) end(active.remove(connection));
            return null;
        }
        UUID profile = UUID.nameUUIDFromBytes(("hill175-build-replay:v1:" + competition.participantKey(player)).getBytes(StandardCharsets.UTF_8));
        if (scene != null) {
            if (scene.scene.profile().equals(profile) && scene.world.equals(world)) return scene;
            end(active.remove(connection));
        }
        scene = new Active(player, world);
        active.put(connection, scene);
        begin(scene, profile, System.nanoTime());
        return overloaded || stopped.get() ? null : scene;
    }

    private boolean current(Active scene) { return active.get(scene.player.getUniqueId()) == scene; }

    private void begin(Active scene, UUID profile, long at) {
        lastSceneStart = Math.max(lastSceneStart, System.currentTimeMillis());
        scene.scene = new BuildJournal.Scene(profile, UUID.randomUUID(), scene.player.getName(),
                competition.buildReplayWorldLabel(scene.world), lastSceneStart, sequence++);
        protectedScenes.add(scene.scene.id());
        scene.startedNanos = at;
        scene.lastStaged = 0;
        scene.pose = null;
        scene.records = 0;
        scene.bytes = 8L + 3L * (scene.scene.name().length() + scene.scene.world().length());
        sample(scene, scene.player.getLocation(), 0);
    }

    private boolean rotateIfNeeded(Active scene, long at) {
        long elapsed = elapsed(scene, at);
        if (elapsed < SCENE_MILLIS && scene.records < SCENE_RECORDS && scene.bytes < SCENE_BYTES) return false;
        stage(scene, elapsed);
        retire(scene.scene.id());
        begin(scene, scene.scene.profile(), at);
        return true;
    }

    private void sample(Active scene, Location location, long time) {
        BuildTape.Pose previous = scene.pose;
        if (previous == null || previous.x() != location.getX() || previous.y() != location.getY()
                || previous.z() != location.getZ() || previous.yaw() != location.getYaw() || previous.pitch() != location.getPitch()) {
            BuildTape.Pose pose = new BuildTape.Pose(time, location.getX(), location.getY(), location.getZ(), location.getYaw(), location.getPitch());
            stage(scene, time).poses.add(pose);
            scene.pose = pose;
            countRecord(scene, 40);
        } else if (time - scene.lastStaged >= HEARTBEAT_MILLIS) {
            stage(scene, time);
        }
        if (overloaded || stopped.get()) return;
        int cx = location.getBlockX() >> 4, cz = location.getBlockZ() >> 4;
        for (int x = cx - 1; x <= cx + 1; x++) {
            for (int z = cz - 1; z <= cz + 1; z++) {
                if (scene.world.isChunkLoaded(x, z)) terrain.capture(scene.scene.id(), scene.world.getChunkAt(x, z, false));
            }
        }
    }

    private void end(Active scene) {
        if (scene == null) return;
        if (!overloaded && !stopped.get() && !storage.paused() && !storageGap) stage(scene, elapsed(scene, System.nanoTime()));
        retire(scene.scene.id());
    }

    private void retire(UUID scene) {
        terrain.end(scene);
        retiring.add(scene);
    }

    private void endAll() {
        for (Active scene : active.values()) end(scene);
        active.clear();
    }

    private static long elapsed(Active scene, long at) { return Math.max(0, (at - scene.startedNanos) / 1_000_000); }

    private Staged stage(Active scene, long time) {
        Staged batch = staged.computeIfAbsent(scene.scene, ignored -> {
            scene.bytes += 24;
            return new Staged();
        });
        batch.duration = Math.max(batch.duration, time);
        scene.lastStaged = Math.max(scene.lastStaged, time);
        return batch;
    }

    private void countRecord(Active scene, long bytes) {
        scene.records++;
        scene.bytes += bytes;
        if (++stagedRecords >= BATCH_RECORDS) flushBatch();
    }

    private void flushBatch() {
        if (staged.isEmpty() && retiring.isEmpty()) return;
        List<BuildJournal.Frame> frames = new ArrayList<>(staged.size());
        staged.forEach((scene, contents) -> frames.add(new BuildJournal.Frame(scene, contents.duration,
                List.copyOf(contents.poses), List.copyOf(contents.edits))));
        staged.clear();
        stagedRecords = 0;
        Set<UUID> sealed = Set.copyOf(retiring);
        var scenery = sealed.isEmpty() ? null : terrain.flush();
        try {
            writer.execute(() -> {
                try {
                    if (!writeFailed && !storage.paused()) for (BuildJournal.Frame frame : frames) journal.append(frame);
                } catch (ReplayStorage.Full gap) {
                    return;
                } catch (IOException | RuntimeException exception) {
                    diskFailure(exception);
                } finally {
                    if (scenery != null) scenery.whenComplete((ignored, failure) -> protectedScenes.removeAll(sealed));
                }
            });
            retiring.clear();
        } catch (RejectedExecutionException exception) {
            overloaded = true;
            endAll();
            plugin.getLogger().warning("Build replay journal is backlogged; a recording gap was dropped. Recording will resume when the queue drains.");
        }
    }

    private void scheduleMaintenance(boolean retentionDue, boolean mayResume) {
        if (!maintaining.compareAndSet(false, true)) return;
        try {
            writer.execute(() -> {
                try { maintain(retentionDue, mayResume); }
                catch (IOException | RuntimeException failure) {
                    plugin.getLogger().log(Level.WARNING, "Could not maintain build replay storage.", failure);
                } finally { maintaining.set(false); }
            });
        } catch (RejectedExecutionException busy) { maintaining.set(false); }
    }

    private void maintain(boolean retentionDue, boolean mayResume) throws IOException {
        if (initialized && (retentionDue || mayResume)) storage.recount();
        if (retentionDue || storage.needsPrune()) {
            journal.prune(System.currentTimeMillis() - retentionMillis, protectedScenes, pins::containsKey);
        }
        storage.checkSpace(mayResume);
    }

    private void diskFailure(Exception exception) {
        writeFailed = true;
        stopRecording(exception);
    }

    private void stopRecording(Exception exception) {
        if (stopped.compareAndSet(false, true)) {
            plugin.getLogger().log(Level.SEVERE, "Build replay recording stopped (existing recordings are still available); restart after checking the replay storage", exception);
        }
    }

    @Override
    public void close() {
        if (closed) return;
        if (ticker != null) ticker.cancel();
        HandlerList.unregisterAll(this);
        finishPending(List.of());
        endAll();
        flushBatch();
        closed = true;
        writer.shutdown();
        reader.shutdown();
        terrain.close();
        try {
            if (!writer.awaitTermination(10, TimeUnit.SECONDS)) {
                int lost = writer.shutdownNow().size();
                plugin.getLogger().warning("Build replay journal did not finish shutdown; " + lost + " queued tasks were canceled.");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            writer.shutdownNow();
            plugin.getLogger().warning("Build replay journal shutdown was interrupted.");
        }
    }

    private static ThreadPoolExecutor executor(String name, int queueSize) {
        return new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(queueSize), task -> {
            Thread thread = new Thread(task, name);
            thread.setDaemon(true);
            return thread;
        });
    }

    private static final class Active {
        private final Player player;
        private final World world;
        private BuildJournal.Scene scene;
        private long startedNanos;
        private long lastStaged;
        private long bytes;
        private int records;
        private BuildTape.Pose pose;

        private Active(Player player, World world) {
            this.player = player;
            this.world = world;
        }
    }

    private static final class Staged {
        private long duration;
        private final List<BuildTape.Pose> poses = new ArrayList<>();
        private final List<BuildTape.Edit> edits = new ArrayList<>();
    }

    private record Observer(Active active, boolean subject, double x, double z) {
        private boolean includes(int blockX, int blockZ) {
            if (subject) return true;
            double dx = x - blockX, dz = z - blockZ;
            return dx * dx + dz * dz <= CONTEXT_RADIUS * CONTEXT_RADIUS;
        }
    }
    private record Connection(BlockData before, Set<BlockFace> faces) {}
    private record Pending(EditCapture edit, Block block, BlockData before, Set<BlockFace> shapeFaces) {}
}
