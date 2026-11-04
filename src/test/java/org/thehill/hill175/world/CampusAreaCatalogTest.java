package org.thehill.hill175.world;

import org.bukkit.configuration.file.YamlConfiguration;
import org.junit.jupiter.api.Test;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import static org.junit.jupiter.api.Assertions.*;

class CampusAreaCatalogTest {
    @Test
    void campusWorkRectanglesKeepTheUnassignedGapProtected() {
        var yaml = YamlConfiguration.loadConfiguration(new InputStreamReader(
                getClass().getResourceAsStream("/hill-areas.yml"), StandardCharsets.UTF_8));
        var catalog = CampusAreaCatalog.parse(yaml);
        assertEquals(7, catalog.areas().size());
        var area = catalog.find("area-s2").orElseThrow();
        assertTrue(area.regions("entry").stream().anyMatch(part -> part.contains(520, 80, -500)));
        assertFalse(area.regions("entry").stream().anyMatch(part -> part.contains(400, 80, -500)));
        assertTrue(area.envelope().region("entry", -64, 320, 0).contains(400, 80, -500));
    }

    @Test
    void refusesOverlappingAreasAndMalformedBounds() throws Exception {
        var yaml = new YamlConfiguration();
        yaml.loadFromString("coordinate-frame: hill-local-east-south-2x\nareas:\n  area-a:\n    name: A\n    boxes: [[0, 0, 10, 10]]\n  area-b:\n    name: B\n    boxes: [[10, 10, 20, 20]]\n");
        assertThrows(IllegalStateException.class, () -> CampusAreaCatalog.parse(yaml));
        yaml.set("areas.area-b.boxes", java.util.List.of(java.util.List.of(11.5, 11, 20, 20)));
        assertThrows(IllegalStateException.class, () -> CampusAreaCatalog.parse(yaml));
    }
}
