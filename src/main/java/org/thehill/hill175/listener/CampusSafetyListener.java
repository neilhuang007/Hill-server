package org.thehill.hill175.listener;

import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.data.type.RespawnAnchor;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.block.BlockDispenseEvent;
import org.bukkit.event.block.BlockFormEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.ExplosionPrimeEvent;
import org.bukkit.event.hanging.HangingBreakEvent;
import org.bukkit.event.player.PlayerBucketEmptyEvent;
import org.bukkit.event.player.PlayerInteractEvent;

import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

/** Additional campus protections that complement ServerListener's ownership checks. */
public final class CampusSafetyListener implements Listener {
    private static final Set<Material> castProducts = Set.of(Material.STONE, Material.COBBLESTONE, Material.OBSIDIAN);
    private static final Set<Material> mobBuckets = Set.of(Material.COD_BUCKET, Material.SALMON_BUCKET,
            Material.TROPICAL_FISH_BUCKET, Material.PUFFERFISH_BUCKET, Material.AXOLOTL_BUCKET, Material.TADPOLE_BUCKET);
    private final Predicate<World> protectedWorld;

    public CampusSafetyListener(Predicate<World> protectedWorld) {
        this.protectedWorld = Objects.requireNonNull(protectedWorld, "protectedWorld");
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onLavaCast(BlockFormEvent event) {
        Block block = event.getBlock();
        if (isProtected(block.getWorld()) && (block.getType() == Material.LAVA || block.getType() == Material.WATER)
                && castProducts.contains(event.getNewState().getType())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onMobBucket(PlayerBucketEmptyEvent event) {
        if (isProtected(event.getBlock().getWorld()) && mobBuckets.contains(event.getBucket())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onMobDispense(BlockDispenseEvent event) {
        if (isProtected(event.getBlock().getWorld()) && isMobItem(event.getItem().getType())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onDangerousInteraction(PlayerInteractEvent event) {
        if (!isProtected(event.getPlayer().getWorld()) || !event.getAction().isRightClick()) return;
        if (event.getItem() != null && isMobItem(event.getItem().getType())) {
            event.setCancelled(true);
            return;
        }
        if (event.getAction() == Action.RIGHT_CLICK_BLOCK && wouldExplode(event)) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onExplosionPrime(ExplosionPrimeEvent event) {
        if (isProtected(event.getEntity().getWorld())) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onExplosionDamage(EntityDamageEvent event) {
        if (!isProtected(event.getEntity().getWorld())) return;
        if (event.getCause() == EntityDamageEvent.DamageCause.ENTITY_EXPLOSION
                || event.getCause() == EntityDamageEvent.DamageCause.BLOCK_EXPLOSION) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onHangingExplosion(HangingBreakEvent event) {
        if (isProtected(event.getEntity().getWorld()) && event.getCause() == HangingBreakEvent.RemoveCause.EXPLOSION) {
            event.setCancelled(true);
        }
    }

    private boolean isProtected(World world) {
        return world != null && protectedWorld.test(world);
    }

    private static boolean isMobItem(Material material) {
        return material.name().endsWith("_SPAWN_EGG") || mobBuckets.contains(material);
    }

    private static boolean wouldExplode(PlayerInteractEvent event) {
        Block block = event.getClickedBlock();
        if (block == null) return false;
        World.Environment environment = block.getWorld().getEnvironment();
        if (block.getType().name().endsWith("_BED")) return environment != World.Environment.NORMAL;
        if (block.getType() != Material.RESPAWN_ANCHOR || environment == World.Environment.NETHER) return false;
        if (!(block.getBlockData() instanceof RespawnAnchor anchor) || anchor.getCharges() == 0) return false;
        return event.getItem() == null || event.getItem().getType() != Material.GLOWSTONE
                || anchor.getCharges() >= anchor.getMaximumCharges();
    }
}
