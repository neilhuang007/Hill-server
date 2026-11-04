package org.thehill.hill175.listener;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockFace;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.Directional;
import org.bukkit.event.block.BlockDispenseEvent;
import org.bukkit.event.block.BlockFadeEvent;
import org.bukkit.event.block.BlockFormEvent;
import org.bukkit.event.block.BlockFromToEvent;
import org.bukkit.event.block.BlockGrowEvent;
import org.bukkit.event.block.BlockPistonExtendEvent;
import org.bukkit.event.block.BlockPistonRetractEvent;
import org.bukkit.event.world.StructureGrowEvent;
import org.bukkit.inventory.ItemStack;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.*;

class SharedCampusEnvironmentTest {
    private final CompetitionModule competition = mock(CompetitionModule.class);
    private final WorldModule worlds = mock(WorldModule.class);
    private final ServerListener listener = new ServerListener(mock(JavaPlugin.class), competition, mock(MenuModule.class), worlds);
    private final World world = mock(World.class);
    private final Entry shared = new Entry(UUID.randomUUID(), Category.PEOPLE, Set.of(), "hill_campus",
            new BuildRegion("hill_campus", 0, 0, 0, 63, 127, 63), 0);

    @BeforeEach void sharedAdapter() {
        when(world.getName()).thenReturn("hill_campus");
        when(worlds.isSharedCampus(world)).thenReturn(true);
        when(worlds.sharedCampusEntry()).thenReturn(Optional.of(shared));
        when(competition.entryAt(any(Location.class))).thenAnswer(invocation -> {
            Location location = invocation.getArgument(0);
            return shared.containsEditable(location) ? Optional.of(shared) : Optional.empty();
        });
        assertTrue(shared.members().isEmpty());
    }

    @Test void ownerlessCampusAllowsWaterFlowInsideItsBoundary() {
        BlockFromToEvent inside = flow(block(20, 65, 20), block(21, 65, 20));
        BlockFromToEvent outside = flow(block(63, 65, 20), block(64, 65, 20));
        listener.onFluidFlow(inside);
        listener.onFluidFlow(outside);
        verify(inside, never()).setCancelled(anyBoolean());
        verify(outside).setCancelled(true);
    }

    @Test void ownerlessCampusAllowsGrowthFormationAndFadeWithoutPublishingAnEntry() {
        Block source = block(20, 65, 20);
        BlockGrowEvent grow = mock(BlockGrowEvent.class);
        BlockFormEvent form = mock(BlockFormEvent.class);
        BlockFadeEvent fade = mock(BlockFadeEvent.class);
        when(grow.getBlock()).thenReturn(source);
        when(form.getBlock()).thenReturn(source);
        when(fade.getBlock()).thenReturn(source);
        listener.onGrow(grow);
        listener.onForm(form);
        listener.onFade(fade);
        verify(grow, never()).setCancelled(anyBoolean());
        verify(form, never()).setCancelled(anyBoolean());
        verify(fade, never()).setCancelled(anyBoolean());
    }

    @Test void sharedDispenserAllowsWaterButStillBlocksExplosivesAndBoundaryCrossing() {
        BlockDispenseEvent water = dispense(20, Material.WATER_BUCKET);
        BlockDispenseEvent tnt = dispense(20, Material.TNT);
        BlockDispenseEvent outside = dispense(63, Material.WATER_BUCKET);
        listener.onDispense(water);
        listener.onDispense(tnt);
        listener.onDispense(outside);
        verify(water, never()).setCancelled(anyBoolean());
        verify(tnt).setCancelled(true);
        verify(outside).setCancelled(true);
    }

    @Test void sharedPistonsMayMoveBlocksWithinTheCampus() {
        Block piston = block(20, 65, 20);
        Block moved = block(21, 65, 20);
        Block east = block(22, 65, 20);
        Block west = block(20, 65, 20);
        when(moved.getRelative(BlockFace.EAST)).thenReturn(east);
        when(moved.getRelative(BlockFace.WEST)).thenReturn(west);
        BlockPistonExtendEvent extend = new BlockPistonExtendEvent(piston, List.of(moved), BlockFace.EAST);
        BlockPistonRetractEvent retract = new BlockPistonRetractEvent(piston, List.of(moved), BlockFace.WEST);
        listener.onPistonExtend(extend);
        listener.onPistonRetract(retract);
        org.junit.jupiter.api.Assertions.assertFalse(extend.isCancelled());
        org.junit.jupiter.api.Assertions.assertFalse(retract.isCancelled());
    }

    @Test void sharedPistonCannotPushPastTheCampusBoundary() {
        Block piston = block(62, 65, 20);
        Block moved = block(63, 65, 20);
        Block target = block(64, 65, 20);
        when(moved.getRelative(BlockFace.EAST)).thenReturn(target);
        BlockPistonExtendEvent extend = new BlockPistonExtendEvent(piston, List.of(moved), BlockFace.EAST);
        listener.onPistonExtend(extend);
        assertTrue(extend.isCancelled());
    }

    @Test void sharedTreeGrowthMustRemainWithinTheCampus() {
        StructureGrowEvent inside = treeAt(20, stateAt(22));
        StructureGrowEvent outside = treeAt(63, stateAt(64));
        listener.onStructureGrow(inside);
        listener.onStructureGrow(outside);
        verify(inside, never()).setCancelled(anyBoolean());
        verify(outside).setCancelled(true);
    }

    @Test void noAdapterOutsideCampusKeepsEnvironmentalChangesProtected() {
        BlockGrowEvent grow = mock(BlockGrowEvent.class);
        Block source = block(64, 65, 20);
        when(grow.getBlock()).thenReturn(source);
        listener.onGrow(grow);
        verify(grow).setCancelled(true);
    }

    private BlockFromToEvent flow(Block source, Block target) {
        BlockFromToEvent event = mock(BlockFromToEvent.class);
        when(event.getBlock()).thenReturn(source);
        when(event.getToBlock()).thenReturn(target);
        return event;
    }

    private BlockDispenseEvent dispense(int x, Material material) {
        Block source = block(x, 65, 20);
        Block target = block(x + 1, 65, 20);
        Directional direction = mock(Directional.class);
        when(direction.getFacing()).thenReturn(BlockFace.EAST);
        when(source.getBlockData()).thenReturn(direction);
        when(source.getRelative(BlockFace.EAST)).thenReturn(target);
        ItemStack item = mock(ItemStack.class);
        when(item.getType()).thenReturn(material);
        BlockDispenseEvent event = mock(BlockDispenseEvent.class);
        when(event.getBlock()).thenReturn(source);
        when(event.getItem()).thenReturn(item);
        return event;
    }

    private StructureGrowEvent treeAt(int x, BlockState state) {
        StructureGrowEvent event = mock(StructureGrowEvent.class);
        when(event.getWorld()).thenReturn(world);
        when(event.getLocation()).thenReturn(new Location(world, x, 65, 20));
        when(event.getBlocks()).thenReturn(List.of(state));
        return event;
    }

    private BlockState stateAt(int x) {
        BlockState state = mock(BlockState.class);
        when(state.getLocation()).thenReturn(new Location(world, x, 66, 20));
        return state;
    }

    private Block block(int x, int y, int z) {
        Block block = mock(Block.class);
        when(block.getWorld()).thenReturn(world);
        when(block.getLocation()).thenReturn(new Location(world, x, y, z));
        return block;
    }
}
