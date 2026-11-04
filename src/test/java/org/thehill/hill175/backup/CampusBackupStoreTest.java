package org.thehill.hill175.backup;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CampusBackupStoreTest {
    @TempDir Path folder;

    @Test
    void backupRestoresWorldAndPluginDataAndPreservesCurrentState() throws Exception {
        Path world = Files.createDirectory(folder.resolve("world"));
        Path plugin = Files.createDirectory(folder.resolve("plugin"));
        Files.writeString(world.resolve("blocks"), "accepted campus");
        Files.writeString(plugin.resolve("owners"), "student ownership");
        var backups = new CampusBackupStore(folder.resolve("backups"));
        String id = backups.capture(Map.of("hill_campus", world, "plugin", plugin), "smoke");
        Files.writeString(world.resolve("blocks"), "griefed campus");
        Files.writeString(plugin.resolve("owners"), "changed ownership");
        var staged = backups.stageRestore(id, folder.resolve("stage"));
        var destinations = Map.of("hill_campus", world, "plugin", plugin);
        CampusBackupStore.replaceStaged(staged, destinations, folder.resolve("preserved"));
        assertEquals("accepted campus", Files.readString(world.resolve("blocks")));
        assertEquals("student ownership", Files.readString(plugin.resolve("owners")));
        assertEquals("griefed campus", Files.readString(folder.resolve("preserved/hill_campus/blocks")));
        assertEquals("changed ownership", Files.readString(folder.resolve("preserved/plugin/owners")));
        CampusBackupStore.replaceStaged(staged, destinations, folder.resolve("preserved"));
        assertEquals("accepted campus", Files.readString(world.resolve("blocks")));
        assertEquals(1, backups.list().size());
    }

    @Test
    void interruptedDirectorySwapResumesWithoutDeletingOriginal() throws Exception {
        Path world = Files.createDirectory(folder.resolve("world"));
        Files.writeString(world.resolve("blocks"), "before");
        var backups = new CampusBackupStore(folder.resolve("backups"));
        String id = backups.capture(Map.of("hill_campus", world), "test");
        var staged = backups.stageRestore(id, folder.resolve("stage"));
        Files.writeString(world.resolve("blocks"), "after");
        Path preserved = Files.createDirectory(folder.resolve("preserved"));
        Files.move(world, preserved.resolve("hill_campus"));
        CampusBackupStore.replaceStaged(staged, Map.of("hill_campus", world), preserved);
        assertEquals("before", Files.readString(world.resolve("blocks")));
        assertEquals("after", Files.readString(preserved.resolve("hill_campus/blocks")));
    }

    @Test
    void refusesTamperedAndUnlistedBackupFilesAndTraversalNames() throws Exception {
        Path world = Files.createDirectory(folder.resolve("world"));
        Files.writeString(world.resolve("blocks"), "before");
        var backups = new CampusBackupStore(folder.resolve("backups"));
        String id = backups.capture(Map.of("hill_campus", world), "test");
        Files.writeString(folder.resolve("backups").resolve(id).resolve("hill_campus/blocks"), "tampered");
        assertThrows(IOException.class, () -> backups.verify(id));
        assertThrows(IllegalArgumentException.class, () -> backups.verify("../world"));
        String second = backups.capture(Map.of("hill_campus", world), "second");
        Files.writeString(folder.resolve("backups").resolve(second).resolve("surprise"), "unlisted");
        assertThrows(IOException.class, () -> backups.verify(second));
    }

    @Test
    void refusesRecursiveBackupSource() throws Exception {
        var backups = new CampusBackupStore(folder.resolve("backups"));
        assertThrows(IOException.class, () -> backups.capture(Map.of("plugin", folder), "invalid"));
    }
}
