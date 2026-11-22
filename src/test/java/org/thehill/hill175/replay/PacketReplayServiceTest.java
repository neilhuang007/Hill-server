package org.thehill.hill175.replay;

import org.bukkit.Bukkit;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.PluginCommand;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.plugin.PluginManager;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.MockedStatic;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class PacketReplayServiceTest {
    @Test void disabledDoesNotRequireRecorderButEnabledFailsClosed() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        YamlConfiguration config = new YamlConfiguration();
        when(plugin.getConfig()).thenReturn(config);
        PluginManager manager = mock(PluginManager.class);
        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(Bukkit::getPluginManager).thenReturn(manager);
            assertDoesNotThrow(() -> new PacketReplayService(plugin, player -> true).start());
            config.set("packet-replay.enabled", true);
            assertThrows(IllegalStateException.class, () -> new PacketReplayService(plugin, player -> true).start());
        }
    }

    @Test void upstreamCommandsAreDeniedEvenWhenCaptureIsDisabledOrJarUnpatched() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        JavaPlugin upstream = mock(JavaPlugin.class);
        YamlConfiguration config = new YamlConfiguration();
        when(plugin.getConfig()).thenReturn(config);
        when(upstream.isEnabled()).thenReturn(true);
        PluginCommand command = mock(PluginCommand.class);
        when(upstream.getCommand("replay")).thenReturn(command);
        PluginManager manager = mock(PluginManager.class);
        when(manager.getPlugin("FlashbackServer")).thenReturn(upstream);
        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(Bukkit::getPluginManager).thenReturn(manager);
            bukkit.when(Bukkit::getMinecraftVersion).thenReturn("26.2");
            new PacketReplayService(plugin, player -> true).start();
            ArgumentCaptor<CommandExecutor> executor = ArgumentCaptor.forClass(CommandExecutor.class);
            verify(command).setExecutor(executor.capture());
            CommandSender user = mock(CommandSender.class);
            assertTrue(executor.getValue().onCommand(user, command, "flashbackserver:replay", new String[]{"start"}));
            verify(user).sendMessage(contains("Raw replay controls are disabled"));
            config.set("packet-replay.enabled", true);
            assertThrows(IllegalStateException.class, () -> new PacketReplayService(plugin, player -> true).start());
        }
    }
}
