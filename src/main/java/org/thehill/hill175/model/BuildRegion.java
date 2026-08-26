package org.thehill.hill175.model;

import org.bukkit.Location;

public record BuildRegion(
        String worldName,
        int minX,
        int minY,
        int minZ,
        int maxX,
        int maxY,
        int maxZ
) {
    public BuildRegion {
        if (worldName == null || worldName.isBlank()) {
            throw new IllegalArgumentException("worldName is required");
        }
        if (minX > maxX || minY > maxY || minZ > maxZ) {
            throw new IllegalArgumentException("region minimums must not exceed maximums");
        }
    }

    public boolean contains(Location location) {
        if (location == null || location.getWorld() == null || !worldName.equals(location.getWorld().getName())) {
            return false;
        }
        return contains(location.getBlockX(), location.getBlockY(), location.getBlockZ());
    }

    public boolean contains(int x, int y, int z) {
        return x >= minX && x <= maxX
                && y >= minY && y <= maxY
                && z >= minZ && z <= maxZ;
    }

    public int centerX() {
        return minX + ((maxX - minX) / 2);
    }

    public int centerZ() {
        return minZ + ((maxZ - minZ) / 2);
    }
}
