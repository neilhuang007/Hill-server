package org.thehill.hill175.world;

import org.thehill.hill175.model.BuildRegion;

import java.util.Optional;

/** Finds a two-block-tall standing position without looking outside an entry's owned region. */
final class SafeSpawnFinder {
    private static final int MAX_HORIZONTAL_SEARCH_RADIUS = 32;

    private SafeSpawnFinder() {
    }

    static Optional<SpawnBlock> find(
            BuildRegion region,
            int preferredX,
            int preferredY,
            int preferredZ,
            CellSafety cells
    ) {
        int originX = clamp(preferredX, region.minX(), region.maxX());
        int originY = clamp(preferredY, region.minY() + 1, region.maxY() - 1);
        int originZ = clamp(preferredZ, region.minZ(), region.maxZ());
        int maximumRadius = Math.min(MAX_HORIZONTAL_SEARCH_RADIUS, Math.max(
                Math.max(originX - region.minX(), region.maxX() - originX),
                Math.max(originZ - region.minZ(), region.maxZ() - originZ)
        ));

        for (int radius = 0; radius <= maximumRadius; radius++) {
            int minX = Math.max(region.minX(), originX - radius);
            int maxX = Math.min(region.maxX(), originX + radius);
            int minZ = Math.max(region.minZ(), originZ - radius);
            int maxZ = Math.min(region.maxZ(), originZ + radius);
            for (int x = minX; x <= maxX; x++) {
                for (int z = minZ; z <= maxZ; z++) {
                    if (Math.max(Math.abs(x - originX), Math.abs(z - originZ)) != radius) {
                        continue;
                    }
                    Optional<SpawnBlock> safe = findInColumn(region, x, originY, z, cells);
                    if (safe.isPresent()) {
                        return safe;
                    }
                }
            }
        }
        return Optional.empty();
    }

    private static Optional<SpawnBlock> findInColumn(
            BuildRegion region,
            int x,
            int preferredY,
            int z,
            CellSafety cells
    ) {
        int maximumVerticalOffset = Math.max(
                preferredY - (region.minY() + 1),
                (region.maxY() - 1) - preferredY
        );
        for (int offset = 0; offset <= maximumVerticalOffset; offset++) {
            int above = preferredY + offset;
            if (above <= region.maxY() - 1 && isSafe(x, above, z, cells)) {
                return Optional.of(new SpawnBlock(x, above, z));
            }
            int below = preferredY - offset;
            if (offset > 0 && below >= region.minY() + 1 && isSafe(x, below, z, cells)) {
                return Optional.of(new SpawnBlock(x, below, z));
            }
        }
        return Optional.empty();
    }

    private static boolean isSafe(int x, int y, int z, CellSafety cells) {
        return cells.canStandOn(x, y - 1, z)
                && cells.canOccupy(x, y, z)
                && cells.canOccupy(x, y + 1, z);
    }

    private static int clamp(int value, int minimum, int maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    interface CellSafety {
        boolean canOccupy(int x, int y, int z);

        boolean canStandOn(int x, int y, int z);
    }

    record SpawnBlock(int x, int y, int z) {
    }
}
