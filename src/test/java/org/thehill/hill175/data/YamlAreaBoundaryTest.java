package org.thehill.hill175.data;

import org.bukkit.Location;
import org.bukkit.World;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.*;
import java.nio.file.Path;
import java.util.*;
import java.util.logging.Logger;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class YamlAreaBoundaryTest {
    @TempDir Path directory;

    @Test
    void frozenUnionSurvivesRestartWithoutExpandingIntoTheGap() {
        var entry = new Entry(UUID.randomUUID(), Category.PLACE, Set.of("student"), "campus",
                new BuildRegion("campus", 0, -64, 0, 30, 319, 30), 0);
        entry.selectedBuildingId("area-test");
        entry.editableRegions(List.of(new BuildRegion("campus", 0, -64, 0, 10, 319, 30),
                new BuildRegion("campus", 11, -64, 20, 30, 319, 30)));
        var store = new YamlCompetitionStore(directory.toFile(), Logger.getAnonymousLogger());
        store.saveEntry(entry);
        var restored = new YamlCompetitionStore(directory.toFile(), Logger.getAnonymousLogger()).entry(entry.id()).orElseThrow();
        assertEquals(entry.editableRegions(), restored.editableRegions());
        World world = mock(World.class);
        when(world.getName()).thenReturn("campus");
        assertTrue(restored.containsEditable(new Location(world, 10, 80, 10)));
        assertFalse(restored.containsEditable(new Location(world, 11, 80, 10)));
        assertTrue(restored.containsEditable(new Location(world, 11, 80, 20)));
        assertThrows(IllegalArgumentException.class, () -> restored.editableRegions(List.of(
                new BuildRegion("another-world", 0, -64, 0, 10, 319, 10))));
    }
}
