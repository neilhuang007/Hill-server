package org.thehill.hill175.auth.sso;

import com.nimbusds.jose.util.JSONObjectUtils;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

/** One process owns this private file. A link and participant name commit in one atomic replacement. */
final class SchoolIdentityStore implements AutoCloseable {
    private final Path file;
    private final FileChannel lockChannel;
    private final FileLock lock;
    private volatile Map<String, String> names = Map.of();
    private Map<String, String> links = Map.of();
    private boolean closed;
    private boolean writeFailed;

    SchoolIdentityStore(Path path) throws IOException {
        file = path.toAbsolutePath().normalize();
        Files.createDirectories(file.getParent());
        Path lockPath = file.resolveSibling(file.getFileName() + ".lock");
        lockChannel = FileChannel.open(lockPath, StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        restrict(lockPath);
        FileLock acquired;
        try {
            acquired = lockChannel.tryLock();
            if (acquired == null) throw new IOException("School identity store is already in use.");
        } catch (RuntimeException | IOException exception) {
            lockChannel.close();
            throw new IOException("School identity store is already in use.");
        }
        lock = acquired;
        try {
            if (Files.exists(file)) load();
        } catch (Exception exception) {
            close();
            throw new IOException("School identity store is invalid; restore the protected backup before starting.");
        }
    }

    private void load() throws Exception {
        if (Files.size(file) > 10 * 1024 * 1024) throw new IOException("Identity store size limit exceeded.");
        Map<String, Object> data = JSONObjectUtils.parse(Files.readString(file));
        if (JSONObjectUtils.getInt(data, "version") != 1) throw new IOException("Unsupported identity format.");
        Map<String, String> loadedNames = strings(JSONObjectUtils.getJSONObject(data, "participants"));
        Map<String, String> loadedLinks = strings(JSONObjectUtils.getJSONObject(data, "gameAccounts"));
        for (var entry : loadedNames.entrySet()) {
            validateParticipant(entry.getKey());
            if (!MicrosoftTokenVerifier.sanitizeName(entry.getValue()).equals(entry.getValue())) throw new IOException();
        }
        for (var entry : loadedLinks.entrySet()) {
            GameIdentity.validate(entry.getKey());
            if (!loadedNames.containsKey(entry.getValue())) throw new IOException();
        }
        names = Map.copyOf(loadedNames);
        links = Map.copyOf(loadedLinks);
        restrict(file);
    }

    synchronized void link(String gameIdentity, SchoolIdentity identity, int cap) {
        if (closed) throw new SsoException("School identity storage is unavailable. Contact event staff.");
        if (writeFailed) throw new SsoException("School identity storage needs an operator review and server restart before sign-in can continue.");
        GameIdentity.validate(gameIdentity);
        validateParticipant(identity.participantKey());
        String existing = links.get(gameIdentity);
        if (existing != null && !existing.equals(identity.participantKey())) {
            throw new SsoException("This game account is linked to another Hill participant. Contact the event staff.");
        }
        if (existing == null && links.values().stream().filter(identity.participantKey()::equals).count() >= cap) {
            throw new SsoException("This Hill account has reached the linked game account limit. Contact the event staff.");
        }
        if (existing == null && links.size() >= 50_000) throw new SsoException("Identity storage limit reached. Contact event staff.");
        if (existing != null && identity.displayName().equals(names.get(existing))) return;
        Map<String, String> updatedNames = new HashMap<>(names);
        Map<String, String> updatedLinks = new HashMap<>(links);
        updatedNames.put(identity.participantKey(), identity.displayName());
        updatedLinks.put(gameIdentity, identity.participantKey());
        try {
            persist(updatedNames, updatedLinks);
        } catch (IOException | RuntimeException exception) {
            // Rename may have completed before a directory flush failed. Never retry using an
            // uncertain in-memory snapshot: that could overwrite an association already on disk.
            writeFailed = true;
            throw new SsoException("School account linking could not be saved. Contact event staff to review storage and restart the server.");
        }
        names = Map.copyOf(updatedNames);
        links = Map.copyOf(updatedLinks);
    }

    Optional<String> nameLookup(String participantKey) { return Optional.ofNullable(names.get(participantKey)); }

    private void persist(Map<String, String> updatedNames, Map<String, String> updatedLinks) throws IOException {
        String json = JSONObjectUtils.toJSONString(Map.of("version", 1, "participants", updatedNames, "gameAccounts", updatedLinks));
        Path temporary = Files.createTempFile(file.getParent(), file.getFileName() + ".", ".tmp");
        try {
            restrict(temporary);
            try (FileChannel output = FileChannel.open(temporary, StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING)) {
                ByteBuffer bytes = java.nio.charset.StandardCharsets.UTF_8.encode(json);
                while (bytes.hasRemaining()) output.write(bytes);
                output.force(true);
            }
            // No non-atomic fallback: a partial identity write must never admit a student.
            Files.move(temporary, file, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            if (Files.getFileStore(file.getParent()).supportsFileAttributeView("posix")) {
                try (FileChannel directory = FileChannel.open(file.getParent(), StandardOpenOption.READ)) {
                    directory.force(true);
                }
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static void validateParticipant(String key) {
        String[] parts = key.split(":", -1);
        if (parts.length != 3 || !parts[0].equals("entra")
                || !SsoConfig.uuid(parts[1]).toString().equals(parts[1])
                || !SsoConfig.uuid(parts[2]).toString().equals(parts[2])) throw new IllegalArgumentException("Invalid participant key.");
    }

    private static Map<String, String> strings(Map<String, Object> source) throws IOException {
        Map<String, String> result = new HashMap<>();
        for (var entry : source.entrySet()) {
            if (!(entry.getValue() instanceof String value)) throw new IOException();
            result.put(entry.getKey(), value);
        }
        return result;
    }

    private static void restrict(Path path) throws IOException {
        if (Files.getFileStore(path).supportsFileAttributeView("posix")) {
            Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rw-------"));
        }
    }

    @Override public synchronized void close() throws IOException {
        if (closed) return;
        closed = true;
        lock.release();
        lockChannel.close();
    }
}
