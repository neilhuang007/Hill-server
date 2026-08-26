package org.thehill.hill175.command;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.ui.MenuModule;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class CommandModule implements CommandExecutor, TabCompleter {
    private final CompetitionModule competition;
    private final MenuModule menus;

    public CommandModule(CompetitionModule competition, MenuModule menus) {
        this.competition = competition;
        this.menus = menus;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("This command is only available in-game.");
            return true;
        }
        return switch (command.getName().toLowerCase(Locale.ROOT)) {
            case "register" -> register(player, args);
            case "login" -> login(player, args);
            case "hill175", "competition" -> competitionMenu(player);
            case "hub", "lobby", "help" -> routedUtility(player, command.getName().toLowerCase(Locale.ROOT), args);
            case "rules" -> rules(player);
            case "entry" -> entry(player, args);
            case "team" -> team(player, args);
            case "camera" -> camera(player, args);
            default -> false;
        };
    }

    private boolean register(Player player, String[] args) {
        if (args.length != 3) {
            player.sendMessage("Usage: /register <username> <password> <repeatPassword>");
            return true;
        }
        competition.register(player, args[0], args[1], args[2]);
        return true;
    }

    private boolean login(Player player, String[] args) {
        if (args.length != 1) {
            player.sendMessage("Usage: /login <password>");
            return true;
        }
        competition.login(player, args[0]);
        return true;
    }

    private boolean competitionMenu(Player player) {
        if (!competition.isAuthenticated(player)) {
            competition.sendAuthenticationInstructions(player);
            return true;
        }
        menus.openMain(player);
        return true;
    }

    private boolean routedUtility(Player player, String commandName, String[] args) {
        if (commandName.equals("help")) {
            competition.sendHelp(player);
            return true;
        }
        if (!competition.isAuthenticated(player)) {
            competition.sendAuthenticationInstructions(player);
            return true;
        }
        competition.teleportHub(player);
        return true;
    }

    private boolean rules(Player player) {
        competition.sendRules(player);
        return true;
    }

    private boolean entry(Player player, String[] args) {
        if (!competition.isAuthenticated(player)) {
            competition.sendAuthenticationInstructions(player);
            return true;
        }
        if (args.length == 0) {
            menus.openMain(player);
            return true;
        }
        switch (args[0].toLowerCase(Locale.ROOT)) {
            case "create" -> {
                if (args.length != 2) {
                    player.sendMessage("Usage: /entry create <journey|place|people>");
                    return true;
                }
                Category.parse(args[1]).ifPresentOrElse(
                        category -> competition.createEntry(player, category),
                        () -> player.sendMessage("Unknown category. Use journey, place, or people.")
                );
            }
            case "home" -> {
                if (!competition.home(player)) {
                    menus.openMain(player);
                }
            }
            case "list" -> menus.openMain(player);
            case "visit" -> menus.openVisits(player, 0);
            case "reset" -> competition.resetCurrentEntry(player);
            case "delete" -> competition.deleteCurrentEntry(player);
            case "switch" -> {
                if (args.length != 2) {
                    player.sendMessage("Usage: /entry switch <journey|place|people>");
                    return true;
                }
                Category.parse(args[1]).ifPresentOrElse(
                        category -> competition.switchCurrentEntry(player, category),
                        () -> player.sendMessage("Unknown category. Use journey, place, or people.")
                );
            }
            case "title" -> {
                if (args.length < 2) {
                    player.sendMessage("Usage: /entry title <project title>");
                    return true;
                }
                competition.setTitle(player, joinFrom(args, 1));
            }
            case "description", "desc" -> {
                if (args.length < 2) {
                    player.sendMessage("Usage: /entry description <short description>");
                    return true;
                }
                competition.setDescription(player, joinFrom(args, 1));
            }
            case "submit" -> competition.submit(player);
            case "unlock" -> competition.unlock(player);
            default -> player.sendMessage("Entry commands: create, home, list, visit, reset, delete, switch, title, description, submit, unlock");
        }
        return true;
    }

    private boolean team(Player player, String[] args) {
        if (!competition.isAuthenticated(player)) {
            competition.sendAuthenticationInstructions(player);
            return true;
        }
        if (args.length == 0) {
            player.sendMessage("Team commands: /team invite <nickname>, /team accept <nickname>, /team leave");
            return true;
        }
        switch (args[0].toLowerCase(Locale.ROOT)) {
            case "invite" -> {
                if (args.length != 2) {
                    player.sendMessage("Usage: /team invite <nickname>");
                } else {
                    competition.invite(player, args[1]);
                }
            }
            case "accept" -> {
                if (args.length != 2) {
                    player.sendMessage("Usage: /team accept <inviterNickname>");
                } else {
                    competition.acceptInvite(player, args[1]);
                }
            }
            case "leave" -> competition.leaveTeam(player);
            default -> player.sendMessage("Team commands: invite, accept, leave");
        }
        return true;
    }

    private boolean camera(Player player, String[] args) {
        if (!competition.isAuthenticated(player)) {
            competition.sendAuthenticationInstructions(player);
            return true;
        }
        if (args.length == 0 || args[0].equalsIgnoreCase("save")) {
            competition.recordCamera(player);
            return true;
        }
        switch (args[0].toLowerCase(Locale.ROOT)) {
            case "list" -> competition.listCameras(player);
            case "preview" -> competition.previewNextCamera(player);
            case "remove" -> {
                if (args.length != 2) {
                    player.sendMessage("Usage: /camera remove <1-3>");
                    return true;
                }
                try {
                    competition.removeCamera(player, Integer.parseInt(args[1]));
                } catch (NumberFormatException ignored) {
                    player.sendMessage("Camera index must be 1, 2, or 3.");
                }
            }
            default -> player.sendMessage("Camera commands: save, list, preview, remove <1-3>");
        }
        return true;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        if (command.getName().equalsIgnoreCase("entry")) {
            if (args.length == 1) {
                return filter(args[0], List.of("create", "home", "list", "visit", "reset", "delete", "switch", "title", "description", "submit", "unlock"));
            }
            if (args.length == 2 && (args[0].equalsIgnoreCase("create") || args[0].equalsIgnoreCase("switch"))) {
                return filter(args[1], List.of("journey", "place", "people"));
            }
        }
        if (command.getName().equalsIgnoreCase("team") && args.length == 1) {
            return filter(args[0], List.of("invite", "accept", "leave"));
        }
        if (command.getName().equalsIgnoreCase("camera") && args.length == 1) {
            return filter(args[0], List.of("save", "list", "preview", "remove"));
        }
        return List.of();
    }

    private static String joinFrom(String[] args, int start) {
        return String.join(" ", Arrays.copyOfRange(args, start, args.length));
    }

    private static List<String> filter(String prefix, List<String> choices) {
        String normalized = prefix.toLowerCase(Locale.ROOT);
        List<String> result = new ArrayList<>();
        for (String choice : choices) {
            if (choice.startsWith(normalized)) {
                result.add(choice);
            }
        }
        return result;
    }
}
