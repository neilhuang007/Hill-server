package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class CameraPoseResolverTest {
    private static final BuildRegion REGION = new BuildRegion("hill_journey", 0, 60, 0, 20, 90, 20);
    private static final CameraPose POSE = new CameraPose("hill_journey", 10.5, 67.62, 10.5, 35.0f, -12.0f);

    @Test
    void convertsSavedEyeCoordinatesToFeetWithoutChangingTheView() {
        var result = CameraPoseResolver.resolve(REGION, POSE, 1.62, alwaysInside(), alwaysClear()).orElseThrow();

        assertEquals(66.0, result.feetY(), 0.000_001);
        assertEquals(POSE.x(), result.x());
        assertEquals(POSE.z(), result.z());
        assertEquals(POSE.yaw(), result.yaw());
        assertEquals(POSE.pitch(), result.pitch());
    }

    @Test
    void rejectsAViewWhenThePlayersFeetOrEyesWouldBeInsideABlock() {
        var result = CameraPoseResolver.resolve(
                REGION,
                POSE,
                1.62,
                alwaysInside(),
                (x, y, z) -> y != 67
        );

        assertTrue(result.isEmpty());
    }

    @Test
    void rejectsViewsOutsideTheEntryOrWorldBorder() {
        CameraPose outsideEntry = new CameraPose("hill_journey", 30.5, 67.62, 10.5, 0.0f, 0.0f);
        assertTrue(CameraPoseResolver.resolve(REGION, outsideEntry, 1.62, alwaysInside(), alwaysClear()).isEmpty());
        assertTrue(CameraPoseResolver.resolve(REGION, POSE, 1.62, (x, y, z) -> x < 10.0, alwaysClear()).isEmpty());
    }

    @Test
    void rejectsAnOutwardFacingViewThatWouldFeatureAnotherPlot() {
        CameraPose outward = new CameraPose("hill_journey", 1.5, 67.62, 10.5, 90.0f, 0.0f);
        CameraPose inward = new CameraPose("hill_journey", 1.5, 67.62, 10.5, -90.0f, 0.0f);

        assertTrue(CameraPoseResolver.resolve(REGION, outward, 1.62, alwaysInside(), alwaysClear()).isEmpty());
        assertTrue(CameraPoseResolver.resolve(REGION, inward, 1.62, alwaysInside(), alwaysClear()).isPresent());
    }

    @Test
    void rejectsAnotherWorldAndNonFiniteCoordinates() {
        CameraPose anotherWorld = new CameraPose("hill_place", 10.5, 67.62, 10.5, 0.0f, 0.0f);
        CameraPose invalid = new CameraPose("hill_journey", Double.NaN, 67.62, 10.5, 0.0f, 0.0f);

        assertTrue(CameraPoseResolver.resolve(REGION, anotherWorld, 1.62, alwaysInside(), alwaysClear()).isEmpty());
        assertTrue(CameraPoseResolver.resolve(REGION, invalid, 1.62, alwaysInside(), alwaysClear()).isEmpty());
    }

    private static CameraPoseResolver.Boundary alwaysInside() {
        return (x, y, z) -> true;
    }

    private static CameraPoseResolver.CellSafety alwaysClear() {
        return (x, y, z) -> true;
    }
}
