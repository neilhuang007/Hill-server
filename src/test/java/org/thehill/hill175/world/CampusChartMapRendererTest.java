package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;
import org.thehill.hill175.model.BuildRegion;

import java.awt.Color;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class CampusChartMapRendererTest {
    private static final BuildRegion CAMPUS = new BuildRegion(
            "hill_people_example",
            -283,
            70,
            -1_742,
            1_453,
            133,
            197
    );

    @Test
    void mapsEntireCampusBoundsWithNorthAtTheTop() {
        assertEquals(CampusChartMapRenderer.CHART_MIN_PIXEL,
                CampusChartMapRenderer.worldXToPixel(CAMPUS, CAMPUS.minX()));
        assertEquals(CampusChartMapRenderer.CHART_MAX_PIXEL,
                CampusChartMapRenderer.worldXToPixel(CAMPUS, CAMPUS.maxX()));
        assertEquals(CampusChartMapRenderer.CHART_MIN_PIXEL,
                CampusChartMapRenderer.worldZToPixel(CAMPUS, CAMPUS.minZ()),
                "negative Z is north in Minecraft and must appear at the top of the chart");
        assertEquals(CampusChartMapRenderer.CHART_MAX_PIXEL,
                CampusChartMapRenderer.worldZToPixel(CAMPUS, CAMPUS.maxZ()));

        assertTrue(Math.abs(CampusChartMapRenderer.MAP_SIZE / 2
                - CampusChartMapRenderer.worldXToPixel(CAMPUS, CAMPUS.centerX())) <= 1);
        assertTrue(Math.abs(CampusChartMapRenderer.MAP_SIZE / 2
                - CampusChartMapRenderer.worldZToPixel(CAMPUS, CAMPUS.centerZ())) <= 1);
    }

    @Test
    void clampsOffCampusPlayerLocationsToTheChartFrame() {
        assertEquals(CampusChartMapRenderer.CHART_MIN_PIXEL,
                CampusChartMapRenderer.worldXToPixel(CAMPUS, -99_999.0));
        assertEquals(CampusChartMapRenderer.CHART_MAX_PIXEL,
                CampusChartMapRenderer.worldXToPixel(CAMPUS, 99_999.0));
        assertEquals(CampusChartMapRenderer.CHART_MIN_PIXEL,
                CampusChartMapRenderer.worldZToPixel(CAMPUS, -99_999.0));
        assertEquals(CampusChartMapRenderer.CHART_MAX_PIXEL,
                CampusChartMapRenderer.worldZToPixel(CAMPUS, 99_999.0));
    }

    @Test
    void prechartsCampusFrameGridAndNorthArrow() {
        Color[] pixels = CampusChartMapRenderer.basePixels();

        assertEquals(CampusChartMapRenderer.BACKGROUND_COLOR, pixel(pixels, 0, 0));
        assertEquals(CampusChartMapRenderer.CAMPUS_BORDER_COLOR,
                pixel(pixels, CampusChartMapRenderer.CHART_MIN_PIXEL, CampusChartMapRenderer.CHART_MIN_PIXEL));
        assertEquals(CampusChartMapRenderer.PATH_COLOR,
                pixel(pixels, CampusChartMapRenderer.MAP_SIZE / 2, CampusChartMapRenderer.MAP_SIZE / 2));
        assertEquals(CampusChartMapRenderer.NORTH_ARROW_COLOR,
                pixel(pixels, CampusChartMapRenderer.MAP_SIZE / 2, 2));
    }

    @Test
    void convertsPixelCoordinatesIntoVanillaMapCursorSpace() {
        assertEquals((byte) -128, CampusChartMapRenderer.pixelToCursorCoordinate(0));
        assertEquals((byte) 0, CampusChartMapRenderer.pixelToCursorCoordinate(64));
        assertEquals((byte) 126, CampusChartMapRenderer.pixelToCursorCoordinate(127));
    }

    private static Color pixel(Color[] pixels, int x, int y) {
        return pixels[(y * CampusChartMapRenderer.MAP_SIZE) + x];
    }
}
