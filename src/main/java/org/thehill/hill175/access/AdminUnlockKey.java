package org.thehill.hill175.access;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

/** Bootstrap credentials stay in a private runtime file, never plugin metadata, help or source. */
final class AdminUnlockKey {
    private AdminUnlockKey() { }

    static String load(Path folder, String configuredHash) throws IOException {
        if (configuredHash != null) {
            if (!configuredHash.matches("[a-fA-F0-9]{64}")) throw new IOException("Invalid administrator bootstrap configuration.");
            return configuredHash.toLowerCase(java.util.Locale.ROOT);
        }
        Files.createDirectories(folder);
        Path key = folder.resolve("admin-unlock-key.txt");
        if (!Files.exists(key)) {
            byte[] random = new byte[32];
            new SecureRandom().nextBytes(random);
            String token = Base64.getUrlEncoder().withoutPadding().encodeToString(random);
            if (Files.getFileStore(folder).supportsFileAttributeView("posix")) {
                Files.createFile(key, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
                Files.writeString(key, token + "\n", StandardOpenOption.WRITE);
            } else Files.writeString(key, token + "\n", StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        }
        if (Files.isSymbolicLink(key) || !Files.isRegularFile(key) || Files.size(key) > 256) {
            throw new IOException("Invalid administrator bootstrap key file.");
        }
        if (Files.getFileStore(folder).supportsFileAttributeView("posix")) {
            Files.setPosixFilePermissions(key, PosixFilePermissions.fromString("rw-------"));
        }
        String token = Files.readString(key).strip();
        if (!token.matches("[A-Za-z0-9_-]{43,128}")) throw new IOException("Invalid administrator bootstrap key file.");
        return hash(token);
    }

    static String hash(String token) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(java.nio.charset.StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    static boolean matches(String token, String expected) {
        return token != null && token.matches("[A-Za-z0-9_-]{43,128}") && MessageDigest.isEqual(
                hash(token).getBytes(java.nio.charset.StandardCharsets.US_ASCII), expected.getBytes(java.nio.charset.StandardCharsets.US_ASCII));
    }
}
