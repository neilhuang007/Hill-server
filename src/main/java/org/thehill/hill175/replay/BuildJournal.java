package org.thehill.hill175.replay;

import org.bukkit.plugin.java.JavaPlugin;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Predicate;
import java.util.logging.Level;
import java.util.stream.Stream;
import java.util.zip.CRC32C;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

/** Disk format for build replay. Frames are forced to disk; a crash can leave only the last frame incomplete. */
final class BuildJournal {
    private static final int MAGIC = 0x48425201;
    private static final int MAX_FRAME_BYTES = 8 * 1024 * 1024;
    private static final int MAX_FRAME_RECORDS = 2_048;
    private static final int MIN_COMPRESS_BYTES = 512;
    private static final int FRAME_PREFIX_BYTES = 2 * Integer.BYTES;
    private static final long WINDOW_BYTES = 16L * 1024 * 1024;
    private static final int WINDOW_SCENES = 256;
    private final JavaPlugin plugin;
    private final ReplayStorage storage;
    private final Path root;
    private final Map<UUID, BuildTape.Profile> profiles = new ConcurrentHashMap<>();
    private final Map<Path, KnownSize> sizes = new HashMap<>();

    BuildJournal(JavaPlugin plugin, ReplayStorage storage) {
        this.plugin = plugin;
        this.storage = storage;
        root = plugin.getDataFolder().toPath().toAbsolutePath().normalize().resolve("build-replays").resolve("journal");
    }

    record Scene(UUID profile, UUID id, String name, String world, long startedAt, long order) {}
    record Frame(Scene scene, long duration, List<BuildTape.Pose> poses, List<BuildTape.Edit> edits) {}
    record ReadPoint(String name, List<ReadScene> scenes, int index, int count) {}
    private record ReadScene(UUID id, Path path, long length) {}
    private record Header(String name, String world) {}
    private record EncodedFrame(byte[] bytes, int signedLength) {}
    private record KnownSize(long fileBytes, long logicalBytes) {}
    private record Prunable(UUID scene, UUID profile, Path tape, long modified, long tapeBytes) {}

    List<BuildTape.Profile> profiles() {
        return profiles.values().stream().sorted(Comparator.comparing(BuildTape.Profile::name, String.CASE_INSENSITIVE_ORDER)
                .thenComparing(BuildTape.Profile::id)).toList();
    }

    void initialize() throws IOException {
        requireSafeRoot();
        Files.createDirectories(root);
        try (var dirs = Files.list(root)) {
            for (Path dir : (Iterable<Path>) dirs::iterator) {
                UUID profile = uuid(dir.getFileName().toString());
                if (profile == null || !Files.isDirectory(dir, LinkOption.NOFOLLOW_LINKS)) continue;
                indexProfile(profile, dir);
            }
        }
    }

    void append(Frame frame) throws IOException {
        Scene scene = frame.scene;
        Path dir = root.resolve(scene.profile.toString());
        Path path = dir.resolve(String.format(Locale.ROOT, "%013d-%020d-%s.tape", scene.startedAt, scene.order, scene.id));
        byte[] data = frameBytes(frame);
        EncodedFrame encoded = compress(data);
        int storedSize = Math.abs(encoded.signedLength);
        CRC32C crc = new CRC32C();
        crc.update(encoded.bytes, 0, storedSize);
        requireSafeRoot();
        requireDirectory(dir);
        long oldSize = fileSize(path);
        byte[] header = oldSize == 0 ? headerBytes(scene) : new byte[0];
        long appended = (long) header.length + FRAME_PREFIX_BYTES + storedSize;
        storage.write(path, appended, () -> {
            requireSafeRoot();
            requireDirectory(dir);
            Files.createDirectories(dir);
            try (FileChannel channel = FileChannel.open(path, StandardOpenOption.CREATE, StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND, LinkOption.NOFOLLOW_LINKS)) {
                if (channel.size() != oldSize) throw new IOException("Build replay scene changed before write");
                writeFully(channel, ByteBuffer.wrap(header));
                writeFully(channel, ByteBuffer.allocate(FRAME_PREFIX_BYTES).putInt(encoded.signedLength).putInt((int) crc.getValue()).flip());
                writeFully(channel, ByteBuffer.wrap(encoded.bytes, 0, storedSize));
                channel.force(true);
            }
        });
        KnownSize known = sizes.get(path);
        long logicalAppended = (long) header.length + FRAME_PREFIX_BYTES + data.length;
        if (oldSize == 0 || (known != null && known.fileBytes == oldSize)) {
            sizes.put(path, new KnownSize(oldSize + appended, (oldSize == 0 ? 0 : known.logicalBytes) + logicalAppended));
        }
        profiles.put(scene.profile, new BuildTape.Profile(scene.profile, scene.name));
    }

