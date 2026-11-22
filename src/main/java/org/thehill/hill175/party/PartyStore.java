package org.thehill.hill175.party;

import org.bukkit.configuration.InvalidConfigurationException;
import org.bukkit.configuration.file.YamlConfiguration;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

final class PartyStore {
    private final Path file;

    PartyStore(Path folder) {
        file = folder.resolve("parties.yml");
    }

    Map<String, Campus> load() throws IOException, InvalidConfigurationException {
        if (!Files.exists(file, LinkOption.NOFOLLOW_LINKS)) return Map.of();
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Party registry must be a regular file.");
        }
        YamlConfiguration yaml = new YamlConfiguration();
        yaml.load(file.toFile());
        if (yaml.getInt("schema-version", -1) != 1 || !yaml.isList("campuses")) {
            throw new IOException("Unsupported or incomplete party registry.");
        }
        LinkedHashMap<String, Campus> campuses = new LinkedHashMap<>();
        Set<UUID> entryIds = new LinkedHashSet<>();
        Set<String> worldNames = new LinkedHashSet<>();
        Set<UUID> invitationTokens = new LinkedHashSet<>();
        try {
            for (Object rawCampus : yaml.getList("campuses", List.of())) {
                Map<?, ?> values = objectMap(rawCampus);
                String ownerKey = text(values, "owner");
                String ownerLabel = text(values, "owner-label");
                UUID entryId = UUID.fromString(text(values, "entry"));
                String worldName = optionalText(values, "world");
                Phase phase = Phase.valueOf(text(values, "phase"));
                Instant lastInviteAt = Instant.parse(text(values, "last-invite-at"));
                if ((phase == Phase.READY && worldName.isEmpty())
                        || !worldName.isEmpty() && !worldName.matches("[A-Za-z0-9_-]+")) {
                    throw new IllegalArgumentException("Invalid personal campus world.");
                }
                LinkedHashMap<String, String> guests = new LinkedHashMap<>();
                for (Object rawGuest : objectList(values, "guests")) {
                    Map<?, ?> guest = objectMap(rawGuest);
                    String identity = text(guest, "identity");
                    if (identity.equals(ownerKey) || guests.putIfAbsent(identity, text(guest, "label")) != null) {
                        throw new IllegalArgumentException("Duplicate guest or owner in guest roster.");
                    }
                }
                LinkedHashMap<String, Invitation> invitations = new LinkedHashMap<>();
                for (Object rawInvitation : objectList(values, "invitations")) {
                    Map<?, ?> invitation = objectMap(rawInvitation);
                    String identity = text(invitation, "identity");
                    Instant issuedAt = Instant.parse(text(invitation, "issued-at"));
                    Instant expiresAt = Instant.parse(text(invitation, "expires-at"));
                    UUID token = invitation.containsKey("token") ? UUID.fromString(text(invitation, "token"))
                            : UUID.nameUUIDFromBytes(("hill175:invitation:" + ownerKey.length() + ":" + ownerKey
                            + ":" + identity.length() + ":" + identity + ":" + issuedAt).getBytes(StandardCharsets.UTF_8));
                    if (!expiresAt.isAfter(issuedAt) || identity.equals(ownerKey) || guests.containsKey(identity)
                            || !invitationTokens.add(token)
                            || invitations.putIfAbsent(identity, new Invitation(text(invitation, "label"), issuedAt, expiresAt, token)) != null) {
                        throw new IllegalArgumentException("Invalid or duplicate invitation.");
                    }
                }
                Campus campus = new Campus(ownerKey, ownerLabel, entryId, worldName, phase, guests, invitations, lastInviteAt);
                if (campuses.putIfAbsent(ownerKey, campus) != null || !entryIds.add(entryId)
                        || !worldName.isEmpty() && !worldNames.add(worldName)) {
                    throw new IllegalArgumentException("Duplicate personal campus owner, entry or world.");
                }
            }
        } catch (IllegalArgumentException exception) {
            throw new IOException("Malformed party registry; no partial roster was loaded.", exception);
        }
        return Collections.unmodifiableMap(campuses);
    }

    void save(Map<String, Campus> campuses) throws IOException {
        YamlConfiguration yaml = new YamlConfiguration();
        yaml.set("schema-version", 1);
        List<Map<String, Object>> serialized = new ArrayList<>();
        for (Campus campus : campuses.values()) {
            Map<String, Object> values = new LinkedHashMap<>();
            values.put("owner", campus.ownerKey());
            values.put("owner-label", campus.ownerLabel());
            values.put("entry", campus.entryId().toString());
            values.put("world", campus.worldName());
            values.put("phase", campus.phase().name());
            values.put("last-invite-at", campus.lastInviteAt().toString());
            List<Map<String, Object>> guests = new ArrayList<>();
            campus.guests().forEach((identity, label) -> guests.add(Map.of("identity", identity, "label", label)));
            values.put("guests", guests);
            List<Map<String, Object>> invitations = new ArrayList<>();
            campus.invitations().forEach((identity, invitation) -> {
                Map<String, Object> invite = new LinkedHashMap<>();
                invite.put("identity", identity);
                invite.put("label", invitation.label());
                invite.put("token", invitation.token().toString());
                invite.put("issued-at", invitation.issuedAt().toString());
                invite.put("expires-at", invitation.expiresAt().toString());
                invitations.add(invite);
            });
            values.put("invitations", invitations);
            serialized.add(values);
        }
        yaml.set("campuses", serialized);
        Files.createDirectories(file.getParent());
        if (Files.exists(file, LinkOption.NOFOLLOW_LINKS) && !Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Party registry must be a regular file.");
        }
        Path temporary = Files.createTempFile(file.getParent(), "parties-", ".tmp");
        try {
            byte[] contents = yaml.saveToString().getBytes(StandardCharsets.UTF_8);
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING)) {
                ByteBuffer buffer = ByteBuffer.wrap(contents);
                while (buffer.hasRemaining()) channel.write(buffer);
                channel.force(true);
            }
            Files.move(temporary, file, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static Map<?, ?> objectMap(Object value) {
        if (!(value instanceof Map<?, ?> values)) throw new IllegalArgumentException("Expected a record.");
        return values;
    }

    private static List<?> objectList(Map<?, ?> values, String key) {
        if (!(values.get(key) instanceof List<?> list)) throw new IllegalArgumentException("Expected list: " + key);
        return list;
    }

    private static String text(Map<?, ?> values, String key) {
        String value = optionalText(values, key);
        if (value.isBlank()) throw new IllegalArgumentException("Missing text: " + key);
        return value;
    }

    private static String optionalText(Map<?, ?> values, String key) {
        if (!(values.get(key) instanceof String value) || value.length() > 512
                || value.chars().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("Invalid text: " + key);
        }
        return value;
    }

    enum Phase { PROVISIONING, READY, LOCKED }

    record Invitation(String label, Instant issuedAt, Instant expiresAt, UUID token) {
        Invitation(String label, Instant issuedAt, Instant expiresAt) {
            this(label, issuedAt, expiresAt, UUID.randomUUID());
        }

        boolean active(Instant now) { return expiresAt.isAfter(now); }
    }

    record Campus(String ownerKey, String ownerLabel, UUID entryId, String worldName, Phase phase,
                  Map<String, String> guests, Map<String, Invitation> invitations, Instant lastInviteAt) {
        Campus {
            guests = Collections.unmodifiableMap(new LinkedHashMap<>(guests));
            invitations = Collections.unmodifiableMap(new LinkedHashMap<>(invitations));
        }

        Campus allocation(String allocatedWorld) {
            return new Campus(ownerKey, ownerLabel, entryId, allocatedWorld, phase, guests, invitations, lastInviteAt);
        }

        Campus phase(Phase next) {
            return new Campus(ownerKey, ownerLabel, entryId, worldName, next, guests, invitations, lastInviteAt);
        }

        Campus roster(Map<String, String> nextGuests, Map<String, Invitation> nextInvitations, Instant inviteAt) {
            return new Campus(ownerKey, ownerLabel, entryId, worldName, phase, nextGuests, nextInvitations, inviteAt);
        }
    }
}
