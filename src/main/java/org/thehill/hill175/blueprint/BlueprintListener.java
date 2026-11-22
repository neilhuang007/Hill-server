package org.thehill.hill175.blueprint;

import com.destroystokyo.paper.event.block.BlockDestroyEvent;
import io.papermc.paper.event.player.PlayerFlowerPotManipulateEvent;
import io.papermc.paper.event.player.PlayerInsertLecternBookEvent;
import io.papermc.paper.event.player.PlayerLecternPageChangeEvent;
import org.bukkit.Location;
import org.bukkit.block.Block;
import org.bukkit.block.BlockState;
import org.bukkit.block.DoubleChest;
import org.bukkit.block.TileState;
import org.bukkit.event.Cancellable;
import org.bukkit.event.Event;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.*;
import org.bukkit.event.entity.EntityChangeBlockEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.EntityExplodeEvent;
import org.bukkit.event.inventory.*;
import org.bukkit.event.player.*;
import org.bukkit.event.world.StructureGrowEvent;
import org.bukkit.event.world.WorldLoadEvent;
import org.bukkit.inventory.BlockInventoryHolder;
import org.bukkit.inventory.Inventory;

import java.util.List;

public final class BlueprintListener implements Listener {
    private final BlueprintService service;

    BlueprintListener(BlueprintService service) { this.service = service; }

    private void changing(Cancellable event, Block block) {
        if (event.isCancelled()) return;
        if (!service.changed(block.getWorld(), block.getX(), block.getZ())) event.setCancelled(true);
    }

