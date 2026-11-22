package org.thehill.hill175.replay;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IncidentStoreTest {
    @TempDir Path directory;
    private static final UUID ACTOR = UUID.fromString("64c2e6fa-31d5-4819-97ef-e525139dd247");
    private static final UUID WORLD = UUID.fromString("1ac8893e-e808-4ac3-ac6e-c0c952f05bba");

    @Test void roundTripsSafeTextAndFiltersExactActor() {
        IncidentRecord record = new IncidentRecord(Instant.parse("2026-10-20T10:00:00Z").toEpochMilli(), ACTOR,
                "Student.Name", IncidentRecord.Kind.PLACE, WORLD, "Hill Campus", -10, 64, 24, "sign=Hi, world");
        assertEquals(record, IncidentRecord.parse(record.serialize()));
        assertTrue(record.matches(record.time(), "student.name"));
        assertTrue(record.matches(record.time(), ACTOR.toString()));
        assertFalse(record.matches(record.time() + 1, "Student.Name"));
        assertFalse(record.matches(record.time(), "Student"));
        assertThrows(IllegalArgumentException.class, () -> IncidentRecord.parse("1\tgarbage"));
        assertThrows(IllegalArgumentException.class, () -> IncidentRecord.parse("x".repeat(2049)));
    }

    @Test void keepsNewestMatchingRecordsAcrossSegments() throws Exception {
        long now = System.currentTimeMillis();
        IncidentRecord old = new IncidentRecord(now - 30_000, ACTOR, "Student", IncidentRecord.Kind.BREAK,
                WORLD, "campus", 1, 2, 3, "STONE");
        IncidentRecord mid = new IncidentRecord(now - 20_000, ACTOR, "Student", IncidentRecord.Kind.PLACE,
                WORLD, "campus", 4, 5, 6, "DIRT");
        IncidentRecord latest = new IncidentRecord(now - 10_000, ACTOR, "Student", IncidentRecord.Kind.POSITION,
                WORLD, "campus", 7, 8, 9, "sample");
        String day = java.time.LocalDate.now(java.time.ZoneOffset.UTC).toString();
        Files.writeString(directory.resolve("incident-" + day + "-00000.log"), old.serialize() + "\n" + mid.serialize() + "\n",
                StandardCharsets.UTF_8);
        Files.writeString(directory.resolve("incident-" + day + "-00001.log"), "malformed\n" + latest.serialize() + "\n",
                StandardCharsets.UTF_8);
        try (IncidentStore store = new IncidentStore(directory, Logger.getAnonymousLogger())) {
            IncidentStore.Result result = store.query(now - 60_000, ACTOR.toString(), 2);
            assertEquals(java.util.List.of(mid, latest), result.records());
            assertFalse(result.partial());
            assertEquals(java.util.List.of(), store.query(now - 60_000, "someone-else", 2).records());
        }
    }
}
