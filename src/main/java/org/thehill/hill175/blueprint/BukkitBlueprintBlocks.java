package org.thehill.hill175.blueprint;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.TileState;
import org.bukkit.block.structure.Mirror;
import org.bukkit.block.structure.StructureRotation;
import org.bukkit.util.BlockVector;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Map;
import java.util.Random;

final class BukkitBlueprintBlocks implements BlueprintMerge.Blocks {
    private final World world;

    BukkitBlueprintBlocks(World world) { this.world = world; }

    @Override
    public BlockSnapshot read(BlockPosition position) throws IOException {
        return capture(world.getBlockAt(position.blockX(), position.blockY(), position.blockZ()));
    }

    static BlockSnapshot capture(Block block) throws IOException {
        String data = block.getBlockData().getAsString();
        if (!(block.getState(false) instanceof TileState)) return new BlockSnapshot(data, null);
        var manager = Bukkit.getStructureManager();
        var structure = manager.createStructure();
        structure.fill(block.getLocation(), new BlockVector(1, 1, 1), false);
        var bytes = new ByteArrayOutputStream();
        manager.saveStructure(bytes, structure);
        return new BlockSnapshot(data, bytes.toByteArray());
    }

    @Override
    public void write(BlockPosition position, BlockSnapshot snapshot) throws IOException { write(Map.of(position, snapshot)); }

    /**
     * Placing a block-entity structure reshapes the block from its neighbours, which turns a lone bed half
     * into air and a lone double-chest half into a single chest. Every block shape is set first without
     * physics, so block-entity data is placed once the neighbours already exist.
     */
    @Override
    public void write(Map<BlockPosition, BlockSnapshot> blocks) throws IOException {
        for (var entry : blocks.entrySet()) {
            BlockPosition position = entry.getKey();
            if (position.blockY() < world.getMinHeight() || position.blockY() >= world.getMaxHeight()) {
                throw new IOException("Blueprint change is outside world height.");
            }
            block(position).setBlockData(Bukkit.createBlockData(entry.getValue().blockData()), false);
        }
        for (var entry : blocks.entrySet()) {
            byte[] bytes = entry.getValue().structure();
            if (bytes.length == 0) continue;
            var structure = Bukkit.getStructureManager().loadStructure(new ByteArrayInputStream(bytes));
            if (structure.getSize().getBlockX() != 1 || structure.getSize().getBlockY() != 1
                    || structure.getSize().getBlockZ() != 1 || structure.getEntityCount() != 0) {
                throw new IOException("Invalid block entity snapshot size.");
            }
            structure.place(block(entry.getKey()).getLocation(), false, StructureRotation.NONE, Mirror.NONE, 0, 1.0f, new Random(0));
        }
        for (var entry : blocks.entrySet()) {
            if (!read(entry.getKey()).equals(entry.getValue())) throw new IOException("Block restoration did not match its snapshot: " + entry.getKey());
        }
    }

    private Block block(BlockPosition position) { return world.getBlockAt(position.blockX(), position.blockY(), position.blockZ()); }
}
