package org.thehill.hill175.world;

import org.bukkit.configuration.file.YamlConfiguration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

final class BuildingCatalogTest {
    @Test
    void loadsExistingMeasuredCampusWithOfficialMapNumbers(@TempDir Path folder) throws IOException {
        Files.writeString(folder.resolve(CampusTemplateMetadata.FILE_NAME), """
                revision: campus-v19-2x
                blocks-per-metre: 2
                block-bounds: [-576, 18, -1600, 1407, 319, 415]
                spawn: [228, 91, 154]
                """);
        BuildingCatalog catalog = BuildingCatalog.read(folder);
        assertEquals(36, catalog.buildings().size());
        BuildingCatalog.Building library = catalog.find("ryan-library").orElseThrow();
        assertEquals(library, catalog.find("2").orElseThrow());
        assertEquals(229, library.minX());
        assertEquals(9, library.minZ());
        assertEquals(316, library.maxX());
        assertEquals(100, library.maxZ());
        BuildRegion region = library.region("entry", -64, 320, 16);
        assertTrue(region.contains(229, -64, 9));
        assertTrue(region.contains(332, 319, 116));
        assertFalse(region.contains(333, 80, 116));
        assertTrue(catalog.find("does-not-exist").isEmpty());
        assertTrue(catalog.find(null).isEmpty());
    }

    @Test
    void refusesToGuessCoordinatesForAnUnidentifiedMap(@TempDir Path folder) throws IOException {
        Files.writeString(folder.resolve(CampusTemplateMetadata.FILE_NAME), """
                revision: operator-custom-world
                blocks-per-metre: 1
                """);
        assertTrue(assertThrows(IllegalStateException.class, () -> BuildingCatalog.read(folder))
                .getMessage().contains("its own hill-buildings.yml"));
    }

    @Test
    void usesTemplateLocalBuildingsInsteadOfBundledCoordinates(@TempDir Path folder) throws IOException {
        Files.writeString(folder.resolve(BuildingCatalog.fileName), """
                buildings:
                  measured-chapel:
                    name: Measured Chapel
                    map-number: 6
                    bounds-xz: [400, -200, 449, -121]
                """);
        BuildingCatalog.Building building = BuildingCatalog.read(folder).find("6").orElseThrow();
        assertEquals("measured-chapel", building.id());
        assertEquals(50, building.width());
        assertEquals(80, building.depth());
    }

    @Test
    void rejectsIncompleteOrInvertedMetadata() {
        YamlConfiguration incomplete = new YamlConfiguration();
        incomplete.set("buildings.chapel.name", "Chapel");
        assertThrows(IllegalStateException.class, () -> BuildingCatalog.parse(incomplete, "test"));
        assertThrows(IllegalStateException.class, () ->
                new BuildingCatalog.Building("bad", "Bad", 1, 20, 0, 10, 50));
    }
}
