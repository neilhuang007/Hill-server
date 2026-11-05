package org.thehill.hill175.backup;

import org.junit.jupiter.api.Test;
import org.thehill.hill175.model.BuildRegion;

import java.util.HashSet;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class WorldEditAreaRestoreTest {
    @Test void slicesPreserveDisjointPartsAndNegativeChunkEdgesWithoutTouchingHolesOrNeighbors() {
        var parts = List.of(new BuildRegion("hill_campus", -17, -64, -2, -15, 319, 2),
                new BuildRegion("hill_campus", 3, -64, -2, 18, 319, 2));
        var slices = WorldEditAreaRestore.slices(parts);
        var blocks = new HashSet<String>();
        for (var slice : slices) {
            assertEquals(Math.floorDiv(slice.minX(), 16), Math.floorDiv(slice.maxX(), 16));
            assertEquals(Math.floorDiv(slice.minZ(), 16), Math.floorDiv(slice.maxZ(), 16));
            assertTrue(slice.maxY() - slice.minY() < 16);
            for (int x = slice.minX(); x <= slice.maxX(); x++) for (int z = slice.minZ(); z <= slice.maxZ(); z++) for (int y = slice.minY(); y <= slice.maxY(); y++) {
                assertTrue(blocks.add(x + ":" + y + ":" + z), "No block may be restored twice");
                int px = x, py = y, pz = z;
                assertTrue(parts.stream().anyMatch(p -> p.contains(px, py, pz)), "No hole or neighbor may be restored");
            }
        }
        assertEquals((3 + 16) * 5 * 384, blocks.size());
    }
}
