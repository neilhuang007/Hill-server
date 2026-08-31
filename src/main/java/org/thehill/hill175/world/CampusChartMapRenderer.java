package org.thehill.hill175.world;

import net.kyori.adventure.text.Component;
import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.map.MapCanvas;
import org.bukkit.map.MapCursor;
import org.bukkit.map.MapCursorCollection;
import org.bukkit.map.MapRenderer;
import org.bukkit.map.MapView;
import org.thehill.hill175.model.BuildRegion;

import java.awt.Color;
import java.util.Arrays;
import java.util.Objects;

public final class CampusChartMapRenderer extends MapRenderer {
    static final int MAP_SIZE = 128;
    static final int CHART_MIN_PIXEL = 9;
    static final int CHART_MAX_PIXEL = 118;
    static final Color BACKGROUND_COLOR = new Color(198, 219, 205);
    static final Color CAMPUS_FILL_COLOR = new Color(224, 214, 177);
    static final Color CAMPUS_BORDER_COLOR = new Color(74, 83, 62);
    static final Color GRID_COLOR = new Color(174, 171, 145);
    static final Color PATH_COLOR = new Color(189, 178, 145);
    static final Color NORTH_ARROW_COLOR = new Color(128, 33, 34);
    static final Color MARKER_COLOR = new Color(183, 34, 42);
    static final Color MARKER_CENTER_COLOR = new Color(255, 255, 255);

    private static final int CENTER_PIXEL = MAP_SIZE / 2;

    private final BuildRegion bounds;
    private final Color[] basePixels;

    public CampusChartMapRenderer(BuildRegion bounds) {
        super(true);
        this.bounds = Objects.requireNonNull(bounds, "bounds");
        this.basePixels = basePixels();
    }

    @Override
    public void render(MapView view, MapCanvas canvas, Player player) {
        for (int y = 0; y < MAP_SIZE; y++) {
            int row = y * MAP_SIZE;
            for (int x = 0; x < MAP_SIZE; x++) {
                canvas.setPixelColor(x, y, basePixels[row + x]);
            }
        }
        if (player == null || player.getWorld() == null || !bounds.worldName().equals(player.getWorld().getName())) {
            canvas.setCursors(new MapCursorCollection());
            return;
        }
        Location location = player.getLocation();
        int markerX = worldXToPixel(bounds, location.getX());
        int markerY = worldZToPixel(bounds, location.getZ());
        drawCurrentLocation(canvas, markerX, markerY);

        MapCursorCollection cursors = new MapCursorCollection();
        cursors.addCursor(new MapCursor(
                pixelToCursorCoordinate(markerX),
                pixelToCursorCoordinate(markerY),
                (byte) 0,
                MapCursor.Type.PLAYER,
                true,
                Component.text("You")
        ));
        canvas.setCursors(cursors);
    }

    static int worldXToPixel(BuildRegion bounds, double worldX) {
        return coordinateToPixel(worldX, bounds.minX(), bounds.maxX());
    }

    static int worldZToPixel(BuildRegion bounds, double worldZ) {
        return coordinateToPixel(worldZ, bounds.minZ(), bounds.maxZ());
    }

    static byte pixelToCursorCoordinate(int pixel) {
        int clamped = clamp(pixel, 0, MAP_SIZE - 1);
        return (byte) ((clamped * 2) - 128);
    }

    static Color[] basePixels() {
        Color[] pixels = new Color[MAP_SIZE * MAP_SIZE];
        Arrays.fill(pixels, BACKGROUND_COLOR);
        fillRect(pixels, CHART_MIN_PIXEL, CHART_MIN_PIXEL, CHART_MAX_PIXEL, CHART_MAX_PIXEL, CAMPUS_FILL_COLOR);
        drawRect(pixels, CHART_MIN_PIXEL, CHART_MIN_PIXEL, CHART_MAX_PIXEL, CHART_MAX_PIXEL, CAMPUS_BORDER_COLOR);

        for (int step = 1; step < 4; step++) {
            int pixel = CHART_MIN_PIXEL + (int) Math.round((CHART_MAX_PIXEL - CHART_MIN_PIXEL) * (step / 4.0));
            drawVerticalLine(pixels, pixel, CHART_MIN_PIXEL + 1, CHART_MAX_PIXEL - 1, GRID_COLOR);
            drawHorizontalLine(pixels, CHART_MIN_PIXEL + 1, CHART_MAX_PIXEL - 1, pixel, GRID_COLOR);
        }

        drawVerticalLine(pixels, CENTER_PIXEL, CHART_MIN_PIXEL + 1, CHART_MAX_PIXEL - 1, PATH_COLOR);
        drawHorizontalLine(pixels, CHART_MIN_PIXEL + 1, CHART_MAX_PIXEL - 1, CENTER_PIXEL, PATH_COLOR);
        drawRect(pixels, CENTER_PIXEL - 5, CENTER_PIXEL - 5, CENTER_PIXEL + 5, CENTER_PIXEL + 5, CAMPUS_BORDER_COLOR);
        drawNorthArrow(pixels);
        return pixels;
    }

