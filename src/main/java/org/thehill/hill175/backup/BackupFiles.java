package org.thehill.hill175.backup;

import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.FileChannel;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Properties;
import java.util.UUID;

final class BackupFiles {
    private BackupFiles() { }

    static void atomicWrite(Path destination, byte[] bytes) throws IOException {
        Files.createDirectories(destination.getParent());
        Path temporary = destination.resolveSibling(destination.getFileName() + ".tmp." + UUID.randomUUID());
        try (var channel = FileChannel.open(temporary, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(bytes);
            while (buffer.hasRemaining()) channel.write(buffer);
            channel.force(true);
        }
        move(temporary, destination);
    }

    static void move(Path source, Path destination) throws IOException {
        try { Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
        catch (AtomicMoveNotSupportedException exception) {
            Files.move(source, destination, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    static Properties readProperties(Path file) throws IOException {
        Properties properties = new Properties();
        try (var reader = Files.newBufferedReader(file)) { properties.load(reader); }
        return properties;
    }

    static void writeProperties(Path file, Properties properties) throws IOException {
        var text = new java.io.StringWriter();
        properties.store(text, "Hill campus backup");
        atomicWrite(file, text.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }

    static void copyTree(Path source, Path destination) throws IOException {
        if (!Files.isDirectory(source, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Missing source folder: " + source);
        if (Files.exists(destination)) throw new IOException("Destination already exists: " + destination);
        try (var paths = Files.walk(source)) {
            for (Path file : paths.toList()) copyPath(source, destination, file);
        }
    }

    private static void copyPath(Path source, Path destination, Path file) throws IOException {
        if (Files.isSymbolicLink(file)) throw new IOException("Symbolic links are not accepted in snapshots: " + file);
        Path target = destination.resolve(source.relativize(file));
        if (Files.isDirectory(file)) { Files.createDirectories(target); return; }
        if (file.getFileName().toString().equals("session.lock")) return;
        Files.copy(file, target, StandardCopyOption.COPY_ATTRIBUTES);
    }

    static String digest(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = Files.newInputStream(file)) {
                byte[] buffer = new byte[65536];
                int count;
                while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }

    static Path child(Path root, String name) {
        if (!name.matches("[A-Za-z0-9_.-]+") || name.equals(".") || name.equals("..")) {
            throw new IllegalArgumentException("Invalid snapshot name.");
        }
        Path child = root.resolve(name).toAbsolutePath().normalize();
        if (!child.getParent().equals(root.toAbsolutePath().normalize())) throw new IllegalArgumentException("Invalid path.");
        return child;
    }
}
