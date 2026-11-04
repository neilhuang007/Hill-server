package org.thehill.hill175.backup;

import org.bukkit.Bukkit;
import org.bukkit.Server;
import org.bukkit.World;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class CampusBackupRecoveryTest {
    @TempDir Path folder;

    @Test
    void pendingLiveEditsAreFlushedBeforeTheSnapshotCopiesRegionFiles() throws Exception {
        Path campusFolder = Files.createDirectories(folder.resolve("world/dimensions/minecraft/hill_campus/region")).getParent();
        Path blocks = campusFolder.resolve("region/test.mca");
        Files.writeString(blocks, "stale disk state");
        JavaPlugin plugin = mock(JavaPlugin.class);
        Server server = mock(Server.class);
        World campus = mock(World.class);
        when(plugin.getServer()).thenReturn(server);
        when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
        when(server.getWorldContainer()).thenReturn(folder.toFile());
        when(campus.getWorldFolder()).thenReturn(campusFolder.toFile());
        doAnswer(invocation -> { Files.writeString(blocks, "newly placed blue wool"); return null; }).when(campus).save(true);
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(Bukkit::isPrimaryThread).thenReturn(true);
            bukkit.when(() -> Bukkit.getWorld("hill_campus")).thenReturn(campus);
            var service = new CampusBackupService(plugin, ignored -> true);
            String id = service.capture("immediate save after placement");
            Path saved = folder.resolve("campus-backups/shared-campus").resolve(id).resolve("hill_campus/region/test.mca");
            assertEquals("newly placed blue wool", Files.readString(saved));
        }
    }

    @Test
    void restartRecoveryRestoresOnlyCampusAndNeverRewindsIdentityData() throws Exception {
        Path campusFolder = Files.createDirectories(folder.resolve("world/dimensions/minecraft/hill_campus/region")).getParent();
        Path blocks = campusFolder.resolve("region/test.mca");
        Files.writeString(blocks, "campus before damage");
        Path identityFile = Files.createDirectories(folder.resolve("plugins/Hill175")).resolve("school-identities.json");
        Files.writeString(identityFile, "first identity");
        JavaPlugin plugin = mock(JavaPlugin.class);
        Server server = mock(Server.class);
        World campus = mock(World.class);
        World primary = mock(World.class);
        ConsoleCommandSender console = mock(ConsoleCommandSender.class);
        when(plugin.getServer()).thenReturn(server);
        when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
        when(server.getWorldContainer()).thenReturn(folder.toFile());
        when(campus.getWorldFolder()).thenReturn(campusFolder.toFile());
        when(primary.getName()).thenReturn("world");
        when(console.getName()).thenReturn("CONSOLE");
        when(console.hasPermission("hill175.campus.rollback")).thenReturn(true);
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(Bukkit::isPrimaryThread).thenReturn(true);
            bukkit.when(() -> Bukkit.getWorld("hill_campus")).thenReturn(campus);
            bukkit.when(Bukkit::getWorlds).thenReturn(List.of(primary));
            var service = new CampusBackupService(plugin, ignored -> true);
            String id = service.capture("test recovery point");
            Files.writeString(blocks, "campus damage");
            Files.writeString(identityFile, "new student identity must survive");
            service.requestRestore(console, id);
            assertTrue(service.isBusy());
            assertEquals(2, service.list().size());
            bukkit.when(() -> Bukkit.getWorld("hill_campus")).thenReturn(null);
            CampusBackupService.applyPendingRestore(plugin);
            assertEquals("campus before damage", Files.readString(blocks));
            assertEquals("new student identity must survive", Files.readString(identityFile));
            assertFalse(Files.exists(folder.resolve("campus-shared-restore-request.properties")));
            try (var preserved = Files.list(folder)) {
                Path original = preserved.filter(path -> path.getFileName().toString().startsWith("campus-before-restore-")).findFirst().orElseThrow();
                assertEquals("campus damage", Files.readString(original.resolve("hill_campus/region/test.mca")));
            }
        }
    }
}
