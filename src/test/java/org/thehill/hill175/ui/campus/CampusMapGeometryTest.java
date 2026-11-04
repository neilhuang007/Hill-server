package org.thehill.hill175.ui.campus;

import org.junit.jupiter.api.Test;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.world.BuildingCatalog;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CampusMapGeometryTest {
    private final BuildRegion campus = new BuildRegion("campus", -576, -64, -1600, 1471, 319, 415);
    private final CampusMapGeometry geometry = new CampusMapGeometry(campus);

    @Test void allWorldEdgesRemainSelectableWhileLetterboxIsInactive() {
        assertTrue(geometry.tile(0).isEmpty());
        assertTrue(geometry.tile(8).isEmpty());
        assertTrue(geometry.tile(-1).isEmpty());
        assertTrue(geometry.tile(45).isEmpty());
        for (int x : List.of(campus.minX(), campus.centerX(), campus.maxX())) {
            for (int z : List.of(campus.minZ(), campus.centerZ(), campus.maxZ())) {
                assertTrue(geometry.tile(geometry.slotAt(x, z)).orElseThrow().contains(x, z), x + "," + z);
            }
        }
        assertEquals(-1, geometry.slotAt(campus.minX() - 1, campus.minZ()));
        assertEquals(-1, geometry.slotAt(campus.maxX(), campus.maxZ() + 1));
    }

    @Test void northIsUpAndEastIsRightWithoutRotatingOrMirroringTheCoordinates() {
        int northWest = geometry.slotAt(-576, -1600);
        int southEast = geometry.slotAt(1471, 415);
        assertEquals(0, northWest / 9);
        assertEquals(4, southEast / 9);
        assertTrue(northWest % 9 < southEast % 9);
    }

    @Test void everyBlockColumnMapsBackIntoItsTileWithoutGapsAtRoundingBoundaries() {
        for (int x = campus.minX(); x <= campus.maxX(); x++) {
            var tile = geometry.tile(geometry.slotAt(x, 0)).orElseThrow();
            assertTrue(tile.contains(x, 0), Integer.toString(x));
        }
        for (int z = campus.minZ(); z <= campus.maxZ(); z++) {
            var tile = geometry.tile(geometry.slotAt(0, z)).orElseThrow();
            assertTrue(tile.contains(0, z), Integer.toString(z));
        }
    }

    @Test void buildingsCrossingATileBoundaryAppearInBothChoices() {
        var left = geometry.tile(22).orElseThrow();
        var building = new BuildingCatalog.Building("boundary-building", "Boundary Building", 1,
                left.maxX() - 2, left.centerZ(), left.maxX() + 2, left.centerZ() + 4);
        assertEquals(List.of(building), left.buildings(List.of(building)));
        assertEquals(List.of(building), geometry.tile(23).orElseThrow().buildings(List.of(building)));
        assertTrue(geometry.tile(4).orElseThrow().buildings(List.of(building)).isEmpty());
    }
}
