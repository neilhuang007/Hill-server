package org.thehill.hill175.backup;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.function.Predicate;
import java.util.logging.Level;

/** Five minute recovery points for the shared campus, without rolling back student identities. */
public final class CampusBackupService implements CommandExecutor, TabCompleter, AutoCloseable {
    private static final String campusWorld = "hill_campus";
    private static final String rollbackPermission = "hill175.campus.rollback";
    private final JavaPlugin plugin;
    private final Predicate<Player> isAuthenticated;
    private final CampusBackupStore snapshots;
    private BukkitTask timer;
    private boolean isBusy;
    private boolean isClosing;

    public CampusBackupService(JavaPlugin plugin, Predicate<Player> isAuthenticated) {
        this.plugin = plugin;
        this.isAuthenticated = isAuthenticated;
        try { snapshots = new CampusBackupStore(backupFolder(plugin)); }
        catch (IOException exception) { throw new UncheckedIOException("Cannot open campus backup storage.", exception); }
    }

    public void initialize() {
        if (Bukkit.getWorld(campusWorld) == null) throw new IllegalStateException("The shared campus must load before backups start.");
        Bukkit.getScheduler().runTask(plugin, () -> scheduledCapture("Initial campus recovery point"));
        timer = Bukkit.getScheduler().runTaskTimer(plugin, () -> scheduledCapture(), 20L * 300, 20L * 300);
    }

    public CampusBackupService commands() { return this; }
    public boolean isBusy() { return isBusy || isClosing; }

    public String capture(String reason) throws IOException {
        requireMainThread();
        requireIdle();
        isBusy = true;
        try {
            World world = Bukkit.getWorld(campusWorld);
            if (world == null) throw new IOException("The shared campus is not loaded.");
            flushCampus(world);
            long started = System.nanoTime();
            String id = snapshots.capture(Map.of(campusWorld, world.getWorldFolder().toPath()), reason);
            plugin.getLogger().info("Campus backup saved: " + id + " (" + ((System.nanoTime() - started) / 1_000_000) + " ms)");
            return id;
        } finally { isBusy = false; }
    }

    private static void flushCampus(World world) throws IOException {
        try {
            // Command dispatch may queue a nested save until after this command returns.
            // The Paper API flushes this world's region writes before snapshot copying.
            world.save(true);
        } catch (RuntimeException exception) {
            throw new IOException("Campus save could not be flushed. No backup was created.", exception);
        }
    }

    public List<String> list() throws IOException { return snapshots.list(); }

    public void requireOperator(CommandSender sender) {
        if (!sender.hasPermission(rollbackPermission)) throw new SecurityException("Only campus staff can use backup and restore controls.");
        if (sender instanceof Player player && !isAuthenticated.test(player)) throw new SecurityException("Sign in before using campus staff controls.");
    }

    public void requestRestore(CommandSender sender, String id) throws IOException {
        requireMainThread();
        requireOperator(sender);
        requireIdle();
        snapshots.verify(id);
        String safety = capture("Before restore requested by " + sender.getName());
        Properties request = new Properties();
        request.setProperty("backup", id);
        request.setProperty("safetyBackup", safety);
        request.setProperty("actor", sender.getName());
        BackupFiles.writeProperties(requestFile(plugin), request);
        isClosing = true;
    }

    /** Must run before WorldModule opens hill_campus. The primary survival dimension is untouched. */
    public static void applyPendingRestore(JavaPlugin plugin) {
        Path requestFile = requestFile(plugin);
        if (!Files.exists(requestFile)) return;
        if (Bukkit.getWorld(campusWorld) != null) throw new IllegalStateException("Shared campus was loaded before recovery.");
        try { completeRestore(plugin, requestFile); }
        catch (IOException exception) { throw new UncheckedIOException("Campus restore failed. Startup is stopped to protect the existing world.", exception); }
    }

    private static void completeRestore(JavaPlugin plugin, Path requestFile) throws IOException {
        Properties request = BackupFiles.readProperties(requestFile);
        Path server = plugin.getServer().getWorldContainer().toPath().toAbsolutePath().normalize();
        Path stage = restoreStage(plugin, request, requestFile);
        Map<String, Path> staged = Map.of(campusWorld, BackupFiles.child(stage, campusWorld));
        Map<String, Path> destination = Map.of(campusWorld, dimensionFolder(plugin));
        Path preserved = BackupFiles.child(server, request.getProperty("preserved"));
        CampusBackupStore.replaceStaged(staged, destination, preserved);
        BackupFiles.move(requestFile, server.resolve("campus-restore-complete-" + UUID.randomUUID() + ".properties"));
        plugin.getLogger().info("Restored shared campus backup " + request.getProperty("backup") + ". Previous world preserved in " + preserved);
    }

