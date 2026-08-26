package org.thehill.hill175.listener;

import io.papermc.paper.event.player.AsyncChatEvent;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.block.BlockFace;
import org.bukkit.block.data.Directional;
import org.bukkit.entity.EnderCrystal;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Player;
import org.bukkit.entity.ArmorStand;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockBurnEvent;
import org.bukkit.event.block.BlockDispenseEvent;
import org.bukkit.event.block.BlockExplodeEvent;
import org.bukkit.event.block.BlockFadeEvent;
import org.bukkit.event.block.BlockFormEvent;
import org.bukkit.event.block.BlockFromToEvent;
import org.bukkit.event.block.BlockGrowEvent;
import org.bukkit.event.block.BlockIgniteEvent;
import org.bukkit.event.block.BlockPistonExtendEvent;
import org.bukkit.event.block.BlockPistonRetractEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.block.BlockSpreadEvent;
import org.bukkit.event.block.TNTPrimeEvent;
import org.bukkit.event.entity.CreatureSpawnEvent;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.EntityExplodeEvent;
import org.bukkit.event.entity.EntityPlaceEvent;
import org.bukkit.event.entity.EntitySpawnEvent;
import org.bukkit.event.hanging.HangingBreakByEntityEvent;
import org.bukkit.event.hanging.HangingPlaceEvent;
import org.bukkit.event.player.PlayerArmorStandManipulateEvent;
import org.bukkit.event.player.PlayerBucketEmptyEvent;
import org.bukkit.event.player.PlayerBucketFillEvent;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.event.player.PlayerDropItemEvent;
import org.bukkit.event.player.PlayerInteractEntityEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerMoveEvent;
import org.bukkit.event.player.PlayerPortalEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.player.PlayerSwapHandItemsEvent;
import org.bukkit.event.vehicle.VehicleCreateEvent;
import org.bukkit.event.vehicle.VehicleMoveEvent;
import org.bukkit.event.world.PortalCreateEvent;
import org.bukkit.event.world.StructureGrowEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.inventory.ItemStack;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

public final class ServerListener implements Listener {
    private static final String CAMERA_MARKER_TAG = "hill175_camera_marker";
    private static final Set<String> AUTH_COMMANDS = Set.of("login", "register", "rules", "help");
    private static final Set<String> COMPETITION_COMMANDS = Set.of(
            "hill175", "competition", "entry", "team", "camera", "hub", "lobby", "rules", "login", "register", "help"
    );
    private static final Set<Material> TNT_IGNITERS = Set.of(Material.FLINT_AND_STEEL, Material.FIRE_CHARGE);

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final MenuModule menus;
    private final WorldModule worlds;
    private final Map<java.util.UUID, Instant> lastDenialMessage = new HashMap<>();

