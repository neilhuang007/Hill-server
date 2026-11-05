package org.thehill.hill175.backup;

import io.papermc.paper.math.Position;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.*;
import org.bukkit.entity.Player;
import org.bukkit.event.*;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.EntityPickupItemEvent;
import org.bukkit.event.inventory.*;
import org.bukkit.event.player.*;
import org.bukkit.generator.ChunkGenerator;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.ui.BedrockForms;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.function.Consumer;
import java.util.logging.Level;

/** Staff inspect an immutable Restic version in their own disposable world before confirming an area restore. */
public final class CampusRecoveryPreview implements Listener, AutoCloseable {
    private static final int PAGE_SIZE = 12;
    private static final long LIFETIME = java.time.Duration.ofMinutes(10).toNanos();
    private static final String MARKER = ".hill175-recovery-preview";
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("MMM d, uuuu HH:mm:ss 'UTC'", Locale.ENGLISH).withZone(ZoneOffset.UTC);
    private final JavaPlugin plugin;
    private final CampusRecoveryService recovery;
    private final CompetitionModule competition;
    private final BedrockForms bedrock;
    private final NamespacedKey actionKey;
    private final Path states;
    private final Path dimensions;
    private final Map<UUID, Session> previews = new HashMap<>();
    private final Map<UUID, Menu> menus = new HashMap<>();
    private final Set<UUID> awaitingInventory = new HashSet<>();
    private BukkitTask timer;
    private boolean closed;

    public CampusRecoveryPreview(JavaPlugin plugin, CampusRecoveryService recovery, CompetitionModule competition) {
        this.plugin = plugin; this.recovery = recovery; this.competition = competition;
        bedrock = new BedrockForms(plugin);
        actionKey = new NamespacedKey(plugin, "recovery-preview-action");
        states = plugin.getDataFolder().toPath().resolve("recovery-preview-players");
        dimensions = dimensionRoot(plugin);
    }

    static Path dimensionRoot(JavaPlugin plugin) {
        // Paper 26.2 can report the primary dimension as world/dimensions/minecraft/overworld.
        // Custom dimensions remain under the primary level root, as in WorldModule's clone loader.
        return plugin.getServer().getWorldContainer().toPath().toAbsolutePath().normalize()
                .resolve(Bukkit.getWorlds().getFirst().getName()).resolve("dimensions/minecraft");
    }

