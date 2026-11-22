package org.thehill.hill175.download;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.entity.Player;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.DataOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;
import java.util.zip.ZipFile;

import static org.mockito.Mockito.*;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.*;

class StudentMapDownloadTest {
    @TempDir Path temp;
    private static final Instant START = Instant.parse("2026-10-01T12:00:00Z");

    @Test void ticketsExpireAtFifteenMinutesAndAuditCannotBeUsedAsBearer() throws Exception {
        Path file = temp.resolve("fingerprints.tsv");
        MapDownloadTickets store = new MapDownloadTickets(file);
        UUID player = UUID.randomUUID();
        var first = store.issue(player, START);
        assertTrue(first.fresh());
        assertEquals(first.ticket(), store.issue(player, START.plusSeconds(30)).ticket());
        assertNotNull(store.lookup(first.ticket().token(), START.plusSeconds(899)));
        assertNull(store.lookup(first.ticket().token(), START.plusSeconds(900)));
        assertTrue(store.issue(player, START.plusSeconds(900)).fresh());
        assertTrue(store.issue(player, START.plusSeconds(1800)).fresh());
        assertThrows(IllegalStateException.class, () -> store.issue(player, START.plusSeconds(2700)));
        assertTrue(store.issue(player, START.plusSeconds(3600)).fresh());
        String audit = Files.readString(file);
        assertTrue(audit.contains(player.toString()));
        assertTrue(audit.contains(first.ticket().fingerprint()));
        assertFalse(audit.contains(first.ticket().token()));
    }

    @Test void preparedExportIncludesOpaqueMarkerAndRejectsPrivateFilesSymlinksAndPlayerNbt() throws Exception {
        Path source = temp.resolve("prepared");
        Files.createDirectories(source.resolve("region"));
        levelDat(source, false);
        Files.writeString(source.resolve("region/r.0.0.mca"), "sample");
        Path output = temp.resolve("copy.zip");
        String fingerprint = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
        String mapDigest = new PreparedWorldArchive(source).build(output, fingerprint);
        assertTrue(mapDigest.matches("[0-9a-f]{64}"));
        try (ZipFile zip = new ZipFile(output.toFile())) {
            assertTrue(zip.getComment().contains(mapDigest));
            assertTrue(zip.getComment().contains(fingerprint));
            assertNotNull(zip.getEntry("world/level.dat"));
            assertNotNull(zip.getEntry("world/region/r.0.0.mca"));
            assertTrue(new String(zip.getInputStream(zip.getEntry("world/.hill175-copy.txt")).readAllBytes()).contains(fingerprint));
            assertFalse(zip.stream().anyMatch(entry -> entry.getName().contains("playerdata")));
        }
        Files.writeString(source.resolve("region/r.0.0.mca"), "sample2");
        assertNotEquals(mapDigest, new PreparedWorldArchive(source).build(output, fingerprint));
        Files.createDirectories(source.resolve("playerdata"));
        Files.writeString(source.resolve("playerdata/uuid.dat"), "secret");
        assertThrows(IOException.class, () -> new PreparedWorldArchive(source).build(output, fingerprint));
        Files.delete(source.resolve("playerdata/uuid.dat"));
        Files.delete(source.resolve("playerdata"));
        levelDat(source, true);
        assertThrows(IOException.class, () -> new PreparedWorldArchive(source).build(output, fingerprint));
        levelDat(source, false);
        Path outside = temp.resolve("outside");
        Files.writeString(outside, "secret");
        try {
            Files.createSymbolicLink(source.resolve("region/leak"), outside);
            assertThrows(IOException.class, () -> new PreparedWorldArchive(source).build(output, fingerprint));
        } catch (UnsupportedOperationException | java.nio.file.FileSystemException ignored) { }
    }

