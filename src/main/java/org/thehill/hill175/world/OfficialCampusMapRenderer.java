package org.thehill.hill175.world;

import org.bukkit.entity.Player;
import org.bukkit.map.MapCanvas;
import org.bukkit.map.MapCursorCollection;
import org.bukkit.map.MapRenderer;
import org.bukkit.map.MapView;

import java.awt.image.BufferedImage;
import java.util.Objects;

/** Static official artwork. Its oblique perspective cannot locate a player accurately. */
public final class OfficialCampusMapRenderer extends MapRenderer {
    private static final int mapSize = 128;
    private final BufferedImage image;
    private MapCanvas renderedCanvas;

    public OfficialCampusMapRenderer(BufferedImage image) {
        super(false);
        Objects.requireNonNull(image, "Official campus artwork is required.");
        if (image.getWidth() != mapSize || image.getHeight() != mapSize) {
            throw new IllegalArgumentException("The official held map must be exactly 128 by 128 pixels.");
        }
        this.image = new BufferedImage(mapSize, mapSize, BufferedImage.TYPE_INT_ARGB);
        this.image.setRGB(0, 0, mapSize, mapSize, image.getRGB(0, 0, mapSize, mapSize, null, 0, mapSize), 0, mapSize);
    }

    @Override
    public void render(MapView view, MapCanvas canvas, Player player) {
        if (canvas == renderedCanvas) return;
        canvas.drawImage(0, 0, image);
        canvas.setCursors(new MapCursorCollection());
        renderedCanvas = canvas;
    }
}