    private void inventory(Cancellable event, Inventory inventory) {
        Location location = inventory.getLocation();
        if (location != null) changing(event, location.getBlock());
        if (inventory.getHolder(false) instanceof DoubleChest chest) {
            if (chest.getLeftSide() instanceof BlockInventoryHolder left) changing(event, left.getBlock());
            if (chest.getRightSide() instanceof BlockInventoryHolder right) changing(event, right.getBlock());
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void place(BlockPlaceEvent event) {
        if (event instanceof BlockMultiPlaceEvent) return;
        boolean fresh = service.uncaptured(event.getBlock());
        changing(event, event.getBlock());
        if (fresh && !event.isCancelled()) service.replaced(event.getBlockReplacedState());
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void breakBlock(BlockBreakEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void multiple(BlockMultiPlaceEvent event) {
        List<BlockState> fresh = event.getReplacedBlockStates().stream().filter(state -> service.uncaptured(state.getBlock())).toList();
        event.getReplacedBlockStates().forEach(state -> changing(event, state.getBlock()));
        if (!event.isCancelled()) fresh.forEach(service::replaced);
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void leftWorld(PlayerChangedWorldEvent event) {
        if (service.isBlueprint(event.getFrom())) service.editorLeft(event.getPlayer());
    }
    @EventHandler(priority = EventPriority.MONITOR)
    public void quit(PlayerQuitEvent event) { service.editorLeft(event.getPlayer()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void fluid(BlockFromToEvent event) { changing(event, event.getBlock()); changing(event, event.getToBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void form(BlockFormEvent event) { changing(event, event.getBlock()); }
    private void natural(Cancellable event, Block block) {
        if (service.stopsNaturalChanges(block.getWorld())) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void loaded(WorldLoadEvent event) { service.worldLoaded(event.getWorld()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void spread(BlockSpreadEvent event) { natural(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void grow(BlockGrowEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void fade(BlockFadeEvent event) { natural(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void decay(LeavesDecayEvent event) { natural(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void burn(BlockBurnEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void ignite(BlockIgniteEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void sign(SignChangeEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void entity(EntityChangeBlockEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void damage(EntityDamageEvent event) {
        if (service.protects(event.getEntity().getWorld())) event.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void destroy(BlockDestroyEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void gameSignal(BlockReceiveGameEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void dispense(BlockDispenseEvent event) {
        changing(event, event.getBlock());
        if (event.getBlock().getBlockData() instanceof org.bukkit.block.data.Directional facing) {
            changing(event, event.getBlock().getRelative(facing.getFacing()));
        }
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void bucketEmpty(PlayerBucketEmptyEvent event) {
        changing(event, event.getBlock());
        changing(event, event.getBlockClicked().getRelative(event.getBlockFace()));
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void bucketFill(PlayerBucketFillEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void structure(StructureGrowEvent event) { event.getBlocks().forEach(state -> changing(event, state.getBlock())); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void fertilize(BlockFertilizeEvent event) { event.getBlocks().forEach(state -> changing(event, state.getBlock())); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void explosion(EntityExplodeEvent event) { event.blockList().forEach(block -> changing(event, block)); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void blockExplosion(BlockExplodeEvent event) { event.blockList().forEach(block -> changing(event, block)); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void sponge(SpongeAbsorbEvent event) { event.getBlocks().forEach(state -> changing(event, state.getBlock())); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void cauldron(CauldronLevelChangeEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void harvest(PlayerHarvestBlockEvent event) { changing(event, event.getHarvestedBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void flowerpot(PlayerFlowerPotManipulateEvent event) { changing(event, event.getFlowerpot()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void insertBook(PlayerInsertLecternBookEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void takeBook(PlayerTakeLecternBookEvent event) { changing(event, event.getLectern().getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void lecternPage(PlayerLecternPageChangeEvent event) { changing(event, event.getLectern().getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void cook(BlockCookEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void furnaceBurn(FurnaceBurnEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void brew(BrewEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void brewingFuel(BrewingStandFuelEvent event) { changing(event, event.getBlock()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void note(NotePlayEvent event) { changing(event, event.getBlock()); }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void physics(BlockPhysicsEvent event) {
        if (service.protects(event.getBlock().getWorld())) event.setCancelled(true);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void pistonExtend(BlockPistonExtendEvent event) {
        changing(event, event.getBlock());
        event.getBlocks().forEach(block -> { changing(event, block); changing(event, block.getRelative(event.getDirection())); });
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void pistonRetract(BlockPistonRetractEvent event) {
        changing(event, event.getBlock());
        event.getBlocks().forEach(block -> {
            changing(event, block);
            changing(event, block.getRelative(event.getDirection()));
            changing(event, block.getRelative(event.getDirection().getOppositeFace()));
        });
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void redstone(BlockRedstoneEvent event) {
        if (service.protects(event.getBlock().getWorld())) { event.setNewCurrent(event.getOldCurrent()); return; }
        if (event.getNewCurrent() != event.getOldCurrent()
                && !service.changed(event.getBlock().getWorld(), event.getBlock().getX(), event.getBlock().getZ())) {
            event.setNewCurrent(event.getOldCurrent());
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void interact(PlayerInteractEvent event) {
        Block clicked = event.getClickedBlock();
        if (clicked == null) return;
        if (!service.mayChange(event.getPlayer(), clicked.getWorld())) { event.setCancelled(true); return; }
        if (event.useInteractedBlock() == Event.Result.DENY) return;
        if (event.getAction() == Action.PHYSICAL || event.getAction() == Action.RIGHT_CLICK_BLOCK
                && (clicked.getType().isInteractable() || clicked.getState(false) instanceof TileState || event.hasItem())) changing(event, clicked);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void inventoryOpen(InventoryOpenEvent event) {
        Location location = event.getInventory().getLocation();
        if (location != null && event.getPlayer() instanceof org.bukkit.entity.Player player
                && !service.mayChange(player, location.getWorld())) event.setCancelled(true);
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void inventoryClick(InventoryClickEvent event) {
        if (event.getAction() != InventoryAction.NOTHING) inventory(event, event.getInventory());
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void inventoryDrag(InventoryDragEvent event) { inventory(event, event.getInventory()); }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void inventoryMove(InventoryMoveItemEvent event) {
        inventory(event, event.getSource());
        inventory(event, event.getDestination());
    }
    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void inventoryPickup(InventoryPickupItemEvent event) { inventory(event, event.getInventory()); }
}
