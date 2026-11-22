package org.thehill.hill175.blueprint;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

public final class BlueprintCommands implements CommandExecutor, TabCompleter {
    private final BlueprintService service;

    BlueprintCommands(BlueprintService service) { this.service = service; }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] arguments) {
        try {
            service.requireAuthenticated(sender);
            if (command.getName().equalsIgnoreCase("review")) service.openReview(requirePlayer(sender));
            else execute(sender, arguments);
        } catch (IOException | UncheckedIOException | IllegalArgumentException | IllegalStateException | SecurityException exception) {
            sender.sendMessage("Blueprint: " + exception.getMessage());
        }
        return true;
    }

    private void execute(CommandSender sender, String[] arguments) throws IOException {
        String action = arguments.length == 0 ? "menu" : arguments[0].toLowerCase(Locale.ROOT);
        switch (action) {
            case "menu" -> {
                if (sender instanceof Player player) service.openMenu(player);
                else help(sender);
            }
            case "visit" -> service.visit(requirePlayer(sender));
            case "send", "submit" -> service.screens().send(requirePlayer(sender));
            case "fix", "conflicts", "sync" -> service.screens().conflicts(requirePlayer(sender));
            case "cancel", "withdraw" -> sender.sendMessage(service.cancel(requirePlayer(sender))
                    ? "Your waiting request was cancelled. Your campus is unchanged." : "You have no request waiting for approval.");
            case "news", "changes" -> service.visitChanges(requirePlayer(sender), arguments.length == 1 ? null : Long.valueOf(arguments[1]));
            case "list", "history" -> list(sender, action.equals("history"));
            case "review" -> service.openReview(requirePlayer(sender));
            case "edit" -> service.startEditing(requirePlayer(sender));
            case "save" -> service.saveEdits(sender);
            case "approve" -> approve(sender, arguments);
            case "reject" -> reject(sender, arguments);
            case "backup" -> backup(sender);
            case "backups" -> showBackups(sender);
            case "help" -> help(sender);
            default -> throw new IllegalArgumentException("Unknown blueprint action. Use /blueprint help.");
        }
    }

    private void help(CommandSender sender) {
        sender.sendMessage("/blueprint — send your build, the same as the emerald in your campus hotbar.");
        sender.sendMessage("/blueprint visit — walk around the shared blueprint (look only).");
        List<String> actions = service.allowedActions(sender);
        if (actions.contains("send")) {
            sender.sendMessage("/blueprint send — fly to each change: green dye sends, red dye skips, Box Corners draw your own box.");
            sender.sendMessage("/blueprint fix — choose what to keep where the blueprint changed blocks you also changed.");
        }
        if (actions.contains("review")) {
            sender.sendMessage("/review — fly to each waiting build on the blueprint; the hotbar has Accept and Reject. /review again stops.");
            sender.sendMessage("/blueprint edit — build directly in the shared blueprint; /blueprint save (or leaving it) sends the edits to every campus.");
            sender.sendMessage("Advanced: /blueprint approve <id> confirm [keep-blueprint|use-student] or /blueprint reject <id> <reason>.");
        }
        if (actions.contains("backup")) sender.sendMessage("/blueprint backup or /blueprint backups — blueprint-only recovery snapshots; no broad restore command.");
    }

    private void list(CommandSender sender, boolean history) throws IOException {
        var visible = service.repository().summaries().stream().filter(submission -> service.maySee(sender, submission))
                .filter(submission -> history || submission.status() == BlueprintRepository.Status.PENDING).limit(25).toList();
        if (visible.isEmpty()) { sender.sendMessage("No blueprint requests to show."); return; }
        boolean reviewer = service.allowedActions(sender).contains("review");
        for (var submission : visible) {
            Component message = Component.text(submission.title() + " | " + submission.status() + " | " + submission.changedBlocks() + " blocks | "
                    + submission.createdAt() + (reviewer ? " | " + submission.id() : ""));
            if (reviewer) message = message.clickEvent(ClickEvent.runCommand("/review"));
            sender.sendMessage(message);
            if (!submission.reason().isBlank()) sender.sendMessage("  " + submission.reason());
        }
    }

    private void reject(CommandSender sender, String[] arguments) throws IOException {
        if (arguments.length < 3) throw new IllegalArgumentException("Use /blueprint reject <id> <reason>.");
        service.reject(sender, id(arguments), String.join(" ", Arrays.copyOfRange(arguments, 2, arguments.length)));
        sender.sendMessage("Changes requested. The student keeps building and can send a new snapshot.");
    }

    private void approve(CommandSender sender, String[] arguments) throws IOException {
        service.requireReviewer(sender);
        if (arguments.length < 3 || arguments.length > 4 || !arguments[2].equals("confirm")) {
            throw new IllegalArgumentException("Inspect the request with /review first. To merge, use /blueprint approve <id> confirm [keep-blueprint|use-student].");
        }
        BlueprintService.ConflictChoice choice = arguments.length == 3 ? BlueprintService.ConflictChoice.REFUSE : switch (arguments[3].toLowerCase(Locale.ROOT)) {
            case "keep-blueprint" -> BlueprintService.ConflictChoice.KEEP_BLUEPRINT;
            case "use-student" -> BlueprintService.ConflictChoice.USE_PROPOSAL;
            default -> throw new IllegalArgumentException("Choose keep-blueprint or use-student for conflicting blocks.");
        };
        service.approve(sender, id(arguments), choice);
    }

    private void backup(CommandSender sender) throws IOException {
        service.requireBackupOperator(sender);
        sender.sendMessage("Blueprint-only recovery snapshot saved: " + service.captureBackup("Manual blueprint recovery snapshot"));
    }

    private void showBackups(CommandSender sender) throws IOException {
        service.requireBackupOperator(sender);
        List<String> backups = service.backups().list();
        if (backups.isEmpty()) { sender.sendMessage("No blueprint recovery snapshots yet."); return; }
        backups.stream().limit(20).forEach(sender::sendMessage);
    }

    private static UUID id(String[] arguments) {
        if (arguments.length < 2) throw new IllegalArgumentException("Include the request id from /blueprint list.");
        return UUID.fromString(arguments[1]);
    }

    private static Player requirePlayer(CommandSender sender) {
        if (sender instanceof Player player) return player;
        throw new IllegalArgumentException("Use this action from Minecraft.");
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] arguments) {
        if (command.getName().equalsIgnoreCase("review")) return List.of();
        List<String> allowed = service.allowedActions(sender);
        if (arguments.length == 1) return allowed.stream().filter(value -> value.startsWith(arguments[0].toLowerCase(Locale.ROOT))).toList();
        if (arguments.length == 4 && arguments[0].equalsIgnoreCase("approve") && allowed.contains("approve")) {
            return List.of("keep-blueprint", "use-student").stream().filter(value -> value.startsWith(arguments[3])).toList();
        }
        return List.of();
    }
}
