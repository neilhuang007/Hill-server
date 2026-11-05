package org.thehill.hill175.backup;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.block.BlockMultiPlaceEvent;
import org.bukkit.event.block.BlockFromToEvent;
import org.bukkit.event.block.BlockPistonExtendEvent;
import org.bukkit.event.block.BlockPistonRetractEvent;
import org.bukkit.event.player.PlayerBucketEvent;
import org.bukkit.event.player.PlayerBucketEmptyEvent;
import org.bukkit.event.player.PlayerBucketFillEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.inventory.InventoryMoveItemEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.world.WorldModule;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.function.BiConsumer;
import java.util.function.Predicate;
import java.util.function.Consumer;
import java.util.logging.Level;

/** Staff controls shared by Java and Floodgate, backed by established recovery tools. */
public final class CampusRecoveryService implements CommandExecutor, TabCompleter, Listener, AutoCloseable {
    private static final String ALL = "hill175.campus.rollback";
    private final JavaPlugin plugin;
    private final Predicate<Player> authenticated;
    private final ResticRepository repository;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final ScheduledExecutorService clock = Executors.newSingleThreadScheduledExecutor(
            Thread.ofPlatform().daemon(true).name("campus-backup-clock").factory());
    private final Path server;
    private List<CampusRecoveryAreas.Area> areas;
    private World campus;
    private ScheduledFuture<?> timer;
    private BukkitTask restoreTask;
    private WorldEditAreaRestore operation;
    private CampusRecoveryAreas.Area lockedArea;
    private boolean busy;
    private boolean scheduledPending;
    private volatile boolean closing;
    private Boolean previousAutoSave;
    private Consumer<Player> menuAction;

    public CampusRecoveryService(JavaPlugin plugin, Predicate<Player> authenticated) {
        this(plugin, authenticated, List.of());
    }

    CampusRecoveryService(JavaPlugin plugin, Predicate<Player> authenticated, List<CampusRecoveryAreas.Area> areas) {
        this.plugin = plugin;
        this.authenticated = authenticated;
        this.areas = List.copyOf(areas);
        server = plugin.getServer().getWorldContainer().toPath().toAbsolutePath().normalize();
        repository = new ResticRepository(server);
    }

    public void initialize(WorldModule worlds) {
        try { repository.checkInstalled(); }
        catch (IOException exception) { throw new IllegalStateException(exception.getMessage(), exception); }
        if (!Bukkit.getPluginManager().isPluginEnabled("WorldEdit")) throw new IllegalStateException("WorldEdit is required for campus area recovery.");
        campus = Bukkit.getWorld("hill_campus");
        if (campus == null) throw new IllegalStateException("Campus must be loaded before recovery.");
        areas = CampusRecoveryAreas.read(worlds, campus.getMinHeight(), campus.getMaxHeight() - 1);
        Bukkit.getPluginManager().registerEvents(this, plugin);
        if (Files.isRegularFile(journal())) {
            try {
                Properties request = BackupFiles.readProperties(journal());
                var area = area(request.getProperty("area"));
                Bukkit.getScheduler().runTask(plugin, () -> startRestore(Bukkit.getConsoleSender(), request.getProperty("snapshot"), area, request.getProperty("safety")));
            } catch (IOException exception) { throw new IllegalStateException("Cannot read interrupted area restore.", exception); }
        } else Bukkit.getScheduler().runTask(plugin, () -> scheduledCapture("initial"));
        timer = clock.scheduleAtFixedRate(() -> {
            if (!closing) Bukkit.getScheduler().runTask(plugin, () -> scheduledCapture("five-minute"));
        }, 300, 300, TimeUnit.SECONDS);
        plugin.getLogger().info("Campus recovery: Restic every 300 seconds, WorldEdit area restore, " + areas.size() + " available areas.");
    }

