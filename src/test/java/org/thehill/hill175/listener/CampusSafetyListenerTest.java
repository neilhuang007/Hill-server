package org.thehill.hill175.listener;

import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.type.RespawnAnchor;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Hanging;
import org.bukkit.entity.Player;
import org.bukkit.event.block.Action;
import org.bukkit.event.block.BlockDispenseEvent;
import org.bukkit.event.block.BlockFormEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.ExplosionPrimeEvent;
import org.bukkit.event.hanging.HangingBreakEvent;
import org.bukkit.event.player.PlayerBucketEmptyEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.ItemStack;
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.*;

class CampusSafetyListenerTest {
    private final World campus = mock(World.class);
    private final World survival = mock(World.class);
    private final CampusSafetyListener listener = new CampusSafetyListener(world -> world == campus);

    @Test void lavaCannotBecomeStoneCobblestoneOrObsidian() {
        for (Material product : new Material[]{Material.STONE, Material.COBBLESTONE, Material.OBSIDIAN}) {
            BlockFormEvent event = form(campus, Material.LAVA, product);
            listener.onLavaCast(event);
            verify(event).setCancelled(true);
        }
        BlockFormEvent flowingLavaIntoWater = form(campus, Material.WATER, Material.STONE);
        listener.onLavaCast(flowingLavaIntoWater);
        verify(flowingLavaIntoWater).setCancelled(true);
    }

    @Test void lavaCastingAndOtherFormsRemainUnchangedInSurvival() {
        BlockFormEvent survivalCast = form(survival, Material.LAVA, Material.COBBLESTONE);
        BlockFormEvent snow = form(campus, Material.AIR, Material.SNOW);
        BlockFormEvent stone = form(campus, Material.STONE, Material.COBBLESTONE);
        listener.onLavaCast(survivalCast);
        listener.onLavaCast(snow);
        listener.onLavaCast(stone);
        verify(survivalCast, never()).setCancelled(anyBoolean());
        verify(snow, never()).setCancelled(anyBoolean());
        verify(stone, never()).setCancelled(anyBoolean());
    }

    @Test void mobBucketsAreBlockedBeforeTheyEmptyButWaterRemainsUsable() {
        PlayerBucketEmptyEvent fish = bucket(campus, Material.COD_BUCKET);
        PlayerBucketEmptyEvent water = bucket(campus, Material.WATER_BUCKET);
        PlayerBucketEmptyEvent survivalFish = bucket(survival, Material.COD_BUCKET);
        listener.onMobBucket(fish);
        listener.onMobBucket(water);
        listener.onMobBucket(survivalFish);
        verify(fish).setCancelled(true);
        verify(water, never()).setCancelled(anyBoolean());
        verify(survivalFish, never()).setCancelled(anyBoolean());
    }

    @Test void mobDispensersAreBlockedWithoutDisablingNormalDispensers() {
        BlockDispenseEvent egg = dispense(campus, Material.CREEPER_SPAWN_EGG);
        BlockDispenseEvent fish = dispense(campus, Material.AXOLOTL_BUCKET);
        BlockDispenseEvent water = dispense(campus, Material.WATER_BUCKET);
        BlockDispenseEvent survivalEgg = dispense(survival, Material.CREEPER_SPAWN_EGG);
        listener.onMobDispense(egg);
        listener.onMobDispense(fish);
        listener.onMobDispense(water);
        listener.onMobDispense(survivalEgg);
        verify(egg).setCancelled(true);
        verify(fish).setCancelled(true);
        verify(water, never()).setCancelled(anyBoolean());
        verify(survivalEgg, never()).setCancelled(anyBoolean());
    }

    @Test void spawnEggInteractionIsBlockedBeforeConsumption() {
        PlayerInteractEvent egg = interact(campus, Material.COW_SPAWN_EGG, null);
        PlayerInteractEvent survivalEgg = interact(survival, Material.COW_SPAWN_EGG, null);
        listener.onDangerousInteraction(egg);
        listener.onDangerousInteraction(survivalEgg);
        verify(egg).setCancelled(true);
        verify(survivalEgg, never()).setCancelled(anyBoolean());
    }

    @Test void dangerousBedsAndAnchorsAreBlockedButDecorationCanBeCharged() {
        when(campus.getEnvironment()).thenReturn(World.Environment.THE_END);
        PlayerInteractEvent bed = interact(campus, null, block(campus, Material.RED_BED));
        Block anchorBlock = block(campus, Material.RESPAWN_ANCHOR);
        RespawnAnchor anchor = mock(RespawnAnchor.class);
        when(anchor.getCharges()).thenReturn(1);
        when(anchor.getMaximumCharges()).thenReturn(4);
        when(anchorBlock.getBlockData()).thenReturn(anchor);
        PlayerInteractEvent explodeAnchor = interact(campus, null, anchorBlock);
        PlayerInteractEvent chargeAnchor = interact(campus, Material.GLOWSTONE, anchorBlock);
        listener.onDangerousInteraction(bed);
        listener.onDangerousInteraction(explodeAnchor);
        listener.onDangerousInteraction(chargeAnchor);
        verify(bed).setCancelled(true);
        verify(explodeAnchor).setCancelled(true);
        verify(chargeAnchor, never()).setCancelled(anyBoolean());
    }

