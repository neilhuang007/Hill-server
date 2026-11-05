package org.thehill.hill175.backup;

import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.world.WorldModule;

import java.util.ArrayList;
import java.util.List;

/** Reuses measured building footprints and exact work area unions. Tiles cover remaining grounds. */
public final class CampusRecoveryAreas {
    public record Area(String id, String name, List<BuildRegion> parts) {
        public Area { parts = List.copyOf(parts); }
        public boolean contains(int x, int z) { return parts.stream().anyMatch(p -> x >= p.minX() && x <= p.maxX() && z >= p.minZ() && z <= p.maxZ()); }
    }

    public static List<Area> read(WorldModule worlds, int minY, int maxY) {
        BuildRegion campus = worlds.sharedCampusEntry().orElseThrow().region();
        List<Area> areas = new ArrayList<>();
        worlds.areas().forEach(area -> add(areas, area.id(), area.name(), area.parts(), campus, minY, maxY));
        worlds.buildings().forEach(building -> add(areas, building.id(), building.name(),
                List.of(new BuildRegion(campus.worldName(), building.minX(), minY, building.minZ(), building.maxX(), maxY, building.maxZ())), campus, minY, maxY));
        for (int x = Math.floorDiv(campus.minX(), 128); x <= Math.floorDiv(campus.maxX(), 128); x++) {
            for (int z = Math.floorDiv(campus.minZ(), 128); z <= Math.floorDiv(campus.maxZ(), 128); z++) {
                String id = "tile_" + x + "_" + z;
                add(areas, id, "Grounds tile " + x + ", " + z,
                        List.of(new BuildRegion(campus.worldName(), x * 128, minY, z * 128, x * 128 + 127, maxY, z * 128 + 127)), campus, minY, maxY);
            }
        }
        return List.copyOf(areas);
    }

    private static void add(List<Area> result, String id, String name, List<BuildRegion> parts, BuildRegion campus, int minY, int maxY) {
        List<BuildRegion> clipped = new ArrayList<>();
        for (BuildRegion p : parts) {
            int x1 = Math.max(p.minX(), campus.minX()), x2 = Math.min(p.maxX(), campus.maxX());
            int z1 = Math.max(p.minZ(), campus.minZ()), z2 = Math.min(p.maxZ(), campus.maxZ());
            if (x1 <= x2 && z1 <= z2) clipped.add(new BuildRegion(campus.worldName(), x1, minY, z1, x2, maxY, z2));
        }
        if (!clipped.isEmpty()) result.add(new Area(id, name, clipped));
    }
}