    public CampusRecoveryService commands() { return this; }
    public void menuAction(Consumer<Player> action) { menuAction = action; }
    public boolean canUse(Player player) {
        try { requireStaff(player); return true; } catch (SecurityException denied) { return false; }
    }
    public List<CampusRecoveryAreas.Area> permittedAreas(Player player) {
        requireStaff(player);
        return areas.stream().filter(a -> player.hasPermission(ALL) || player.hasPermission(ALL + "." + a.id())).toList();
    }
    void snapshots(Player player, Consumer<List<ResticRepository.Snapshot>> callback) {
        requireStaff(player);
        background(repository::list, (snapshots, error) -> {
            if (error != null) player.sendMessage("Campus recovery: " + error.getMessage());
            else if (player.isOnline() && canUse(player)) callback.accept(snapshots);
        });
    }

    /** Restore into an isolated, marked folder. No live world data or student identities are copied. */
    void preparePreview(Player player, String id, CampusRecoveryAreas.Area area, String name,
                        BiConsumer<PreparedPreview, Exception> callback) {
        requireArea(player, area);
        if (!name.matches("hill_recovery_[a-f0-9]{32}")) throw new IllegalArgumentException("Invalid preview world name.");
        Path destination = CampusRecoveryPreview.dimensionRoot(plugin).resolve(name);
        Path relative = server.relativize(campus.getWorldFolder().toPath().toAbsolutePath().normalize());
        Path stage = server.resolve("campus-backups/restore-stage-" + UUID.randomUUID());
        background(() -> {
            var snapshot = repository.requireSnapshot(id);
            try {
                Path source = repository.stage(snapshot.id(), relative, stage);
                Files.createDirectory(destination);
                Files.writeString(destination.resolve(".hill175-recovery-preview"), name);
                Files.move(source.resolve("region"), destination.resolve("region"));
                for (String file : List.of("hill-campus-template.yml", "hill-buildings.yml", "hill-areas.yml")) {
                    if (Files.isRegularFile(source.resolve(file))) Files.copy(source.resolve(file), destination.resolve(file));
                }
                return new PreparedPreview(snapshot, destination);
            } finally { if (Files.exists(stage)) deleteStage(stage); }
        }, callback);
    }

    void removePreview(Path folder) {
        background(() -> { CampusRecoveryPreview.deleteWorldFolder(folder); return true; }, (result, error) -> {
            if (error != null) plugin.getLogger().log(Level.WARNING, "Could not remove temporary recovery world " + folder, error);
        });
    }

    void restorePreview(Player player, String snapshot, CampusRecoveryAreas.Area area) throws IOException {
        checkRestore(player, snapshot, area);
        startRestore(player, snapshot, area, null);
    }
    void checkRestore(Player player, String snapshot, CampusRecoveryAreas.Area area) throws IOException {
        idle(); requireArea(player, area);
        if (Files.exists(journal())) throw new IllegalStateException("Finish the pending area restore before starting another.");
    }
    record PreparedPreview(ResticRepository.Snapshot snapshot, Path folder) { }
    public boolean isRestoring() { return lockedArea != null; }
    private Path journal() { return server.resolve("campus-backups/area-restore-request.properties"); }
    private CampusRecoveryAreas.Area area(String id) {
        return areas.stream().filter(a -> a.id().equals(id)).findFirst().orElseThrow(() -> new IllegalArgumentException("Unknown area. Use /campusbackup areas or /campusbackup here."));
    }

    public void requireStaff(CommandSender sender) {
        if (sender instanceof Player player && !authenticated.test(player)) throw new SecurityException("Sign in before using campus recovery controls.");
        if (!sender.hasPermission(ALL) && areas.stream().noneMatch(a -> sender.hasPermission(ALL + "." + a.id()))) {
            throw new SecurityException("Only campus staff can use backup and restore controls.");
        }
    }

    public void requireArea(CommandSender sender, CampusRecoveryAreas.Area area) {
        requireStaff(sender);
        if (!sender.hasPermission(ALL) && !sender.hasPermission(ALL + "." + area.id())) throw new SecurityException("You do not have recovery access to this area.");
    }

    private void idle() { if (busy || closing) throw new IllegalStateException("A campus backup or restore is already running."); }

    private <T> void background(Callable<T> action, BiConsumer<T, Exception> callback) {
        worker.submit(() -> {
            T result = null;
            Exception failure = null;
            try { result = action.call(); }
            catch (Exception exception) { failure = exception; }
            T value = result;
            Exception error = failure;
            if (!closing) Bukkit.getScheduler().runTask(plugin, () -> { if (!closing) callback.accept(value, error); });
        });
    }

