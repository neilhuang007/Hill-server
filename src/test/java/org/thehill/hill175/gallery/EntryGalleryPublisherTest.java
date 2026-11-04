package org.thehill.hill175.gallery;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class EntryGalleryPublisherTest {
    @TempDir Path directory;

    @Test
    void draftRequiresItsOwnCapabilityAndNeverExportsParticipantOrCameraData() throws IOException {
        Entry entry = entry();
        Entry other = entry();
        EntryGalleryPublisher publisher = new EntryGalleryPublisher(directory, List.of(entry, other));
        acceptImage(publisher, entry, 1);

        assertEquals("{\"entries\":[]}", publisher.publicIndexJson());
        assertTrue(publisher.entryManifest(entry.id()).isEmpty());
        assertTrue(publisher.image(entry.id(), 1, null).isEmpty());
        assertTrue(publisher.image(entry.id(), 1, other.previewToken()).isEmpty());
        assertTrue(publisher.image(entry.id(), 1, "../../captures.properties").isEmpty());
        String preview = publisher.previewManifest(entry.previewToken()).orElseThrow();
        assertTrue(preview.contains("?token=" + entry.previewToken()));
        assertFalse(preview.contains("private-school-participant"));
        assertFalse(preview.contains("secret_world"));
        assertFalse(preview.contains("yaw"));
        assertTrue(publisher.image(entry.id(), 1, entry.previewToken()).isPresent());
    }

    @Test
    void publicationRequiresEverySavedImageAndUnlockImmediatelyRevokesPublicAccess() throws IOException {
        Entry entry = entry();
        entry.setCameraPose(3, new CameraPose(entry.worldName(), 6, 5, 6, 30, 0));
        EntryGalleryPublisher publisher = new EntryGalleryPublisher(directory, List.of(entry));
        entry.submit(Instant.parse("2026-10-15T15:00:00Z"));
        acceptImage(publisher, entry, 1);
        assertTrue(publisher.entryManifest(entry.id()).isEmpty());
        acceptImage(publisher, entry, 3);
        assertTrue(publisher.entryManifest(entry.id()).isPresent());
        assertTrue(publisher.image(entry.id(), 1, null).isPresent());
        assertFalse(publisher.publicIndexJson().contains(entry.previewToken()));

        entry.clearSubmission();
        publisher.update(entry);
        assertEquals("{\"entries\":[]}", publisher.publicIndexJson());
        assertTrue(publisher.entryManifest(entry.id()).isEmpty());
        assertTrue(publisher.image(entry.id(), 1, null).isEmpty());
        assertTrue(publisher.image(entry.id(), 1, entry.previewToken()).isPresent());
    }

    @Test
    void restartRestoresOnlyImagesForTheCurrentCameraAndRejectsAStaleCompletion() throws IOException {
        Entry entry = entry();
        EntryGalleryPublisher publisher = new EntryGalleryPublisher(directory, List.of(entry));
        CameraPose oldPose = entry.cameraPose(1).orElseThrow();
        acceptImage(publisher, entry, 1);
        EntryGalleryPublisher restarted = new EntryGalleryPublisher(directory, List.of(entry));
        assertTrue(restarted.hasImage(entry, 1));

        entry.setCameraPose(1, new CameraPose(entry.worldName(), 8, 5, 8, 60, 0));
        publisher.update(entry);
        Path stale = publisher.createRenderFile();
        Files.write(stale, new byte[]{1, 2, 3});
        assertThrows(IOException.class, () -> publisher.acceptImage(entry, 1, oldPose, stale));
        assertFalse(publisher.hasImage(entry, 1));
        assertFalse(new EntryGalleryPublisher(directory, List.of(entry)).hasImage(entry, 1));
    }

    @Test
    void invalidationAndDeletionPersistAndRevokeOldLinks() throws IOException {
        Entry entry = entry();
        EntryGalleryPublisher publisher = new EntryGalleryPublisher(directory, List.of(entry));
        acceptImage(publisher, entry, 1);
        publisher.invalidateImage(entry, 1);
        assertTrue(publisher.image(entry.id(), 1, entry.previewToken()).isEmpty());
        assertFalse(new EntryGalleryPublisher(directory, List.of(entry)).hasImage(entry, 1));
        acceptImage(publisher, entry, 1);
        publisher.remove(entry.id());
        assertTrue(publisher.previewManifest(entry.previewToken()).isEmpty());
        assertTrue(publisher.image(entry.id(), 1, entry.previewToken()).isEmpty());
    }

    @Test
    void metadataEscapesQuotesAndControlCharacters() throws IOException {
        Entry entry = entry();
        entry.title("A \"window\"\nwith a slash \\");
        EntryGalleryPublisher publisher = new EntryGalleryPublisher(directory, List.of(entry));
        String preview = publisher.previewManifest(entry.previewToken()).orElseThrow();
        assertTrue(preview.contains("A \\\"window\\\"\\nwith a slash \\\\"));
        assertFalse(preview.contains("\n"));
    }

    @Test
    void sameCameraGetsANewRevisionWhenItsWorldImageChangesAndKeepsItAfterRestart() throws IOException {
        Entry entry = entry();
        EntryGalleryPublisher publisher = new EntryGalleryPublisher(directory, List.of(entry));
        acceptImage(publisher, entry, 1);
        String before = publisher.previewManifest(entry.previewToken()).orElseThrow();
        Path updated = publisher.createRenderFile();
        Files.write(updated, new byte[]{(byte)137, 80, 78, 71, 5});
        publisher.acceptImage(entry, 1, entry.cameraPose(1).orElseThrow(), updated);
        String after = publisher.previewManifest(entry.previewToken()).orElseThrow();
        assertNotEquals(before, after);
        assertEquals(after, new EntryGalleryPublisher(directory, List.of(entry))
                .previewManifest(entry.previewToken()).orElseThrow());
    }

    private static void acceptImage(EntryGalleryPublisher publisher, Entry entry, int slot) throws IOException {
        Path image = publisher.createRenderFile();
        Files.write(image, new byte[]{(byte) 137, 80, 78, 71});
        publisher.acceptImage(entry, slot, entry.cameraPose(slot).orElseThrow(), image);
    }

    private static Entry entry() {
        Entry entry = new Entry(UUID.randomUUID(), Category.JOURNEY, Set.of("private-school-participant"),
                "secret_world", new BuildRegion("secret_world", -32, 0, -32, 32, 50, 32), 0);
        entry.setCameraPose(1, new CameraPose(entry.worldName(), 4, 5, 4, 0, 0));
        return entry;
    }
}
