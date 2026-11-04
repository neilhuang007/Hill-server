package org.thehill.hill175.gallery;

import org.bukkit.Bukkit;
import org.bukkit.Chunk;
import org.bukkit.ChunkSnapshot;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Entry;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

/** Bounded main-thread snapshots followed by a single off-thread image renderer. */
public final class CameraCaptureService implements AutoCloseable {
    private static final int maxPendingCaptures = 24;
    private final JavaPlugin plugin;
    private final EntryGalleryPublisher publisher;
    private final ExecutorService renderer;
    private final ArrayDeque<CaptureJob> queue = new ArrayDeque<>();
    private final Map<CameraKey, CaptureJob> latest = new HashMap<>();
    private final Map<CameraKey, Status> statuses = new HashMap<>();
    private final AtomicReference<Path> renderingFile = new AtomicReference<>();
    private BukkitTask driver;
    private int[] colors;
    private CaptureJob active;
    private volatile boolean isClosed;

    public CameraCaptureService(JavaPlugin plugin, EntryGalleryPublisher publisher) {
        this.plugin = plugin;
        this.publisher = publisher;
        this.renderer = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "Hill175-camera-renderer");
            thread.setDaemon(true);
            return thread;
        });
    }

    public boolean capture(Entry entry, int slot, Consumer<Result> callback) {
        if (isClosed || entry.cameraPose(slot).isEmpty() || queue.size() >= maxPendingCaptures) {
            return false;
        }
        if (driver == null) {
            driver = Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 1, 1);
        }
        CameraKey key = new CameraKey(entry.id(), slot);
        CaptureJob job = new CaptureJob(key, entry, entry.cameraPose(slot).orElseThrow(), callback);
        latest.put(key, job);
        queue.removeIf(queued -> queued.key.equals(key));
        queue.add(job);
        statuses.put(key, Status.QUEUED);
        return true;
    }

    public Status status(Entry entry, int slot) {
        return statuses.getOrDefault(new CameraKey(entry.id(), slot),
                publisher.hasImage(entry, slot) ? Status.READY : Status.MISSING);
    }

    public void cancel(UUID entryId) {
        latest.keySet().removeIf(key -> key.entryId().equals(entryId));
        statuses.keySet().removeIf(key -> key.entryId().equals(entryId));
        queue.removeIf(job -> job.key.entryId().equals(entryId));
    }

    public void cancel(UUID entryId, int slot) {
        CameraKey key = new CameraKey(entryId, slot);
        latest.remove(key);
        statuses.remove(key);
        queue.removeIf(job -> job.key.equals(key));
    }

    private void tick() {
        if (isClosed) {
            return;
        }
        if (active == null) {
            beginNext();
            return;
        }
        if (!isCurrent(active) && active.rendered == null) {
            finish(active, Result.failure("This camera capture was replaced."));
            return;
        }
        if (active.rendered != null) {
            finishRendering(active);
            return;
        }
        if (System.nanoTime() - active.startedAt > Duration.ofSeconds(60).toNanos()) {
            finish(active, Result.failure("Camera capture timed out; try saving the view again."));
            return;
        }
        captureNextChunk(active);
    }

    private void beginNext() {
        CaptureJob next = queue.poll();
        if (next == null) {
            return;
        }
        active = next;
        next.startedAt = System.nanoTime();
        if (!isCurrent(next)) {
            finish(next, Result.failure("This camera capture was replaced."));
            return;
        }
        World world = Bukkit.getWorld(next.pose.worldName());
        if (world == null) {
            finish(next, Result.failure("The build world is not available; reopen the entry and retry."));
            return;
        }
        if (colors == null) {
            colors = createPalette();
        }
        next.minY = world.getMinHeight();
        next.maxY = world.getMaxHeight();
        next.coordinates.addAll(chunkCoordinates(next.entry.region(), next.pose));
        statuses.put(next.key, Status.CAPTURING);
    }

    private void captureNextChunk(CaptureJob job) {
        try {
            if (job.loading != null && !job.loading.isDone()) {
                return;
            }
            if (job.loading != null) {
                Chunk chunk = job.loading.join();
                if (chunk != null) {
                    job.snapshots.put(chunkKey(chunk.getX(), chunk.getZ()), chunk.getChunkSnapshot(false, false, false));
                }
                job.loading = null;
            }
            ChunkCoordinate coordinate = job.coordinates.poll();
            if (coordinate == null) {
                beginRendering(job);
                return;
            }
            World world = Bukkit.getWorld(job.pose.worldName());
            if (world == null) {
                throw new IllegalStateException("The build world was unloaded during capture.");
            }
            job.loading = world.getChunkAtAsync(coordinate.x(), coordinate.z(), false);
        } catch (RuntimeException exception) {
            failCapture(job, exception);
        }
    }

    private void beginRendering(CaptureJob job) {
        statuses.put(job.key, Status.RENDERING);
        try {
            Path output = publisher.createRenderFile();
            SnapshotScene scene = new SnapshotScene(job.entry.region(), Map.copyOf(job.snapshots), colors, job.minY, job.maxY);
            job.rendered = CompletableFuture.supplyAsync(() -> render(scene, job.pose, output), renderer);
        } catch (IOException | RuntimeException exception) {
            failCapture(job, exception);
        }
    }

    private RenderResult render(SnapshotScene scene, CameraPose pose, Path output) {
        renderingFile.set(output);
        try {
            new VoxelPerspectiveRenderer().render(scene, pose, output);
            if (isClosed) {
                Files.deleteIfExists(output);
                return new RenderResult(null, new IOException("Camera service stopped."));
            }
            return new RenderResult(output, null);
        } catch (IOException | RuntimeException exception) {
            deleteTemporary(output);
            return new RenderResult(null, exception);
        } finally {
            renderingFile.compareAndSet(output, null);
        }
    }

    private void finishRendering(CaptureJob job) {
        if (!job.rendered.isDone()) {
            return;
        }
        RenderResult rendered = job.rendered.join();
        if (!isCurrent(job)) {
            deleteTemporary(rendered.file());
            finish(job, Result.failure("This camera capture was replaced."));
            return;
        }
        if (rendered.error() != null) {
            failCapture(job, rendered.error());
            return;
        }
        try {
            publisher.acceptImage(job.entry, job.key.slot(), job.pose, rendered.file());
            finish(job, Result.success());
        } catch (IOException exception) {
            deleteTemporary(rendered.file());
            failCapture(job, exception);
        }
    }

    private boolean isCurrent(CaptureJob job) {
        return latest.get(job.key) == job && job.entry.cameraPose(job.key.slot()).filter(job.pose::equals).isPresent();
    }

    private void failCapture(CaptureJob job, Exception exception) {
        plugin.getLogger().log(java.util.logging.Level.WARNING, "Camera image generation failed for entry " + job.key.entryId(), exception);
        finish(job, Result.failure("The image could not be generated. Save the camera again to retry."));
    }

    private void finish(CaptureJob job, Result result) {
        if (latest.get(job.key) == job) {
            statuses.put(job.key, result.isSuccess() ? Status.READY : Status.FAILED);
            latest.remove(job.key);
        }
        if (active == job) {
            active = null;
        }
        try {
            job.callback.accept(result);
        } catch (RuntimeException exception) {
            plugin.getLogger().log(java.util.logging.Level.SEVERE, "Camera completion action failed", exception);
        }
    }

    @Override
    public void close() {
        isClosed = true;
        if (driver != null) driver.cancel();
        queue.clear();
        latest.clear();
        renderer.shutdownNow();
        if (active != null && active.rendered != null && active.rendered.isDone()) {
            deleteTemporary(active.rendered.join().file());
        }
        deleteTemporary(renderingFile.get());
        active = null;
    }

    private static int[] createPalette() {
        int[] palette = new int[Material.values().length];
        for (Material material : Material.values()) {
            if (!material.isBlock() || material.isLegacy() || material.isAir()) {
                continue;
            }
            int color = material.createBlockData().getMapColor().asRGB();
            palette[material.ordinal()] = 0xff000000 | (color == 0 ? fallbackColor(material) : color);
        }
        return palette;
    }

    private static int fallbackColor(Material material) {
        String name = material.name();
        if (name.contains("GLASS")) return 0xb5d4db;
        if (name.contains("LEAVES") || name.contains("GRASS")) return 0x527c35;
        if (name.contains("WATER")) return 0x3d6ca8;
        return 0x969286;
    }

    private static List<ChunkCoordinate> chunkCoordinates(BuildRegion region, CameraPose pose) {
        int range = VoxelPerspectiveRenderer.viewDistance;
        int minX = Math.max(region.minX(), (int) Math.floor(pose.x()) - range) >> 4;
        int maxX = Math.min(region.maxX(), (int) Math.floor(pose.x()) + range) >> 4;
        int minZ = Math.max(region.minZ(), (int) Math.floor(pose.z()) - range) >> 4;
        int maxZ = Math.min(region.maxZ(), (int) Math.floor(pose.z()) + range) >> 4;
        List<ChunkCoordinate> coordinates = new ArrayList<>();
        for (int x = minX; x <= maxX; x++) {
            for (int z = minZ; z <= maxZ; z++) {
                coordinates.add(new ChunkCoordinate(x, z));
            }
        }
        return coordinates;
    }

    private static long chunkKey(int x, int z) {
        return (long) x << 32 | (z & 0xffffffffL);
    }

    private static void deleteTemporary(Path path) {
        if (path == null) return;
        try { Files.deleteIfExists(path); } catch (IOException ignored) { }
    }

    public enum Status { MISSING, QUEUED, CAPTURING, RENDERING, READY, FAILED }

    public record Result(boolean isSuccess, String message) {
        static Result success() { return new Result(true, "Image ready."); }
        static Result failure(String message) { return new Result(false, message); }
    }

    private record CameraKey(UUID entryId, int slot) { }
    private record ChunkCoordinate(int x, int z) { }
    private record RenderResult(Path file, Exception error) { }

    private static final class CaptureJob {
        private final CameraKey key;
        private final Entry entry;
        private final CameraPose pose;
        private final Consumer<Result> callback;
        private final ArrayDeque<ChunkCoordinate> coordinates = new ArrayDeque<>();
        private final Map<Long, ChunkSnapshot> snapshots = new HashMap<>();
        private CompletableFuture<Chunk> loading;
        private CompletableFuture<RenderResult> rendered;
        private int minY;
        private int maxY;
        private long startedAt;

        private CaptureJob(CameraKey key, Entry entry, CameraPose pose, Consumer<Result> callback) {
            this.key = key; this.entry = entry; this.pose = pose; this.callback = callback;
        }
    }

    private record SnapshotScene(BuildRegion region, Map<Long, ChunkSnapshot> chunks, int[] colors,
                                 int minY, int maxY) implements VoxelPerspectiveRenderer.Scene {
        @Override
        public int colorAt(int x, int y, int z) {
            if (y < minY || y >= maxY || !region.contains(x, y, z)) return 0;
            ChunkSnapshot snapshot = chunks.get(chunkKey(x >> 4, z >> 4));
            return snapshot == null ? 0 : colors[snapshot.getBlockType(x & 15, y, z & 15).ordinal()];
        }
    }
}
