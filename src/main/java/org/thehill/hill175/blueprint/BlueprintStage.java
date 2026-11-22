package org.thehill.hill175.blueprint;

import org.bukkit.Bukkit;
import org.bukkit.Chunk;
import org.bukkit.ChunkSnapshot;
import org.bukkit.World;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.BlockData;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.model.BuildRegion;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.function.LongSupplier;

/**
 * Captures chunks as immutable snapshots on the server thread and compares two captures off it. A student
 * snapshot captures a campus and the blueprint in the same tick; a staff edit compares a chunk captured
 * before its first edit with the same chunk afterwards.
 */
final class BlueprintStage {
    private static final long MAXIMUM_TILE_BYTES = 16_777_216L;

    record Result(List<BlockChange> changes, Set<String> cleanChunks, long sequence) { }

    /** One chunk at one moment: its blocks plus full data of chests, signs and other block entities. */
    record Side(ChunkSnapshot snapshot, Map<Integer, BlockSnapshot> tiles) { }

    record Pair(int chunkX, int chunkZ, Side before, Side after) { }

    /** Area and height limits shared by both sides of a comparison. */
    record Bounds(List<BuildRegion> regions, int minimumY, int maximumY, int minimumHeight) {
        static Bounds of(World world, List<BuildRegion> regions) {
            int minimumY = Math.max(world.getMinHeight(), regions.stream().mapToInt(BuildRegion::minY).min().orElseThrow());
            int maximumY = Math.min(world.getMaxHeight() - 1, regions.stream().mapToInt(BuildRegion::maxY).max().orElseThrow());
            return new Bounds(List.copyOf(regions), minimumY, maximumY, world.getMinHeight());
        }
        boolean inside(int blockX, int blockY, int blockZ) {
            for (BuildRegion region : regions) if (region.contains(blockX, blockY, blockZ)) return true;
            return false;
        }
    }

    private BlueprintStage() { }

    /** Compares a campus with the blueprint: before is the blueprint, after is the campus. */
    static CompletableFuture<Result> run(JavaPlugin plugin, World campus, World blueprint, List<String> chunks,
                                         List<BuildRegion> regions, int limit, LongSupplier sequence) {
        CompletableFuture<Result> result = new CompletableFuture<>();
        Bounds bounds = Bounds.of(campus, regions);
        List<int[]> coordinates = chunks.stream().map(BlueprintStage::chunk).toList();
        List<CompletableFuture<Chunk>> loads = new ArrayList<>();
        for (int[] chunk : coordinates) {
            for (World world : List.of(campus, blueprint)) {
                loads.add(world.getChunkAtAsync(chunk[0], chunk[1]).thenApply(loaded -> {
                    loaded.addPluginChunkTicket(plugin);
                    return loaded;
                }));
            }
        }
        CompletableFuture.allOf(loads.toArray(CompletableFuture[]::new)).whenComplete((ignored, loadError) ->
                Bukkit.getScheduler().runTask(plugin, () -> {
                    List<Pair> pairs = new ArrayList<>();
                    long capturedAt;
                    try {
                        if (loadError != null) throw new IOException("Some of your campus could not be loaded.", loadError);
                        capturedAt = sequence.getAsLong();
                        long[] tileBytes = {0};
                        for (int[] chunk : coordinates) {
                            pairs.add(new Pair(chunk[0], chunk[1], side(blueprint.getChunkAt(chunk[0], chunk[1]), bounds, tileBytes),
                                    side(campus.getChunkAt(chunk[0], chunk[1]), bounds, tileBytes)));
                        }
                    } catch (Exception exception) {
                        result.completeExceptionally(exception);
                        return;
                    } finally {
                        for (int[] chunk : coordinates) {
                            campus.removePluginChunkTicket(chunk[0], chunk[1], plugin);
                            blueprint.removePluginChunkTicket(chunk[0], chunk[1], plugin);
                        }
                    }
                    compareLater(plugin, pairs, bounds, limit, capturedAt).whenComplete((compared, error) -> {
                        if (error != null) result.completeExceptionally(error);
                        else result.complete(compared);
                    });
                }));
        return result;
    }

