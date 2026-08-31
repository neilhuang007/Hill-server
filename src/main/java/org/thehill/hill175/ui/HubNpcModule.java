package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.Color;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.entity.Display;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.entity.TextDisplay;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.player.PlayerInteractAtEntityEvent;
import org.bukkit.event.player.PlayerInteractEntityEvent;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.PlayerInventory;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scoreboard.Scoreboard;
import org.bukkit.scoreboard.Team;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.world.WorldModule;

import java.time.Duration;
import java.time.Instant;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/** Real player-entity hub guides with Hypixel-style floating titles. */
public final class HubNpcModule implements Listener {
    private static final String NPC_TAG = "hill175_category_npc";
    private static final String NPC_PART_TAG = "hill175_category_npc_part";
    private static final String NPC_TEAM_NAME = "hill175_npcs";
    private static final String SURVIVAL_TAG = "hill175_survival_guide";
    private static final Duration INTERACTION_DEBOUNCE = Duration.ofMillis(350);
    private static final Pattern PROFILE_NAME_PATTERN = Pattern.compile("^[A-Za-z0-9_]{3,16}$");
    private static final Pattern TEXTURE_HASH_PATTERN = Pattern.compile("^[0-9a-f]{64}$");

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final MenuModule menus;
    private final WorldModule worlds;
    private final Map<Category, SyntheticPlayerNpc> categoryNpcs = new EnumMap<>(Category.class);
    private final Map<Category, TextDisplay> categoryNameplates = new EnumMap<>(Category.class);
    private final Map<UUID, RecentInteraction> recentInteractions = new HashMap<>();
    private SyntheticPlayerNpc survivalNpc;
    private TextDisplay survivalNameplate;

    public HubNpcModule(JavaPlugin plugin, CompetitionModule competition, MenuModule menus, WorldModule worlds) {
        this.plugin = plugin;
        this.competition = competition;
        this.menus = menus;
        this.worlds = worlds;
    }

    public void spawnCategoryNpcs() {
        removeCategoryNpcs();
        for (Category category : Category.values()) {
            worlds.hubNpcLocation(category).getChunk().load();
        }
        worlds.survivalNpcLocation().getChunk().load();
        // Remove guides left by an interrupted reload or the former armor-stand implementation.
        for (Entity entity : worlds.hubWorld().getEntities()) {
            if (entity.getScoreboardTags().contains(NPC_TAG)
                    || entity.getScoreboardTags().contains(NPC_PART_TAG)) {
                entity.remove();
            }
        }

        Map<Category, CategoryStyle> styles = new EnumMap<>(Category.class);
        Set<String> profileNames = new HashSet<>();
        for (Category category : Category.values()) {
            CategoryStyle style = configuredStyle(category);
            if (!profileNames.add(style.profileName().toLowerCase(Locale.ROOT))) {
                throw new IllegalStateException("Category NPC profile names must be unique");
            }
            styles.put(category, style);
        }
        SurvivalStyle survivalStyle = configuredSurvivalStyle();
        if (!profileNames.add(survivalStyle.profileName().toLowerCase(Locale.ROOT))) {
            throw new IllegalStateException("Hub NPC profile names must be unique");
        }
        try {
            spawn(worlds.hubNpcLocation(Category.JOURNEY), Category.JOURNEY, styles.get(Category.JOURNEY));
            spawn(worlds.hubNpcLocation(Category.PLACE), Category.PLACE, styles.get(Category.PLACE));
            spawn(worlds.hubNpcLocation(Category.PEOPLE), Category.PEOPLE, styles.get(Category.PEOPLE));
            spawnSurvival(worlds.survivalNpcLocation(), survivalStyle);
        } catch (RuntimeException exception) {
            removeCategoryNpcs();
            throw exception;
        }
        plugin.getLogger().info("Hill 175 player hub guides ready: " + (categoryNpcs.size() + (survivalNpc == null ? 0 : 1)) + "/4.");
    }

    public void shutdown() {
        removeCategoryNpcs();
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        // The hub is in another dimension, so preload the profiles before the
        // authenticated viewer gets close enough to track the NPC entities.
        sendNpcsTo(event.getPlayer());
    }

