package org.thehill.hill175.listener;

import io.papermc.paper.event.player.AsyncChatEvent;
import io.papermc.paper.event.player.PlayerArmSwingEvent;
import io.papermc.paper.event.player.PrePlayerAttackEntityEvent;
import com.destroystokyo.paper.event.server.PaperServerListPingEvent;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
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
import org.bukkit.event.block.Action;
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
import org.bukkit.event.entity.EntityToggleGlideEvent;
import org.bukkit.event.entity.EntityToggleSwimEvent;
import org.bukkit.event.entity.PlayerDeathEvent;
import org.bukkit.event.hanging.HangingBreakByEntityEvent;
import org.bukkit.event.hanging.HangingPlaceEvent;
import org.bukkit.event.player.PlayerArmorStandManipulateEvent;
import org.bukkit.event.player.PlayerAdvancementDoneEvent;
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
import org.bukkit.event.player.PlayerRespawnEvent;
import org.bukkit.event.player.PlayerSwapHandItemsEvent;
import org.bukkit.event.player.PlayerToggleSneakEvent;
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
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

public final class ServerListener implements Listener {
    private static final String CAMERA_MARKER_TAG = "hill175_camera_marker";
    private static final Set<String> AUTH_COMMANDS = Set.of("login", "register", "verify", "rules", "help");
    private static final Set<String> COMPETITION_COMMANDS = Set.of(
            "hill175", "competition", "entry", "team", "camera", "hub", "lobby", "rules", "login", "register", "verify", "help"
    );
    private static final Set<Material> TNT_IGNITERS = Set.of(Material.FLINT_AND_STEEL, Material.FIRE_CHARGE);

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final MenuModule menus;
    private final WorldModule worlds;
    private final Map<UUID, Instant> lastDenialMessage = new HashMap<>();
    private final Set<UUID> survivalDeaths = new HashSet<>();

