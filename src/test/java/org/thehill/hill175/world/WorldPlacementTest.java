package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class WorldPlacementTest {
    @TempDir Path map;

    @Test
    void mapWithoutPlacementKeepsItsOwnSpawn() {
        assertSame(WorldPlacement.NONE, WorldPlacement.read(map));
    }

    @Test
    void readsArrivalPointAndGuidePositionsSuppliedWithTheMap() throws Exception {
        write("""
                spawn: [70.5, 66.1, 42.5, 0.0, 0.0]
                npcs:
                  journey: [70.5, 67.0, 70.5, 180.0, 0.0]
                  survival: [70.5, 66, 31.5]
                """);
        WorldPlacement placement = WorldPlacement.read(map);
        assertEquals(Optional.of(new WorldPlacement.Pose(70.5, 66.1, 42.5, 0.0f, 0.0f)), placement.spawn());
        assertEquals(Set.of("journey", "survival"), placement.npcs().keySet());
        assertEquals(new WorldPlacement.Pose(70.5, 67.0, 70.5, 180.0f, 0.0f), placement.npcs().get("journey"));
        assertEquals(new WorldPlacement.Pose(70.5, 66.0, 31.5, 0.0f, 0.0f), placement.npcs().get("survival"));
    }

    @Test
    void refusesMisspelledEntriesRatherThanFallingBackToAnotherPosition() throws Exception {
        write("spwan: [1, 2, 3]\n");
        assertThrows(IllegalStateException.class, () -> WorldPlacement.read(map));
        write("npcs:\n  guide: [1, 2, 3]\n");
        assertThrows(IllegalStateException.class, () -> WorldPlacement.read(map));
    }

    @Test
    void refusesIncompleteOrNonNumericPositions() throws Exception {
        write("spawn: [1, 2]\n");
        assertThrows(IllegalStateException.class, () -> WorldPlacement.read(map));
        write("spawn: [1, two, 3]\n");
        assertThrows(IllegalStateException.class, () -> WorldPlacement.read(map));
        write("npcs: [1, 2, 3]\n");
        assertThrows(IllegalStateException.class, () -> WorldPlacement.read(map));
        write("spawn: [1, 2, 3\n");
        assertThrows(IllegalStateException.class, () -> WorldPlacement.read(map));
    }

    private void write(String yaml) throws Exception {
        Files.writeString(map.resolve(WorldPlacement.FILE_NAME), yaml);
    }
}
