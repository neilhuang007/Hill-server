package org.thehill.hill175.world;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SceneryTemplateTest {
    @TempDir Path server;
    private Path supplied;
    private Path legacy;
    private Path migrated;
    private Path record;

    @BeforeEach
    void supplyMap() throws Exception {
        supplied = server.resolve("world-templates/hill_hub");
        legacy = server.resolve("hill_hub");
        migrated = server.resolve("world/dimensions/minecraft/hill_hub");
        record = server.resolve("plugins/Hill175/imported-worlds.yml");
        write(supplied.resolve("level.dat"), "level");
        write(supplied.resolve("region/r.0.0.mca"), "terrain");
    }

    @Test
    void folderIsAMapOnlyWithLevelDataDirectlyInside() throws Exception {
        assertTrue(SceneryTemplate.isWorldSave(supplied));
        assertFalse(SceneryTemplate.isWorldSave(server.resolve("world-templates")));
        assertFalse(SceneryTemplate.isWorldSave(server.resolve("world-templates/hill_auth")));
    }

    @Test
    void installsWorldDataWithoutPlayerStateOrPlacementNotes() throws Exception {
        write(supplied.resolve("playerdata/owner.dat"), "inventory");
        write(supplied.resolve("advancements/owner.json"), "{}");
        write(supplied.resolve("session.lock"), "lock");
        write(supplied.resolve("uid.dat"), "uid");
        write(supplied.resolve(WorldPlacement.FILE_NAME), "spawn: [0, 64, 0]\n");

        assertTrue(install("first"));

        assertEquals("terrain", Files.readString(legacy.resolve("region/r.0.0.mca")));
        assertEquals("level", Files.readString(legacy.resolve("level.dat")));
        try (var installed = Files.walk(legacy)) {
            assertEquals(2, installed.filter(Files::isRegularFile).count());
        }
        assertFalse(Files.exists(server.resolve("hill_hub.importing")));
        assertFalse(Files.exists(server.resolve("replaced-worlds")));
    }

    @Test
    void unchangedMapIsNotImportedAgainOncePaperHasMigratedIt() throws Exception {
        assertTrue(install("first"));
        Files.createDirectories(migrated.getParent());
        Files.move(legacy, migrated);
        write(migrated.resolve("region/r.0.0.mca"), "terrain edited on the server");
        write(supplied.resolve(WorldPlacement.FILE_NAME), "spawn: [1, 64, 1]\n");

        assertFalse(install("second"));

        assertFalse(Files.exists(legacy));
        assertEquals("terrain edited on the server", Files.readString(migrated.resolve("region/r.0.0.mca")));
    }

    @Test
    void replacedMapKeepsThePreviousCopy() throws Exception {
        assertTrue(install("first"));
        Files.createDirectories(migrated.getParent());
        Files.move(legacy, migrated);
        String before = SceneryTemplate.fingerprint(supplied);
        write(supplied.resolve("region/r.0.0.mca"), "new terrain");
        assertNotEquals(before, SceneryTemplate.fingerprint(supplied));

        assertTrue(install("second"));

        assertEquals("new terrain", Files.readString(legacy.resolve("region/r.0.0.mca")));
        assertFalse(Files.exists(migrated));
        assertEquals("terrain", Files.readString(
                server.resolve("replaced-worlds/second/modern/region/r.0.0.mca")));
    }

    @Test
    void installedWorldOfUnknownOriginIsKeptBeforeTheSuppliedMapReplacesIt() throws Exception {
        write(migrated.resolve("region/r.0.0.mca"), "installed by an earlier release");

        assertTrue(install("first"));

        assertEquals("terrain", Files.readString(legacy.resolve("region/r.0.0.mca")));
        assertEquals("installed by an earlier release", Files.readString(
                server.resolve("replaced-worlds/first/modern/region/r.0.0.mca")));
    }

    @Test
    void missingWorldIsRestoredFromTheSameMap() throws Exception {
        assertTrue(install("first"));
        Files.delete(legacy.resolve("region/r.0.0.mca"));
        Files.delete(legacy.resolve("region"));
        Files.delete(legacy.resolve("level.dat"));
        Files.delete(legacy);

        assertTrue(install("second"));

        assertEquals("terrain", Files.readString(legacy.resolve("region/r.0.0.mca")));
    }

    private boolean install(String retainedName) throws Exception {
        return SceneryTemplate.install(supplied, "hill_hub", legacy, migrated,
                server.resolve("replaced-worlds").resolve(retainedName), record);
    }

    private static void write(Path file, String content) throws Exception {
        Files.createDirectories(file.getParent());
        Files.writeString(file, content);
    }
}
