package org.thehill.hill175.gallery;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class GalleryHttpServerTest {
    @TempDir Path directory;
    private final HttpClient client = HttpClient.newHttpClient();

    @Test void draftImagesRequireThePrivateLinkAndDoNotExposeParticipantRecords() throws Exception {
        Entry entry = entry();
        EntryGalleryPublisher publisher = publisher(entry);
        try (var server = server(publisher)) {
            assertEquals("{\"entries\":[]}", get(server, "/api/entries").body());
            assertEquals(404, get(server, "/api/entries/" + entry.id()).statusCode());
            assertEquals(404, get(server, imagePath(entry)).statusCode());
            assertEquals(404, get(server, imagePath(entry) + "?token=" + "x".repeat(32)).statusCode());
            var preview = get(server, "/api/preview/" + entry.previewToken());
            assertEquals(200, preview.statusCode());
            assertTrue(preview.body().contains("?token=" + entry.previewToken()));
            assertFalse(preview.body().contains("private-participant"));
            assertFalse(preview.body().contains("private-world"));
            assertEquals(200, get(server, imagePath(entry) + "?token=" + entry.previewToken()).statusCode());
            assertEquals(200, get(server, imagePath(entry) + "?version=" + "a".repeat(64) + "&token=" + entry.previewToken()).statusCode());
            assertEquals(404, get(server, imagePath(entry) + "?version=" + "a".repeat(64)).statusCode());
            assertEquals(404, get(server, imagePath(entry) + "?token=" + entry.previewToken() + "&version=invalid").statusCode());
            assertEquals(404, get(server, imagePath(entry) + "?token=" + entry.previewToken() + "&token=" + entry.previewToken()).statusCode());
        }
    }

    @Test void publicationAndWithdrawalTakeEffectOnEveryRequest() throws Exception {
        Entry entry = entry();
        EntryGalleryPublisher publisher = publisher(entry);
        try (var server = server(publisher)) {
            entry.submit(Instant.now());
            publisher.update(entry);
            assertEquals(200, get(server, "/api/entries/" + entry.id()).statusCode());
            assertEquals(200, get(server, imagePath(entry)).statusCode());
            assertEquals(200, get(server, imagePath(entry) + "?version=" + "a".repeat(64)).statusCode());
            assertTrue(get(server, "/api/entries").body().contains(entry.id().toString()));
            entry.clearSubmission();
            publisher.update(entry);
            assertEquals(404, get(server, "/api/entries/" + entry.id()).statusCode());
            assertEquals(404, get(server, imagePath(entry)).statusCode());
            publisher.remove(entry.id());
            assertEquals(404, get(server, "/api/preview/" + entry.previewToken()).statusCode());
            assertEquals(404, get(server, imagePath(entry) + "?token=" + entry.previewToken()).statusCode());
        }
    }

    @Test void onlyKnownRoutesAndBoundedWhitelistedAssetsAreReachable() throws Exception {
        EntryGalleryPublisher publisher = publisher(entry());
        Files.writeString(directory.resolve("assets/credentials.txt"), "never serve this");
        Files.write(directory.resolve("assets/stone.png"), new byte[512 * 1024 + 1]);
        try (var server = server(publisher)) {
            for (String path : List.of("/assets/credentials.txt", "/assets/stone.png", "/assets/../credentials.txt",
                    "/assets/%2e%2e/credentials.txt", "/api/entries/../../credentials.txt", "/gallery.js?token=guess",
                    "/api/entries?token=guess", "/entries/unknown", "/preview/short")) {
                assertEquals(404, get(server, path).statusCode(), path);
            }
            assertEquals(200, get(server, "/").statusCode());
            assertEquals(200, get(server, "/gallery.js").statusCode());
            assertEquals(200, get(server, "/health").statusCode());
        }
    }

    @Test void browserResponsesPreventCachingAndTokenReferrersAndRejectMutations() throws Exception {
        try (var server = server(publisher(entry()))) {
            var response = get(server, "/");
            assertEquals("no-store, max-age=0", response.headers().firstValue("Cache-Control").orElseThrow());
            assertEquals("no-referrer", response.headers().firstValue("Referrer-Policy").orElseThrow());
            assertTrue(response.headers().firstValue("Content-Security-Policy").orElseThrow().contains("frame-ancestors 'none'"));
            assertEquals("nosniff", response.headers().firstValue("X-Content-Type-Options").orElseThrow());
            var head = request(server, "/", "HEAD");
            assertEquals(200, head.statusCode());
            assertTrue(head.body().isEmpty());
            var post = request(server, "/api/entries", "POST");
            assertEquals(405, post.statusCode());
            assertEquals("GET, HEAD", post.headers().firstValue("Allow").orElseThrow());
        }
    }

    @Test void onlyThePreparedBrowserFontIsServedWithTheCorrectMimeAndSizeBound() throws Exception {
        var publisher = publisher(entry());
        Path font = directory.resolve("assets/minecraft.woff2");
        Files.write(font, new byte[]{119, 79, 70, 50});
        try (var server = server(publisher)) {
            var response = get(server, "/assets/minecraft.woff2");
            assertEquals(200, response.statusCode());
            assertEquals("font/woff2", response.headers().firstValue("Content-Type").orElseThrow());
            assertEquals(404, get(server, "/assets/other.woff2").statusCode());
            Files.write(font, new byte[512 * 1024 + 1]);
            assertEquals(404, get(server, "/assets/minecraft.woff2").statusCode());
        }
    }

    private Entry entry() {
        var entry = new Entry(UUID.randomUUID(), Category.JOURNEY, Set.of("private-participant"), "private-world",
                new BuildRegion("private-world", 0, 0, 0, 64, 64, 64), 0);
        entry.title("A submitted build");
        entry.setCameraPose(1, new CameraPose("private-world", 2, 3, 4, 90, 10));
        return entry;
    }

    private EntryGalleryPublisher publisher(Entry entry) throws Exception {
        Files.createDirectories(directory.resolve("assets"));
        var publisher = new EntryGalleryPublisher(directory.resolve("gallery"), List.of(entry));
        Path capture = publisher.createRenderFile();
        Files.write(capture, new byte[]{(byte) 137, 80, 78, 71});
        publisher.acceptImage(entry, 1, entry.cameraPose(1).orElseThrow(), capture);
        return publisher;
    }

    private GalleryHttpServer server(EntryGalleryPublisher publisher) throws Exception {
        var server = new GalleryHttpServer(0, publisher, directory.resolve("assets"));
        server.start();
        return server;
    }

    private String imagePath(Entry entry) { return "/api/entries/" + entry.id() + "/images/1"; }

    private HttpResponse<String> get(GalleryHttpServer server, String path) throws Exception {
        return request(server, path, "GET");
    }

    private HttpResponse<String> request(GalleryHttpServer server, String path, String method) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + server.port() + path))
                .method(method, HttpRequest.BodyPublishers.noBody()).build(), HttpResponse.BodyHandlers.ofString());
    }
}
