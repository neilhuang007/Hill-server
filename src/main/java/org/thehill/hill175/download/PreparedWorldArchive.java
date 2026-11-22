package org.thehill.hill175.download;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

final class PreparedWorldArchive {
    private static final long MAX_TOTAL = 2L * 1024 * 1024 * 1024;
    private static final long MAX_FILE = 512L * 1024 * 1024;
    private static final Set<String> ALLOWED_ROOT = Set.of("level.dat", "region", "entities", "poi", "DIM-1", "DIM1", "dimensions", "datapacks");
    private static final Set<String> PRIVATE_NAMES = Set.of("playerdata", "stats", "advancements", "usercache.json",
            "ops.json", "whitelist.json", "banned-players.json", "banned-ips.json", "session.lock", "plugins",
            "logs", "crash-reports", "backups", "level.dat_old", "scoreboard.dat");
    private final Path source;

    PreparedWorldArchive(Path source) {
        this.source = source.toAbsolutePath().normalize();
    }

    String build(Path destination, String fingerprint) throws IOException {
        if (!fingerprint.matches("[A-Za-z0-9_-]{32}")) throw new IllegalArgumentException("Invalid fingerprint.");
        if (Files.isSymbolicLink(source) || !Files.isDirectory(source, LinkOption.NOFOLLOW_LINKS)
                || !Files.isRegularFile(source.resolve("level.dat"), LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("A prepared world directory with level.dat is required.");
        }
        Path root = source.toRealPath(LinkOption.NOFOLLOW_LINKS);
        PreparedLevelData.verify(root.resolve("level.dat"));
        List<Path> files = new ArrayList<>();
        long[] bytes = {0};
        Files.walkFileTree(root, new SimpleFileVisitor<>() {
            @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) throws IOException {
                validate(dir, attrs);
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                validate(file, attrs);
                if (!attrs.isRegularFile() || attrs.size() > MAX_FILE) throw new IOException("Unsupported prepared export file.");
                bytes[0] += attrs.size();
                if (bytes[0] > MAX_TOTAL || files.size() >= 30000) throw new IOException("Prepared export exceeds limits.");
                files.add(file);
                return FileVisitResult.CONTINUE;
            }
            private void validate(Path file, BasicFileAttributes attrs) throws IOException {
                if (attrs.isSymbolicLink() || !file.toRealPath(LinkOption.NOFOLLOW_LINKS).startsWith(root)
                        || root.relativize(file).getNameCount() > 24) throw new IOException("Unsafe prepared export path.");
                if (file.equals(root)) return;
                Path relative = root.relativize(file);
                String first = relative.getName(0).toString();
                if (!ALLOWED_ROOT.contains(first)) throw new IOException("Unexpected prepared export content: " + first);
                for (Path segment : relative) {
                    String name = segment.toString().toLowerCase(Locale.ROOT);
                    if (PRIVATE_NAMES.contains(name) || name.indexOf('\\') >= 0 || name.indexOf(':') >= 0) {
                        throw new IOException("Private or unsafe prepared export content.");
                    }
                }
                if (first.equals("level.dat") && relative.getNameCount() != 1)
                    throw new IOException("Invalid level.dat layout.");
            }
        });
        if (files.isEmpty()) throw new IOException("Empty prepared export.");
        long requiredFreeSpace = bytes[0] * 2 + 1024L * 1024 * 1024;
        if (Files.getFileStore(destination.toAbsolutePath().getParent()).getUsableSpace() < requiredFreeSpace)
            throw new IOException("Insufficient free space for bounded map archive construction.");
        files.sort(Comparator.comparing(file -> root.relativize(file).toString()));
        MessageDigest digest;
        try { digest = MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
        String mapDigest;
        try (OutputStream output = Files.newOutputStream(destination, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
             ZipOutputStream zip = new ZipOutputStream(output)) {
            byte[] buffer = new byte[64 * 1024];
            long written = 0;
            for (Path file : files) {
                String name = "world/" + root.relativize(file).toString().replace('\\', '/');
                zip.putNextEntry(new ZipEntry(name));
                byte[] pathBytes = name.getBytes(StandardCharsets.UTF_8);
                digest.update(ByteBuffer.allocate(4).putInt(pathBytes.length).array());
                digest.update(pathBytes);
                digest.update(ByteBuffer.allocate(8).putLong(Files.size(file)).array());
                try (InputStream in = Files.newInputStream(file, LinkOption.NOFOLLOW_LINKS)) {
                    int count;
                    long current = 0;
                    while ((count = in.read(buffer)) != -1) {
                        current += count;
                        written += count;
                        if (current > MAX_FILE || written > MAX_TOTAL) throw new IOException("Export changed or exceeds size limit.");
                        zip.write(buffer, 0, count);
                        digest.update(buffer, 0, count);
                    }
                }
                zip.closeEntry();
            }
            mapDigest = HexFormat.of().formatHex(digest.digest());
            zip.setComment("Hill175 map SHA-256: " + mapDigest + "; copy fingerprint: " + fingerprint);
            zip.putNextEntry(new ZipEntry("world/.hill175-copy.txt"));
            zip.write(("Hill175 map SHA-256: " + mapDigest + "\nHill175 copy fingerprint: " + fingerprint
                    + "\nThis identifier does not establish who distributed a copy.\n").getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        return mapDigest;
    }
}
