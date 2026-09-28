package org.thehill.hill175.auth;

import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.auth.sso.GameIdentity;

import java.lang.reflect.Method;
import java.util.UUID;

/** Uses authenticated transport identities, never names or a Bedrock username prefix. */
public final class GameIdentityResolver {
    private final Object floodgateApi;
    private final Method getFloodgatePlayer;
    private final Method getXuid;

    public GameIdentityResolver(JavaPlugin plugin) {
        if (!plugin.getServer().getOnlineMode()) {
            throw new IllegalStateException("Microsoft authentication requires server.properties online-mode=true.");
        }
        Plugin floodgate = plugin.getServer().getPluginManager().getPlugin("floodgate");
        if (floodgate == null) {
            floodgateApi = null;
            getFloodgatePlayer = null;
            getXuid = null;
            return;
        }
        if (!floodgate.isEnabled()) {
            throw new IllegalStateException("Installed Floodgate must be enabled before Hill175 authentication starts.");
        }
        try {
            ClassLoader loader = floodgate.getClass().getClassLoader();
            Class<?> apiType = Class.forName("org.geysermc.floodgate.api.FloodgateApi", true, loader);
            floodgateApi = apiType.getMethod("getInstance").invoke(null);
            getFloodgatePlayer = apiType.getMethod("getPlayer", UUID.class);
            getXuid = getFloodgatePlayer.getReturnType().getMethod("getXuid");
            if (floodgateApi == null) {
                throw new IllegalStateException("Floodgate API is unavailable.");
            }
        } catch (ReflectiveOperationException exception) {
            throw new IllegalStateException("Installed Floodgate has an unsupported identity API.", exception);
        }
    }

    public String resolve(Player player) {
        if (floodgateApi != null) {
            try {
                Object bedrockPlayer = getFloodgatePlayer.invoke(floodgateApi, player.getUniqueId());
                if (bedrockPlayer != null) {
                    String xuid = (String) getXuid.invoke(bedrockPlayer);
                    return GameIdentity.bedrock(xuid);
                }
            } catch (ReflectiveOperationException exception) {
                throw new IllegalStateException("Cannot verify this connection's Floodgate identity.", exception);
            }
        }
        return "java:" + player.getUniqueId();
    }

}