    public ServerListener(JavaPlugin plugin, CompetitionModule competition, MenuModule menus, WorldModule worlds) {
        this.plugin = plugin;
        this.competition = competition;
        this.menus = menus;
        this.worlds = worlds;
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onJoin(PlayerJoinEvent event) {
        event.joinMessage(competition.usesMicrosoftAuthentication() ? null
                : Component.text(event.getPlayer().getName() + " joined the Hill 175 server.", NamedTextColor.GRAY));
        competition.handleJoin(event.getPlayer());
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onQuit(PlayerQuitEvent event) {
        if (competition.usesMicrosoftAuthentication()) {
            event.quitMessage(null);
        }
        competition.handleQuit(event.getPlayer());
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onServerListPing(PaperServerListPingEvent event) {
        if (competition.usesMicrosoftAuthentication()) {
            event.setHidePlayers(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onDeathAnnouncement(PlayerDeathEvent event) {
        if (competition.usesMicrosoftAuthentication()) {
            event.deathMessage(null);
            event.setShowDeathMessages(false);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onAdvancementAnnouncement(PlayerAdvancementDoneEvent event) {
        if (competition.usesMicrosoftAuthentication()) {
            event.message(null);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onChat(AsyncChatEvent event) {
        if (!competition.isAuthenticated(event.getPlayer())) {
            event.setCancelled(true);
            event.getPlayer().sendMessage(Component.text("Authenticate before using public chat.", NamedTextColor.RED));
            return;
        }
        if (competition.usesMicrosoftAuthentication()) {
            event.viewers().removeIf(viewer -> viewer instanceof Player player && !competition.isAuthenticated(player));
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onCommand(PlayerCommandPreprocessEvent event) {
        if (!competition.usesMicrosoftAuthentication() && competition.isAuthenticated(event.getPlayer())
                && worlds.isSurvivalWorld(event.getPlayer().getWorld())) {
            return;
        }
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
        Optional<Location> lockedLocation = competition.lockedSessionLocation(player);
        if (lockedLocation.isPresent()) {
            event.setTo(lockedLocation.get());
            return;
        }
        Location to = event.getTo();
        if (to == null) {
            return;
        }
        if (worlds.isSurvivalWorld(event.getFrom()) && worlds.isSurvivalWorld(to)) {
            return;
        }
        if (!event.hasChangedBlock() && event.getFrom().getWorld().equals(to.getWorld())) {
            return;
        }
        competition.refreshMovementMode(player, to);
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onToggleSneak(PlayerToggleSneakEvent event) {
        if (competition.isCameraPreviewing(event.getPlayer())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onToggleSwim(EntityToggleSwimEvent event) {
        if (event.getEntity() instanceof Player player && competition.isCameraPreviewing(player)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onToggleGlide(EntityToggleGlideEvent event) {
        if (event.getEntity() instanceof Player player && competition.isCameraPreviewing(player)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPlayerAnimation(PlayerArmSwingEvent event) {
        if (event.getHand() != EquipmentSlot.HAND) {
            return;
        }
        Player player = event.getPlayer();
        ItemStack item = player.getInventory().getItemInMainHand();
        if (competition.isCompetitionItem(item, CompetitionModule.CAMERA_PREVIEW_ITEM_ID)) {
            if (competition.acceptsCameraPreviewLeftClick(player)) {
                event.setCancelled(true);
                competition.exitCameraPreview(player);
            }
            return;
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onInteract(PlayerInteractEvent event) {
        Player player = event.getPlayer();
        if (!competition.isAuthenticated(player)) {
            event.setCancelled(true);
            return;
        }
        if (worlds.isSurvivalWorld(player.getWorld())) {
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
                if (event.getAction().isRightClick()) {
                    competition.useCameraItem(player);
                }
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.CAMERA_PREVIEW_ITEM_ID)) {
                event.setCancelled(true);
                competition.exitCameraPreview(player);
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.CAMERA_PREVIEW_REMOVE_ITEM_ID)) {
                event.setCancelled(true);
                menus.openActiveCameraRemovalConfirmation(player);
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.ENTRY_RESET_ITEM_ID)) {
                event.setCancelled(true);
                competition.currentEntry(player).ifPresentOrElse(entry -> {
                    if (entry.isMember(competition.participantKey(player))) {
                        menus.openResetConfirmation(player, entry);
                    } else {
                        deny(player, "Open one of your entries first.");
                    }
                }, () -> deny(player, "Open one of your entries first."));
                return;
            }
            if (competition.isCompetitionItem(item, CompetitionModule.ENTRY_SUBMIT_ITEM_ID)) {
                event.setCancelled(true);
                competition.currentEntry(player).ifPresentOrElse(entry -> {
                    if (entry.submitted()) {
                        competition.unlockEntry(player, entry);
                    } else if (entry.isMember(competition.participantKey(player))) {
                        menus.openSubmitConfirmation(player, entry);
                    } else {
                        deny(player, "Open one of your entries first.");
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
            if (competition.isCompetitionItem(item, CompetitionModule.CAMPUS_CHART_ITEM_ID)) {
                event.setCancelled(true);
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
        if (worlds.isSurvivalWorld(event.getPlayer().getWorld())) {
            return;
        }
        if (event.getHand() == EquipmentSlot.HAND
                && competition.isCompetitionItem(
                event.getPlayer().getInventory().getItemInMainHand(),
                CompetitionModule.CAMERA_PREVIEW_ITEM_ID)) {
            event.setCancelled(true);
            competition.exitCameraPreview(event.getPlayer());
            return;
        }
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

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPrePlayerAttackEntity(PrePlayerAttackEntityEvent event) {
        if (worlds.isSurvivalWorld(event.getPlayer().getWorld())) {
            return;
        }
        if (competition.isCompetitionItem(event.getPlayer().getInventory().getItemInMainHand(),
                CompetitionModule.CAMERA_PREVIEW_ITEM_ID)) {
            event.setCancelled(true);
            if (competition.acceptsCameraPreviewLeftClick(event.getPlayer())) {
                competition.exitCameraPreview(event.getPlayer());
            }
            return;
        }
        if (!event.getAttacked().getScoreboardTags().contains(CAMERA_MARKER_TAG)) {
            return;
        }
        event.setCancelled(true);
        competition.previewCameraMarker(event.getPlayer(), event.getAttacked());
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player) || worlds.isSurvivalWorld(player.getWorld())) {
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
        if (event.getWhoClicked() instanceof Player player && worlds.isSurvivalWorld(player.getWorld())) {
            return;
        }
        if (event.getNewItems().values().stream().anyMatch(this::isProtectedCompetitionItem)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onSwapHands(PlayerSwapHandItemsEvent event) {
        if (worlds.isSurvivalWorld(event.getPlayer().getWorld())) {
            return;
        }
        if (isProtectedCompetitionItem(event.getMainHandItem()) || isProtectedCompetitionItem(event.getOffHandItem())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent event) {
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
        if (!competition.mayBuild(event.getPlayer(), event.getBlock().getLocation())) {
            event.setCancelled(true);
            deny(event.getPlayer(), "You may only break blocks inside your own unlocked entry.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPlace(BlockPlaceEvent event) {
        if (worlds.isSurvivalWorld(event.getBlockPlaced().getWorld())) {
            return;
        }
        if (!competition.mayBuild(event.getPlayer(), event.getBlockPlaced().getLocation())) {
            event.setCancelled(true);
            deny(event.getPlayer(), "You may only place blocks inside your own unlocked entry.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBucketEmpty(PlayerBucketEmptyEvent event) {
        if (worlds.isSurvivalWorld(event.getBlockClicked().getWorld())) {
            return;
        }
        Location target = event.getBlockClicked().getRelative(event.getBlockFace()).getLocation();
        if (!competition.mayBuild(event.getPlayer(), target)) {
            event.setCancelled(true);
            deny(event.getPlayer(), "Fluids must stay inside your own entry.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBucketFill(PlayerBucketFillEvent event) {
        if (worlds.isSurvivalWorld(event.getBlockClicked().getWorld())) {
            return;
        }
        if (!competition.mayBuild(event.getPlayer(), event.getBlockClicked().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onFluidFlow(BlockFromToEvent event) {
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())
                || worlds.isSurvivalWorld(event.getToBlock().getWorld())) {
            return;
        }
        Optional<Entry> sourceEntry = competition.entryAt(event.getBlock().getLocation());
        if (sourceEntry.isEmpty() || !sourceEntry.get().region().contains(event.getToBlock().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onDispense(BlockDispenseEvent event) {
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getSource().getWorld())
                || worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
        if (competition.entryAt(event.getBlock().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onStructureGrow(StructureGrowEvent event) {
        if (worlds.isSurvivalWorld(event.getWorld())) {
            return;
        }
        Optional<Entry> sourceEntry = competition.entryAt(event.getLocation());
        if (sourceEntry.isEmpty() || event.getBlocks().stream()
                .anyMatch(state -> !sourceEntry.get().region().contains(state.getLocation()))) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onForm(BlockFormEvent event) {
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
        if (competition.entryAt(event.getBlock().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onFade(BlockFadeEvent event) {
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
        if (competition.entryAt(event.getBlock().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBurn(BlockBurnEvent event) {
        if (!worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onTntPrime(TNTPrimeEvent event) {
        if (!worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onEntityExplode(EntityExplodeEvent event) {
        if (!worlds.isSurvivalWorld(event.getEntity().getWorld())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBlockExplode(BlockExplodeEvent event) {
        if (!worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onEntitySpawn(EntitySpawnEvent event) {
        if (worlds.isSurvivalWorld(event.getLocation().getWorld())) {
            return;
        }
        if (event.getEntityType() == EntityType.TNT) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onCreatureSpawn(CreatureSpawnEvent event) {
        if (worlds.isSurvivalWorld(event.getLocation().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getEntity().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getRightClicked().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getEntity().getWorld())) {
            return;
        }
        if (event.getPlayer() == null || !competition.mayBuild(event.getPlayer(), event.getEntity().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onHangingBreak(HangingBreakByEntityEvent event) {
        if (worlds.isSurvivalWorld(event.getEntity().getWorld())) {
            return;
        }
        if (!(event.getRemover() instanceof Player player) || !competition.mayBuild(player, event.getEntity().getLocation())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onVehicleCreate(VehicleCreateEvent event) {
        if (worlds.isSurvivalWorld(event.getVehicle().getWorld())) {
            return;
        }
        if (competition.entryAt(event.getVehicle().getLocation()).isEmpty()) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onVehicleMove(VehicleMoveEvent event) {
        if (worlds.isSurvivalWorld(event.getVehicle().getWorld())
                || worlds.isSurvivalWorld(event.getFrom())
                || worlds.isSurvivalWorld(event.getTo())) {
            return;
        }
        Optional<Entry> entry = competition.entryAt(event.getFrom());
        if (entry.isPresent() && !entry.get().region().contains(event.getTo())) {
            event.getVehicle().teleport(event.getFrom());
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPistonExtend(BlockPistonExtendEvent event) {
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
        Optional<Entry> entry = competition.entryAt(event.getBlock().getLocation());
        if (entry.isEmpty() || event.getBlocks().stream()
                .map(block -> block.getRelative(event.getDirection()).getLocation())
                .anyMatch(location -> !entry.get().region().contains(location))) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPistonRetract(BlockPistonRetractEvent event) {
        if (worlds.isSurvivalWorld(event.getBlock().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getFrom())) {
            // The survival world is Paper's primary Overworld/Nether/End trio,
            // so retaining Paper's resolved destination preserves normal portal
            // search, creation, coordinate scaling, and safe arrival behavior.
            if (event.getTo() == null || !worlds.isSurvivalWorld(event.getTo())) {
                event.setCancelled(true);
                plugin.getLogger().warning("Blocked a survival portal whose resolved destination left the primary world trio.");
                deny(event.getPlayer(), "That portal destination is unavailable. Please try again.");
            }
            return;
        }
        event.setCancelled(true);
        deny(event.getPlayer(), "Portals are disabled in the competition.");
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPortalCreate(PortalCreateEvent event) {
        if (!worlds.isSurvivalWorld(event.getWorld())
                && event.getBlocks().stream().noneMatch(state -> worlds.isSurvivalWorld(state.getWorld()))) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onDamage(EntityDamageEvent event) {
        if (worlds.isSurvivalWorld(event.getEntity().getWorld())) {
            return;
        }
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
        if (worlds.isSurvivalWorld(event.getPlayer().getWorld())) {
            return;
        }
        if (isProtectedCompetitionItem(event.getItemDrop().getItemStack())) {
            event.setCancelled(true);
        }
    }

    private boolean isProtectedCompetitionItem(ItemStack item) {
        return competition.isCompetitionItem(item, CompetitionModule.COMPASS_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.ENTRY_MENU_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.CAMERA_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.CAMERA_PREVIEW_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.CAMERA_PREVIEW_REMOVE_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.ENTRY_RESET_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.ENTRY_SUBMIT_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.LOBBY_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.CAMPUS_CHART_ITEM_ID)
                || competition.isCompetitionItem(item, CompetitionModule.RULES_ITEM_ID);
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onDeath(PlayerDeathEvent event) {
        if (worlds.isSurvivalWorld(event.getPlayer().getWorld())) {
            survivalDeaths.add(event.getPlayer().getUniqueId());
            competition.handleSurvivalDeath(event.getPlayer());
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onRespawn(PlayerRespawnEvent event) {
        Player player = event.getPlayer();
        if (!survivalDeaths.remove(player.getUniqueId())) {
            return;
        }
        if (!worlds.isSurvivalWorld(event.getRespawnLocation().getWorld())) {
            event.setRespawnLocation(worlds.survivalSpawn());
        }
        Bukkit.getScheduler().runTask(plugin, () -> competition.handleSurvivalRespawn(player));
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
