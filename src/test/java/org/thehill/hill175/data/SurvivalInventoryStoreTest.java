package org.thehill.hill175.data;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.logging.Logger;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SurvivalInventoryStoreTest {
    @TempDir
    Path tempDir;

    @Test
    void savesOneAtomicYamlFilePerUuid() throws Exception {
        UUID playerId = UUID.fromString("00000000-0000-0000-0000-000000000175");
        SurvivalInventoryStore store = new SurvivalInventoryStore(tempDir.toFile(), Logger.getAnonymousLogger());
        SurvivalPlayerState state = new SurvivalPlayerState(
                List.of(),
                List.of(),
                null,
                List.of(),
                List.of(),
                3,
                0.25f,
                42,
                18,
                6.0f,
                0.0f,
                19.0,
                300,
                0,
                new SurvivalLocationSnapshot("hill_survival", 0.5, 80.0, 0.5, 0.0f, 0.0f),
                null
        );

        store.save(playerId, state);

        Path expectedFile = tempDir.resolve("survival-inventories").resolve(playerId + ".yml");
        assertTrue(Files.isRegularFile(expectedFile));
        try (Stream<Path> files = Files.list(expectedFile.getParent())) {
            assertFalse(files.anyMatch(path -> path.getFileName().toString().endsWith(".tmp")));
        }
        SurvivalPlayerState loaded = store.load(playerId).orElseThrow();
        assertEquals(SurvivalPlayerState.STORAGE_SIZE, loaded.storage().size());
        assertEquals(3, loaded.level());
        assertEquals("hill_survival", loaded.location().orElseThrow().worldName());
    }

    @Test
    void corruptYamlFallsBackToMissingState() throws Exception {
        UUID playerId = UUID.fromString("00000000-0000-0000-0000-000000001851");
        Path directory = tempDir.resolve("survival-inventories");
        Files.createDirectories(directory);
        Files.writeString(directory.resolve(playerId + ".yml"), "inventory: [unterminated");

        SurvivalInventoryStore store = new SurvivalInventoryStore(tempDir.toFile(), Logger.getAnonymousLogger());

        assertTrue(store.load(playerId).isEmpty());
    }

    @Test
    void resumeIntentPersistsAcrossStoreInstances() throws Exception {
        UUID playerId = UUID.fromString("00000000-0000-0000-0000-000000001752");
        SurvivalInventoryStore store = new SurvivalInventoryStore(tempDir.toFile(), Logger.getAnonymousLogger());

        store.markActive(playerId);

        Path expectedFile = tempDir.resolve("survival-resume-intent").resolve(playerId + ".yml");
        assertTrue(Files.isRegularFile(expectedFile));
        assertTrue(store.isActive(playerId));
        assertTrue(new SurvivalInventoryStore(tempDir.toFile(), Logger.getAnonymousLogger()).isActive(playerId));
        try (Stream<Path> files = Files.list(expectedFile.getParent())) {
            assertFalse(files.anyMatch(path -> path.getFileName().toString().endsWith(".tmp")));
        }
    }

    @Test
    void markInactiveClearsOnlyResumeIntent() {
        UUID playerId = UUID.fromString("00000000-0000-0000-0000-000000001753");
        SurvivalInventoryStore store = new SurvivalInventoryStore(tempDir.toFile(), Logger.getAnonymousLogger());

        store.save(playerId, sampleState());
        store.markActive(playerId);
        store.markInactive(playerId);

        assertFalse(store.isActive(playerId));
        assertTrue(store.load(playerId).isPresent());
    }

    @Test
    void deathPendingMarkerPersistsUntilCleared() {
        UUID playerId = UUID.fromString("00000000-0000-0000-0000-000000001754");
        SurvivalInventoryStore store = new SurvivalInventoryStore(tempDir.toFile(), Logger.getAnonymousLogger());

        store.markDeathPending(playerId);

        assertTrue(store.isDeathPending(playerId));
        assertTrue(new SurvivalInventoryStore(tempDir.toFile(), Logger.getAnonymousLogger()).isDeathPending(playerId));
        store.clearDeathPending(playerId);
        assertFalse(store.isDeathPending(playerId));
    }

    private static SurvivalPlayerState sampleState() {
        return new SurvivalPlayerState(
                List.of(),
                List.of(),
                null,
                List.of(),
                List.of(),
                1,
                0.5f,
                7,
                20,
                5.0f,
                0.0f,
                20.0,
                300,
                0,
                new SurvivalLocationSnapshot("hill_survival", 12.5, 71.0, -4.5, 90.0f, 15.0f),
                null
        );
    }
}
