package org.thehill.hill175.access;

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
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.Set;

/** Atomic private moderation records. Reads use immutable snapshots, including from chat threads. */
final class AccessStore implements AutoCloseable {
    record Sanction(String reason, Instant until) {
        boolean active(Instant now) { return until.isAfter(now); }
    }
    record Account(ServerRole assigned, ServerRole microsoft, Sanction ban, Sanction mute) {
        ServerRole role() { return assigned.ordinal() > microsoft.ordinal() ? assigned : microsoft; }
    }
    record Profile(String subject, String gameName, String displayName) { }
    private static final Account DEFAULT = new Account(ServerRole.PLAYER, ServerRole.PLAYER, null, null);
    private final Path file;
    private final FileChannel channel;
    private final FileLock lock;
    private volatile Map<String, Account> accounts = Map.of();
    private volatile Map<UUID, Profile> profiles = Map.of();
    private List<Map<String, String>> audit = List.of();
    private Set<String> consumedUnlocks = Set.of();
    private volatile boolean failed;

    AccessStore(Path path) throws IOException {
        file = path.toAbsolutePath().normalize();
        Files.createDirectories(file.getParent());
        Path lockPath = file.resolveSibling(file.getFileName() + ".lock");
        channel = FileChannel.open(lockPath, StandardOpenOption.CREATE, StandardOpenOption.WRITE);
        restrict(lockPath);
        try {
            lock = channel.tryLock();
            if (lock == null) throw new IOException("Moderation storage is already in use.");
        } catch (IOException | RuntimeException exception) {
            channel.close();
            throw new IOException("Moderation storage is already in use.", exception);
        }
        try {
            if (Files.exists(file)) load();
        } catch (Exception exception) {
            close();
            throw new IOException("Moderation storage is invalid. Restore its protected backup before starting.", exception);
        }
    }

    Account account(String subject) {
        if (failed) throw new IllegalStateException("Moderation storage needs an operator review and restart.");
        return accounts.getOrDefault(subject, DEFAULT);
    }
    Optional<Profile> profile(UUID id) { return Optional.ofNullable(profiles.get(id)); }
    Map<UUID, Profile> profiles() { return profiles; }

    synchronized void remember(UUID id, String gameName, String displayName, String subject, ServerRole microsoft) throws IOException {
        validateSubject(subject);
        var updatedProfiles = new HashMap<>(profiles);
        Profile profile = new Profile(subject, gameName, displayName);
        Account old = account(subject);
        if (profile.equals(profiles.get(id)) && old.microsoft == microsoft) return;
        updatedProfiles.put(id, profile);
        var updated = new HashMap<>(accounts);
        updated.put(subject, new Account(old.assigned, microsoft, old.ban, old.mute));
        persist(updated, updatedProfiles, audit);
    }

    synchronized void change(String subject, String action, String value, String actor, Instant now, Instant until) throws IOException {
        validateSubject(subject);
        Account old = account(subject);
        Account next = switch (action) {
            case "role" -> new Account(ServerRole.parse(value), old.microsoft, old.ban, old.mute);
            case "ban" -> new Account(old.assigned, old.microsoft, new Sanction(value, until), old.mute);
            case "unban" -> new Account(old.assigned, old.microsoft, null, old.mute);
            case "mute" -> new Account(old.assigned, old.microsoft, old.ban, new Sanction(value, until));
            case "unmute" -> new Account(old.assigned, old.microsoft, old.ban, null);
            case "kick" -> old;
            default -> throw new IllegalArgumentException("Unknown moderation action.");
        };
        var updated = new HashMap<>(accounts);
        updated.put(subject, next);
        var events = new ArrayList<>(audit);
        events.add(Map.of("at", now.toString(), "actor", actor, "subject", subject, "action", action,
                "value", value, "until", until.toString()));
        persist(updated, profiles, events);
    }

    synchronized void claimAdministrator(String subject, String keyHash, Instant now) throws IOException {
        validateSubject(subject);
        if (consumedUnlocks.contains(keyHash)) throw new SecurityException("Unknown command.");
        Account old = account(subject);
        var updated = new HashMap<>(accounts);
        updated.put(subject, new Account(ServerRole.ADMINISTRATOR, old.microsoft, old.ban, old.mute));
        var events = new ArrayList<>(audit);
        events.add(Map.of("at", now.toString(), "actor", subject, "subject", subject, "action", "administrator-unlock", "value", "ADMINISTRATOR"));
        var consumed = new java.util.HashSet<>(consumedUnlocks);
        consumed.add(keyHash);
        persist(updated, profiles, events, consumed);
    }

    static void validateSubject(String subject) {
        if (subject == null) throw new IllegalArgumentException("Missing account identifier.");
        String[] parts = subject.split(":", -1);
        if (parts.length == 2 && parts[0].equals("game") && canonicalUuid(parts[1])) return;
        if (parts.length == 3 && parts[0].equals("entra") && canonicalUuid(parts[1]) && canonicalUuid(parts[2])) return;
        throw new IllegalArgumentException("Use a known game name, game UUID, or exact entra:<tenant>:<object> identifier.");
    }
    private static boolean canonicalUuid(String value) {
        try { return UUID.fromString(value).toString().equals(value) && !UUID.fromString(value).equals(new UUID(0, 0)); }
        catch (IllegalArgumentException exception) { return false; }
    }

