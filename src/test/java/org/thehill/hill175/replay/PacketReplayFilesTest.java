package org.thehill.hill175.replay;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class PacketReplayFilesTest {
    @TempDir Path directory;

    @Test void retentionIncludesAbandonedPendingButNeverActiveWrites() throws Exception {
        PacketReplayFiles store = new PacketReplayFiles(directory);
        Path oldFinal = store.reserve(UUID.randomUUID());
        Path oldPending = Path.of(store.reserve(UUID.randomUUID()) + ".pending");
        Path active = Path.of(store.reserve(UUID.randomUUID()) + ".pending");
        Path recent = store.reserve(UUID.randomUUID());
        long expired = System.currentTimeMillis() - PacketReplayFiles.MAX_AGE_MILLIS - 60_000;
        for (Path path : new Path[]{oldFinal, oldPending, active}) {
            Files.writeString(path, "private replay");
            Files.setLastModifiedTime(path, FileTime.fromMillis(expired));
        }
        Files.writeString(recent, "recent replay");
        store.beginWrite(active);
        store.prune();
        assertFalse(Files.exists(oldFinal));
        assertFalse(Files.exists(oldPending));
        assertTrue(Files.exists(active));
        assertTrue(Files.exists(recent));
        store.endWrite(active);
        store.prune();
        assertFalse(Files.exists(active));
    }

    @Test void attributionNeverUsesUntrustedNamesOrArbitraryPaths() throws Exception {
        PacketReplayFiles store = new PacketReplayFiles(directory);
        UUID player = UUID.randomUUID();
        Path file = store.reserve(player);
        assertTrue(file.getFileName().toString().matches("\\d{13}-" + player + "-[a-f0-9-]{36}\\.flashback"));
        store.event("SAVED", player, file, "detail\tforged\nrow");
        String index = Files.readString(directory.resolve("segments.tsv"));
        assertEquals(1, index.lines().count());
        assertTrue(index.contains(player.toString()));
        assertFalse(index.contains("\tforged\n"));
        assertThrows(java.io.IOException.class, () -> store.saved(directory.resolve("../elsewhere.flashback")));
    }
}