    /** Compares captured pairs off the server thread and completes on the server thread. */
    static CompletableFuture<Result> compareLater(JavaPlugin plugin, List<Pair> pairs, Bounds bounds, int limit, long sequence) {
        CompletableFuture<Result> result = new CompletableFuture<>();
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                Result compared = compare(pairs, bounds, limit, sequence);
                Bukkit.getScheduler().runTask(plugin, () -> result.complete(compared));
            } catch (Exception exception) {
                Bukkit.getScheduler().runTask(plugin, () -> result.completeExceptionally(exception));
            }
        });
        return result;
    }

    /** Captures one loaded chunk. Must run on the server thread. */
    static Side side(Chunk chunk, Bounds bounds, long[] tileBytes) throws IOException {
        Map<Integer, BlockSnapshot> tiles = new HashMap<>();
        for (BlockState state : chunk.getTileEntities(false)) {
            if (state.getY() < bounds.minimumY() || state.getY() > bounds.maximumY() || !bounds.inside(state.getX(), state.getY(), state.getZ())) continue;
            BlockSnapshot snapshot = BukkitBlueprintBlocks.capture(state.getBlock());
            tileBytes[0] += snapshot.structure().length;
            if (tileBytes[0] > MAXIMUM_TILE_BYTES) {
                throw new IOException("This area has too many chests, signs or other special blocks to check at once. Ask a moderator for help.");
            }
            tiles.put(index(state.getX() & 15, state.getY() - bounds.minimumY(), state.getZ() & 15), snapshot);
        }
        return new Side(chunk.getChunkSnapshot(false, false, false, false), Map.copyOf(tiles));
    }

    static Result compare(List<Pair> pairs, Bounds bounds, int limit, long sequence) throws IOException {
        List<BlockChange> changes = new ArrayList<>();
        Set<String> clean = new HashSet<>();
        for (Pair pair : pairs) {
            int found = changes.size();
            ChunkSnapshot before = pair.before().snapshot();
            ChunkSnapshot after = pair.after().snapshot();
            for (int sectionY = bounds.minimumY(); sectionY <= bounds.maximumY(); sectionY = ((sectionY >> 4) + 1) << 4) {
                int section = (sectionY - bounds.minimumHeight()) >> 4;
                if (before.isSectionEmpty(section) && after.isSectionEmpty(section)) continue;
                int sectionTop = Math.min(bounds.maximumY(), (((sectionY >> 4) + 1) << 4) - 1);
                for (int blockY = sectionY; blockY <= sectionTop; blockY++) {
                    for (int localZ = 0; localZ < 16; localZ++) {
                        for (int localX = 0; localX < 16; localX++) {
                            int blockX = (pair.chunkX() << 4) + localX;
                            int blockZ = (pair.chunkZ() << 4) + localZ;
                            if (!bounds.inside(blockX, blockY, blockZ)) continue;
                            int key = index(localX, blockY - bounds.minimumY(), localZ);
                            BlockSnapshot tileBefore = pair.before().tiles().get(key);
                            BlockSnapshot tileAfter = pair.after().tiles().get(key);
                            BlockSnapshot from;
                            BlockSnapshot to;
                            if (tileBefore != null || tileAfter != null) {
                                from = tileBefore != null ? tileBefore : plain(before, localX, blockY, localZ);
                                to = tileAfter != null ? tileAfter : plain(after, localX, blockY, localZ);
                                if (from.equals(to)) continue;
                            } else {
                                BlockData fromData = before.getBlockData(localX, blockY, localZ);
                                BlockData toData = after.getBlockData(localX, blockY, localZ);
                                if (fromData.equals(toData)) continue;
                                from = new BlockSnapshot(fromData.getAsString(), null);
                                to = new BlockSnapshot(toData.getAsString(), null);
                                if (from.equals(to)) continue;
                            }
                            changes.add(new BlockChange(new BlockPosition(blockX, blockY, blockZ), from, to));
                            if (changes.size() > limit) {
                                throw new IOException("More than " + limit + " blocks changed, which is too much to handle at once. Ask a moderator for help.");
                            }
                        }
                    }
                }
            }
            if (changes.size() == found) clean.add(pair.chunkX() + "," + pair.chunkZ());
        }
        return new Result(List.copyOf(changes), Set.copyOf(clean), sequence);
    }

    private static BlockSnapshot plain(ChunkSnapshot snapshot, int localX, int blockY, int localZ) {
        return new BlockSnapshot(snapshot.getBlockData(localX, blockY, localZ).getAsString(), null);
    }

    private static int index(int localX, int offsetY, int localZ) { return (offsetY << 8) | (localZ << 4) | localX; }

    private static int[] chunk(String value) {
        String[] parts = value.split(",");
        if (parts.length != 2) throw new IllegalArgumentException("Invalid saved chunk coordinate.");
        return new int[]{Integer.parseInt(parts[0]), Integer.parseInt(parts[1])};
    }
}
