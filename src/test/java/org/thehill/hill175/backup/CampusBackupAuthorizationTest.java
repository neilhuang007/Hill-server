package org.thehill.hill175.backup;

import org.bukkit.Server;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.function.Predicate;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class CampusBackupAuthorizationTest {
    @TempDir Path folder;

    @Test
    void rollbackRequiresStaffPermissionAndPlayerAuthentication() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        Server server = mock(Server.class);
        when(plugin.getServer()).thenReturn(server);
        when(server.getWorldContainer()).thenReturn(folder.toFile());
        @SuppressWarnings("unchecked") Predicate<Player> authenticated = mock(Predicate.class);
        var service = new CampusBackupService(plugin, authenticated);
        Player student = mock(Player.class);
        assertThrows(SecurityException.class, () -> service.requireOperator(student));
        when(student.hasPermission("hill175.campus.rollback")).thenReturn(true);
        assertThrows(SecurityException.class, () -> service.requireOperator(student));
        when(authenticated.test(student)).thenReturn(true);
        assertDoesNotThrow(() -> service.requireOperator(student));
        CommandSender console = mock(CommandSender.class);
        when(console.hasPermission("hill175.campus.rollback")).thenReturn(true);
        assertDoesNotThrow(() -> service.requireOperator(console));
    }
}
