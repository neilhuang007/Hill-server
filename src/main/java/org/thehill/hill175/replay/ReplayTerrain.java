package org.thehill.hill175.replay;

import org.bukkit.Bukkit;
import org.bukkit.Chunk;
import org.bukkit.ChunkSnapshot;
import org.bukkit.block.data.BlockData;
import org.bukkit.generator.ChunkGenerator;
import org.bukkit.generator.WorldInfo;
import org.bukkit.plugin.java.JavaPlugin;
import org.jetbrains.annotations.NotNull;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InterruptedIOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Pattern;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

/** First-seen local scenery for a build-replay segment, not a copy of the live world. */
public final class ReplayTerrain implements AutoCloseable {
    private static final int MAGIC = 0x4852544E;
    private static final int VERSION = 2;
    private static final int MAX_PENDING_CHUNKS = 48;
    private static final int MAX_SECTIONS = 64;
    private static final int SECTION_VOLUME = 4096;
    private static final int MAX_PALETTE = 16_384;
    private static final int MAX_STATE_BYTES = 1024;
    private static final int MAX_PALETTE_BYTES = 2 * 1024 * 1024;
    private static final Pattern SCENERY_FILE = Pattern.compile("-?\\d{1,10}_-?\\d{1,10}\\.bin\\.gz|snapshot-\\d{1,20}\\.tmp");