    @EventHandler
    public void onChangedWorld(PlayerChangedWorldEvent event) {
        if (!event.getPlayer().getWorld().equals(worlds.hubWorld())) {
            return;
        }
        Bukkit.getScheduler().runTask(plugin, () -> {
            if (!event.getPlayer().isOnline() || !event.getPlayer().getWorld().equals(worlds.hubWorld())) {
                return;
            }
            sendNpcsTo(event.getPlayer());
        });
    }

    @EventHandler
    public void onInteractAt(PlayerInteractAtEntityEvent event) {
        Entity npc = npcEntity(event.getRightClicked());
        if (npc == null) {
            return;
        }
        event.setCancelled(true);
        handle(event.getPlayer(), npc);
    }

    @EventHandler
    public void onInteract(PlayerInteractEntityEvent event) {
        Entity npc = npcEntity(event.getRightClicked());
        if (npc == null) {
            return;
        }
        event.setCancelled(true);
        handle(event.getPlayer(), npc);
    }

    @EventHandler
    public void onDamage(EntityDamageEvent event) {
        Entity npc = npcEntity(event.getEntity());
        if (npc == null) {
            return;
        }
        event.setCancelled(true);
        if (event instanceof EntityDamageByEntityEvent damageByEntity
                && damageByEntity.getDamager() instanceof Player player) {
            handle(player, npc);
        }
    }

    private void handle(Player player, Entity entity) {
        if (!entity.getScoreboardTags().contains(NPC_TAG)) {
            return;
        }
        Instant now = Instant.now();
        RecentInteraction recent = recentInteractions.get(player.getUniqueId());
        if (recent != null
                && recent.entityId().equals(entity.getUniqueId())
                && Duration.between(recent.when(), now).compareTo(INTERACTION_DEBOUNCE) < 0) {
            return;
        }
        recentInteractions.put(player.getUniqueId(), new RecentInteraction(entity.getUniqueId(), now));
        if (entity.getScoreboardTags().contains(SURVIVAL_TAG)) {
            if (!competition.isAuthenticated(player)) {
                competition.sendAuthenticationInstructions(player);
                return;
            }
            menus.openSurvival(player);
            return;
        }
        for (Category category : Category.values()) {
            if (!entity.getScoreboardTags().contains(categoryTag(category))) {
                continue;
            }
            if (!competition.isAuthenticated(player)) {
                competition.sendAuthenticationInstructions(player);
                return;
            }
            menus.openCategory(player, category);
            return;
        }
    }

    private void spawn(Location location, Category category, CategoryStyle style) {
        location.getChunk().load();
        npcTeam().addEntry(style.profileName());
        SyntheticPlayerNpc synthetic = SyntheticPlayerNpc.spawn(
                plugin,
                location,
                style.profileName(),
                style.skinTexture()
        );
        Player npc = synthetic.player();
        npc.addScoreboardTag(NPC_TAG);
        npc.addScoreboardTag(categoryTag(category));
        npc.setCanPickupItems(false);
        npc.setRotation(location.getYaw(), location.getPitch());
        PlayerInventory inventory = npc.getInventory();
        inventory.setHeldItemSlot(0);
        inventory.setItemInMainHand(new ItemStack(style.heldItem()));
        inventory.setItemInOffHand(new ItemStack(style.offhandItem()));
        categoryNpcs.put(category, synthetic);
        categoryNameplates.put(category,
                spawnNameplate(location, style.title(), style.titleColor(), Set.of(categoryTag(category))));
        synthetic.activate();
        plugin.getLogger().fine("Spawned player category NPC " + category.name() + " at " + location);
    }

