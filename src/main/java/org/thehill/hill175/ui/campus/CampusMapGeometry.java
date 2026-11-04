package org.thehill.hill175.ui.campus;

import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.world.BuildingCatalog;

import java.util.List;
import java.util.Optional;

/** Letterboxed map projection shared by tile selection and prepared artwork. */
public final class CampusMapGeometry {
    public static final int columns = 9;
    public static final int rows = 5;
    public static final int tileCount = columns * rows;
    private final BuildRegion bounds;
    private final double scale;
    private final double offsetX;
    private final double offsetZ;

    public CampusMapGeometry(BuildRegion bounds) {
        this.bounds = java.util.Objects.requireNonNull(bounds);
        double width = (double) bounds.maxX() - bounds.minX() + 1;
        double depth = (double) bounds.maxZ() - bounds.minZ() + 1;
        scale = Math.min(columns / width, rows / depth);
        offsetX = (columns - width * scale) / 2;
        offsetZ = (rows - depth * scale) / 2;
    }

    public Optional<Tile> tile(int slot) {
        if (slot < 0 || slot >= tileCount) return Optional.empty();
        int column = slot % columns;
        int row = slot / columns;
        int minX = Math.max(bounds.minX(), (int) Math.ceil((column - offsetX) / scale + bounds.minX()));
        int minZ = Math.max(bounds.minZ(), (int) Math.ceil((row - offsetZ) / scale + bounds.minZ()));
        int maxX = Math.min(bounds.maxX(), (int) Math.ceil((column + 1 - offsetX) / scale + bounds.minX()) - 1);
        int maxZ = Math.min(bounds.maxZ(), (int) Math.ceil((row + 1 - offsetZ) / scale + bounds.minZ()) - 1);
        if (minX > maxX || minZ > maxZ) return Optional.empty();
        return Optional.of(new Tile(slot, minX, minZ, maxX, maxZ));
    }

    public int slotAt(int x, int z) {
        if (x < bounds.minX() || x > bounds.maxX() || z < bounds.minZ() || z > bounds.maxZ()) return -1;
        int column = Math.min(columns - 1, (int) Math.floor(offsetX + (x - bounds.minX()) * scale));
        int row = Math.min(rows - 1, (int) Math.floor(offsetZ + (z - bounds.minZ()) * scale));
        return row * columns + column;
    }

    public record Tile(int slot, int minX, int minZ, int maxX, int maxZ) {
        public int centerX() { return minX + (maxX - minX) / 2; }
        public int centerZ() { return minZ + (maxZ - minZ) / 2; }
        public boolean contains(int x, int z) { return x >= minX && x <= maxX && z >= minZ && z <= maxZ; }
        public List<BuildingCatalog.Building> buildings(List<BuildingCatalog.Building> catalog) {
            return catalog.stream().filter(building -> building.maxX() >= minX && building.minX() <= maxX
                    && building.maxZ() >= minZ && building.minZ() <= maxZ).toList();
        }
    }
}
