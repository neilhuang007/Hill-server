package org.thehill.hill175.blueprint;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Groups nearby changed blocks into boxes that students and moderators can visit one at a time. */
public final class ChangeAreas {
    private static final int FIRST_CELL_SIZE = 8;
    private static final int MAXIMUM_CELL_SIZE = 64;
    static final int MAXIMUM_AREAS = 40;

    private ChangeAreas() { }

    public record Area(int minX, int minY, int minZ, int maxX, int maxY, int maxZ, List<BlockPosition> positions) {
        public Area { positions = List.copyOf(positions); }
        public int size() { return positions.size(); }
        public boolean contains(BlockPosition position) {
            return position.blockX() >= minX && position.blockX() <= maxX && position.blockY() >= minY
                    && position.blockY() <= maxY && position.blockZ() >= minZ && position.blockZ() <= maxZ;
        }
        public BlockPosition center() { return new BlockPosition((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2); }
    }

    public static List<Area> of(Collection<BlockPosition> positions) {
        if (positions.isEmpty()) return List.of();
        List<Area> areas = List.of();
        for (int cell = FIRST_CELL_SIZE; cell <= MAXIMUM_CELL_SIZE; cell *= 2) {
            areas = cluster(positions, cell);
            if (areas.size() <= MAXIMUM_AREAS) break;
        }
        return areas;
    }

    private static List<Area> cluster(Collection<BlockPosition> positions, int cell) {
        Map<Cell, List<BlockPosition>> cells = new LinkedHashMap<>();
        for (BlockPosition position : positions) {
            cells.computeIfAbsent(new Cell(Math.floorDiv(position.blockX(), cell), Math.floorDiv(position.blockY(), cell),
                    Math.floorDiv(position.blockZ(), cell)), ignored -> new ArrayList<>()).add(position);
        }
        Map<Cell, Cell> parent = new HashMap<>();
        for (Cell key : cells.keySet()) parent.put(key, key);
        for (Cell key : cells.keySet()) {
            for (int offsetX = -1; offsetX <= 1; offsetX++) for (int offsetY = -1; offsetY <= 1; offsetY++) for (int offsetZ = -1; offsetZ <= 1; offsetZ++) {
                Cell neighbor = new Cell(key.x + offsetX, key.y + offsetY, key.z + offsetZ);
                if (parent.containsKey(neighbor)) union(parent, key, neighbor);
            }
        }
        Map<Cell, List<BlockPosition>> groups = new LinkedHashMap<>();
        cells.forEach((key, members) -> groups.computeIfAbsent(root(parent, key), ignored -> new ArrayList<>()).addAll(members));
        List<Area> areas = new ArrayList<>();
        for (List<BlockPosition> members : groups.values()) {
            members.sort(null);
            int minX = Integer.MAX_VALUE, minY = Integer.MAX_VALUE, minZ = Integer.MAX_VALUE;
            int maxX = Integer.MIN_VALUE, maxY = Integer.MIN_VALUE, maxZ = Integer.MIN_VALUE;
            for (BlockPosition position : members) {
                minX = Math.min(minX, position.blockX());
                minY = Math.min(minY, position.blockY());
                minZ = Math.min(minZ, position.blockZ());
                maxX = Math.max(maxX, position.blockX());
                maxY = Math.max(maxY, position.blockY());
                maxZ = Math.max(maxZ, position.blockZ());
            }
            areas.add(new Area(minX, minY, minZ, maxX, maxY, maxZ, members));
        }
        areas.sort(Comparator.comparingInt(Area::minX).thenComparingInt(Area::minZ).thenComparingInt(Area::minY));
        return List.copyOf(areas);
    }

    private static Cell root(Map<Cell, Cell> parent, Cell cell) {
        Cell current = cell;
        while (!parent.get(current).equals(current)) {
            Cell next = parent.get(current);
            parent.put(current, parent.get(next));
            current = next;
        }
        return current;
    }

    private static void union(Map<Cell, Cell> parent, Cell first, Cell second) {
        Cell firstRoot = root(parent, first);
        Cell secondRoot = root(parent, second);
        if (!firstRoot.equals(secondRoot)) parent.put(secondRoot, firstRoot);
    }

    private record Cell(int x, int y, int z) { }
}
