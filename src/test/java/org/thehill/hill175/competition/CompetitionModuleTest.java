package org.thehill.hill175.competition;

import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

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
}