    @Test void explosionsCannotStartOrDamageDecorationsButSurvivalIsUnaffected() {
        ExplosionPrimeEvent prime = mock(ExplosionPrimeEvent.class);
        ExplosionPrimeEvent survivalPrime = mock(ExplosionPrimeEvent.class);
        Entity campusEntity = entity(campus);
        Entity survivalEntity = entity(survival);
        when(prime.getEntity()).thenReturn(campusEntity);
        when(survivalPrime.getEntity()).thenReturn(survivalEntity);
        listener.onExplosionPrime(prime);
        listener.onExplosionPrime(survivalPrime);
        verify(prime).setCancelled(true);
        verify(survivalPrime, never()).setCancelled(anyBoolean());
        for (EntityDamageEvent.DamageCause cause : new EntityDamageEvent.DamageCause[]{
                EntityDamageEvent.DamageCause.BLOCK_EXPLOSION, EntityDamageEvent.DamageCause.ENTITY_EXPLOSION}) {
            EntityDamageEvent damage = damage(campus, cause);
            listener.onExplosionDamage(damage);
            verify(damage).setCancelled(true);
        }
        EntityDamageEvent survivalDamage = damage(survival, EntityDamageEvent.DamageCause.BLOCK_EXPLOSION);
        EntityDamageEvent ordinaryDamage = damage(campus, EntityDamageEvent.DamageCause.ENTITY_ATTACK);
        listener.onExplosionDamage(survivalDamage);
        listener.onExplosionDamage(ordinaryDamage);
        verify(survivalDamage, never()).setCancelled(anyBoolean());
        verify(ordinaryDamage, never()).setCancelled(anyBoolean());
    }

    @Test void explosionsDoNotRemoveHangingDecorations() {
        Hanging hanging = mock(Hanging.class);
        when(hanging.getWorld()).thenReturn(campus);
        HangingBreakEvent event = mock(HangingBreakEvent.class);
        when(event.getEntity()).thenReturn(hanging);
        when(event.getCause()).thenReturn(HangingBreakEvent.RemoveCause.EXPLOSION);
        listener.onHangingExplosion(event);
        verify(event).setCancelled(true);
    }

    private BlockFormEvent form(World world, Material before, Material after) {
        BlockFormEvent event = mock(BlockFormEvent.class);
        BlockState state = mock(BlockState.class);
        Block block = block(world, before);
        when(state.getType()).thenReturn(after);
        when(event.getNewState()).thenReturn(state);
        when(event.getBlock()).thenReturn(block);
        return event;
    }

    private PlayerBucketEmptyEvent bucket(World world, Material material) {
        PlayerBucketEmptyEvent event = mock(PlayerBucketEmptyEvent.class);
        Block block = block(world, Material.AIR);
        when(event.getBlock()).thenReturn(block);
        when(event.getBucket()).thenReturn(material);
        return event;
    }

    private BlockDispenseEvent dispense(World world, Material material) {
        BlockDispenseEvent event = mock(BlockDispenseEvent.class);
        Block block = block(world, Material.DISPENSER);
        ItemStack item = item(material);
        when(event.getBlock()).thenReturn(block);
        when(event.getItem()).thenReturn(item);
        return event;
    }

    private PlayerInteractEvent interact(World world, Material item, Block clicked) {
        PlayerInteractEvent event = mock(PlayerInteractEvent.class);
        Player player = mock(Player.class);
        when(player.getWorld()).thenReturn(world);
        when(event.getPlayer()).thenReturn(player);
        when(event.getAction()).thenReturn(clicked == null ? Action.RIGHT_CLICK_AIR : Action.RIGHT_CLICK_BLOCK);
        when(event.getClickedBlock()).thenReturn(clicked);
        if (item != null) {
            ItemStack stack = item(item);
            when(event.getItem()).thenReturn(stack);
        }
        return event;
    }

    private EntityDamageEvent damage(World world, EntityDamageEvent.DamageCause cause) {
        EntityDamageEvent event = mock(EntityDamageEvent.class);
        Entity entity = entity(world);
        when(event.getEntity()).thenReturn(entity);
        when(event.getCause()).thenReturn(cause);
        return event;
    }

    private Entity entity(World world) {
        Entity entity = mock(Entity.class);
        when(entity.getWorld()).thenReturn(world);
        return entity;
    }

    private Block block(World world, Material material) {
        Block block = mock(Block.class);
        when(block.getWorld()).thenReturn(world);
        when(block.getType()).thenReturn(material);
        return block;
    }

    private ItemStack item(Material material) {
        ItemStack item = mock(ItemStack.class);
        when(item.getType()).thenReturn(material);
        return item;
    }
}
