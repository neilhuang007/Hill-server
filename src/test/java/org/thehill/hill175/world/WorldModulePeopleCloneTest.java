package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;

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
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("data", "paper", "metadata.dat")));
        assertFalse(WorldModule.shouldSkipWorldClonePath(Path.of("region", "r.0.0.mca")));
        assertFalse(WorldModule.shouldSkipWorldClonePath(Path.of("data", "paper", "unrelated.dat")));
    }
}
