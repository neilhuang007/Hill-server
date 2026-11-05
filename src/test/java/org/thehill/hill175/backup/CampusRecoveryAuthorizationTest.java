package org.thehill.hill175.backup;

import org.bukkit.Server;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;

import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class CampusRecoveryAuthorizationTest {
    @TempDir Path folder;

    @Test void scopedStaffCannotRestoreAnotherAreaOrUsePermissionsBeforeSigningIn() {
        var plugin = mock(JavaPlugin.class);
        var server = mock(Server.class);
        when(plugin.getServer()).thenReturn(server);
        when(server.getWorldContainer()).thenReturn(folder.toFile());
        var first = new CampusRecoveryAreas.Area("area-s1", "Chapel", List.of(new BuildRegion("hill_campus", 0, -64, 0, 15, 319, 15)));
        var other = new CampusRecoveryAreas.Area("area-s7", "Hunt", List.of(new BuildRegion("hill_campus", 16, -64, 0, 31, 319, 15)));
        var signedIn = new AtomicBoolean(false);
        try (var recovery = new CampusRecoveryService(plugin, ignored -> signedIn.get(), List.of(first, other))) {
            var player = mock(Player.class);
            when(player.hasPermission("hill175.campus.rollback.area-s1")).thenReturn(true);
            assertThrows(SecurityException.class, () -> recovery.requireArea(player, first));
            signedIn.set(true);
            assertDoesNotThrow(() -> recovery.requireArea(player, first));
            assertThrows(SecurityException.class, () -> recovery.requireArea(player, other));
            when(player.hasPermission("hill175.campus.rollback")).thenReturn(true);
            assertDoesNotThrow(() -> recovery.requireArea(player, other));
        }
    }
}
