package org.thehill.hill175.data;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.nio.file.Path;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.*;

class YamlEntryGalleryStateTest {
    @TempDir Path directory;

    @Test
    void preservesThePrivatePreviewCapabilityAndSelectedBuildingAcrossRestart() {
        YamlCompetitionStore store = new YamlCompetitionStore(directory.toFile(), Logger.getAnonymousLogger());
        Entry entry = new Entry(UUID.randomUUID(), Category.PLACE, Set.of("builder"), "private-place",
                new BuildRegion("private-place", 0, 0, 0, 20, 30, 20), 0);
        entry.selectedBuildingId("chapel");
        store.saveEntry(entry);

        Entry restored = new YamlCompetitionStore(directory.toFile(), Logger.getAnonymousLogger()).entry(entry.id()).orElseThrow();
        assertEquals("chapel", restored.selectedBuildingId());
        assertEquals(entry.previewToken(), restored.previewToken());
        assertTrue(restored.previewToken().matches("[A-Za-z0-9_-]{22,64}"));
        assertNotEquals(new Entry(UUID.randomUUID(), Category.PLACE, Set.of("builder"), "private-place",
                restored.region(), 0).previewToken(), restored.previewToken());
    }
}
