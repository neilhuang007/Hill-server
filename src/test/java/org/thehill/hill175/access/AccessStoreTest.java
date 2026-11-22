package org.thehill.hill175.access;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class AccessStoreTest {
    @TempDir Path directory;
    private static final String SUBJECT = "entra:76b02f9e-4050-43db-807c-e05e683be3de:8ef143d9-8b69-43b8-b1fb-5ddc68f8b4e4";
    private static final Instant NOW = Instant.parse("2026-11-09T12:00:00Z");

    @Test void roleBanMuteAndLinkedProfilesSurviveRestartAndApplyToBothEditions() throws Exception {
        Path file = directory.resolve("moderation.json");
        UUID java = UUID.randomUUID(), bedrock = UUID.randomUUID();
        try (var store = new AccessStore(file)) {
            store.remember(java, "JavaName", "Hill Person", SUBJECT, ServerRole.PLAYER);
            store.remember(bedrock, ".BedrockName", "Hill Person", SUBJECT, ServerRole.PLAYER);
            store.change(SUBJECT, "role", "MODERATOR", "console", NOW, Instant.MAX);
            store.change(SUBJECT, "ban", "Griefing", "console", NOW, Instant.MAX);
            store.change(SUBJECT, "mute", "Chat abuse", "console", NOW, NOW.plusSeconds(600));
        }
        try (var store = new AccessStore(file)) {
            assertEquals(ServerRole.MODERATOR, store.account(store.profile(java).orElseThrow().subject()).role());
            assertTrue(store.account(store.profile(bedrock).orElseThrow().subject()).ban().active(NOW));
            assertTrue(store.account(SUBJECT).mute().active(NOW.plusSeconds(599)));
            assertFalse(store.account(SUBJECT).mute().active(NOW.plusSeconds(600)));
            store.change(SUBJECT, "unban", "", "console", NOW, Instant.MAX);
            store.change(SUBJECT, "unmute", "", "console", NOW, Instant.MAX);
        }
        try (var store = new AccessStore(file)) {
            assertNull(store.account(SUBJECT).ban());
            assertNull(store.account(SUBJECT).mute());
            assertTrue(Files.readString(file).contains("Griefing"));
        }
    }

    @Test void refreshedMicrosoftRoleDoesNotEraseLocalRoleOrSanctions() throws Exception {
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            UUID id = UUID.randomUUID();
            store.remember(id, "GameName", "Hill Person", SUBJECT, ServerRole.ADMINISTRATOR);
            assertEquals(ServerRole.ADMINISTRATOR, store.account(SUBJECT).role());
            store.change(SUBJECT, "ban", "Reason", "console", NOW, Instant.MAX);
            store.change(SUBJECT, "role", "STAFF", "console", NOW, Instant.MAX);
            store.remember(id, "Renamed", "Updated Hill Person", SUBJECT, ServerRole.PLAYER);
            assertEquals(ServerRole.STAFF, store.account(SUBJECT).role());
            assertNotNull(store.account(SUBJECT).ban());
            assertEquals("Updated Hill Person", store.profile(id).orElseThrow().displayName());
        }
    }

    @Test void corruptOrAlreadyLockedRecordsPreventStartupAndFailedWritesDoNotDisappear() throws Exception {
        Path file = directory.resolve("moderation.json");
        try (var store = new AccessStore(file)) {
            assertThrows(java.io.IOException.class, () -> new AccessStore(file));
            store.change(SUBJECT, "ban", "Reason", "console", NOW, Instant.MAX);
        }
        Files.writeString(file, "{invalid");
        assertThrows(java.io.IOException.class, () -> new AccessStore(file));
    }

    @Test void schoolNamesAndEmailsCannotBecomeAuthorityKeys() {
        for (String invalid : new String[]{"Alex Smith", "alex@thehill.org", "entra:invalid:object", "game:1-1-1-1-1"}) {
            assertThrows(IllegalArgumentException.class, () -> AccessStore.validateSubject(invalid));
        }
    }
}