    public ServerListener(JavaPlugin plugin, CompetitionModule competition, MenuModule menus, WorldModule worlds) {
        this.plugin = plugin;
        this.competition = competition;
        this.menus = menus;
        this.worlds = worlds;
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onJoin(PlayerJoinEvent event) {
        event.joinMessage(Component.text(event.getPlayer().getName() + " joined the Hill 175 server.", NamedTextColor.GRAY));
        competition.handleJoin(event.getPlayer());
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onQuit(PlayerQuitEvent event) {
        competition.handleQuit(event.getPlayer());
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onChat(AsyncChatEvent event) {
        if (!competition.isAuthenticated(event.getPlayer())) {
            event.setCancelled(true);
            event.getPlayer().sendMessage(Component.text("Authenticate before using public chat.", NamedTextColor.RED));
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onCommand(PlayerCommandPreprocessEvent event) {
        if (isNamespacedCommand(event.getMessage())) {
            event.setCancelled(true);
            deny(event.getPlayer(), "Use the Hill commands shown in /help.");
            return;
        }
        String commandName = commandName(event.getMessage());
        if (commandName.equals("help")) {
            event.setCancelled(true);
            competition.sendHelp(event.getPlayer());
            return;
        }
        Set<String> allowed = competition.isAuthenticated(event.getPlayer()) ? COMPETITION_COMMANDS : AUTH_COMMANDS;
        if (!allowed.contains(commandName)) {
            event.setCancelled(true);
            deny(event.getPlayer(), "Only Hill competition commands are enabled.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onMove(PlayerMoveEvent event) {
        Player player = event.getPlayer();
        if (!competition.isAuthenticated(player)) {
            Location locked = worlds.authenticationSpawn();
            Location to = event.getTo();
            if (to == null) {
                event.setTo(locked);
                return;
            }
            boolean movedPosition = !to.getWorld().equals(locked.getWorld())
                    || Math.abs(to.getX() - locked.getX()) > 0.001
                    || Math.abs(to.getY() - locked.getY()) > 0.001
                    || Math.abs(to.getZ() - locked.getZ()) > 0.001;
            if (movedPosition) {
                Location corrected = locked.clone();
                corrected.setYaw(to.getYaw());
                corrected.setPitch(to.getPitch());
                event.setTo(corrected);
            }
            return;
        }
        if (!event.hasChangedBlock() && event.getFrom().getWorld().equals(event.getTo().getWorld())) {
            return;
        }
        competition.refreshMovementMode(player, event.getTo());
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onInteract(PlayerInteractEvent event) {
        Player player = event.getPlayer();
        if (!competition.isAuthenticated(player)) {
            event.setCancelled(true);
            return;
        }
        if (event.getHand() == EquipmentSlot.HAND) {
            ItemStack item = event.getItem();
            if (competition.isCompetitionItem(item, CompetitionModule.COMPASS_ITEM_ID)) {
                event.setCancelled(true);
                menus.openMain(player);
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.ENTRY_MENU_ITEM_ID)) {
                event.setCancelled(true);
                menus.openCurrentEntry(player);
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.CAMERA_ITEM_ID)) {
                event.setCancelled(true);
                if (event.getAction().isLeftClick()) {
                    competition.previewNextCamera(player);
                } else if (competition.mayBuild(player, player.getLocation())) {
                    competition.recordCamera(player);
                } else {
                    competition.previewNextCamera(player);
                }
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.CAMERA_PREVIEW_ITEM_ID)) {
                event.setCancelled(true);
                competition.previewNextCamera(player);
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.ENTRY_RESET_ITEM_ID)) {
                event.setCancelled(true);
                competition.resetCurrentEntry(player);
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.ENTRY_SUBMIT_ITEM_ID)) {
                event.setCancelled(true);
                competition.currentEntry(player).ifPresentOrElse(entry -> {
                    if (entry.submitted()) {
                        competition.unlockEntry(player, entry);
                    } else {
                        competition.submitEntry(player, entry);
                    }
                }, () -> deny(player, "Open one of your entries first."));
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.LOBBY_ITEM_ID)) {
                event.setCancelled(true);
                competition.teleportHub(player);
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.RULES_ITEM_ID)) {
                event.setCancelled(true);
                competition.sendRules(player);
                return;
            }
        }
        if (event.getClickedBlock() != null
                && event.getClickedBlock().getType() == Material.TNT
                && event.getItem() != null
                && TNT_IGNITERS.contains(event.getItem().getType())) {
            event.setCancelled(true);
            deny(player, "TNT may be placed as decoration but cannot be ignited.");
            return;
        }
        if (event.getClickedBlock() != null && !competition.mayBuild(player, event.getClickedBlock().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onInteractEntity(PlayerInteractEntityEvent event) {
        Entity entity = event.getRightClicked();
        if (entity.getScoreboardTags().contains("hill175_category_npc")) {
            return;
        }
        if (entity.getScoreboardTags().contains(CAMERA_MARKER_TAG)) {
            event.setCancelled(true);
            competition.previewCameraMarker(event.getPlayer(), entity);
            return;
        }
        if (!competition.mayBuild(event.getPlayer(), entity.getLocation())) {
            event.setCancelled(true);
            deny(event.getPlayer(), "Visitor Mode is read-only.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player)) {
            return;
        }
        ItemStack hotbarItem = event.getHotbarButton() >= 0
                ? event.getWhoClicked().getInventory().getItem(event.getHotbarButton())
                : null;
        if (isProtectedCompetitionItem(event.getCurrentItem())
                || isProtectedCompetitionItem(event.getCursor())
                || isProtectedCompetitionItem(hotbarItem)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onInventoryDrag(InventoryDragEvent event) {
        if (event.getNewItems().values().stream().anyMatch(this::isProtectedCompetitionItem)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onSwapHands(PlayerSwapHandItemsEvent event) {
        if (isProtectedCompetitionItem(event.getMainHandItem()) || isProtectedCompetitionItem(event.getOffHandItem())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent event) {
        if (!competition.mayBuild(event.getPlayer(), event.getBlock().getLocation())) {
            event.setCancelled(true);
            deny(event.getPlayer(), "You may only break blocks inside your own unlocked entry.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPlace(BlockPlaceEvent event) {
        if (!competition.mayBuild(event.getPlayer(), event.getBlockPlaced().getLocation())) {
            event.setCancelled(true);
            deny(event.getPlayer(), "You may only place blocks inside your own unlocked entry.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBucketEmpty(PlayerBucketEmptyEvent event) {
        Location target = event.getBlockClicked().getRelative(event.getBlockFace()).getLocation();
        if (!competition.mayBuild(event.getPlayer(), target)) {
            event.setCancelled(true);
            deny(event.getPlayer(), "Fluids must stay inside your own entry.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBucketFill(PlayerBucketFillEvent event) {
        if (!competition.mayBuild(event.getPlayer(), event.getBlockClicked().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onFluidFlow(BlockFromToEvent event) {
        Optional<Entry> sourceEntry = competition.entryAt(event.getBlock().getLocation());
        if (sourceEntry.isEmpty() || !sourceEntry.get().region().contains(event.getToBlock().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onDispense(BlockDispenseEvent event) {
        Optional<Entry> entry = competition.entryAt(event.getBlock().getLocation());
        if (entry.isEmpty() || !(event.getBlock().getBlockData() instanceof Directional directional)) {
            event.setCancelled(true);
            return;
        }
        Location target = event.getBlock().getRelative(directional.getFacing()).getLocation();
        Material material = event.getItem().getType();
        boolean unsafeProjectile = material == Material.FIRE_CHARGE
                || material == Material.TNT
                || material == Material.TNT_MINECART;
        if (unsafeProjectile || !entry.get().region().contains(target)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onIgnite(BlockIgniteEvent event) {
        boolean allowed = switch (event.getCause()) {
            case FLINT_AND_STEEL, FIREBALL -> event.getPlayer() != null
                    && competition.mayBuild(event.getPlayer(), event.getBlock().getLocation());
            case LAVA -> event.getIgnitingBlock() != null
                    && competition.entryAt(event.getIgnitingBlock().getLocation())
                    .filter(entry -> entry.region().contains(event.getBlock().getLocation()))
                    .isPresent();
            default -> false;
        };
        event.setCancelled(!allowed);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onFireSpread(BlockSpreadEvent event) {
        if (event.getSource().getType() == Material.FIRE || event.getSource().getType() == Material.SOUL_FIRE) {
            event.setCancelled(true);
            return;
        }
        Optional<Entry> sourceEntry = competition.entryAt(event.getSource().getLocation());
        if (sourceEntry.isEmpty() || !sourceEntry.get().region().contains(event.getBlock().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onGrow(BlockGrowEvent event) {
        if (competition.entryAt(event.getBlock().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onStructureGrow(StructureGrowEvent event) {
        Optional<Entry> sourceEntry = competition.entryAt(event.getLocation());
        if (sourceEntry.isEmpty() || event.getBlocks().stream()
                .anyMatch(state -> !sourceEntry.get().region().contains(state.getLocation()))) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onForm(BlockFormEvent event) {
        if (competition.entryAt(event.getBlock().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onFade(BlockFadeEvent event) {
        if (competition.entryAt(event.getBlock().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBurn(BlockBurnEvent event) {
        event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onTntPrime(TNTPrimeEvent event) {
        event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onEntityExplode(EntityExplodeEvent event) {
        event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBlockExplode(BlockExplodeEvent event) {
        event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onEntitySpawn(EntitySpawnEvent event) {
        if (event.getEntityType() == EntityType.TNT) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onCreatureSpawn(CreatureSpawnEvent event) {
        if (event.getEntity() instanceof ArmorStand) {
            return;
        }
        boolean systemNpc = event.getSpawnReason() == CreatureSpawnEvent.SpawnReason.CUSTOM
                && event.getLocation().getWorld().equals(worlds.hubWorld());
        if (!systemNpc) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onEntityPlace(EntityPlaceEvent event) {
        Player player = event.getPlayer();
        if (player == null || !competition.mayBuild(player, event.getEntity().getLocation())) {
            event.setCancelled(true);
            return;
        }
        Optional<Entry> entry = competition.entryAt(event.getEntity().getLocation());
        if (entry.isPresent()) {
            long entityCount = event.getEntity().getWorld().getEntities().stream()
                    .filter(entity -> entry.get().region().contains(entity.getLocation()))
                    .count();
            int limit = plugin.getConfig().getInt("build-rules.max-non-player-entities-per-entry", 128);
            if (entityCount > limit) {
                event.setCancelled(true);
                deny(player, "This entry reached its decorative entity limit of " + limit + ".");
            }
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onArmorStandManipulate(PlayerArmorStandManipulateEvent event) {
        if (event.getRightClicked().getScoreboardTags().contains(CAMERA_MARKER_TAG)) {
            event.setCancelled(true);
            return;
        }
        if (!competition.mayBuild(event.getPlayer(), event.getRightClicked().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onHangingPlace(HangingPlaceEvent event) {
        if (event.getPlayer() == null || !competition.mayBuild(event.getPlayer(), event.getEntity().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onHangingBreak(HangingBreakByEntityEvent event) {
        if (!(event.getRemover() instanceof Player player) || !competition.mayBuild(player, event.getEntity().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onVehicleCreate(VehicleCreateEvent event) {
        if (competition.entryAt(event.getVehicle().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onVehicleMove(VehicleMoveEvent event) {
        Optional<Entry> entry = competition.entryAt(event.getFrom());
        if (entry.isPresent() && !entry.get().region().contains(event.getTo())) {
            event.getVehicle().teleport(event.getFrom());
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPistonExtend(BlockPistonExtendEvent event) {
        Optional<Entry> entry = competition.entryAt(event.getBlock().getLocation());
        if (entry.isEmpty() || event.getBlocks().stream()
                .map(block -> block.getRelative(event.getDirection()).getLocation())
                .anyMatch(location -> !entry.get().region().contains(location))) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPistonRetract(BlockPistonRetractEvent event) {
        Optional<Entry> entry = competition.entryAt(event.getBlock().getLocation());
        BlockFace direction = event.getDirection();
        if (entry.isEmpty() || event.getBlocks().stream().anyMatch(block ->
                !entry.get().region().contains(block.getLocation())
                        || !entry.get().region().contains(block.getRelative(direction).getLocation())
                        || !entry.get().region().contains(block.getRelative(direction.getOppositeFace()).getLocation()))) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPortal(PlayerPortalEvent event) {
        event.setCancelled(true);
        deny(event.getPlayer(), "Portals are disabled in the competition.");
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPortalCreate(PortalCreateEvent event) {
        event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onDamage(EntityDamageEvent event) {
        if (event.getEntity() instanceof Player) {
            event.setCancelled(true);
            return;
        }
        if (event.getEntity().getScoreboardTags().contains(CAMERA_MARKER_TAG)) {
            event.setCancelled(true);
            if (event instanceof EntityDamageByEntityEvent byEntity
                    && byEntity.getDamager() instanceof Player player) {
                competition.previewCameraMarker(player, event.getEntity());
            }
            return;
        }
        if (event.getEntity() instanceof EnderCrystal) {
            event.setCancelled(true);
            if (event instanceof EntityDamageByEntityEvent byEntity
                    && byEntity.getDamager() instanceof Player player
                    && player.isSneaking()
                    && competition.mayBuild(player, event.getEntity().getLocation())) {
                event.getEntity().remove();
                player.sendMessage(Component.text("Decorative end crystal removed safely.", NamedTextColor.YELLOW));
            }
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onDrop(PlayerDropItemEvent event) {
        if (isProtectedCompetitionItem(event.getItemDrop().getItemStack())) {
            event.setCancelled(true);
        }
    }

    private boolean isProtectedCompetitionItem(ItemStack item) {
        return competition.isCompetitionItem(item, CompetitionModule.COMPASS_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.ENTRY_MENU_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.CAMERA_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.CAMERA_PREVIEW_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.ENTRY_RESET_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.ENTRY_SUBMIT_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.LOBBY_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.RULES_ITEM_ID);
    }

    private void deny(Player player, String text) {
        Instant now = Instant.now();
        Instant previous = lastDenialMessage.get(player.getUniqueId());
        if (previous != null && Duration.between(previous, now).toMillis() < 1_000) {
            return;
        }
        lastDenialMessage.put(player.getUniqueId(), now);
        player.sendMessage(Component.text(text, NamedTextColor.RED));
    }

    private static String commandName(String rawCommand) {
        String stripped = rawCommand.startsWith("/") ? rawCommand.substring(1) : rawCommand;
        int space = stripped.indexOf(' ');
        String name = space >= 0 ? stripped.substring(0, space) : stripped;
        int namespace = name.indexOf(':');
        if (namespace >= 0) {
            name = name.substring(namespace + 1);
        }
        return name.toLowerCase(Locale.ROOT);
    }

    private static boolean isNamespacedCommand(String rawCommand) {
        String stripped = rawCommand.startsWith("/") ? rawCommand.substring(1) : rawCommand;
        int space = stripped.indexOf(' ');
        String name = space >= 0 ? stripped.substring(0, space) : stripped;
        return name.contains(":");
    }
}