    private static Path restoreStage(JavaPlugin plugin, Properties request, Path requestFile) throws IOException {
        Path server = plugin.getServer().getWorldContainer().toPath().toAbsolutePath().normalize();
        if (request.containsKey("stage")) return BackupFiles.child(server, request.getProperty("stage"));
        String suffix = UUID.randomUUID().toString();
        Path stage = BackupFiles.child(server, "campus-restore-stage-" + suffix);
        var snapshots = new CampusBackupStore(backupFolder(plugin));
        Map<String, Path> sources = snapshots.stageRestore(request.getProperty("backup"), stage);
        if (!sources.keySet().equals(java.util.Set.of(campusWorld))) throw new IOException("The snapshot does not contain exactly the shared campus.");
        request.setProperty("stage", stage.getFileName().toString());
        request.setProperty("preserved", "campus-before-restore-" + suffix);
        BackupFiles.writeProperties(requestFile, request);
        return stage;
    }

    private static Path dimensionFolder(JavaPlugin plugin) {
        Path server = plugin.getServer().getWorldContainer().toPath().toAbsolutePath().normalize();
        String primary = Bukkit.getWorlds().getFirst().getName();
        return BackupFiles.child(server, primary).resolve("dimensions/minecraft").resolve(campusWorld);
    }

    private static Path backupFolder(JavaPlugin plugin) {
        return plugin.getServer().getWorldContainer().toPath().resolve("campus-backups/shared-campus");
    }

    private static Path requestFile(JavaPlugin plugin) {
        return plugin.getServer().getWorldContainer().toPath().resolve("campus-shared-restore-request.properties");
    }

    private void scheduledCapture() {
        scheduledCapture("Scheduled five minute campus backup");
    }

    private void scheduledCapture(String reason) {
        if (isBusy()) return;
        try { capture(reason); }
        catch (IOException exception) { plugin.getLogger().log(Level.SEVERE, "Campus backup failed. Previous recovery points are preserved.", exception); }
    }

    private void requireIdle() {
        if (isBusy()) throw new IllegalStateException("A campus backup or restore is already running.");
    }

    private static void requireMainThread() {
        if (!Bukkit.isPrimaryThread()) throw new IllegalStateException("Campus backup operations require the server thread.");
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] arguments) {
        try {
            requireOperator(sender);
            execute(sender, arguments);
        } catch (IOException | IllegalArgumentException | IllegalStateException | SecurityException exception) {
            sender.sendMessage("Campus backup: " + exception.getMessage());
        }
        return true;
    }

    private void execute(CommandSender sender, String[] arguments) throws IOException {
        String action = arguments.length == 0 ? "list" : arguments[0].toLowerCase(java.util.Locale.ROOT);
        switch (action) {
            case "list" -> showList(sender, arguments.length > 1 ? Integer.parseInt(arguments[1]) : 1);
            case "save" -> sender.sendMessage("Campus backup saved: " + capture("Manual backup requested by " + sender.getName()));
            case "restore" -> restore(sender, arguments);
            default -> sender.sendMessage("Use /campusbackup list [page], /campusbackup save, or /campusbackup restore <backup> confirm.");
        }
    }

    private void showList(CommandSender sender, int page) throws IOException {
        List<String> available = snapshots.list();
        if (available.isEmpty()) { sender.sendMessage("No campus backups yet. Recovery points are saved every five minutes."); return; }
        int pageCount = Math.max(1, (available.size() + 9) / 10);
        if (page < 1 || page > pageCount) throw new IllegalArgumentException("Choose a backup page from 1 to " + pageCount + ".");
        sender.sendMessage("Campus recovery points, page " + page + " of " + pageCount + ". Click to prepare a restore; restoring requires a restart.");
        available.stream().skip((long) (page - 1) * 10).limit(10).forEach(id -> sender.sendMessage(Component.text(id)
                .clickEvent(ClickEvent.suggestCommand("/campusbackup restore " + id + " confirm"))));
        if (page < pageCount) sender.sendMessage(Component.text("[Older backups]").clickEvent(ClickEvent.runCommand("/campusbackup list " + (page + 1))));
        if (page > 1) sender.sendMessage(Component.text("[Newer backups]").clickEvent(ClickEvent.runCommand("/campusbackup list " + (page - 1))));
    }

    private void restore(CommandSender sender, String[] arguments) throws IOException {
        if (arguments.length != 3 || !arguments[2].equals("confirm")) {
            throw new IllegalArgumentException("Use /campusbackup restore <backup> confirm. This preserves the current world and restarts the server.");
        }
        requestRestore(sender, arguments[1]);
        Bukkit.broadcast(Component.text("The campus server is restarting to restore a verified backup. Current world data has been preserved."));
        Bukkit.shutdown();
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] arguments) {
        if (!sender.hasPermission(rollbackPermission)) return List.of();
        if (arguments.length == 1) return List.of("list", "save", "restore").stream().filter(value -> value.startsWith(arguments[0])).toList();
        if (arguments.length == 3 && arguments[0].equals("restore")) return List.of("confirm");
        return List.of();
    }

    @Override
    public void close() {
        isClosing = true;
        if (timer != null) timer.cancel();
    }
}