    private void capture(String reason, BiConsumer<String, Exception> callback) {
        try {
            campus.save(true);
            previousAutoSave = campus.isAutoSave();
            campus.setAutoSave(false);
            Path world = campus.getWorldFolder().toPath();
            background(() -> repository.capture(world, reason), (id, error) -> {
                resumeSaving();
                if (error == null) plugin.getLogger().info("Campus Restic backup saved: " + id);
                callback.accept(id, error);
            });
        } catch (Exception exception) {
            resumeSaving();
            callback.accept(null, exception);
        }
    }

    private void resumeSaving() {
        if (previousAutoSave != null) { campus.setAutoSave(previousAutoSave); previousAutoSave = null; }
    }

    private void scheduledCapture(String reason) {
        if (closing) return;
        if (busy) { if (reason.equals("five-minute")) scheduledPending = true; return; }
        busy = true;
        capture(reason, (id, error) -> {
            busy = false;
            if (error != null) plugin.getLogger().log(Level.SEVERE, "Campus Restic backup failed. Previous recovery points are preserved.", error);
            runPendingCapture();
        });
    }

    private void startRestore(CommandSender sender, String id, CampusRecoveryAreas.Area area, String existingSafety) {
        idle();
        requireArea(sender, area);
        busy = true;
        lockedArea = area;
        Path stage = server.resolve("campus-backups/restore-stage-" + UUID.randomUUID());
        Path relativeWorld = server.relativize(campus.getWorldFolder().toPath().toAbsolutePath().normalize());
        sender.sendMessage("Verifying snapshot and preparing " + area.name() + ". Building in this area is paused.");
        background(() -> {
            Path world = repository.stage(id, relativeWorld, stage);
            var prepared = new WorldEditAreaRestore(world, area);
            try { prepared.verify(); }
            catch (Exception error) { prepared.close(); throw error; }
            return prepared;
        }, (prepared, error) -> {
            if (error != null) { fail(sender, error); return; }
            operation = prepared;
            try { requireArea(sender, area); }
            catch (SecurityException denied) { fail(sender, denied); return; }
            if (existingSafety != null) beginEdits(sender, id, area, existingSafety, stage);
            else capture("before-area-restore", (safety, failure) -> {
                if (failure != null) fail(sender, failure);
                else beginEdits(sender, id, area, safety, stage);
            });
        });
    }

    private void beginEdits(CommandSender sender, String id, CampusRecoveryAreas.Area area, String safety, Path stage) {
        try {
            requireArea(sender, area);
            Properties request = new Properties();
            request.setProperty("area", area.id()); request.setProperty("snapshot", id);
            request.setProperty("safety", safety); request.setProperty("actor", sender.getName());
            BackupFiles.writeProperties(journal(), request);
            sender.sendMessage("Restoring " + area.name() + ". Safety snapshot: " + safety.substring(0, 8) + ". Other areas stay open.");
            restoreTask = Bukkit.getScheduler().runTaskTimer(plugin, () -> {
                try {
                    long deadline = System.nanoTime() + 10_000_000;
                    boolean complete;
                    do { complete = operation.step(campus); }
                    while (!complete && System.nanoTime() < deadline);
                    if (!complete) return;
                    campus.save(true);
                    BackupFiles.move(journal(), server.resolve("campus-backups/area-restore-complete-" + UUID.randomUUID() + ".properties"));
                    sender.sendMessage("Campus area restored: " + area.id() + " from " + id + ". Safety snapshot: " + safety.substring(0, 8));
                    plugin.getLogger().info("Campus area restored: " + area.id() + " from " + id + " by " + sender.getName() + ", safety " + safety);
                    finish();
                    // Extracted data is temporary; immutable snapshots and restore records remain.
                    background(() -> { deleteStage(stage); return true; }, (result, error) -> {
                        if (error != null) plugin.getLogger().warning("Could not remove restore staging folder: " + stage);
                    });
                } catch (Exception exception) { fail(sender, exception); }
            }, 1L, 1L);
        } catch (Exception exception) { fail(sender, exception); }
    }

