package org.thehill.hill175.undo;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.block.BlockState;
import org.bukkit.block.TileState;
import org.bukkit.block.data.BlockData;
import org.bukkit.block.data.Waterlogged;

import java.io.IOException;
import java.util.Base64;
import java.util.Objects;

/** Ordinary block data and safe bed snapshots. Inventory and other tile states are never reconstructed. */
final class BlockSnapshot {
    private final BlockData data;
    private final byte[] bedData;
    private final String fingerprint;

    private BlockSnapshot(BlockData data, byte[] bedData, String fingerprint) {
        this.data = data;
        this.bedData = bedData;
        this.fingerprint = fingerprint;
    }

    static BlockSnapshot capture(BlockState state) {
        if (state == null || unsafe(state)) return null;
        BlockData data = state.getBlockData().clone();
        if (!(state instanceof org.bukkit.block.Bed bed)) return new BlockSnapshot(data, null, data.getAsString());
        try {
            byte[] persistentData = bed.getPersistentDataContainer().serializeToBytes();
            return new BlockSnapshot(data, persistentData,
                    data.getAsString() + "|" + Base64.getEncoder().encodeToString(persistentData));
        } catch (IOException exception) {
            return null;
        }
    }

    static boolean unsafe(BlockState state) {
        Material material = state.getType();
        if (material == Material.WATER || material == Material.LAVA || material.hasGravity()) return true;
        if (state.getBlockData() instanceof Waterlogged wet && wet.isWaterlogged()) return true;
        if (state.getBlockData() instanceof org.bukkit.block.data.type.Bed bed && bed.isOccupied()) return true;
        return state instanceof TileState && !(state instanceof org.bukkit.block.Bed);
    }

    String blockData() { return data.getAsString(); }

    boolean restore(Location location) {
        location.getBlock().setBlockData(data.clone(), false);
        if (bedData == null) return true;
        if (!(location.getBlock().getState() instanceof org.bukkit.block.Bed bed)) return false;
        try {
            bed.getPersistentDataContainer().readFromBytes(bedData, true);
            return bed.update(true, false);
        } catch (IOException exception) {
            return false;
        }
    }

    @Override public boolean equals(Object other) {
        return other instanceof BlockSnapshot snapshot && fingerprint.equals(snapshot.fingerprint);
    }

    @Override public int hashCode() { return Objects.hash(fingerprint); }
}