    private final Path root;
    private final ReplayStorage storage;
    private final Logger logger;
    private final AtomicLong lastWarning = new AtomicLong();
    private final Map<UUID, CaptureScene> captured = new HashMap<>();
    private final ThreadPoolExecutor writer = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(MAX_PENDING_CHUNKS),
            Thread.ofPlatform().daemon(true).name("hill-build-replay-terrain").factory());
    private CompletableFuture<Void> tail = CompletableFuture.completedFuture(null);
    private boolean closed;

    ReplayTerrain(JavaPlugin plugin, ReplayStorage storage) {
        root = root(plugin);
        logger = plugin.getLogger();
        this.storage = storage;
    }

    /** Called on the main thread with an already loaded chunk. Does not retain the live chunk. */
    public synchronized void capture(UUID scene, Chunk chunk) {
        if (closed || storage.paused()) return;
        long key = Chunk.getChunkKey(chunk.getX(), chunk.getZ());
        CaptureScene seen = captured.get(scene);
        if (seen != null && (seen.chunks.contains(key) || seen.chunks.size() >= TerrainPack.MAX_CHUNKS)) return;
        if (writer.getQueue().remainingCapacity() == 0 || chunk.getLoadLevel() == Chunk.LoadLevel.UNLOADED) return;
        int minY = chunk.getWorld().getMinHeight();
        int maxY = chunk.getWorld().getMaxHeight();
        if (!validHeight(minY, maxY)) return;
        try {
            ChunkSnapshot snapshot = chunk.getChunkSnapshot(false, false, false, false);
            CaptureScene active = captured.computeIfAbsent(scene, id -> new CaptureScene(new HashSet<>(), new TerrainPack(root.resolve(id.toString()))));
            Write job = new Write(scene, active, key, snapshot, minY, maxY);
            writer.execute(job);
            active.chunks.add(key);
            tail = job.finished;
        } catch (RuntimeException error) {
            warn(logger, lastWarning, "Could not capture build replay scenery", error);
        }
    }

    /** Release deduplication state; pending snapshots are still saved. A new segment needs a new ID. */
    public synchronized void end(UUID scene) {
        captured.remove(scene);
    }

    /** Waits for writes accepted before this call; missing scenery does not invalidate the edit tape. */
    public synchronized CompletableFuture<Void> flush() {
        return tail.copy();
    }

    @Override
    public void close() {
        synchronized (this) {
            if (!closed) {
                closed = true;
                captured.clear();
                writer.shutdown();
            }
        }
        try {
            if (!writer.awaitTermination(30, TimeUnit.SECONDS)) {
                abortWrites(new IOException("Timed out draining build replay scenery"));
            }
        } catch (InterruptedException error) {
            abortWrites(error);
            Thread.currentThread().interrupt();
        }
    }

    private void abortWrites(Exception error) {
        logger.log(Level.WARNING, "Build replay scenery shutdown did not finish", error);
        for (Runnable job : writer.shutdownNow()) ((Write) job).finished.completeExceptionally(error);
    }

    private record CaptureScene(Set<Long> chunks, TerrainPack pack) { }

    private final class Write implements Runnable {
        final UUID scene;
        final CaptureScene active;
        final long key;
        final ChunkSnapshot snapshot;
        final int minY;
        final int maxY;
        final CompletableFuture<Void> finished = new CompletableFuture<>();

        Write(UUID scene, CaptureScene active, long key, ChunkSnapshot snapshot, int minY, int maxY) {
            this.scene = scene;
            this.active = active;
            this.key = key;
            this.snapshot = snapshot;
            this.minY = minY;
            this.maxY = maxY;
        }

        @Override public void run() {
            try {
                if (storage.paused()) retryable();
                else write(root.resolve(scene.toString()), active.pack, scene, snapshot, minY, maxY);
            } catch (ReplayStorage.Full full) {
                retryable();
            } catch (IOException | RuntimeException error) {
                retryable();
                warn(logger, lastWarning, "Could not save build replay scenery for " + scene, error);
            } finally {
                finished.complete(null);
            }
        }

        private void retryable() {
            synchronized (ReplayTerrain.this) {
                if (captured.get(scene) == active) active.chunks.remove(key);
            }
        }
    }

    /** Creates only the recorded scenery and first-before states in a disposable replay world. */
    public static ChunkGenerator generator(JavaPlugin plugin, UUID scene, Map<BuildTape.BlockPos, String> initial) {
        Map<Long, List<InitialBlock>> byChunk = new HashMap<>();
        initial.forEach((pos, state) -> byChunk.computeIfAbsent(Chunk.getChunkKey(pos.x() >> 4, pos.z() >> 4),
                ignored -> new ArrayList<>()).add(new InitialBlock(pos, state)));
        return new SceneryGenerator(root(plugin).resolve(scene.toString()), scene, byChunk, plugin.getLogger());
    }

    /** Delete scenery for an expired, inactive segment after its writes have drained. */
    static long delete(JavaPlugin plugin, UUID scene, ReplayStorage storage) throws IOException {
        Path folder = root(plugin).resolve(scene.toString());
        requireSafeFolder(folder);
        long bytes = 0;
        try (var files = Files.newDirectoryStream(folder)) {
            for (Path file : files) {
                String name = file.getFileName().toString();
                if (!name.equals(TerrainPack.NAME) && !SCENERY_FILE.matcher(name).matches()) continue;
                try {
                    BasicFileAttributes attributes = Files.readAttributes(file, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                    if (attributes.isRegularFile() && Files.deleteIfExists(file)) bytes += storage.footprint(attributes.size());
                } catch (NoSuchFileException ignored) { }
            }
        } catch (NoSuchFileException ignored) {
            return bytes;
        } catch (DirectoryIteratorException error) {
            throw error.getCause();
        }
        try { Files.deleteIfExists(folder); }
        catch (DirectoryNotEmptyException ignored) { }
        return bytes;
    }

    private static Path root(JavaPlugin plugin) {
        return plugin.getDataFolder().toPath().toAbsolutePath().normalize().resolve("build-replays").resolve("terrain");
    }

    private static Path file(Path folder, int x, int z) {
        return folder.resolve(x + "_" + z + ".bin.gz");
    }

    private static void requireSafeFolder(Path sceneFolder) throws IOException {
        Path replayFolder = sceneFolder.getParent().getParent();
        for (Path path = sceneFolder; !path.equals(replayFolder.getParent()); path = path.getParent()) {
            if (Files.exists(path, LinkOption.NOFOLLOW_LINKS) && !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                throw new IOException("Not a replay scenery directory: " + path);
            }
        }
    }

    private static boolean validHeight(int minY, int maxY) {
        return minY >= -4096 && maxY <= 4096 && minY < maxY && ((minY | maxY) & 15) == 0
                && (maxY - minY) / 16 <= MAX_SECTIONS;
    }

    private void write(Path folder, TerrainPack pack, UUID scene, ChunkSnapshot snapshot, int minY, int maxY) throws IOException {
        requireSafeFolder(folder);
        Path target = file(folder, snapshot.getX(), snapshot.getZ());
        if (Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)) return;
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Invalid scenery file: " + target);
        Map<BlockData, Integer> ids = new HashMap<>();
        List<byte[]> palette = new ArrayList<>();
        List<Section> sections = new ArrayList<>();
        int paletteBytes = 0;
        int[] runs = new int[SECTION_VOLUME];
        for (int section = 0; section < (maxY - minY) / 16; section++) {
            if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Scenery writer interrupted");
            if (snapshot.isSectionEmpty(section)) continue;
            int sectionY = minY + section * 16;
            int runCount = 0;
            int last = -1;
            int start = 0;
            for (int i = 0; i < SECTION_VOLUME; i++) {
                BlockData state = snapshot.getBlockData(i & 15, sectionY + (i >> 8), (i >> 4) & 15);
                Integer id = ids.get(state);
                if (id == null) {
                    if (state.getMaterial().isAir()) {
                        id = 0;
                    } else {
                        byte[] name = state.getAsString().getBytes(StandardCharsets.UTF_8);
                        paletteBytes += name.length;
                        if (name.length == 0 || name.length > MAX_STATE_BYTES || paletteBytes > MAX_PALETTE_BYTES
                                || palette.size() == MAX_PALETTE) throw new IOException("Scenery block palette exceeds its limit");
                        palette.add(name);
                        id = palette.size();
                    }
                    ids.put(state, id);
                }
                if (id != last) {
                    if (i > 0) runs[runCount++] = ((i - start) << 16) | last;
                    last = id;
                    start = i;
                }
            }
            if (start == 0 && last == 0) continue;
            runs[runCount++] = ((SECTION_VOLUME - start) << 16) | last;
            sections.add(new Section(section, Arrays.copyOf(runs, runCount)));
        }
        byte[] encoded = encode(scene, snapshot.getX(), snapshot.getZ(), minY, maxY, palette, sections);
        requireSafeFolder(folder);
        pack.append(storage, snapshot.getX(), snapshot.getZ(), encoded);
    }

    private static byte[] encode(UUID scene, int x, int z, int minY, int maxY, List<byte[]> palette, List<Section> sections) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream(4096);
        try (var out = new DataOutputStream(new BufferedOutputStream(new GZIPOutputStream(bytes)))) {
            out.writeInt(MAGIC);
            out.writeByte(VERSION);
            out.writeLong(scene.getMostSignificantBits());
            out.writeLong(scene.getLeastSignificantBits());
            out.writeInt(x);
            out.writeInt(z);
            out.writeInt(minY);
            out.writeInt(maxY);
            out.writeShort(palette.size());
            for (byte[] state : palette) {
                out.writeShort(state.length);
                out.write(state);
            }
            out.writeShort(sections.size());
            byte[] plane = new byte[SECTION_VOLUME];
            for (Section section : sections) {
                out.writeShort(section.index());
                out.writeShort(section.runs().length);
                int[] runs = section.runs();
                for (int shift = 24; shift >= 0; shift -= 8) {
                    for (int index = 0; index < runs.length; index++) plane[index] = (byte) (runs[index] >>> shift);
                    out.write(plane, 0, runs.length);
                }
            }
        }
        return bytes.toByteArray();
    }

    private static InputStream snapshotStream(Path folder, TerrainPack pack, int x, int z) throws IOException {
        requireSafeFolder(folder);
        InputStream packed = pack.open(x, z);
        if (packed != null) return packed;
        Path legacy = file(folder, x, z);
        BasicFileAttributes attrs = Files.readAttributes(legacy, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!attrs.isRegularFile() || attrs.size() > TerrainPack.MAX_CHUNK_BYTES) throw new IOException("Invalid scenery file size or type");
        return Files.newInputStream(legacy, LinkOption.NOFOLLOW_LINKS);
    }

    private static Terrain read(Path folder, TerrainPack pack, UUID scene, int x, int z) throws IOException {
        try (var raw = snapshotStream(folder, pack, x, z)) {
            try (var in = new DataInputStream(new BufferedInputStream(new GZIPInputStream(raw)))) {
                if (in.readInt() != MAGIC) throw new IOException("Invalid scenery header");
                int version = in.readUnsignedByte();
                if (version < 1 || version > VERSION || in.readLong() != scene.getMostSignificantBits() || in.readLong() != scene.getLeastSignificantBits()
                        || in.readInt() != x || in.readInt() != z) throw new IOException("Invalid scenery header");
                int minY = in.readInt();
                int maxY = in.readInt();
                int paletteSize = in.readUnsignedShort();
                if (!validHeight(minY, maxY) || paletteSize > MAX_PALETTE) throw new IOException("Invalid scenery dimensions or palette");
                String[] palette = new String[paletteSize + 1];
                int paletteBytes = 0;
                for (int i = 1; i <= paletteSize; i++) {
                    int size = in.readUnsignedShort();
                    paletteBytes += size;
                    if (size == 0 || size > MAX_STATE_BYTES || paletteBytes > MAX_PALETTE_BYTES) throw new IOException("Invalid scenery state length");
                    byte[] bytes = in.readNBytes(size);
                    if (bytes.length != size) throw new EOFException("Truncated scenery state");
                    palette[i] = new String(bytes, StandardCharsets.UTF_8);
                }
                int sectionCount = in.readUnsignedShort();
                int maxSections = (maxY - minY) / 16;
                if (sectionCount > maxSections) throw new IOException("Invalid scenery section count");
                List<Section> sections = new ArrayList<>(sectionCount);
                int previous = -1;
                byte[] plane = version == 1 ? null : new byte[SECTION_VOLUME];
                for (int i = 0; i < sectionCount; i++) {
                    int section = in.readUnsignedShort();
                    int count = in.readUnsignedShort();
                    if (section <= previous || section >= maxSections || count == 0 || count > SECTION_VOLUME) {
                        throw new IOException("Invalid scenery section");
                    }
                    previous = section;
                    int[] runs = new int[count];
                    if (version == 1) {
                        for (int index = 0; index < count; index++) runs[index] = in.readInt();
                    } else {
                        for (int shift = 24; shift >= 0; shift -= 8) {
                            in.readFully(plane, 0, count);
                            for (int index = 0; index < count; index++) runs[index] |= (plane[index] & 0xff) << shift;
                        }
                    }
                    int remaining = SECTION_VOLUME;
                    for (int run : runs) {
                        int length = run >>> 16;
                        if (length == 0 || length > remaining || (run & 0xffff) > paletteSize) throw new IOException("Invalid scenery run");
                        remaining -= length;
                    }
                    if (remaining != 0) throw new IOException("Incomplete scenery section");
                    sections.add(new Section(section, runs));
                }
                if (in.read() != -1) throw new IOException("Unexpected trailing scenery data");
                return new Terrain(minY, palette, sections);
            }
        } catch (NoSuchFileException ignored) {
            return null;
        }
    }

    private record Section(int index, int[] runs) { }
    private record Terrain(int minY, String[] palette, List<Section> sections) { }
    private record InitialBlock(BuildTape.BlockPos pos, String state) { }

    private static final class SceneryGenerator extends ChunkGenerator {
        private final Path folder;
        private final TerrainPack pack;
        private final UUID scene;
        private final Map<Long, List<InitialBlock>> byChunk;
        private final Logger logger;
        private final AtomicLong lastWarning = new AtomicLong();

        SceneryGenerator(Path folder, UUID scene, Map<Long, List<InitialBlock>> byChunk, Logger logger) {
            this.folder = folder;
            this.pack = new TerrainPack(folder);
            this.scene = scene;
            this.byChunk = byChunk;
            this.logger = logger;
        }

        @Override public void generateNoise(@NotNull WorldInfo info, @NotNull Random random, int x, int z, @NotNull ChunkData chunk) {
            Terrain terrain = null;
            try {
                terrain = read(folder, pack, scene, x, z);
            } catch (IOException | RuntimeException error) {
                warn(logger, lastWarning, "Could not read build replay scenery for " + scene + " at " + x + ", " + z, error);
            }
            List<InitialBlock> initial = byChunk.get(Chunk.getChunkKey(x, z));
            if (terrain == null && initial == null) return;
            Map<String, BlockData> states = new HashMap<>();
            if (terrain != null) {
                BlockData[] palette = new BlockData[terrain.palette().length];
                for (int i = 1; i < palette.length; i++) palette[i] = resolve(states, terrain.palette()[i]);
                for (Section section : terrain.sections()) paint(chunk, terrain.minY() + section.index() * 16, section.runs(), palette);
            }
            if (initial != null) {
                for (InitialBlock block : initial) {
                    BuildTape.BlockPos pos = block.pos();
                    if (pos.y() < chunk.getMinHeight() || pos.y() >= chunk.getMaxHeight()) continue;
                    BlockData state = resolve(states, block.state());
                    if (state != null) chunk.setBlock(pos.x() & 15, pos.y(), pos.z() & 15, state);
                }
            }
        }

        private BlockData resolve(Map<String, BlockData> states, String name) {
            if (name == null || states.containsKey(name)) return states.get(name);
            BlockData state = null;
            try {
                state = Bukkit.createBlockData(name);
            } catch (IllegalArgumentException error) {
                warn(logger, lastWarning, "Unavailable block state in build replay scenery for " + scene, error);
            }
            states.put(name, state);
            return state;
        }

        private static void paint(ChunkData chunk, int y, int[] runs, BlockData[] palette) {
            int start = 0;
            for (int run : runs) {
                int length = run >>> 16;
                BlockData state = palette[run & 0xffff];
                if (state != null) {
                    if (((start | length) & 255) == 0) {
                        int bottom = Math.max(y + (start >> 8), chunk.getMinHeight());
                        int top = Math.min(y + ((start + length) >> 8), chunk.getMaxHeight());
                        if (bottom < top) chunk.setRegion(0, bottom, 0, 16, top, 16, state);
                    } else {
                        for (int i = start; i < start + length; i++) {
                            int blockY = y + (i >> 8);
                            if (blockY >= chunk.getMinHeight() && blockY < chunk.getMaxHeight()) {
                                chunk.setBlock(i & 15, blockY, (i >> 4) & 15, state);
                            }
                        }
                    }
                }
                start += length;
            }
        }
    }

    private static void warn(Logger logger, AtomicLong lastWarning, String message, Exception error) {
        long now = System.currentTimeMillis();
        long before = lastWarning.get();
        if (now - before >= 60_000 && lastWarning.compareAndSet(before, now)) logger.log(Level.WARNING, message, error);
    }
}
