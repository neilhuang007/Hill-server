package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.world.WorldModule;

import java.util.List;
import java.util.Locale;

/** Shared campus map and navigation for authenticated builders. */
public final class CampusWorkshop implements CommandExecutor, TabCompleter {
    private final CompetitionModule competition;
    private final WorldModule worlds;
    private CampusMapMenu map;

    public CampusWorkshop(CompetitionModule competition, WorldModule worlds) {
        this.competition = competition;
        this.worlds = worlds;
    }

    public void map(CampusMapMenu map) { this.map = java.util.Objects.requireNonNull(map); }

    public void open(Player player) {
        if (!competition.isAuthenticated(player)) { competition.sendAuthenticationInstructions(player); return; }
        map.open(player);
    }

    public void select(Player player, CampusMapMenu.Selection selection) {
        if (!competition.isAuthenticated(player)) return;
        if (!competition.enterSharedCampus(player)) return;
        player.closeInventory();
        if (selection.building() != null) competition.travelToBuilding(player, selection.building().id());
        else if (!selection.entireCampus()) competition.travelToCampusPoint(player, selection.x(), selection.z());
        player.sendMessage(Component.text("Build together anywhere inside the campus boundary. Staff can restore saved backups.", NamedTextColor.GREEN));
    }

    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) { sender.sendMessage("Open the campus menu from Minecraft."); return true; }
        if (!competition.isAuthenticated(player)) { competition.sendAuthenticationInstructions(player); return true; }
        String action = args.length == 0 ? "map" : args[0].toLowerCase(Locale.ROOT);
        switch (action) {
            case "map", "start" -> open(player);
            case "home" -> competition.enterSharedCampus(player);
            case "undo" -> competition.undoRecentBuild(player);
            case "go" -> {
                if (args.length == 2) competition.travelToBuilding(player, args[1]);
                else player.sendMessage("Usage: /campus go <building>");
            }
            default -> player.sendMessage("Campus controls: /campus, /campus home, /campus go <building>, /campus undo");
        }
        return true;
    }

    @Override public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        if (!(sender instanceof Player player) || !competition.isAuthenticated(player)) return List.of();
        List<String> choices = args.length == 1 ? List.of("map", "home", "go", "undo")
                : args.length == 2 && args[0].equalsIgnoreCase("go")
                ? worlds.buildings().stream().map(value -> value.id()).toList() : List.of();
        String prefix = args.length == 0 ? "" : args[args.length - 1].toLowerCase(Locale.ROOT);
        return choices.stream().filter(value -> value.startsWith(prefix)).toList();
    }
}
