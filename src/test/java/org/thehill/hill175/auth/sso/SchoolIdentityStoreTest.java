package org.thehill.hill175.auth.sso;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.*;

class SchoolIdentityStoreTest {
    @TempDir Path directory;
    static SchoolIdentity identity(String name) {
        return new SchoolIdentity("entra:" + SsoConfigTest.config().tenantId() + ":" + UUID.randomUUID(), name, Instant.now().plusSeconds(3600));
    }

    @Test void javaAndBedrockLinkToOneParticipantAndCannotBeReassigned() throws Exception {
        Path file = directory.resolve("identities.json");
        SchoolIdentity person = identity("A Student");
        String java = "java:" + UUID.randomUUID();
        try (var store = new SchoolIdentityStore(file)) {
            store.link(java, person, 2); store.link("bedrock:123456", person, 2);
            assertThrows(SsoException.class, () -> store.link("bedrock:987654", person, 2));
            assertThrows(SsoException.class, () -> store.link(java, identity("Other Student"), 2));
            store.link(java, new SchoolIdentity(person.participantKey(), "Updated Name", person.tokenExpiresAt()), 2);
        }
        try (var restored = new SchoolIdentityStore(file)) {
            assertEquals("Updated Name", restored.nameLookup(person.participantKey()).orElseThrow());
            assertThrows(SsoException.class, () -> restored.link(java, identity("Other Student"), 2));
        }
        String saved = Files.readString(file);
        assertFalse(saved.contains("token")); assertFalse(saved.contains("password")); assertFalse(saved.contains("secret"));
    }

    @Test void corruptStoreAndSecondProcessFailClosed() throws Exception {
        Path file = directory.resolve("identities.json");
        try (var store = new SchoolIdentityStore(file)) {
            assertThrows(IOException.class, () -> new SchoolIdentityStore(file));
        }
        Files.writeString(file, "{invalid");
        assertThrows(IOException.class, () -> new SchoolIdentityStore(file));
    }

    @Test void failedAtomicWriteDoesNotUpdateInMemoryIdentity() throws Exception {
        Path file = directory.resolve("identities.json");
        try (var store = new SchoolIdentityStore(file)) {
            Files.createDirectory(file);
            SchoolIdentity person = identity("A Student");
            assertThrows(SsoException.class, () -> store.link("bedrock:123456", person, 4));
            assertTrue(store.nameLookup(person.participantKey()).isEmpty());
            Files.delete(file);
            assertThrows(SsoException.class, () -> store.link("bedrock:123456", identity("Other Student"), 4));
            assertFalse(Files.exists(file));
        }
    }

    @Test void concurrentCompetingClaimsHaveExactlyOneWinner() throws Exception {
        Path file = directory.resolve("identities.json");
        try (var store = new SchoolIdentityStore(file); var executor = Executors.newFixedThreadPool(2)) {
            CountDownLatch ready = new CountDownLatch(1);
            var first = executor.submit(() -> { ready.await(); try { store.link("bedrock:123456", identity("One"), 4); return true; } catch (SsoException expected) { return false; } });
            var second = executor.submit(() -> { ready.await(); try { store.link("bedrock:123456", identity("Two"), 4); return true; } catch (SsoException expected) { return false; } });
            ready.countDown(); assertNotEquals(first.get(), second.get());
        }
    }
}
