package org.thehill.hill175.undo;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Bed;
import org.bukkit.block.Block;
import org.bukkit.block.BlockState;
import org.bukkit.block.TileState;
import org.bukkit.block.data.BlockData;
import org.bukkit.block.data.Waterlogged;
import org.bukkit.persistence.PersistentDataContainer;
import org.junit.jupiter.api.Test;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class BlockSnapshotTest {
    @Test void refusesContainersAndOtherTileStates() {
        for (Material material : new Material[]{Material.CHEST, Material.BARREL, Material.OAK_SIGN, Material.JUKEBOX}) {
            BlockState state = state(mock(TileState.class), material, "minecraft:" + material.name().toLowerCase());
            assertNull(BlockSnapshot.capture(state));
        }
    }

    @Test void refusesFluidsFallingBlocksAndWaterloggedBlocks() {
        for (Material material : new Material[]{Material.WATER, Material.LAVA, Material.SAND, Material.GRAVEL}) {
            assertNull(BlockSnapshot.capture(state(mock(BlockState.class), material, material.name())));
        }
        BlockState wet = state(mock(BlockState.class), Material.OAK_STAIRS, "stairs");
        Waterlogged data = mock(Waterlogged.class);
        when(data.isWaterlogged()).thenReturn(true);
        when(wet.getBlockData()).thenReturn(data);
        assertNull(BlockSnapshot.capture(wet));
    }

    @Test void comparesFullBlockDataNotJustMaterial() {
        BlockSnapshot north = BlockSnapshot.capture(state(mock(BlockState.class), Material.OAK_STAIRS, "stairs[facing=north]"));
        BlockSnapshot south = BlockSnapshot.capture(state(mock(BlockState.class), Material.OAK_STAIRS, "stairs[facing=south]"));
        assertNotEquals(north, south);
    }

    @Test void restoresBedDataOnlyOntoAPlacedBedState() throws IOException {
        Bed original = state(mock(Bed.class), Material.RED_BED, "minecraft:red_bed[facing=north,part=foot,occupied=false]");
        PersistentDataContainer source = mock(PersistentDataContainer.class);
        when(source.serializeToBytes()).thenReturn(new byte[]{1, 2, 3});
        when(original.getPersistentDataContainer()).thenReturn(source);
        BlockSnapshot snapshot = BlockSnapshot.capture(original);
        World world = mock(World.class);
        Block block = mock(Block.class);
        Bed placed = mock(Bed.class);
        PersistentDataContainer destination = mock(PersistentDataContainer.class);
        when(world.getBlockAt(any(Location.class))).thenReturn(block);
        when(block.getState()).thenReturn(placed);
        when(placed.getPersistentDataContainer()).thenReturn(destination);
        when(placed.update(true, false)).thenReturn(true);
        assertTrue(snapshot.restore(new Location(world, 1, 80, 2)));
        verify(block).setBlockData(any(BlockData.class), eq(false));
        verify(destination).readFromBytes(new byte[]{1, 2, 3}, true);
        verify(placed).update(true, false);
        verify(original, never()).copy(any(Location.class));
    }

    @Test void changedBedMetadataIsAConflict() throws IOException {
        Bed first = bedWithData(new byte[]{1});
        Bed second = bedWithData(new byte[]{2});
        assertNotEquals(BlockSnapshot.capture(first), BlockSnapshot.capture(second));
    }

    private Bed bedWithData(byte[] bytes) throws IOException {
        Bed bed = state(mock(Bed.class), Material.RED_BED, "bed");
        PersistentDataContainer container = mock(PersistentDataContainer.class);
        when(container.serializeToBytes()).thenReturn(bytes);
        when(bed.getPersistentDataContainer()).thenReturn(container);
        return bed;
    }

    private <T extends BlockState> T state(T state, Material material, String description) {
        BlockData data = mock(BlockData.class);
        Material snapshotMaterial = snapshotMaterial(material);
        when(data.clone()).thenReturn(data);
        when(data.getAsString()).thenReturn(description);
        when(state.getType()).thenReturn(snapshotMaterial);
        when(state.getBlockData()).thenReturn(data);
        return state;
    }

    private Material snapshotMaterial(Material material) {
        if (material == Material.WATER || material == Material.LAVA) return material;
        // Gravity metadata belongs to Paper's live registry, which is outside this unit fixture.
        Material result = mock(Material.class);
        when(result.hasGravity()).thenReturn(material == Material.SAND || material == Material.GRAVEL);
        return result;
    }
}
