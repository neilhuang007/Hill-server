package org.thehill.hill175.auth;

import org.bukkit.Server;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.PluginManager;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.auth.sso.GameIdentity;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class GameIdentityResolverTest {
    @Test
    void rejectsOfflineJavaTransportEvenWhenSchoolSsoIsAvailable() {
        JavaPlugin plugin = plugin(false);
        assertThrows(IllegalStateException.class, () -> new GameIdentityResolver(plugin));
    }

    @Test
    void derivesJavaIdentityFromVerifiedUuidNotMutableName() {
        JavaPlugin plugin = plugin(true);
        Player player = mock(Player.class);
        UUID id = UUID.randomUUID();
        when(player.getUniqueId()).thenReturn(id);
        when(player.getName()).thenReturn(".LooksLikeBedrock");
        assertEquals("java:" + id, new GameIdentityResolver(plugin).resolve(player));
    }

    @Test
    void installedButDisabledFloodgateCannotSilentlyFallBackToJava() {
        JavaPlugin plugin = plugin(true);
        when(plugin.getServer().getPluginManager().getPlugin("floodgate")).thenReturn(mock(Plugin.class));
        assertThrows(IllegalStateException.class, () -> new GameIdentityResolver(plugin));
    }

    @Test
    void rejectsInvalidOrNoncanonicalBedrockXuids() {
        assertEquals("bedrock:2533274800000000", GameIdentity.bedrock("2533274800000000"));
        for (String xuid : new String[]{"", "0", "001", "-1", "123abc", "18446744073709551616"}) {
            assertThrows(IllegalArgumentException.class, () -> GameIdentity.bedrock(xuid));
        }
        assertThrows(IllegalArgumentException.class, () -> GameIdentity.bedrock(null));
    }

    private static JavaPlugin plugin(boolean online) {
        JavaPlugin plugin = mock(JavaPlugin.class);
        Server server = mock(Server.class);
        when(plugin.getServer()).thenReturn(server);
        when(server.getOnlineMode()).thenReturn(online);
        when(server.getPluginManager()).thenReturn(mock(PluginManager.class));
        return plugin;
    }
}
