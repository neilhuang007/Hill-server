package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class WorldModulePeopleCloneTest {
    @Test
    void clonesTheTemplateIntoPapersActiveCustomDimensionFolder() {
        Path legacy = Path.of("server", "hill_people_example");
        Path migrated = Path.of("server", "world", "dimensions", "minecraft", "hill_people_example");

        assertEquals(migrated, WorldModule.peopleTemplateCloneDestination(legacy, migrated));
    }

    @Test
    void excludesIdentityMetadataWhenCloningPaperWorlds() {
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("uid.dat")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("session.lock")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("level.dat")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("level.dat_old")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("data", "paper", "metadata.dat")));
        assertFalse(WorldModule.shouldSkipWorldClonePath(Path.of("region", "r.0.0.mca")));
        assertFalse(WorldModule.shouldSkipWorldClonePath(Path.of("data", "paper", "unrelated.dat")));
    }

    @Test
    void validatesGeneratedAnvilTemplateShape(@TempDir Path template) throws IOException {
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        Files.writeString(template.resolve(".hill175-people-ready"), "generated\n");
        Path region = Files.createDirectories(template.resolve("region"));
        Path poi = Files.createDirectories(template.resolve("poi"));
        Files.writeString(template.resolve("voxelearth-hill-manifest.json"), "{}\n");
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        Files.write(region.resolve("r.0.-1.mca"), new byte[] {0});
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        for (int index = 0; index < 26; index++) {
            Files.write(region.resolve("r." + index + ".0.mca"), new byte[8_192]);
        }
        for (int index = 0; index < 11; index++) {
            Files.write(poi.resolve("r." + index + ".0.mca"), new byte[8_192]);
        }
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));
        Files.delete(region.resolve("r.0.-1.mca"));
        assertTrue(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        Files.createDirectories(template.resolve("dimensions"));
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));
        Files.delete(template.resolve("dimensions"));

        Files.writeString(template.resolve(".hill175-people-ready"), "wrong\n");
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));
    }
}
