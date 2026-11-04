package org.thehill.hill175.world;

import org.bukkit.map.MapCanvas;
import org.bukkit.map.MapCursorCollection;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.awt.Image;
import java.awt.image.BufferedImage;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class OfficialCampusMapRendererTest {
    @Test
    void rejectsMissingOrIncorrectlySizedArtwork() {
        assertThrows(NullPointerException.class, () -> new OfficialCampusMapRenderer(null));
        assertThrows(IllegalArgumentException.class,
                () -> new OfficialCampusMapRenderer(new BufferedImage(128, 64, BufferedImage.TYPE_INT_RGB)));
    }

    @Test
    void rendersImmutableOfficialPixelsWithoutAnInaccurateWorldCursor() {
        BufferedImage source = new BufferedImage(128, 128, BufferedImage.TYPE_INT_RGB);
        source.setRGB(32, 48, 0xff135790);
        var renderer = new OfficialCampusMapRenderer(source);
        source.setRGB(32, 48, 0xff000000);
        MapCanvas canvas = mock(MapCanvas.class);
        renderer.render(null, canvas, null);
        var pixels = ArgumentCaptor.forClass(Image.class);
        verify(canvas).drawImage(eq(0), eq(0), pixels.capture());
        assertEquals(0xff135790, ((BufferedImage) pixels.getValue()).getRGB(32, 48));
        var cursors = ArgumentCaptor.forClass(MapCursorCollection.class);
        verify(canvas).setCursors(cursors.capture());
        assertEquals(0, cursors.getValue().size());
        assertFalse(renderer.isContextual());
    }

    @Test
    void reusesTheStaticCanvasAndRendersAReplacementCanvas() {
        var renderer = new OfficialCampusMapRenderer(new BufferedImage(128, 128, BufferedImage.TYPE_INT_RGB));
        MapCanvas original = mock(MapCanvas.class);
        MapCanvas replacement = mock(MapCanvas.class);
        renderer.render(null, original, null);
        renderer.render(null, original, null);
        renderer.render(null, replacement, null);
        verify(original, times(1)).drawImage(eq(0), eq(0), any(Image.class));
        verify(original, times(1)).setCursors(any(MapCursorCollection.class));
        verify(replacement, times(1)).drawImage(eq(0), eq(0), any(Image.class));
    }
}