    private void fail(CommandSender sender, Exception exception) {
        sender.sendMessage("Campus recovery failed: " + exception.getMessage() + ". Recovery snapshots are preserved.");
        plugin.getLogger().log(Level.SEVERE, "Campus recovery failed.", exception);
        finish();
    }

    private void deleteStage(Path stage) throws IOException {
        if (!stage.getParent().equals(server.resolve("campus-backups")) || !stage.getFileName().toString().startsWith("restore-stage-")) throw new IOException("Invalid restore staging path.");
        try (var paths = Files.walk(stage)) {
            for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.delete(path);
        }
    }

    private void finish() {
        if (restoreTask != null) { restoreTask.cancel(); restoreTask = null; }
        if (operation != null) {
            try { operation.close(); } catch (IOException error) { plugin.getLogger().warning(error.getMessage()); }
            operation = null;
        }
        // If editing was interrupted, keep this area locked until the recorded request is resumed.
        if (!Files.exists(journal())) lockedArea = null;
        busy = false;
        runPendingCapture();
    }

    private void runPendingCapture() {
        if (scheduledPending && !closing && lockedArea == null) { scheduledPending = false; scheduledCapture("five-minute"); }
    }

    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        try {
            requireStaff(sender);
            String action = args.length == 0 && sender instanceof Player && menuAction != null ? "menu" : args.length == 0 ? "list" : args[0];
            switch (action) {
                case "menu" -> {
                    if (!(sender instanceof Player player) || menuAction == null) throw new IllegalStateException("Open recovery from Minecraft.");
                    menuAction.accept(player);
                }
                case "list" -> {
                    int page = args.length > 1 ? Integer.parseInt(args[1]) : 1;
                    if (page < 1) throw new IllegalArgumentException("Page must be positive.");
                    background(repository::list, (snapshots, error) -> {
                        if (error != null) { sender.sendMessage("Campus recovery: " + error.getMessage()); return; }
                        try { requireStaff(sender); } catch (SecurityException denied) { return; }
                        sender.sendMessage("Campus recovery points, every five minutes. Page " + page + ".");
                        snapshots.stream().skip((long) (page - 1) * 10).limit(10).forEach(s -> sender.sendMessage(s.shortId() + "  " + s.time()));
                    });
                }
                case "areas" -> {
                    int page = args.length > 1 ? Integer.parseInt(args[1]) : 1;
                    if (page < 1) throw new IllegalArgumentException("Page must be positive.");
                    sender.sendMessage("Campus recovery areas, page " + page + ". Use /campusbackup here for your location.");
                    areas.stream().filter(a -> sender.hasPermission(ALL) || sender.hasPermission(ALL + "." + a.id()))
                            .skip((long) (page - 1) * 10).limit(10).forEach(a -> sender.sendMessage(a.id() + ": " + a.name()));
                }
                case "here" -> {
                    if (!(sender instanceof Player player) || !player.getWorld().equals(campus)) throw new IllegalArgumentException("Stand in the shared campus first.");
                    areas.stream().filter(a -> a.contains(player.getLocation().getBlockX(), player.getLocation().getBlockZ()))
                            .filter(a -> sender.hasPermission(ALL) || sender.hasPermission(ALL + "." + a.id()))
                            .forEach(a -> sender.sendMessage(a.id() + ": " + a.name()));
                }
                case "save" -> {
                    idle(); busy = true;
                    capture("staff-save", (id, error) -> {
                        busy = false;
                        if (error != null) fail(sender, error);
                        else sender.sendMessage("Campus backup saved: " + id);
                        runPendingCapture();
                    });
                }
                case "restore" -> {
                    if (args.length < 3 || args.length > 4) throw new IllegalArgumentException("Use /campusbackup restore <snapshot> <area> confirm.");
                    var area = area(args[2]); requireArea(sender, area);
                    if (args.length == 3) sender.sendMessage(Component.text("Restore only " + area.name() + "? Confirm with /campusbackup restore " + args[1] + " " + area.id() + " confirm")
                            .clickEvent(ClickEvent.suggestCommand("/campusbackup restore " + args[1] + " " + area.id() + " confirm")));
                    else if (!args[3].equals("confirm")) throw new IllegalArgumentException("Type confirm after the area ID.");
                    else {
                        if (Files.exists(journal())) {
                            Properties pending = BackupFiles.readProperties(journal());
                            if (!pending.getProperty("area").equals(area.id()) || !pending.getProperty("snapshot").equals(args[1])) throw new IllegalStateException("Resume the pending restore before choosing another: " + pending.getProperty("snapshot") + " " + pending.getProperty("area"));
                            startRestore(sender, args[1], area, pending.getProperty("safety"));
                        } else startRestore(sender, args[1], area, null);
                    }
                }
                default -> sender.sendMessage("Use /campusbackup list, areas, here, save, or restore <snapshot> <area> confirm.");
            }
        } catch (IOException | IllegalArgumentException | IllegalStateException | SecurityException error) { sender.sendMessage("Campus recovery: " + error.getMessage()); }
        return true;
    }

    @Override public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        try { requireStaff(sender); } catch (SecurityException denied) { return List.of(); }
        if (args.length == 1) return List.of("menu", "list", "areas", "here", "save", "restore").stream().filter(a -> a.startsWith(args[0])).toList();
        if (args.length == 3 && args[0].equals("restore")) return areas.stream().filter(a -> sender.hasPermission(ALL) || sender.hasPermission(ALL + "." + a.id())).map(CampusRecoveryAreas.Area::id).filter(id -> id.startsWith(args[2])).toList();
        if (args.length == 4 && args[0].equals("restore")) return List.of("confirm");
        return List.of();
    }

    private boolean locked(Block block) { return lockedArea != null && block != null && block.getWorld().equals(campus) && lockedArea.contains(block.getX(), block.getZ()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void place(BlockPlaceEvent event) {
        if (locked(event.getBlock()) || (event instanceof BlockMultiPlaceEvent multiple && multiple.getReplacedBlockStates().stream().anyMatch(state -> locked(state.getBlock())))) event.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void breakBlock(BlockBreakEvent event) { if (locked(event.getBlock())) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void flow(BlockFromToEvent event) { if (locked(event.getBlock()) || locked(event.getToBlock())) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void interact(PlayerInteractEvent event) { if (locked(event.getClickedBlock())) event.setCancelled(true); }
    private boolean locked(org.bukkit.inventory.Inventory inventory) {
        var location = inventory.getLocation();
        return location != null && locked(location.getBlock());
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void inventory(InventoryClickEvent event) { if (locked(event.getView().getTopInventory())) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void drag(InventoryDragEvent event) { if (locked(event.getView().getTopInventory())) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void hopper(InventoryMoveItemEvent event) { if (locked(event.getSource()) || locked(event.getDestination())) event.setCancelled(true); }
    private boolean bucketLocked(PlayerBucketEvent event) { return locked(event.getBlockClicked()) || locked(event.getBlockClicked().getRelative(event.getBlockFace())); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void empty(PlayerBucketEmptyEvent event) { if (bucketLocked(event)) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void fill(PlayerBucketFillEvent event) { if (bucketLocked(event)) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void piston(BlockPistonExtendEvent event) {
        if (locked(event.getBlock()) || event.getBlocks().stream().anyMatch(b -> locked(b) || locked(b.getRelative(event.getDirection())))) event.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void piston(BlockPistonRetractEvent event) {
        if (locked(event.getBlock()) || event.getBlocks().stream().anyMatch(b -> locked(b) || locked(b.getRelative(event.getDirection())))) event.setCancelled(true);
    }

    @Override public void close() {
        closing = true;
        if (timer != null) timer.cancel(false);
        clock.shutdownNow();
        if (restoreTask != null) restoreTask.cancel();
        worker.shutdownNow();
        try { worker.awaitTermination(30, TimeUnit.SECONDS); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); }
        resumeSaving();
        if (operation != null) try { operation.close(); } catch (IOException error) { plugin.getLogger().warning(error.getMessage()); }
    }
}