    ReadPoint point(UUID profile, int requested) throws IOException {
        BuildTape.Profile indexed = profiles.get(profile);
        if (indexed == null) return new ReadPoint("Unknown player", List.of(), 0, 1);
        Path dir = root.resolve(profile.toString());
        requireSafeRoot();
        requireDirectory(dir);
        List<ReadScene> current = new ArrayList<>();
        List<ReadScene> selected = List.of();
        long length = 0;
        int index = 0;
        try (var files = scenePaths(dir).sorted()) {
            for (Path path : (Iterable<Path>) files::iterator) {
                long size = fileSize(path);
                if (size < 8) continue;
                long logicalSize = logicalSize(path, size);
                if (current.size() == WINDOW_SCENES || (!current.isEmpty() && logicalSize > WINDOW_BYTES - length)) {
                    if (index == requested) selected = List.copyOf(current);
                    current.clear();
                    length = 0;
                    index++;
                }
                length += logicalSize;
                current.add(new ReadScene(sceneId(path), path, size));
            }
        }
        if (requested < 0 || requested >= index) return new ReadPoint(indexed.name(), List.copyOf(current), index, index + 1);
        return new ReadPoint(indexed.name(), selected, requested, index + 1);
    }

    BuildTape read(ReadPoint point) throws IOException {
        List<BuildTape.Segment> segments = new ArrayList<>();
        long remainingBytes = WINDOW_BYTES;
        requireSafeRoot();
        for (ReadScene scene : point.scenes) {
            requireDirectory(scene.path.getParent());
            if (scene.length > WINDOW_BYTES) throw new IOException("Build replay scene exceeds the playback size limit");
            try (DataInputStream input = new DataInputStream(new BufferedInputStream(new LimitedInput(
                    Files.newInputStream(scene.path, LinkOption.NOFOLLOW_LINKS), scene.length)))) {
                Header header;
                try { header = readHeader(input); }
                catch (EOFException ignored) { continue; }
                List<BuildTape.Pose> poses = new ArrayList<>();
                List<BuildTape.Edit> edits = new ArrayList<>();
                long duration = 0;
                while (true) {
                    int signedLength;
                    int checksum;
                    try {
                        signedLength = input.readInt();
                        checksum = input.readInt();
                    } catch (EOFException ignored) { break; }
                    int size = storedSize(signedLength);
                    byte[] payload = input.readNBytes(size);
                    if (payload.length != size) break;
                    CRC32C crc = new CRC32C();
                    crc.update(payload);
                    if ((int) crc.getValue() != checksum) throw new IOException("Invalid build replay frame checksum");
                    int rawLength = signedLength < 0 ? rawSize(size, ByteBuffer.wrap(payload).getInt()) : size;
                    remainingBytes -= FRAME_PREFIX_BYTES + rawLength;
                    if (remainingBytes < 0) throw new IOException("Build replay part exceeds the playback size limit");
                    byte[] contents = signedLength < 0 ? inflate(payload, rawLength) : payload;
                    try (DataInputStream frame = new DataInputStream(new ByteArrayInputStream(contents))) {
                        long end = frame.readLong();
                        if (end < duration) throw new IOException("Build replay durations are out of order");
                        int poseCount = frame.readInt();
                        checkCount(poseCount);
                        for (int i = 0; i < poseCount; i++) {
                            long time = checkTime(frame.readLong(), duration, end);
                            poses.add(new BuildTape.Pose(time, frame.readDouble(), frame.readDouble(), frame.readDouble(),
                                    frame.readFloat(), frame.readFloat()));
                        }
                        int editCount = frame.readInt();
                        checkCount(editCount);
                        if (poseCount + editCount > MAX_FRAME_RECORDS) throw new IOException("Too many build replay frame records");
                        for (int i = 0; i < editCount; i++) {
                            long time = checkTime(frame.readLong(), duration, end);
                            edits.add(new BuildTape.Edit(time, frame.readInt(), frame.readInt(), frame.readInt(),
                                    frame.readUTF(), frame.readUTF(), frame.readBoolean()));
                        }
                        if (frame.read() != -1) throw new IOException("Invalid trailing build replay frame data");
                        duration = end;
                    }
                }
                if (!poses.isEmpty()) segments.add(new BuildTape.Segment(scene.id, header.world, duration,
                        List.copyOf(poses), List.copyOf(edits)));
            }
        }
        return new BuildTape(point.name, List.copyOf(segments), point.index, point.count);
    }