    private void spawnSurvival(Location location, SurvivalStyle style) {
        location.getChunk().load();
        npcTeam().addEntry(style.profileName());
        SyntheticPlayerNpc synthetic = SyntheticPlayerNpc.spawn(
                plugin,
                location,
                style.profileName(),
                style.skinTexture()
        );
        Player npc = synthetic.player();
        npc.addScoreboardTag(NPC_TAG);
        npc.addScoreboardTag(SURVIVAL_TAG);
        npc.setCanPickupItems(false);
        npc.setRotation(location.getYaw(), location.getPitch());
        PlayerInventory inventory = npc.getInventory();
        inventory.setHeldItemSlot(0);
        inventory.setItemInMainHand(new ItemStack(style.heldItem()));
        inventory.setItemInOffHand(new ItemStack(style.offhandItem()));
        survivalNpc = synthetic;
        survivalNameplate = spawnNameplate(location, style.title(), style.titleColor(), Set.of(SURVIVAL_TAG));
        synthetic.activate();
        plugin.getLogger().fine("Spawned player survival NPC at " + location);
    }

    private TextDisplay spawnNameplate(Location location, String title, NamedTextColor titleColor, Set<String> tags) {
        Location nameplateLocation = location.clone().add(0.0, 2.55, 0.0);
        TextDisplay nameplate = worlds.hubWorld().spawn(nameplateLocation, TextDisplay.class, display -> {
            display.text(Component.text()
                    .append(Component.text(title, titleColor))
                    .append(Component.newline())
                    .append(Component.text("CLICK TO OPEN", NamedTextColor.YELLOW))
                    .build());
            display.setBillboard(Display.Billboard.CENTER);
            display.setAlignment(TextDisplay.TextAlignment.CENTER);
            display.setBackgroundColor(Color.fromARGB(0, 0, 0, 0));
            display.setTextOpacity((byte) 255);
            display.setShadowed(true);
            display.setSeeThrough(false);
            display.setDefaultBackground(false);
            display.setDisplayWidth(2.2f);
            display.setDisplayHeight(0.6f);
            display.setViewRange(32.0f);
            display.setGravity(false);
            display.setInvulnerable(true);
            display.setSilent(true);
            display.setPersistent(true);
            display.addScoreboardTag(NPC_PART_TAG);
            tags.forEach(display::addScoreboardTag);
        });
        nameplate.setRotation(location.getYaw(), 0.0f);
        return nameplate;
    }

    private Team npcTeam() {
        Scoreboard scoreboard = Bukkit.getScoreboardManager().getMainScoreboard();
        Team team = scoreboard.getTeam(NPC_TEAM_NAME);
        if (team == null) {
            team = scoreboard.registerNewTeam(NPC_TEAM_NAME);
        }
        team.setOption(Team.Option.NAME_TAG_VISIBILITY, Team.OptionStatus.NEVER);
        team.setOption(Team.Option.COLLISION_RULE, Team.OptionStatus.NEVER);
        return team;
    }

    private void removeCategoryNpcs() {
        Team team = npcTeam();
        for (SyntheticPlayerNpc npc : categoryNpcs.values()) {
            team.removeEntry(npc.player().getName());
            npc.remove();
        }
        for (TextDisplay nameplate : categoryNameplates.values()) {
            nameplate.remove();
        }
        if (survivalNpc != null) {
            team.removeEntry(survivalNpc.player().getName());
            survivalNpc.remove();
        }
        if (survivalNameplate != null) {
            survivalNameplate.remove();
        }
        categoryNpcs.clear();
        categoryNameplates.clear();
        survivalNpc = null;
        survivalNameplate = null;
        recentInteractions.clear();
    }

    private void sendNpcsTo(Player player) {
        for (SyntheticPlayerNpc npc : categoryNpcs.values()) {
            npc.sendTo(player);
        }
        if (survivalNpc != null) {
            survivalNpc.sendTo(player);
        }
    }

    private static Entity npcEntity(Entity entity) {
        if (entity.getScoreboardTags().contains(NPC_TAG)) {
            return entity;
        }
        if (entity.getScoreboardTags().contains(NPC_PART_TAG)) {
            for (Entity nearby : entity.getNearbyEntities(1.0, 3.0, 1.0)) {
                if (nearby.getScoreboardTags().contains(NPC_TAG)) {
                    return nearby;
                }
            }
        }
        return null;
    }

    private static String categoryTag(Category category) {
        return "hill175_category_" + category.name().toLowerCase(Locale.ROOT);
    }

