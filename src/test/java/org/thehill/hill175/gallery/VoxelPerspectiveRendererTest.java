package org.thehill.hill175.gallery;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.CameraPose;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class VoxelPerspectiveRendererTest {
    @TempDir Path directory;

    @Test
    void generatesAnActualPerspectivePngFromBlocksAndSavedOrientation() throws IOException {
        Path south = directory.resolve("south.png");
        Path north = directory.resolve("north.png");
        VoxelPerspectiveRenderer.Scene scene = (x, y, z) -> z >= 8 && z <= 9 && x >= -6 && x <= 6 && y >= 0 && y <= 8
                ? 0xffc55232 : 0;
        VoxelPerspectiveRenderer renderer = new VoxelPerspectiveRenderer();
        renderer.render(scene, new CameraPose("test", 0.5, 4.5, 0.5, 0, 0), south);
        renderer.render(scene, new CameraPose("test", 0.5, 4.5, 0.5, 180, 0), north);

        BufferedImage wall = ImageIO.read(south.toFile());
        BufferedImage sky = ImageIO.read(north.toFile());
        assertEquals(VoxelPerspectiveRenderer.imageWidth, wall.getWidth());
        assertEquals(VoxelPerspectiveRenderer.imageHeight, wall.getHeight());
        int center = wall.getRGB(400, 225);
        assertTrue(((center >> 16) & 255) > (center & 255), "The saved south-facing view should show the red wall.");
        int empty = sky.getRGB(400, 225);
        assertTrue((empty & 255) > ((empty >> 16) & 255), "Turning north should show blue sky.");
        assertNotEquals(center, empty);
    }

    @Test
    void shutdownInterruptStopsTheRendererBeforeAnIncompleteImageCanBePublished() {
        Thread.currentThread().interrupt();
        try {
            assertThrows(IOException.class, () -> new VoxelPerspectiveRenderer().render((x, y, z) -> 0,
                    new CameraPose("test", 0, 5, 0, 0, 0), directory.resolve("interrupted.png")));
        } finally {
            Thread.interrupted();
        }
    }
}