    void prune(long cutoff, Set<UUID> activeScenes, Predicate<UUID> pinned) throws IOException {
        requireSafeRoot();
        long target = storage.reclaimTarget();
        Set<UUID> journalScenes = new HashSet<>();
        List<Prunable> candidates = new ArrayList<>();
        try (var dirs = Files.list(root)) {
            for (Path dir : (Iterable<Path>) dirs::iterator) {
                UUID profile = uuid(dir.getFileName().toString());
                if (profile == null || !Files.isDirectory(dir, LinkOption.NOFOLLOW_LINKS)) continue;
                try (var files = scenePaths(dir)) {
                    for (Path path : (Iterable<Path>) files::iterator) {
                        UUID scene = sceneId(path);
                        journalScenes.add(scene);
                        if (activeScenes.contains(scene) || pinned.test(profile)) continue;
                        BasicFileAttributes attrs = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                        long modified = attrs.lastModifiedTime().toMillis();
                        if (attrs.isRegularFile() && (target > 0 || modified < cutoff)) {
                            candidates.add(new Prunable(scene, profile, path, modified, attrs.size()));
                        }
                    }
                }
            }
        }
        addOrphans(candidates, target > 0 ? Long.MAX_VALUE : cutoff, journalScenes, activeScenes);
        if (candidates.isEmpty()) return;
        candidates.sort(Comparator.comparingLong(Prunable::modified).thenComparing(Prunable::scene));
        Set<UUID> affected = new HashSet<>();
        try {
            storage.remove(() -> {
                long reclaimed = 0;
                for (Prunable candidate : candidates) {
                    if (candidate.modified >= cutoff && reclaimed >= target) break;
                    if (activeScenes.contains(candidate.scene) || (candidate.profile != null && pinned.test(candidate.profile))) continue;
                    try {
                        if (candidate.tape != null) {
                            requireDirectory(candidate.tape.getParent());
                            if (Files.isRegularFile(candidate.tape, LinkOption.NOFOLLOW_LINKS) && Files.deleteIfExists(candidate.tape)) {
                                reclaimed += storage.footprint(candidate.tapeBytes);
                            }
                            sizes.remove(candidate.tape);
                            affected.add(candidate.profile);
                        }
                        reclaimed += ReplayTerrain.delete(plugin, candidate.scene, storage);
                    } catch (IOException exception) {
                        plugin.getLogger().log(Level.WARNING, "Could not prune build replay scene " + candidate.scene, exception);
                    }
                }
                for (UUID profile : affected) {
                    Path dir = root.resolve(profile.toString());
                    try {
                        if (Files.isDirectory(dir, LinkOption.NOFOLLOW_LINKS)) Files.deleteIfExists(dir);
                    } catch (DirectoryNotEmptyException ignored) { }
                }
            });
        } finally {
            for (UUID profile : affected) indexProfile(profile, root.resolve(profile.toString()));
        }
    }

    private void addOrphans(List<Prunable> candidates, long cutoff, Set<UUID> journalScenes, Set<UUID> activeScenes) throws IOException {
        Path terrain = root.getParent().resolve("terrain");
        requireDirectory(terrain);
        if (!Files.isDirectory(terrain, LinkOption.NOFOLLOW_LINKS)) return;
        try (var directories = Files.list(terrain)) {
            for (Path path : (Iterable<Path>) directories::iterator) {
                UUID scene = uuid(path.getFileName().toString());
                if (scene == null || journalScenes.contains(scene) || activeScenes.contains(scene)) continue;
                BasicFileAttributes attrs = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                long modified = attrs.lastModifiedTime().toMillis();
                if (attrs.isDirectory() && modified < cutoff) candidates.add(new Prunable(scene, null, null, modified, 0));
            }
        }
    }

