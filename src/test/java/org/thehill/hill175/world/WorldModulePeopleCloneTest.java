package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class WorldModulePeopleCloneTest {
    @Test
    void clonesTheTemplateIntoPapersActiveCustomDimensionFolder() {
        Path legacy = Path.of("server", "hill_people_example");
        Path migrated = Path.of("server", "world", "dimensions", "minecraft", "hill_people_example");

        assertEquals(migrated, WorldModule.peopleTemplateCloneDestination(legacy, migrated));
    }
}