    public void initialize() {
        try {
            Files.createDirectories(states);
            if (Files.isDirectory(dimensions)) try (var folders = Files.list(dimensions)) {
                for (Path folder : folders.filter(Files::isDirectory).toList()) {
                    if (ownedFolder(folder) && Bukkit.getWorld(folder.getFileName().toString()) == null) recovery.removePreview(folder);
                }
            }
            for (Player player : Bukkit.getOnlinePlayers()) if (Files.isRegularFile(stateFile(player))) awaitingInventory.add(player.getUniqueId());
        } catch (IOException error) { throw new IllegalStateException("Cannot initialize recovery preview state.", error); }
        Bukkit.getPluginManager().registerEvents(this, plugin);
        timer = Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 20L, 20L);
    }

    public boolean contains(Player player) { return previews.containsKey(player.getUniqueId()); }
    public boolean canOpen(Player player) {
        return !closed && player.isOnline() && recovery.canUse(player) && !competition.isCameraPreviewing(player)
                && (contains(player) || !awaitingInventory.contains(player.getUniqueId()))
                && (player.getWorld().getName().equals("hill_campus") || contains(player));
    }

    public void open(Player player) {
        if (!canOpen(player)) { player.sendMessage("Open staff recovery while signed in on the shared campus."); return; }
        Session preview = previews.get(player.getUniqueId());
        if (preview != null) { versions(player, preview.area, 0); return; }
        areas(player, 0);
    }

    private void areas(Player player, int page) {
        if (!canOpen(player)) return;
        List<CampusRecoveryAreas.Area> allowed = new ArrayList<>(recovery.permittedAreas(player));
        allowed.sort(Comparator.comparingInt((CampusRecoveryAreas.Area a) -> a.contains(player.getLocation().getBlockX(), player.getLocation().getBlockZ()) ? 0 : a.id().startsWith("tile_") ? 2 : 1).thenComparing(CampusRecoveryAreas.Area::name));
        int current = Math.clamp(page, 0, Math.max(0, (allowed.size() - 1) / PAGE_SIZE));
        List<Choice> choices = new ArrayList<>();
        allowed.stream().skip((long) current * PAGE_SIZE).limit(PAGE_SIZE).forEach(a -> choices.add(new Choice(a.name(), a.id(), Material.GRASS_BLOCK, p -> versions(p, a, 0))));
        navigation(choices, current, allowed.size(), p -> areas(p, current - 1), p -> areas(p, current + 1));
        choices.add(new Choice("Close", "Return to campus", Material.BARRIER, p -> { }));
        show(player, "Recovery: Areas", "Choose the area to inspect. Areas near you appear first. Only the selected area can be restored.", choices);
    }

    private void versions(Player player, CampusRecoveryAreas.Area area, int page) {
        if (!canOpen(player)) return;
        try {
            recovery.requireArea(player, area);
            Menu request = new Menu(UUID.randomUUID(), List.of());
            menus.put(player.getUniqueId(), request);
            player.sendMessage("Loading saved versions for " + area.name() + ".");
            recovery.snapshots(player, snapshots -> {
                if (!canOpen(player) || menus.get(player.getUniqueId()) != request) return;
                try { recovery.requireArea(player, area); } catch (SecurityException denied) { return; }
                int current = Math.clamp(page, 0, Math.max(0, (snapshots.size() - 1) / PAGE_SIZE));
                List<Choice> choices = new ArrayList<>();
                snapshots.stream().skip((long) current * PAGE_SIZE).limit(PAGE_SIZE).forEach(s -> choices.add(new Choice(
                        TIME.format(Instant.parse(s.time())), "Snapshot " + s.shortId() + ". Click to visit this version.", Material.CLOCK, p -> preview(p, area, s))));
                navigation(choices, current, snapshots.size(), p -> versions(p, area, current - 1), p -> versions(p, area, current + 1));
                choices.add(new Choice(contains(player) ? "Back to Preview" : "Back to Areas", area.name(), Material.ARROW,
                        p -> { if (!contains(p)) areas(p, 0); }));
                show(player, "Recovery: Versions", area.name() + "\nChoose a timestamp to visit its temporary preview. This does not change the live campus.", choices);
            });
        } catch (SecurityException error) { player.sendMessage(error.getMessage()); }
    }

    private void navigation(List<Choice> choices, int page, int count, Consumer<Player> previous, Consumer<Player> next) {
        if (page > 0) choices.add(new Choice("Previous Page", "Page " + page, Material.ARROW, previous));
        if ((long) (page + 1) * PAGE_SIZE < count) choices.add(new Choice("Next Page", "Page " + (page + 2), Material.ARROW, next));
    }

    private void show(Player player, String title, String body, List<Choice> choices) {
        Menu menu = new Menu(UUID.randomUUID(), List.copyOf(choices));
        menus.put(player.getUniqueId(), menu);
        if (bedrock.isBedrock(player)) {
            bedrock.show(player, title, body, choices.stream().map(c -> c.label + "\n" + c.description).toList(),
                    index -> dispatch(player, menu, index), () -> menus.remove(player.getUniqueId(), menu));
        } else {
            player.closeInventory();
            menu.inventory = Bukkit.createInventory(null, 54, Component.text(title));
            for (int index = 0; index < choices.size(); index++) {
                Choice choice = choices.get(index);
                menu.inventory.setItem(index, item(choice.material, choice.label, choice.description, null));
            }
            player.openInventory(menu.inventory);
        }
    }

    private void dispatch(Player player, Menu menu, int index) {
        if (closed || !menus.remove(player.getUniqueId(), menu)) return;
        player.closeInventory();
        Bukkit.getScheduler().runTask(plugin, () -> {
            if (!canOpen(player) || index < 0 || index >= menu.choices.size()) return;
            menu.choices.get(index).action.accept(player);
        });
    }

    private void preview(Player player, CampusRecoveryAreas.Area area, ResticRepository.Snapshot snapshot) {
        if (!canOpen(player)) return;
        try {
            recovery.requireArea(player, area);
            if (contains(player) && !leave(player, true)) return;
            if (previews.size() >= 3) throw new IllegalStateException("Three staff previews are already open. Try again when one closes.");
            Session session = new Session(area, snapshot);
            previews.put(player.getUniqueId(), session);
            player.sendMessage("Preparing a temporary preview of " + area.name() + " from " + TIME.format(Instant.parse(snapshot.time())) + ".");
            recovery.preparePreview(player, snapshot.id(), area, session.worldName, (prepared, error) -> {
                if (previews.get(player.getUniqueId()) != session || !canOpen(player)) {
                    if (prepared != null) recovery.removePreview(prepared.folder());
                    return;
                }
                if (error != null) { previewFailed(player, session, error); return; }
                try {
                    recovery.requireArea(player, area);
                    session.state = RecoveryPlayerState.capture(player);
                    session.state.save(stateFile(player));
                    var part = area.parts().getFirst();
                    int x = area.contains(player.getLocation().getBlockX(), player.getLocation().getBlockZ()) ? player.getLocation().getBlockX() : part.centerX();
                    int z = area.contains(player.getLocation().getBlockX(), player.getLocation().getBlockZ()) ? player.getLocation().getBlockZ() : part.centerZ();
                    session.world = WorldCreator.name(session.worldName).generateStructures(false).generator(new EmptyGenerator())
                            .forcedSpawnPosition(Position.block(x, 100, z), 0, 0).createWorld();
                    if (session.world == null || !session.world.getWorldFolder().toPath().toAbsolutePath().normalize().equals(prepared.folder())) throw new IOException("Could not open the isolated snapshot world.");
                    configure(session.world, area);
                    int y = Math.min(session.world.getMaxHeight() - 2, session.world.getHighestBlockYAt(x, z) + 3);
                    if (!player.teleport(new Location(session.world, x + 0.5, y, z + 0.5))) throw new IOException("Could not enter the snapshot preview.");
                    player.setGameMode(GameMode.ADVENTURE); player.setAllowFlight(true); player.setFlying(true);
                    player.getInventory().setItem(0, item(Material.LIME_DYE, "Confirm Restore", "Restore only " + area.name() + " to this version.", session.token + ":confirm"));
                    player.getInventory().setItem(4, item(Material.CLOCK, "Choose Another Version", "Compare another saved version of this area.", session.token + ":versions"));
                    player.getInventory().setItem(8, item(Material.BARRIER, "Cancel Preview", "Return without changing the live campus.", session.token + ":cancel"));
                    player.getInventory().setHeldItemSlot(4);
                    session.viewing = true;
                    player.sendMessage("Recovery preview ready: " + area.id() + " from " + snapshot.shortId() + ". Fly around, then right click Confirm Restore or Cancel Preview.");
                } catch (Exception failure) { previewFailed(player, session, failure); }
            });
        } catch (SecurityException | IllegalStateException error) { player.sendMessage(error.getMessage()); }
    }

    private void configure(World world, CampusRecoveryAreas.Area area) {
        world.setAutoSave(false); world.setPVP(false); world.setTime(6000); world.setStorm(false); world.setThundering(false);
        world.setViewDistance(5); world.setSimulationDistance(2);
        var envelope = area.parts();
        int minX = envelope.stream().mapToInt(p -> p.minX()).min().orElseThrow(), maxX = envelope.stream().mapToInt(p -> p.maxX()).max().orElseThrow();
        int minZ = envelope.stream().mapToInt(p -> p.minZ()).min().orElseThrow(), maxZ = envelope.stream().mapToInt(p -> p.maxZ()).max().orElseThrow();
        world.getWorldBorder().setCenter((minX + maxX) / 2.0, (minZ + maxZ) / 2.0);
        world.getWorldBorder().setSize(Math.max(maxX - minX + 1, maxZ - minZ + 1) + 64);
        world.setGameRule(GameRules.SPAWN_MOBS, false); world.setGameRule(GameRules.RANDOM_TICK_SPEED, 0);
        world.setGameRule(GameRules.ADVANCE_TIME, false); world.setGameRule(GameRules.ADVANCE_WEATHER, false);
        world.setGameRule(GameRules.FIRE_SPREAD_RADIUS_AROUND_PLAYER, 0); world.setGameRule(GameRules.KEEP_INVENTORY, true);
    }

    private void previewFailed(Player player, Session session, Exception error) {
        plugin.getLogger().log(Level.WARNING, "Could not prepare recovery preview.", error);
        player.sendMessage("Could not open that preview: " + error.getMessage());
        leave(player, true);
        if (session.world == null && Files.exists(dimensions.resolve(session.worldName).resolve(MARKER))) recovery.removePreview(dimensions.resolve(session.worldName));
    }

    private Path stateFile(Player player) { return states.resolve(player.getUniqueId() + ".properties"); }

    /** Save the original inventory back to player data before removing its recovery record. */
    private boolean leave(Player player, boolean returnToCampus) {
        return leave(player, returnToCampus, false);
    }

    private boolean leave(Player player, boolean returnToCampus, boolean recoverAfterLogin) {
        Session session = previews.get(player.getUniqueId());
        if (session == null) return true;
        if (session.leaving) return false;
        session.leaving = true;
        try {
            if (session.state != null) {
                if (returnToCampus && session.world != null && player.getWorld().equals(session.world) && !player.teleport(session.state.location())) {
                    session.leaving = false; player.sendMessage("Could not return to campus. The preview remains open."); return false;
                }
                session.state.apply(player);
                if (!competition.isAuthenticated(player)) { player.setGameMode(GameMode.ADVENTURE); player.setAllowFlight(false); player.setGravity(false); }
                player.saveData();
                if (!recoverAfterLogin) Files.deleteIfExists(stateFile(player));
            }
            previews.remove(player.getUniqueId(), session);
            bedrock.clear(player);
            menus.remove(player.getUniqueId());
            releaseWorld(session);
            return true;
        } catch (Exception error) {
            session.leaving = false;
            plugin.getLogger().log(Level.SEVERE, "Preview player state was preserved for recovery.", error);
            player.sendMessage("Preview recovery could not finish. Your saved inventory is preserved; ask an operator for help.");
            return false;
        }
    }

    private void releaseWorld(Session session) {
        if (session.world == null) return;
        if (session.world.getPlayers().isEmpty() && Bukkit.unloadWorld(session.world, false)) {
            recovery.removePreview(dimensions.resolve(session.worldName));
        } else if (!closed) {
            Bukkit.getScheduler().runTaskLater(plugin, () -> {
                if (session.world.getPlayers().isEmpty() && Bukkit.unloadWorld(session.world, false)) recovery.removePreview(dimensions.resolve(session.worldName));
                else plugin.getLogger().warning("Temporary recovery world remains in use: " + session.worldName);
            }, 1L);
        }
    }

    private void recoverInventory(Player player) throws IOException {
        if (!Files.isRegularFile(stateFile(player))) return;
        RecoveryPlayerState.read(stateFile(player)).applyInventory(player);
        competition.refreshCampusTools(player);
        player.saveData();
        Files.delete(stateFile(player));
        player.sendMessage("Your inventory was recovered from a previous campus preview.");
    }

    private void tick() {
        for (UUID id : List.copyOf(awaitingInventory)) {
            Player player = Bukkit.getPlayer(id);
            if (player == null || !competition.isAuthenticated(player)) continue;
            try { recoverInventory(player); awaitingInventory.remove(id); }
            catch (Exception error) { plugin.getLogger().log(Level.SEVERE, "Cannot recover preview inventory.", error); player.kick(Component.text("Your saved preview inventory needs operator recovery.")); }
        }
        for (var entry : List.copyOf(previews.entrySet())) {
            Player player = Bukkit.getPlayer(entry.getKey());
            Session session = entry.getValue();
            if (player == null) continue;
            boolean allowed;
            try { recovery.requireArea(player, session.area); allowed = true; } catch (SecurityException denied) { allowed = false; }
            if (!allowed || System.nanoTime() - session.opened > LIFETIME) {
                leave(player, true); continue;
            }
            if (session.viewing) {
                player.setGameMode(GameMode.ADVENTURE); player.setAllowFlight(true);
                player.sendActionBar(Component.text("Preview only: " + session.area.name() + " | " + TIME.format(Instant.parse(session.snapshot.time())), NamedTextColor.YELLOW));
            }
        }
    }

    private ItemStack item(Material material, String name, String description, String action) {
        ItemStack item = action == null ? new ItemStack(material) : competition.recoveryControl(material, name, description);
        var meta = item.getItemMeta(); meta.displayName(Component.text(name, NamedTextColor.WHITE));
        meta.lore(List.of(Component.text(description, NamedTextColor.GRAY)));
        if (action != null) meta.getPersistentDataContainer().set(actionKey, PersistentDataType.STRING, action);
        item.setItemMeta(meta); return item;
    }

    @EventHandler(priority = EventPriority.HIGHEST) public void use(PlayerInteractEvent event) {
        Session session = previews.get(event.getPlayer().getUniqueId());
        if (session == null || !session.viewing || session.leaving) return;
        event.setCancelled(true);
        if (event.getHand() != EquipmentSlot.HAND || !event.getAction().isRightClick() || event.getItem() == null || !event.getItem().hasItemMeta()) return;
        String action = event.getItem().getItemMeta().getPersistentDataContainer().get(actionKey, PersistentDataType.STRING);
        if (action == null || !action.startsWith(session.token + ":")) return;
        Player player = event.getPlayer();
        try {
            recovery.requireArea(player, session.area);
            switch (action.substring(session.token.length() + 1)) {
                case "versions" -> versions(player, session.area, 0);
                case "cancel" -> { if (leave(player, true)) player.sendMessage("Recovery preview canceled. The live campus was not changed."); }
                case "confirm" -> {
                    recovery.checkRestore(player, session.snapshot.id(), session.area);
                    if (leave(player, true)) recovery.restorePreview(player, session.snapshot.id(), session.area);
                }
                default -> { }
            }
        } catch (IOException | IllegalStateException | SecurityException error) { player.sendMessage("Campus recovery: " + error.getMessage()); }
    }

    @EventHandler(priority = EventPriority.HIGHEST) public void click(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) return;
        Menu menu = menus.get(player.getUniqueId());
        if (menu != null && menu.inventory != null && event.getView().getTopInventory().equals(menu.inventory)) {
            event.setCancelled(true);
            if (event.getRawSlot() >= 0 && event.getRawSlot() < menu.choices.size()) dispatch(player, menu, event.getRawSlot());
        } else if (contains(player)) event.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void drag(InventoryDragEvent event) { if (event.getWhoClicked() instanceof Player p && (contains(p) || menus.containsKey(p.getUniqueId()))) event.setCancelled(true); }
    @EventHandler public void closeMenu(InventoryCloseEvent event) {
        Menu menu = menus.get(event.getPlayer().getUniqueId());
        if (menu != null && menu.inventory != null && menu.inventory.equals(event.getInventory())) menus.remove(event.getPlayer().getUniqueId(), menu);
    }
    @EventHandler(priority = EventPriority.LOWEST) public void join(PlayerJoinEvent event) {
        if (Files.isRegularFile(stateFile(event.getPlayer()))) awaitingInventory.add(event.getPlayer().getUniqueId());
    }
    @EventHandler(priority = EventPriority.LOWEST) public void quit(PlayerQuitEvent event) { leave(event.getPlayer(), false, true); awaitingInventory.remove(event.getPlayer().getUniqueId()); menus.remove(event.getPlayer().getUniqueId()); bedrock.clear(event.getPlayer()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true) public void teleport(PlayerTeleportEvent event) {
        if (event.getTo() == null || !event.getTo().getWorld().getName().startsWith("hill_recovery_")) return;
        Session session = previews.get(event.getPlayer().getUniqueId());
        if (session == null || !event.getTo().getWorld().getName().equals(session.worldName)) event.setCancelled(true);
    }
    @EventHandler public void changedWorld(PlayerChangedWorldEvent event) {
        Session session = previews.get(event.getPlayer().getUniqueId());
        if (session != null && session.viewing && !session.leaving && !event.getPlayer().getWorld().getName().equals(session.worldName)) leave(event.getPlayer(), false);
    }
    @EventHandler(priority = EventPriority.LOWEST) public void command(PlayerCommandPreprocessEvent event) {
        if (contains(event.getPlayer()) && !event.getMessage().split(" ")[0].equalsIgnoreCase("/campusbackup")) {
            event.setCancelled(true); event.getPlayer().sendMessage("Use Cancel Preview to return to campus first.");
        }
    }
    @EventHandler(priority = EventPriority.HIGHEST) public void drop(PlayerDropItemEvent event) { if (contains(event.getPlayer())) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void swap(PlayerSwapHandItemsEvent event) { if (contains(event.getPlayer())) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void pickup(EntityPickupItemEvent event) { if (event.getEntity() instanceof Player p && contains(p)) event.setCancelled(true); }
    @EventHandler(priority = EventPriority.HIGHEST) public void damage(EntityDamageEvent event) { if (event.getEntity() instanceof Player p && contains(p)) event.setCancelled(true); }

    private static boolean ownedFolder(Path folder) {
        try { return !Files.isSymbolicLink(folder) && folder.getFileName().toString().matches("hill_recovery_[a-f0-9]{32}")
                && Files.isRegularFile(folder.resolve(MARKER)) && Files.readString(folder.resolve(MARKER)).equals(folder.getFileName().toString()); }
        catch (IOException error) { return false; }
    }
    static void deleteWorldFolder(Path folder) throws IOException {
        if (!folder.toAbsolutePath().normalize().equals(folder) || !ownedFolder(folder)
                || !folder.getParent().getFileName().toString().equals("minecraft") || !folder.getParent().getParent().getFileName().toString().equals("dimensions")) throw new IOException("Refusing an unmarked preview world path.");
        try (var paths = Files.walk(folder)) { for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(p); }
    }

    @Override public void close() {
        closed = true;
        if (timer != null) timer.cancel();
        for (Player player : Bukkit.getOnlinePlayers()) leave(player, true, true);
        bedrock.close(); menus.clear();
    }

    private record Choice(String label, String description, Material material, Consumer<Player> action) { }
    private static final class Menu {
        final UUID token; final List<Choice> choices; Inventory inventory;
        Menu(UUID token, List<Choice> choices) { this.token = token; this.choices = choices; }
    }
    private static final class Session {
        final String token = UUID.randomUUID().toString().replace("-", "");
        final String worldName = "hill_recovery_" + token;
        final CampusRecoveryAreas.Area area; final ResticRepository.Snapshot snapshot;
        final long opened = System.nanoTime();
        RecoveryPlayerState state; World world; boolean viewing; boolean leaving;
        Session(CampusRecoveryAreas.Area area, ResticRepository.Snapshot snapshot) { this.area = area; this.snapshot = snapshot; }
    }
    private static final class EmptyGenerator extends ChunkGenerator {
        @Override public boolean shouldGenerateNoise() { return false; }
        @Override public boolean shouldGenerateSurface() { return false; }
        @Override public boolean shouldGenerateCaves() { return false; }
        @Override public boolean shouldGenerateDecorations() { return false; }
        @Override public boolean shouldGenerateMobs() { return false; }
        @Override public boolean shouldGenerateStructures() { return false; }
    }
}
