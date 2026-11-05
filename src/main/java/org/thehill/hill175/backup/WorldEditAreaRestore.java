package org.thehill.hill175.backup;

import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.regions.CuboidRegion;
import com.sk89q.worldedit.util.io.Closer;
import com.sk89q.worldedit.world.snapshot.experimental.SnapshotInfo;
import com.sk89q.worldedit.world.snapshot.experimental.Snapshot;
import com.sk89q.worldedit.world.snapshot.experimental.SnapshotRestore;
import com.sk89q.worldedit.world.snapshot.experimental.fs.FolderSnapshot;
import com.sk89q.worldedit.world.chunk.Chunk;
import com.sk89q.worldedit.world.DataException;
import org.enginehub.linbus.tree.LinCompoundTag;
import org.bukkit.World;
import org.thehill.hill175.model.BuildRegion;

import java.io.IOException;
import java.nio.file.Path;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;

/** WorldEdit owns Anvil decoding and block entity restoration. Each edit is bounded to one chunk section. */
public final class WorldEditAreaRestore implements AutoCloseable {
    private final FolderSnapshot snapshot;
    private BlockVector3 cachedPosition;
    private Chunk cachedChunk;
    private final Snapshot cachedSource = new Snapshot() {
        @Override public SnapshotInfo getInfo() { return snapshot.getInfo(); }
        @Override public LinCompoundTag getChunkTag(BlockVector3 position) throws DataException, IOException { return snapshot.getChunkTag(position); }
        @Override public Chunk getChunk(BlockVector3 position) throws DataException, IOException {
            if (!position.equals(cachedPosition)) { cachedChunk = snapshot.getChunk(position); cachedPosition = position; }
            return cachedChunk;
        }
        @Override public void close() { }
    };
    private final List<BuildRegion> slices;
    private int cursor;

    public WorldEditAreaRestore(Path stagedWorld, CampusRecoveryAreas.Area area) {
        snapshot = new FolderSnapshot(SnapshotInfo.create(stagedWorld.toUri(), ZonedDateTime.now()), stagedWorld, Closer.create());
        slices = slices(area.parts());
    }

    public static List<BuildRegion> slices(List<BuildRegion> parts) {
        List<BuildRegion> result = new ArrayList<>();
        for (BuildRegion p : parts) {
            for (int x = Math.floorDiv(p.minX(), 16); x <= Math.floorDiv(p.maxX(), 16); x++) {
                for (int z = Math.floorDiv(p.minZ(), 16); z <= Math.floorDiv(p.maxZ(), 16); z++) {
                    for (int y = p.minY(); y <= p.maxY(); y += 16) {
                        result.add(new BuildRegion(p.worldName(), Math.max(p.minX(), x * 16), y, Math.max(p.minZ(), z * 16),
                                Math.min(p.maxX(), x * 16 + 15), Math.min(p.maxY(), y + 15), Math.min(p.maxZ(), z * 16 + 15)));
                    }
                }
            }
        }
        return List.copyOf(result);
    }

    /** Check every required source chunk before changing even one live block. Call off the server thread. */
    public void verify() throws IOException {
        try {
            BlockVector3 previous = null;
            for (BuildRegion slice : slices) {
                var position = BlockVector3.at(slice.minX() >> 4, 0, slice.minZ() >> 4);
                if (!position.equals(previous)) snapshot.getChunk(position);
                previous = position;
            }
        } catch (Exception exception) {
            throw new IOException("The snapshot cannot supply this whole area. No blocks were changed.", exception);
        }
    }

    /** Run on the server thread. No off-thread Bukkit edits or full-area block arrays. */
    public boolean step(World world) throws Exception {
        BuildRegion p = slices.get(cursor);
        var adapted = BukkitAdapter.adapt(world);
        Chunk source = cachedSource.getChunk(BlockVector3.at(p.minX() >> 4, 0, p.minZ() >> 4));
        var selection = new CuboidRegion(adapted, BlockVector3.at(p.minX(), p.minY(), p.minZ()), BlockVector3.at(p.maxX(), p.maxY(), p.maxZ()));
        try (var edit = WorldEdit.getInstance().newEditSessionBuilder().world(adapted).maxBlocks(-1).build()) {
            edit.setTrackingHistory(false); // The mandatory Restic safety snapshot is persistent undo.
            edit.setFastMode(true);
            edit.setMask(position -> {
                try { return !edit.getFullBlock(position).equals(source.getBlock(position)); }
                catch (DataException exception) { throw new IllegalStateException("Cannot read a source block.", exception); }
            });
            var restore = new SnapshotRestore(cachedSource, edit, selection);
            restore.restore();
            if (!restore.getMissingChunks().isEmpty() || !restore.getErrorChunks().isEmpty()) {
                throw new IOException("WorldEdit could not restore a source chunk: " + restore.getLastErrorMessage());
            }
        }
        cursor++;
        return cursor == slices.size();
    }

    public int completed() { return cursor; }
    public int total() { return slices.size(); }
    @Override public void close() throws IOException { snapshot.close(); }
}
