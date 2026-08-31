package org.thehill.hill175.model;

import org.junit.jupiter.api.Test;

import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EntryCameraSlotsTest {
    @Test
    void removingOneCameraDoesNotRenumberTheOthers() {
        Entry entry = entry();
        CameraPose first = pose(1.0);
        CameraPose second = pose(2.0);
        CameraPose third = pose(3.0);

        assertTrue(entry.setCameraPose(1, first));
        assertTrue(entry.setCameraPose(2, second));
        assertTrue(entry.setCameraPose(3, third));
        assertTrue(entry.removeCameraPose(2));

        assertEquals(Set.of(1, 3), Set.copyOf(entry.savedCameraSlots()));
        assertEquals(first, entry.cameraPose(1).orElseThrow());
        assertTrue(entry.cameraPose(2).isEmpty());
        assertEquals(third, entry.cameraPose(3).orElseThrow());
        assertEquals(2, entry.firstEmptyCameraSlot().orElseThrow());
    }

    @Test
    void cameraSlotsRejectInvalidIndexesAndNeverExceedThree() {
        Entry entry = entry();

        assertFalse(entry.setCameraPose(0, pose(0.0)));
        assertFalse(entry.setCameraPose(4, pose(4.0)));
        assertTrue(entry.addCameraPose(pose(1.0)));
        assertTrue(entry.addCameraPose(pose(2.0)));
        assertTrue(entry.addCameraPose(pose(3.0)));
        assertFalse(entry.addCameraPose(pose(4.0)));
        assertEquals(3, entry.cameraPoses().size());
    }

    private static Entry entry() {
        return new Entry(
                UUID.fromString("00000000-0000-0000-0000-000000001750"),
                Category.JOURNEY,
                Set.of("builder"),
                "hill_journey",
                new BuildRegion("hill_journey", 0, 0, 0, 63, 63, 63),
                0
        );
    }

    private static CameraPose pose(double coordinate) {
        return new CameraPose("hill_journey", coordinate, 70.0, coordinate, 45.0f, -10.0f);
    }
}
