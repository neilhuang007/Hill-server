package org.thehill.hill175.backup;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class RecoveryPreviewFilesTest {
    @TempDir Path folder;
    @Test void previewUsesThePrimaryLevelRootInsteadOfTheOverworldDimensionFolder() {
        var plugin = mock(org.bukkit.plugin.java.JavaPlugin.class);
        var server = mock(org.bukkit.Server.class);
        var primary = mock(org.bukkit.World.class);
        when(plugin.getServer()).thenReturn(server);
        when(server.getWorldContainer()).thenReturn(folder.toFile());
        when(primary.getName()).thenReturn("world");
        when(primary.getWorldFolder()).thenReturn(folder.resolve("world/dimensions/minecraft/overworld").toFile());
        try (var bukkit = mockStatic(org.bukkit.Bukkit.class)) {
            bukkit.when(org.bukkit.Bukkit::getWorlds).thenReturn(java.util.List.of(primary));
            assertEquals(folder.resolve("world/dimensions/minecraft"), CampusRecoveryPreview.dimensionRoot(plugin));
        }
    }
    @Test void cleanupRequiresTheExactMarkerAndAnIsolatedDimensionFolder() throws Exception {
        String name = "hill_recovery_0123456789abcdef0123456789abcdef";
        Path world = Files.createDirectories(folder.resolve("dimensions/minecraft").resolve(name));
        Path data = Files.writeString(world.resolve("keep.mca"), "snapshot data");
        assertThrows(java.io.IOException.class, () -> CampusRecoveryPreview.deleteWorldFolder(world));
        assertTrue(Files.exists(data));
        Files.writeString(world.resolve(".hill175-recovery-preview"), "different world");
        assertThrows(java.io.IOException.class, () -> CampusRecoveryPreview.deleteWorldFolder(world));
        assertTrue(Files.exists(data));
        Files.writeString(world.resolve(".hill175-recovery-preview"), name);
        CampusRecoveryPreview.deleteWorldFolder(world);
        assertFalse(Files.exists(world));
        assertTrue(Files.isDirectory(folder.resolve("dimensions/minecraft")));
    }
}