    private void load() throws Exception {
        if (Files.size(file) > 64 * 1024 * 1024) throw new IOException("Moderation storage size limit exceeded.");
        Map<String, Object> json = JSONObjectUtils.parse(Files.readString(file));
        if (JSONObjectUtils.getInt(json, "version") != 1) throw new IOException("Unsupported moderation format.");
        Map<String, Account> loaded = new HashMap<>();
        for (var entry : JSONObjectUtils.getJSONObject(json, "accounts").entrySet()) {
            validateSubject(entry.getKey());
            Map<String, Object> data = object(entry.getValue());
            loaded.put(entry.getKey(), new Account(ServerRole.parse(JSONObjectUtils.getString(data, "assigned")),
                    ServerRole.parse(JSONObjectUtils.getString(data, "microsoft")),
                    sanction(data.get("ban")), sanction(data.get("mute"))));
        }
        Map<UUID, Profile> loadedProfiles = new HashMap<>();
        for (var entry : JSONObjectUtils.getJSONObject(json, "profiles").entrySet()) {
            UUID id = UUID.fromString(entry.getKey());
            Map<String, Object> data = object(entry.getValue());
            String subject = JSONObjectUtils.getString(data, "subject");
            validateSubject(subject);
            if (!loaded.containsKey(subject)) throw new IOException("Unknown moderation profile account.");
            loadedProfiles.put(id, new Profile(subject, JSONObjectUtils.getString(data, "gameName"), JSONObjectUtils.getString(data, "displayName")));
        }
        List<Map<String, String>> events = new ArrayList<>();
        for (Object event : JSONObjectUtils.getJSONArray(json, "audit")) {
            Map<String, String> strings = new HashMap<>();
            for (var entry : object(event).entrySet()) {
                if (!(entry.getValue() instanceof String value)) throw new IOException("Invalid moderation audit.");
                strings.put(entry.getKey(), value);
            }
            events.add(Map.copyOf(strings));
        }
        accounts = Map.copyOf(loaded);
        profiles = Map.copyOf(loadedProfiles);
        audit = List.copyOf(events);
        if (json.containsKey("consumedUnlocks")) {
            var consumed = JSONObjectUtils.getStringList(json, "consumedUnlocks");
            if (consumed.stream().anyMatch(value -> !value.matches("[a-f0-9]{64}"))) throw new IOException("Invalid bootstrap state.");
            consumedUnlocks = Set.copyOf(consumed);
        }
        restrict(file);
    }

    private static Map<String, Object> object(Object value) throws java.text.ParseException {
        if (!(value instanceof Map<?, ?> map)) throw new java.text.ParseException("Expected an object.", 0);
        Map<String, Object> result = new HashMap<>();
        for (var entry : map.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw new java.text.ParseException("Expected an object key.", 0);
            result.put(key, entry.getValue());
        }
        return result;
    }
    private static Sanction sanction(Object value) throws java.text.ParseException {
        if (value == null) return null;
        var data = object(value);
        return new Sanction(JSONObjectUtils.getString(data, "reason"), Instant.parse(JSONObjectUtils.getString(data, "until")));
    }
    private static Object json(Sanction sanction) {
        return sanction == null ? null : Map.of("reason", sanction.reason, "until", sanction.until.toString());
    }

    private void persist(Map<String, Account> updated, Map<UUID, Profile> updatedProfiles, List<Map<String, String>> events) throws IOException {
        persist(updated, updatedProfiles, events, consumedUnlocks);
    }
    private void persist(Map<String, Account> updated, Map<UUID, Profile> updatedProfiles, List<Map<String, String>> events, Set<String> consumed) throws IOException {
        if (failed) throw new IOException("Moderation storage is unavailable.");
        Map<String, Object> accountJson = new HashMap<>();
        updated.forEach((key, account) -> {
            Map<String, Object> data = new HashMap<>();
            data.put("assigned", account.assigned.name()); data.put("microsoft", account.microsoft.name());
            data.put("ban", json(account.ban)); data.put("mute", json(account.mute));
            accountJson.put(key, data);
        });
        Map<String, Object> profileJson = new HashMap<>();
        updatedProfiles.forEach((id, profile) -> profileJson.put(id.toString(), Map.of("subject", profile.subject,
                "gameName", profile.gameName, "displayName", profile.displayName)));
        String json = JSONObjectUtils.toJSONString(Map.of("version", 1, "accounts", accountJson, "profiles", profileJson, "audit", events, "consumedUnlocks", consumed.stream().sorted().toList()));
        Path temporary = Files.createTempFile(file.getParent(), "moderation-", ".tmp");
        try {
            restrict(temporary);
            try (var output = FileChannel.open(temporary, StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING)) {
                ByteBuffer bytes = java.nio.charset.StandardCharsets.UTF_8.encode(json);
                while (bytes.hasRemaining()) output.write(bytes);
                output.force(true);
            }
            Files.move(temporary, file, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            if (Files.getFileStore(file.getParent()).supportsFileAttributeView("posix")) {
                try (var directory = FileChannel.open(file.getParent(), StandardOpenOption.READ)) { directory.force(true); }
            }
            accounts = Map.copyOf(updated);
            profiles = Map.copyOf(updatedProfiles);
            audit = List.copyOf(events);
            consumedUnlocks = Set.copyOf(consumed);
        } catch (IOException | RuntimeException exception) {
            failed = true;
            throw exception;
        } finally { Files.deleteIfExists(temporary); }
    }
    private static void restrict(Path path) throws IOException {
        if (Files.getFileStore(path).supportsFileAttributeView("posix")) {
            Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rw-------"));
        }
    }
    @Override public void close() throws IOException { lock.release(); channel.close(); }
}
