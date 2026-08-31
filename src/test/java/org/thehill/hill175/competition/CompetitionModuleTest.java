package org.thehill.hill175.competition;

import org.bukkit.World;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.util.List;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CompetitionModuleTest {
    private static final UUID EXPECTED = UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final UUID OTHER = UUID.fromString("00000000-0000-0000-0000-000000000002");

    @Test
    void completesPeopleTeleportOnlyForTheStillPendingCurrentEntry() {
        assertTrue(CompetitionModule.shouldCompletePendingPeopleTeleport(
                EXPECTED, EXPECTED, EXPECTED, true, true));
        assertFalse(CompetitionModule.shouldCompletePendingPeopleTeleport(
                EXPECTED, OTHER, EXPECTED, true, true));
        assertFalse(CompetitionModule.shouldCompletePendingPeopleTeleport(
                EXPECTED, EXPECTED, OTHER, true, true));
    }

    @Test
    void doesNotCompletePeopleTeleportAfterDisconnectOrLogout() {
        assertFalse(CompetitionModule.shouldCompletePendingPeopleTeleport(
                EXPECTED, EXPECTED, EXPECTED, false, true));
        assertFalse(CompetitionModule.shouldCompletePendingPeopleTeleport(
                EXPECTED, EXPECTED, EXPECTED, true, false));
    }

    @Test
    void givesCampusChartOnlyInsideTheMatchingPeopleWorld() {
        Entry people = entry(Category.PEOPLE, "hill_people_example");
        World peopleWorld = mock(World.class);
        when(peopleWorld.getName()).thenReturn("hill_people_example");
        World otherWorld = mock(World.class);
        when(otherWorld.getName()).thenReturn("hill_people_other");

        assertTrue(CompetitionModule.shouldGiveCampusChart(people, peopleWorld));
        assertFalse(CompetitionModule.shouldGiveCampusChart(people, otherWorld));
        assertFalse(CompetitionModule.shouldGiveCampusChart(entry(Category.JOURNEY, "hill_journey"), peopleWorld));
        assertFalse(CompetitionModule.shouldGiveCampusChart(people, null));
    }

    @Test
    void usesConfiguredVoxelEarthCropBoundsForCampusChart() {
        Entry people = entry(Category.PEOPLE, "hill_people_example");

        assertEquals(
                new BuildRegion("hill_people_example", -283, 70, -1_742, 1_453, 133, 197),
                CompetitionModule.campusChartBounds(people, List.of(-283, 70, -1_742, 1_453, 133, 197))
        );
    }

    @Test
    void fallsBackToEntryRegionWhenCampusChartBoundsAreMissingOrInvalid() {
        Entry people = entry(Category.PEOPLE, "hill_people_example");

        assertEquals(people.region(), CompetitionModule.campusChartBounds(people, List.of()));
        assertEquals(people.region(), CompetitionModule.campusChartBounds(
                people,
                List.of(8, 70, 8, -8, 195, -8)
        ));
    }

    private static Entry entry(Category category, String worldName) {
        return new Entry(
                EXPECTED,
                category,
                Set.of("builder"),
                worldName,
                new BuildRegion(worldName, -8, 64, -8, 8, 80, 8),
                0
        );
    }
}
