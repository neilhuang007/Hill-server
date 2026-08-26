package org.thehill.hill175;

import org.bukkit.Bukkit;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Mob;
import org.bukkit.entity.Player;
import org.bukkit.plugin.PluginManager;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.auth.AlwaysApproveIdentityLinker;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.command.CommandModule;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.data.YamlCompetitionStore;
import org.thehill.hill175.listener.ServerListener;
import org.thehill.hill175.ui.HubNpcModule;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import java.util.List;
import java.util.Objects;

public final class Hill175Plugin extends JavaPlugin {
    private CompetitionStore store;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        getConfig().options().copyDefaults(true);
        saveConfig();
        reloadConfig();
        if (!getConfig().getBoolean("authentication.development-stub-acknowledged", false)) {
            getLogger().severe("Development identity linking is not acknowledged in config.yml; refusing to start.");
            getServer().getPluginManager().disablePlugin(this);
            return;
        }
        getLogger().warning("DEVELOPMENT AUTHENTICATION IS ACTIVE: any unregistered offline nickname can be claimed while registration is open.");

        WorldModule worlds = new WorldModule(this);
        worlds.initialize();

        store = new YamlCompetitionStore(getDataFolder(), getLogger());
        IdentityLinker identityLinker = new AlwaysApproveIdentityLinker(
                getConfig().getString("authentication.stub-link-base-url", "https://example.invalid/hill175/link")
        );
        CompetitionModule competition = new CompetitionModule(
                this,
                store,
                worlds,
                new PasswordHasher(),
                identityLinker
        );
        MenuModule menus = new MenuModule(competition);
        HubNpcModule hubNpcs = new HubNpcModule(this, competition, menus, worlds);
        ServerListener serverListener = new ServerListener(this, competition, menus, worlds);
        CommandModule commands = new CommandModule(competition, menus);

        PluginManager pluginManager = getServer().getPluginManager();
        pluginManager.registerEvents(menus, this);
        pluginManager.registerEvents(hubNpcs, this);
        pluginManager.registerEvents(serverListener, this);

        for (String commandName : List.of("register", "login", "hill175", "competition", "hub", "lobby", "help", "rules", "entry", "team", "camera")) {
            var command = Objects.requireNonNull(getCommand(commandName), "Missing command in plugin.yml: " + commandName);
            command.setExecutor(commands);
            command.setTabCompleter(commands);
        }

        Bukkit.getScheduler().runTask(this, hubNpcs::spawnCategoryNpcs);
        Bukkit.getScheduler().runTask(this, competition::rebuildAllCameraMarkers);
        Bukkit.getScheduler().runTaskTimer(this, this::removeForbiddenMobsAndPrimedTnt, 20L, 20L);
        Bukkit.getScheduler().runTaskTimer(this, store::flush, 20L * 300L, 20L * 300L);

        for (Player onlinePlayer : Bukkit.getOnlinePlayers()) {
            competition.handleJoin(onlinePlayer);
        }
        getLogger().info("Hill 175 competition server enabled with development identity linking.");
    }

    @Override
    public void onDisable() {
        if (store != null) {
            store.flush();
        }
    }

    private void removeForbiddenMobsAndPrimedTnt() {
        for (var world : Bukkit.getWorlds()) {
            for (var entity : world.getEntities()) {
                if (entity instanceof Mob && !entity.getScoreboardTags().contains("hill175_category_npc")) {
                    entity.remove();
                } else if (entity.getType() == EntityType.TNT) {
                    entity.remove();
                }
            }
        }
    }
}