    private CategoryStyle configuredStyle(Category category) {
        CategoryStyle defaults = CategoryStyle.defaultsFor(category);
        String path = "worlds.hub-npcs." + category.name().toLowerCase(Locale.ROOT);
        String profileName = plugin.getConfig().getString(path + ".profile-name", defaults.profileName()).trim();
        String skinTexture = plugin.getConfig().getString(path + ".skin-texture", defaults.skinTexture())
                .trim().toLowerCase(Locale.ROOT);
        if (!PROFILE_NAME_PATTERN.matcher(profileName).matches()) {
            throw new IllegalStateException("Invalid category NPC profile name at " + path + ".profile-name");
        }
        if (!TEXTURE_HASH_PATTERN.matcher(skinTexture).matches()) {
            throw new IllegalStateException("Invalid category NPC texture hash at " + path + ".skin-texture");
        }
        return new CategoryStyle(
                defaults.title(),
                profileName,
                defaults.titleColor(),
                defaults.heldItem(),
                defaults.offhandItem(),
                skinTexture
        );
    }

    private SurvivalStyle configuredSurvivalStyle() {
        SurvivalStyle defaults = SurvivalStyle.defaults();
        String path = "worlds.hub-npcs.survival";
        String profileName = plugin.getConfig().getString(path + ".profile-name", defaults.profileName()).trim();
        String skinTexture = plugin.getConfig().getString(path + ".skin-texture", defaults.skinTexture())
                .trim().toLowerCase(Locale.ROOT);
        if (!PROFILE_NAME_PATTERN.matcher(profileName).matches()) {
            throw new IllegalStateException("Invalid survival NPC profile name at " + path + ".profile-name");
        }
        if (!TEXTURE_HASH_PATTERN.matcher(skinTexture).matches()) {
            throw new IllegalStateException("Invalid survival NPC texture hash at " + path + ".skin-texture");
        }
        return new SurvivalStyle(
                defaults.title(),
                profileName,
                defaults.titleColor(),
                defaults.heldItem(),
                defaults.offhandItem(),
                skinTexture
        );
    }

    private record CategoryStyle(
            String title,
            String profileName,
            NamedTextColor titleColor,
            Material heldItem,
            Material offhandItem,
            String skinTexture
    ) {
        private static CategoryStyle defaultsFor(Category category) {
            return switch (category) {
                case JOURNEY -> new CategoryStyle(
                        "THE JOURNEY",
                        "HillJourney",
                        NamedTextColor.GOLD,
                        Material.BRICKS,
                        Material.COMPASS,
                        // Surveyor/builder with a hard hat and overalls.
                        "af41e2561a2c959f56df5dcda564397df1971d652e1ac159d8b4c74733026077"
                );
                case PLACE -> new CategoryStyle(
                        "THE PLACE",
                        "HillPlace",
                        NamedTextColor.AQUA,
                        Material.BOOKSHELF,
                        Material.WRITABLE_BOOK,
                        // Warm, contemporary interior-designer attire.
                        "6ac6ca262d67bcfb3dbc924ba8215a18195497c780058a5749de674217721892"
                );
                case PEOPLE -> new CategoryStyle(
                        "THE PEOPLE",
                        "HillPeople",
                        NamedTextColor.GREEN,
                        Material.COMPASS,
                        Material.OAK_SAPLING,
                        // Future-facing scientist/planner with green Hill accents.
                        "9658c5ac64cdd7189e8db50393f27439fc9ce9177c9c5285d6f1f7b4eda9d7ec"
                );
            };
        }
    }

    private record RecentInteraction(UUID entityId, Instant when) {
    }

    private record SurvivalStyle(
            String title,
            String profileName,
            NamedTextColor titleColor,
            Material heldItem,
            Material offhandItem,
            String skinTexture
    ) {
        private static SurvivalStyle defaults() {
            return new SurvivalStyle(
                    "Survival Guide",
                    "HillSurvival",
                    NamedTextColor.GREEN,
                    Material.GRASS_BLOCK,
                    Material.COMPASS,
                    // Smoke skin: surveyor/builder. Replace with a Hill-owned survival guide texture before public launch.
                    "af41e2561a2c959f56df5dcda564397df1971d652e1ac159d8b4c74733026077"
            );
        }
    }
}