    private void indexProfile(UUID profile, Path dir) {
        try (var files = scenePaths(dir).sorted(Comparator.reverseOrder())) {
            for (Path path : (Iterable<Path>) files::iterator) {
                try (var input = new DataInputStream(new BufferedInputStream(Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)))) {
                    Header header = readHeader(input);
                    profiles.put(profile, new BuildTape.Profile(profile, header.name));
                    return;
                } catch (EOFException ignored) { }
                catch (IOException exception) {
                    plugin.getLogger().log(Level.WARNING, "Could not read build replay scene header " + path.getFileName(), exception);
                }
            }
        } catch (NoSuchFileException ignored) { }
        catch (IOException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not index a build replay profile " + profile, exception);
            return;
        }
        profiles.remove(profile);
    }

    private long logicalSize(Path path, long length) {
        KnownSize known = sizes.get(path);
        if (known != null && known.fileBytes == length) return known.logicalBytes;
        long size = WINDOW_BYTES;
        if (length < WINDOW_BYTES) {
            try { size = scanLogicalSize(path, length); }
            catch (IOException ignored) { }
        }
        sizes.put(path, new KnownSize(length, size));
        return size;
    }

    private static long scanLogicalSize(Path path, long length) throws IOException {
        try (var input = new DataInputStream(new BufferedInputStream(new LimitedInput(
                Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS), length)))) {
            if (input.readInt() != MAGIC) throw new IOException("Unsupported build replay format");
            int metadata = 0;
            for (int i = 0; i < 2; i++) {
                int field = input.readUnsignedShort();
                input.skipNBytes(field);
                metadata += Short.BYTES + field;
            }
            long position = Integer.BYTES + metadata;
            long logical = position;
            while (length - position >= FRAME_PREFIX_BYTES) {
                int signed = input.readInt();
                input.readInt();
                int stored = storedSize(signed);
                position += FRAME_PREFIX_BYTES;
                if (length - position < stored) break;
                int raw = stored;
                int remaining = stored;
                if (signed < 0) {
                    raw = rawSize(stored, input.readInt());
                    remaining -= Integer.BYTES;
                }
                logical += FRAME_PREFIX_BYTES + raw;
                if (logical >= WINDOW_BYTES) return WINDOW_BYTES;
                input.skipNBytes(remaining);
                position += stored;
            }
            return Math.max(logical, length);
        }
    }

    private static long fileSize(Path path) throws IOException {
        try {
            BasicFileAttributes attrs = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attrs.isRegularFile()) throw new IOException("Not a build replay file: " + path);
            return attrs.size();
        } catch (NoSuchFileException ignored) { return 0; }
    }

    private static byte[] headerBytes(Scene scene) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream header = new DataOutputStream(bytes)) {
            header.writeInt(MAGIC);
            header.writeUTF(scene.name);
            header.writeUTF(scene.world);
        }
        return bytes.toByteArray();
    }

    private static EncodedFrame compress(byte[] input) {
        if (input.length < MIN_COMPRESS_BYTES) return new EncodedFrame(input, input.length);
        byte[] packed = new byte[input.length - 1];
        ByteBuffer.wrap(packed).putInt(input.length);
        try (Deflater deflater = new Deflater(Deflater.BEST_SPEED)) {
            deflater.setInput(input);
            deflater.finish();
            int offset = Integer.BYTES;
            while (offset < packed.length && !deflater.finished()) {
                int count = deflater.deflate(packed, offset, packed.length - offset);
                if (count == 0) break;
                offset += count;
            }
            if (deflater.finished()) return new EncodedFrame(packed, -offset);
        }
        return new EncodedFrame(input, input.length);
    }

    private static byte[] inflate(byte[] payload, int rawLength) throws IOException {
        byte[] raw = new byte[rawLength];
        try (Inflater inflater = new Inflater()) {
            inflater.setInput(payload, Integer.BYTES, payload.length - Integer.BYTES);
            int offset = 0;
            while (offset < raw.length && !inflater.finished()) {
                int count = inflater.inflate(raw, offset, raw.length - offset);
                if (count == 0) break;
                offset += count;
            }
            if (offset != raw.length || (!inflater.finished() && inflater.inflate(new byte[1]) != 0)
                    || !inflater.finished() || inflater.getRemaining() != 0) {
                throw new IOException("Invalid compressed build replay frame");
            }
            return raw;
        } catch (DataFormatException exception) { throw new IOException("Invalid compressed build replay frame", exception); }
    }

    private static int storedSize(int signed) throws IOException {
        int length = Math.abs(signed);
        if (length < (signed < 0 ? Integer.BYTES + 1 : 16) || length > MAX_FRAME_BYTES) {
            throw new IOException("Invalid build replay frame length");
        }
        return length;
    }

    private static int rawSize(int stored, int raw) throws IOException {
        if (raw <= stored || raw < 16 || raw > MAX_FRAME_BYTES) throw new IOException("Invalid compressed build replay frame length");
        return raw;
    }

    private static byte[] frameBytes(Frame frame) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(bytes)) {
            output.writeLong(frame.duration);
            output.writeInt(frame.poses.size());
            for (BuildTape.Pose pose : frame.poses) {
                output.writeLong(pose.time());
                output.writeDouble(pose.x());
                output.writeDouble(pose.y());
                output.writeDouble(pose.z());
                output.writeFloat(pose.yaw());
                output.writeFloat(pose.pitch());
            }
            output.writeInt(frame.edits.size());
            for (BuildTape.Edit edit : frame.edits) {
                output.writeLong(edit.time());
                output.writeInt(edit.x());
                output.writeInt(edit.y());
                output.writeInt(edit.z());
                output.writeUTF(edit.before());
                output.writeUTF(edit.after());
                output.writeBoolean(edit.subject());
            }
        }
        if (bytes.size() > MAX_FRAME_BYTES) throw new IOException("Build replay frame is too large");
        return bytes.toByteArray();
    }

    private static Header readHeader(DataInputStream input) throws IOException {
        if (input.readInt() != MAGIC) throw new IOException("Unsupported build replay format");
        return new Header(input.readUTF(), input.readUTF());
    }

    private static void writeFully(FileChannel channel, ByteBuffer bytes) throws IOException {
        while (bytes.hasRemaining()) channel.write(bytes);
    }

    private void requireSafeRoot() throws IOException {
        requireDirectory(root.getParent());
        requireDirectory(root);
    }

    private static void requireDirectory(Path path) throws IOException {
        if (Files.exists(path, LinkOption.NOFOLLOW_LINKS) && !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Not a build replay directory: " + path);
        }
    }

    private static Stream<Path> scenePaths(Path dir) throws IOException {
        return Files.list(dir).filter(path -> sceneId(path) != null && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS));
    }

    private static UUID sceneId(Path path) {
        String name = path.getFileName().toString();
        if (name.length() != 76 || name.charAt(13) != '-' || name.charAt(34) != '-' || !name.endsWith(".tape")) return null;
        for (int i = 0; i < 34; i++) {
            if (i != 13 && (name.charAt(i) < '0' || name.charAt(i) > '9')) return null;
        }
        return uuid(name.substring(35, 71));
    }

    private static UUID uuid(String value) {
        if (value.length() != 36) return null;
        try {
            UUID id = UUID.fromString(value);
            return value.equals(id.toString()) ? id : null;
        } catch (IllegalArgumentException ignored) { return null; }
    }

    private static void checkCount(int count) throws IOException {
        if (count < 0 || count > MAX_FRAME_RECORDS) throw new IOException("Too many build replay frame records");
    }

    private static long checkTime(long time, long start, long end) throws IOException {
        if (time < start || time > end) throw new IOException("Build replay timestamps are out of order");
        return time;
    }

    private static final class LimitedInput extends FilterInputStream {
        private long remaining;
        private LimitedInput(InputStream input, long remaining) { super(input); this.remaining = remaining; }
        @Override public int read() throws IOException {
            if (remaining == 0) return -1;
            int value = in.read();
            if (value >= 0) remaining--;
            return value;
        }
        @Override public int read(byte[] bytes, int offset, int length) throws IOException {
            if (length == 0) return 0;
            if (remaining == 0) return -1;
            int count = in.read(bytes, offset, (int) Math.min(length, remaining));
            if (count > 0) remaining -= count;
            return count;
        }
        @Override public long skip(long count) throws IOException {
            if (count <= 0 || remaining == 0) return 0;
            long skipped = in.skip(Math.min(count, remaining));
            remaining -= skipped;
            return skipped;
        }
    }
}