    private static int coordinateToPixel(double coordinate, int minimum, int maximum) {
        if (minimum == maximum) {
            return CENTER_PIXEL;
        }
        double normalized = (coordinate - minimum) / (double) (maximum - minimum);
        int pixel = CHART_MIN_PIXEL
                + (int) Math.round(normalized * (CHART_MAX_PIXEL - CHART_MIN_PIXEL));
        return clamp(pixel, CHART_MIN_PIXEL, CHART_MAX_PIXEL);
    }

    private static void drawCurrentLocation(MapCanvas canvas, int centerX, int centerY) {
        for (int offset = -4; offset <= 4; offset++) {
            setCanvasPixel(canvas, centerX + offset, centerY, MARKER_COLOR);
            setCanvasPixel(canvas, centerX, centerY + offset, MARKER_COLOR);
        }
        for (int x = centerX - 1; x <= centerX + 1; x++) {
            for (int y = centerY - 1; y <= centerY + 1; y++) {
                setCanvasPixel(canvas, x, y, MARKER_CENTER_COLOR);
            }
        }
        setCanvasPixel(canvas, centerX, centerY, MARKER_COLOR);
    }

    private static void drawNorthArrow(Color[] pixels) {
        drawVerticalLine(pixels, CENTER_PIXEL, 2, 16, NORTH_ARROW_COLOR);
        for (int offset = 0; offset <= 5; offset++) {
            setPixel(pixels, CENTER_PIXEL - offset, 7 + offset, NORTH_ARROW_COLOR);
            setPixel(pixels, CENTER_PIXEL + offset, 7 + offset, NORTH_ARROW_COLOR);
        }
        drawVerticalLine(pixels, 58, 20, 28, NORTH_ARROW_COLOR);
        drawVerticalLine(pixels, 69, 20, 28, NORTH_ARROW_COLOR);
        for (int offset = 0; offset <= 8; offset++) {
            setPixel(pixels, 59 + offset, 20 + offset, NORTH_ARROW_COLOR);
        }
    }

    private static void fillRect(Color[] pixels, int minX, int minY, int maxX, int maxY, Color color) {
        for (int y = minY; y <= maxY; y++) {
            for (int x = minX; x <= maxX; x++) {
                setPixel(pixels, x, y, color);
            }
        }
    }

    private static void drawRect(Color[] pixels, int minX, int minY, int maxX, int maxY, Color color) {
        drawHorizontalLine(pixels, minX, maxX, minY, color);
        drawHorizontalLine(pixels, minX, maxX, maxY, color);
        drawVerticalLine(pixels, minX, minY, maxY, color);
        drawVerticalLine(pixels, maxX, minY, maxY, color);
    }

    private static void drawHorizontalLine(Color[] pixels, int minX, int maxX, int y, Color color) {
        for (int x = minX; x <= maxX; x++) {
            setPixel(pixels, x, y, color);
        }
    }

    private static void drawVerticalLine(Color[] pixels, int x, int minY, int maxY, Color color) {
        for (int y = minY; y <= maxY; y++) {
            setPixel(pixels, x, y, color);
        }
    }

    private static void setCanvasPixel(MapCanvas canvas, int x, int y, Color color) {
        if (isCanvasPixel(x, y)) {
            canvas.setPixelColor(x, y, color);
        }
    }

    private static void setPixel(Color[] pixels, int x, int y, Color color) {
        if (isCanvasPixel(x, y)) {
            pixels[(y * MAP_SIZE) + x] = color;
        }
    }

    private static boolean isCanvasPixel(int x, int y) {
        return x >= 0 && x < MAP_SIZE && y >= 0 && y < MAP_SIZE;
    }

    private static int clamp(int value, int minimum, int maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }
}
