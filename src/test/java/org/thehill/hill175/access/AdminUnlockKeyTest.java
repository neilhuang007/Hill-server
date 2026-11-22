package org.thehill.hill175.access;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class AdminUnlockKeyTest {
    @TempDir Path directory;
    @Test void privateRandomKeySurvivesRestartAndOnlyItsDigestIsUsedForMatching() throws Exception {
        String hash = AdminUnlockKey.load(directory, null);
        String key = Files.readString(directory.resolve("admin-unlock-key.txt")).strip();
        assertEquals(43, key.length());
        assertNotEquals(key, hash);
        assertTrue(AdminUnlockKey.matches(key, hash));
        assertFalse(AdminUnlockKey.matches("wrong", hash));
        assertEquals(hash, AdminUnlockKey.load(directory, null));
    }
    @Test void suppliedDigestNeverCreatesAPlaintextKeyAndInvalidValuesFailClosed() throws Exception {
        String hash = "a".repeat(64);
        assertEquals(hash, AdminUnlockKey.load(directory, hash));
        assertFalse(Files.exists(directory.resolve("admin-unlock-key.txt")));
        assertThrows(java.io.IOException.class, () -> AdminUnlockKey.load(directory, "bad"));
    }
}
