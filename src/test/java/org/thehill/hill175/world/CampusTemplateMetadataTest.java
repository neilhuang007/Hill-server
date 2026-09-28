package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CampusTemplateMetadataTest {
    @TempDir Path world;

    @Test
    void preservesLegacyWorldsWithoutCampusMetadata() {
        assertFalse(CampusTemplateMetadata.read(world).isPresent());
    }

    @Test
    void importsTwoBlockCampusBoundsIncludingTerrainBelowOldBuildBase() throws Exception {
        Files.writeString(world.resolve(CampusTemplateMetadata.FILE_NAME), """
                block-bounds: [-576, 18, -1600, 1407, 319, 415]
                spawn: [228, 91, 154]
                """);
        var metadata = CampusTemplateMetadata.read(world).orElseThrow();
        assertEquals(new BuildRegion("campus", -576, 18, -1600, 1407, 319, 415),
                metadata.region("campus", -64, 320));
    }

    @Test
    void refusesSpawnOutsideTemplateRatherThanSilentlySpawningInVoid() throws Exception {
        Files.writeString(world.resolve(CampusTemplateMetadata.FILE_NAME), """
                block-bounds: [-576, 18, -1600, 1407, 319, 415]
                spawn: [228, 91, 500]
                """);
        assertThrows(IllegalStateException.class, () -> CampusTemplateMetadata.read(world));
    }
}
