package org.thehill.hill175.replay;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

/** Private bounded archives, not a web/download root. All paths are server-generated. */
final class PacketReplayFiles {
    static final long MAX_BYTES = 2L * 1024 * 1024 * 1024;
    static final long MAX_AGE_MILLIS = TimeUnit.DAYS.toMillis(7);
    private final Path directory;
    private final Path index;
    private final java.util.Set<Path> activePending = java.util.concurrent.ConcurrentHashMap.newKeySet();

    PacketReplayFiles(Path directory) throws IOException {
        this.directory = directory.toAbsolutePath().normalize();
        if (Files.isSymbolicLink(this.directory)) throw new IOException("Replay directory may not be a symlink");
        Files.createDirectories(this.directory);
        protect(this.directory, true);
        index = this.directory.resolve("segments.tsv");
        if (Files.isSymbolicLink(index)) throw new IOException("Replay index may not be a symlink");
    }

    Path reserve(UUID player) {
        return directory.resolve(System.currentTimeMillis() + "-" + player + "-" + UUID.randomUUID() + ".flashback");
    }

    synchronized void event(String event, UUID player, Path file, String detail) throws IOException {
        if (Files.isSymbolicLink(index)) throw new IOException("Replay index may not be a symlink");
        if (Files.isRegularFile(index, LinkOption.NOFOLLOW_LINKS) && Files.size(index) > 8L * 1024 * 1024) {
            Path previous = directory.resolve("segments.previous.tsv");
            if (Files.isSymbolicLink(previous)) throw new IOException("Replay prior index may not be a symlink");
            Files.move(index, previous, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
        String line = Instant.now() + "\t" + event + "\t" + player + "\t"
                + (file == null ? "-" : file.getFileName()) + "\t" + detail.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ') + "\n";
        try (FileChannel channel = FileChannel.open(index, StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.APPEND)) {
            protect(index, false);
            ByteBuffer data = StandardCharsets.UTF_8.encode(line);
            while (data.hasRemaining()) channel.write(data);
            channel.force(false);
        }
    }

    void saved(Path file) throws IOException {
        if (!file.toAbsolutePath().normalize().getParent().equals(directory)
                || !Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Unexpected replay output path");
        protect(file, false);
    }

    void beginWrite(Path path) { activePending.add(path.toAbsolutePath().normalize()); }
    void endWrite(Path path) { activePending.remove(path.toAbsolutePath().normalize()); }

    synchronized void prune() throws IOException {
        List<Path> files;
        try (Stream<Path> entries = Files.list(directory)) {
            files = new ArrayList<>(entries.filter(file -> file.getFileName().toString().matches("\\d{13}-[a-f0-9-]{36}-[a-f0-9-]{36}\\.flashback(?:\\.pending)?"))
                    .filter(file -> Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)).toList());
        }
        files.sort(Comparator.comparing(file -> file.getFileName().toString()));
        long bytes = 0;
        for (Path file : files) bytes += Files.size(file);
        long cutoff = System.currentTimeMillis() - MAX_AGE_MILLIS;
        for (Path file : files) {
            if (activePending.contains(file.toAbsolutePath().normalize())) continue;
            if (bytes <= MAX_BYTES && Files.getLastModifiedTime(file, LinkOption.NOFOLLOW_LINKS).toMillis() >= cutoff) continue;
            long size = Files.size(file);
            Files.delete(file);
            bytes -= size;
        }
    }

    static void protect(Path path, boolean directory) throws IOException {
        try { Files.setPosixFilePermissions(path, PosixFilePermissions.fromString(directory ? "rwx------" : "rw-------")); }
        catch (UnsupportedOperationException ignored) { }
    }
}
