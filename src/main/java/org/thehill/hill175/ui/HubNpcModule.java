package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Color;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerInteractAtEntityEvent;
import org.bukkit.event.player.PlayerInteractEntityEvent;
import org.bukkit.inventory.EntityEquipment;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.LeatherArmorMeta;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.world.WorldModule;

import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

public final class HubNpcModule implements Listener {
    private static final String NPC_TAG = "hill175_category_npc";
    private static final Duration INTERACTION_DEBOUNCE = Duration.ofMillis(350);

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final MenuModule menus;
    private final WorldModule worlds;
    private final Map<UUID, RecentInteraction> recentInteractions = new HashMap<>();

    public HubNpcModule(JavaPlugin plugin, CompetitionModule competition, MenuModule menus, WorldModule worlds) {
        this.plugin = plugin;
        this.competition = competition;
        this.menus = menus;
        this.worlds = worlds;
    }

    public void spawnCategoryNpcs() {
        // Persistent stands in an unloaded anchor chunk are not returned by
        // World#getEntities. Load every configured anchor first so restarts
        // remove old guides before adding replacements.
        for (Category category : Category.values()) {
            worlds.hubNpcLocation(category).getChunk().load();
        }
        for (Entity entity : worlds.hubWorld().getEntities()) {
            if (entity.getScoreboardTags().contains(NPC_TAG)) {
                entity.remove();
            }
        }
        spawn(worlds.hubNpcLocation(Category.JOURNEY), Category.JOURNEY, Color.fromRGB(120, 56, 40));
        spawn(worlds.hubNpcLocation(Category.PLACE), Category.PLACE, Color.fromRGB(58, 93, 166));
        spawn(worlds.hubNpcLocation(Category.PEOPLE), Category.PEOPLE, Color.fromRGB(64, 132, 78));
        long npcCount = worlds.hubWorld().getEntitiesByClass(ArmorStand.class).stream()
                .filter(entity -> entity.getScoreboardTags().contains(NPC_TAG))
                .count();
        plugin.getLogger().info("Hill 175 category guides ready: " + npcCount + "/3.");
    }

    @EventHandler
    public void onInteractAt(PlayerInteractAtEntityEvent event) {
        if (!event.getRightClicked().getScoreboardTags().contains(NPC_TAG)) {
            return;
        }
        event.setCancelled(true);
        handle(event.getPlayer(), event.getRightClicked());
    }

    @EventHandler
    public void onInteract(PlayerInteractEntityEvent event) {
        if (!event.getRightClicked().getScoreboardTags().contains(NPC_TAG)) {
            return;
        }
        event.setCancelled(true);
        handle(event.getPlayer(), event.getRightClicked());
    }

    @EventHandler
    public void onDamage(EntityDamageByEntityEvent event) {
        if (event.getDamager() instanceof Player player && event.getEntity() instanceof ArmorStand) {
            if (event.getEntity().getScoreboardTags().contains(NPC_TAG)) {
                event.setCancelled(true);
                handle(player, event.getEntity());
            }
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
        for (Category category : Category.values()) {
            if (entity.getScoreboardTags().contains(categoryTag(category))) {
                if (!competition.isAuthenticated(player)) {
                    competition.sendAuthenticationInstructions(player);
                    return;
                }
                menus.openCategory(player, category);
                return;
            }
        }
    }

    private void spawn(Location location, Category category, Color color) {
        location.getChunk().load();
        ArmorStand npc = worlds.hubWorld().spawn(location, ArmorStand.class, stand -> {
            stand.customName(Component.text(category.displayName(), NamedTextColor.GOLD));
            stand.setCustomNameVisible(true);
            stand.setGravity(false);
            // Damage events do not fire for an invulnerable armor stand. The NPC
            // remains protected because every tagged damage event is cancelled.
            stand.setInvulnerable(false);
            stand.setPersistent(true);
            stand.setRemoveWhenFarAway(false);
            stand.setArms(true);
            stand.setBasePlate(false);
            stand.setCanPickupItems(false);
            stand.addScoreboardTag(NPC_TAG);
            stand.addScoreboardTag(categoryTag(category));
            EntityEquipment equipment = stand.getEquipment();
            equipment.setHelmet(new ItemStack(category.icon()));
            equipment.setChestplate(coloredChestplate(color));
        });
        npc.setRotation(location.getYaw(), location.getPitch());
        plugin.getLogger().fine("Spawned category NPC " + category.name() + " at " + location);
    }

    private static ItemStack coloredChestplate(Color color) {
        ItemStack chestplate = new ItemStack(Material.LEATHER_CHESTPLATE);
        LeatherArmorMeta meta = (LeatherArmorMeta) chestplate.getItemMeta();
        meta.setColor(color);
        chestplate.setItemMeta(meta);
        return chestplate;
    }

    private static String categoryTag(Category category) {
        return "hill175_category_" + category.name().toLowerCase(Locale.ROOT);
    }

    private record RecentInteraction(UUID entityId, Instant when) {
    }
}