    @Test void anonymousAndMalformedRequestsCannotGetMap() throws Exception {
        Path source = temp.resolve("export");
        Files.createDirectories(source);
        levelDat(source, false);
        Path state = temp.resolve("state");
        Files.createDirectories(state);
        Path stale = state.resolve("prepared-map-orphan.zip");
        Path unrelated = state.resolve("retain.txt");
        Files.writeString(stale, "stale archive");
        Files.writeString(unrelated, "unrelated file");
        try (StudentMapDownloadService service = new StudentMapDownloadService(source, state,
                URI.create("https://downloads.example.test/student-map/"), 0, Player::isOnline)) {
            service.start();
            assertFalse(Files.exists(stale));
            assertTrue(Files.exists(unrelated));
            HttpClient client = HttpClient.newHttpClient();
            URI base = URI.create("http://127.0.0.1:" + service.port() + "/student-map/");
            for (String path : new String[]{"", "not-a-token", "%2f", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/archive?x=1"}) {
                var request = HttpRequest.newBuilder(base.resolve(path)).GET().build();
                var response = client.send(request, HttpResponse.BodyHandlers.ofString());
                assertEquals(404, response.statusCode());
                assertEquals("no-store, max-age=0", response.headers().firstValue("cache-control").orElseThrow());
            }
            var response = client.send(HttpRequest.newBuilder(base).POST(HttpRequest.BodyPublishers.noBody()).build(),
                    HttpResponse.BodyHandlers.ofString());
            assertEquals(405, response.statusCode());
        }
        assertThrows(IllegalArgumentException.class, () -> new StudentMapDownloadService(source, temp.resolve("state"),
                URI.create("http://downloads.example.test/student-map/"), 8791, player -> true));
    }

    @Test void successfulArchiveTransferRecordsMapDigestAndActualServerBytesWithoutBearer() throws Exception {
        Path source = temp.resolve("approved");
        Files.createDirectories(source.resolve("region"));
        levelDat(source, false);
        Files.writeString(source.resolve("region/r.0.0.mca"), "approved-blocks");
        Path state = temp.resolve("state");
        UUID uuid = UUID.randomUUID();
        Player player = mock(Player.class);
        when(player.getUniqueId()).thenReturn(uuid);
        try (StudentMapDownloadService service = new StudentMapDownloadService(source, state,
                URI.create("https://downloads.example.test/student-map/"), 0, ignored -> true)) {
            service.start();
            service.onCommand(player, null, "download", new String[0]);
            ArgumentCaptor<Component> issued = ArgumentCaptor.forClass(Component.class);
            verify(player).sendMessage(issued.capture());
            String text = PlainTextComponentSerializer.plainText().serialize(issued.getValue());
            String token = text.substring(text.lastIndexOf('/') + 1);
            assertEquals(43, token.length());
            URI base = URI.create("http://127.0.0.1:" + service.port() + "/student-map/");
            HttpClient client = HttpClient.newHttpClient();
            URI archive = base.resolve(token + "/archive");
            HttpResponse<byte[]> response = null;
            for (int attempt = 0; attempt < 100; attempt++) {
                response = client.send(HttpRequest.newBuilder(archive).GET().build(), HttpResponse.BodyHandlers.ofByteArray());
                if (response.statusCode() == 200) break;
                assertEquals(503, response.statusCode());
                Thread.sleep(20);
            }
            assertNotNull(response);
            assertEquals(200, response.statusCode());
            assertTrue(response.body().length > 0);
            assertEquals("no-store, max-age=0", response.headers().firstValue("cache-control").orElseThrow());
            String audit = Files.readString(state.resolve("transfers.tsv"));
            for (int attempt = 0; attempt < 100 && !audit.contains("\tCOMPLETED\t"); attempt++) {
                Thread.sleep(10);
                audit = Files.readString(state.resolve("transfers.tsv"));
            }
            String fingerprint = Files.readString(state.resolve("fingerprints.tsv")).trim().split("\\t")[2];
            assertTrue(audit.contains("\tISSUED\t" + uuid + "\t" + fingerprint + "\tPENDING\t0"));
            assertTrue(audit.contains("\tREADY\t" + uuid + "\t" + fingerprint));
            assertTrue(audit.contains("\tSTARTED\t" + uuid + "\t" + fingerprint));
            assertTrue(audit.matches("(?s).*\\tCOMPLETED\\t" + uuid + "\\t" + fingerprint
                    + "\\t[0-9a-f]{64}\\t" + response.body().length + "\\n.*"));
            assertFalse(audit.contains(token));
            assertFalse(Files.readString(state.resolve("fingerprints.tsv")).contains(token));
        }
    }

    @Test void auditCapacityReservesRoomForAnActiveTransferOutcome() throws Exception {
        Path file = temp.resolve("reserved-audit.tsv");
        MapDownloadAudit audit = new MapDownloadAudit(file, 1024);
        UUID player = UUID.randomUUID();
        String fingerprint = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
        String digest = "a".repeat(64);
        audit.append(START, "STARTED", player, fingerprint, digest, 0);
        boolean full = false;
        for (int attempt = 0; attempt < 10; attempt++) {
            try { audit.append(START, "READY", player, fingerprint, digest, 0); }
            catch (IOException expected) { full = true; break; }
        }
        assertTrue(full);
        audit.append(START, "COMPLETED", player, fingerprint, digest, 1234);
        assertTrue(Files.readString(file).contains("\tCOMPLETED\t"));
        assertTrue(Files.size(file) <= 1024);
    }

    @Test void auditFailureDoesNotExposeAWorkingLink() throws Exception {
        Path source = temp.resolve("approved");
        Files.createDirectories(source);
        levelDat(source, false);
        Path state = temp.resolve("state");
        Files.createDirectories(state);
        Path outside = temp.resolve("not-an-audit");
        Files.writeString(outside, "private");
        try {
            Files.createSymbolicLink(state.resolve("transfers.tsv"), outside);
        } catch (UnsupportedOperationException | java.nio.file.FileSystemException ignored) { return; }
        Player player = mock(Player.class);
        when(player.getUniqueId()).thenReturn(UUID.randomUUID());
        try (StudentMapDownloadService service = new StudentMapDownloadService(source, state,
                URI.create("https://downloads.example.test/student-map/"), 0, ignored -> true)) {
            service.start();
            service.onCommand(player, null, "download", new String[0]);
            verify(player, never()).sendMessage(any(Component.class));
            assertEquals("private", Files.readString(outside));
        }
    }

    private void levelDat(Path source, boolean includePlayer) throws IOException {
        try (DataOutputStream output = new DataOutputStream(Files.newOutputStream(source.resolve("level.dat")))) {
            output.writeByte(10);
            output.writeShort(0);
            if (includePlayer) {
                output.writeByte(10);
                output.writeShort(6);
                output.writeBytes("Player");
                output.writeByte(0);
            }
            output.writeByte(0);
        }
    }
}
