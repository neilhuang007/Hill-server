package org.thehill.hill175.navigation;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.auth.GameIdentityResolver;

import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Predicate;

public final class SurvivalNavigation implements CommandExecutor {
    private final Predicate<Player> authenticated;
    private final Consumer<Player> localSurvival;
    private final GameIdentityResolver identities;
    private final String mode;
    private final String host;
    private final int port;
    private final boolean bedrockLocal;

    public SurvivalNavigation(JavaPlugin plugin, Predicate<Player> authenticated, Consumer<Player> localSurvival) {
        this.authenticated = authenticated;
        this.localSurvival = localSurvival;
        mode = System.getenv().getOrDefault("HILL175_SURVIVAL_MODE",
                plugin.getConfig().getString("survival-navigation.mode", "local")).toLowerCase(Locale.ROOT);
        if (!mode.equals("local") && !mode.equals("transfer") && !mode.equals("disabled")) {
            throw new IllegalArgumentException("survival-navigation.mode must be local, transfer or disabled.");
        }
        host = System.getenv().getOrDefault("HILL175_SURVIVAL_JAVA_HOST",
                plugin.getConfig().getString("survival-navigation.java-host", "")).trim();
        port = Integer.parseInt(System.getenv().getOrDefault("HILL175_SURVIVAL_JAVA_PORT",
                Integer.toString(plugin.getConfig().getInt("survival-navigation.java-port", 25567))));
        bedrockLocal = flag("HILL175_SURVIVAL_BEDROCK_LOCAL",
                plugin.getConfig().getBoolean("survival-navigation.bedrock-local", true));
        if (mode.equals("transfer")) {
            if (!host.matches("[A-Za-z0-9][A-Za-z0-9.-]{0,252}") || port < 1 || port > 65535) {
                throw new IllegalArgumentException("Configure a valid Java survival hostname and port.");
            }
            if (!flag("HILL175_SURVIVAL_DESTINATION_ACCESS_CONFIGURED",
                    plugin.getConfig().getBoolean("survival-navigation.destination-access-configured", false))) {
                throw new IllegalArgumentException("Secure destination admission before enabling survival transfer.");
            }
            identities = new GameIdentityResolver(plugin);
        } else {
            identities = null;
        }
    }

    private static boolean flag(String key, boolean fallback) {
        String value = System.getenv(key);
        if (value == null) return fallback;
        if (!value.equals("true") && !value.equals("false")) throw new IllegalArgumentException(key + " must be true or false.");
        return Boolean.parseBoolean(value);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] arguments) {
        if (sender instanceof Player player) travel(player);
        else sender.sendMessage("Use /survival in game.");
        return true;
    }

    public void travel(Player player) {
        if (!authenticated.test(player)) {
            player.sendMessage(Component.text("Sign in first, then use /survival.", NamedTextColor.YELLOW));
            return;
        }
        if (mode.equals("disabled")) {
            player.sendMessage(Component.text("Survival is not available yet.", NamedTextColor.YELLOW));
            return;
        }
        if (mode.equals("local")) {
            localSurvival.accept(player);
            return;
        }
        try {
            if (identities.resolve(player).startsWith("bedrock:")) {
                if (bedrockLocal) localSurvival.accept(player);
                else player.sendMessage(Component.text("This survival server is Java-only. Use /campus or /hub.", NamedTextColor.YELLOW));
                return;
            }
            player.sendMessage(Component.text("Connecting to Java survival. Rejoin the campus address to return.", NamedTextColor.GREEN));
            player.transfer(host, port);
        } catch (IllegalStateException exception) {
            player.sendMessage(Component.text("Survival transfer is unavailable. Please contact staff.", NamedTextColor.RED));
        }
    }
}
