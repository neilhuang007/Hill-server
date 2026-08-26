package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;
import org.thehill.hill175.model.BuildRegion;

import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class SafeSpawnFinderTest {
    private static final BuildRegion REGION = new BuildRegion("hill_journey", 0, 64, 0, 7, 72, 7);

    @Test
    void keepsThePreferredSpawnWhenFeetAndHeadAreClearAboveSolidGround() {
        Set<Point> solid = floor();

        var result = SafeSpawnFinder.find(REGION, 3, 67, 3, safety(solid));

        assertEquals(new SafeSpawnFinder.SpawnBlock(3, 65, 3), result.orElseThrow());
    }

    @Test
    void movesToANearbySafeColumnWhenThePreferredSpawnIsInsideABuild() {
        Set<Point> solid = floor();
        for (int y = 65; y <= 72; y++) {
            solid.add(new Point(3, y, 3));
        }

        var result = SafeSpawnFinder.find(REGION, 3, 67, 3, safety(solid));

        SafeSpawnFinder.SpawnBlock spawn = result.orElseThrow();
        assertTrue(REGION.contains(spawn.x(), spawn.y(), spawn.z()));
        assertTrue(REGION.contains(spawn.x(), spawn.y() + 1, spawn.z()));
        assertTrue(spawn.x() != 3 || spawn.z() != 3, "must leave the blocked center column");
        assertTrue(!solid.contains(new Point(spawn.x(), spawn.y(), spawn.z())));
        assertTrue(!solid.contains(new Point(spawn.x(), spawn.y() + 1, spawn.z())));
        assertTrue(solid.contains(new Point(spawn.x(), spawn.y() - 1, spawn.z())));
    }

    @Test
    void neverEscapesTheOwnedRegionWhenNoSafeSpawnExists() {
        var result = SafeSpawnFinder.find(REGION, 3, 67, 3, new SafeSpawnFinder.CellSafety() {
            @Override
            public boolean canOccupy(int x, int y, int z) {
                return false;
            }

            @Override
            public boolean canStandOn(int x, int y, int z) {
                return false;
            }
        });

        assertTrue(result.isEmpty());
    }

    private static Set<Point> floor() {
        Set<Point> floor = new HashSet<>();
        for (int x = REGION.minX(); x <= REGION.maxX(); x++) {
            for (int z = REGION.minZ(); z <= REGION.maxZ(); z++) {
                floor.add(new Point(x, 64, z));
            }
        }
        return floor;
    }

    private static SafeSpawnFinder.CellSafety safety(Set<Point> solid) {
        return new SafeSpawnFinder.CellSafety() {
            @Override
            public boolean canOccupy(int x, int y, int z) {
                return !solid.contains(new Point(x, y, z));
            }

            @Override
            public boolean canStandOn(int x, int y, int z) {
                return solid.contains(new Point(x, y, z));
            }
        };
    }

    private record Point(int x, int y, int z) {
    }
}
