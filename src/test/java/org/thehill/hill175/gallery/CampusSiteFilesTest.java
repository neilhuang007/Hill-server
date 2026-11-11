package org.thehill.hill175.gallery;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class CampusSiteFilesTest {
    @TempDir Path root;

    @Test void renderedMapCanBeReusedButLiveDataAndDownloadsStayPrivate() throws Exception {
        Path site = root.resolve("site");
        Path tile = site.resolve("map/maps/campus/tiles/0/x0/z0.prbm.gz");
        Files.createDirectories(tile.getParent());
        Files.createDirectories(site.resolve("map/maps/campus/live"));
        Files.writeString(tile, "rendered tile");
        Files.writeString(site.resolve("map/settings.json"), "{}");
        Files.writeString(site.resolve("map/maps/campus/live/players.json"), "[]");
        var publisher = new EntryGalleryPublisher(root.resolve("gallery"), List.of());
        try (var server = new GalleryHttpServer(0, publisher, root.resolve("assets"), site)) {
            server.start();
            var client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:" + server.port();
            URI uri = URI.create(base + "/map/maps/campus/tiles/0/x0/z0.prbm.gz");
            var first = client.send(HttpRequest.newBuilder(uri).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(200, first.statusCode());
            assertEquals("public, max-age=3600", first.headers().firstValue("Cache-Control").orElseThrow());
            assertTrue(first.headers().firstValue("Pragma").isEmpty());
            String etag = first.headers().firstValue("ETag").orElseThrow();
            var cached = client.send(HttpRequest.newBuilder(uri).header("If-None-Match", etag).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(304, cached.statusCode());
            assertEquals("", cached.body());
            Files.writeString(tile, "updated rendered tile");
            var changed = client.send(HttpRequest.newBuilder(uri).header("If-None-Match", etag).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(200, changed.statusCode());
            assertEquals("updated rendered tile", changed.body());
            assertNotEquals(etag, changed.headers().firstValue("ETag").orElseThrow());
            var settings = client.send(HttpRequest.newBuilder(URI.create(base + "/map/settings.json")).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals("public, no-cache", settings.headers().firstValue("Cache-Control").orElseThrow());
            for (String path : List.of("/map/maps/campus/live/players.json", "/download/", "/downloads/hill-campus.zip")) {
                var privateResponse = client.send(HttpRequest.newBuilder(URI.create(base + path)).build(), HttpResponse.BodyHandlers.ofString());
                assertTrue(privateResponse.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"), path);
                assertTrue(privateResponse.headers().firstValue("ETag").isEmpty(), path);
            }
        }
    }

    @Test void publicExportRoutesCannotReachWorldsCredentialsOrProvenance() throws Exception {
        Path site = root.resolve("site");
        Files.createDirectories(site.resolve("downloads"));
        Files.createDirectories(site.resolve("map/assets"));
        Files.createDirectories(site.resolve("map/lang"));
        Files.createDirectories(site.resolve("snapshot"));
        Files.writeString(site.resolve("downloads/hill-campus.zip"), "prepared world archive");
        Files.writeString(site.resolve("map/index.html"), "campus map");
        Files.writeString(site.resolve("map/assets/app.js"), "map script");
        Files.writeString(site.resolve("map/lang/en.conf"), "map language");
        Files.writeString(site.resolve("map/private.conf"), "not a public language file");
        Files.writeString(site.resolve("map/sql.php"), "never execute or expose");
        Files.writeString(site.resolve("provenance.json"), "private source paths");
        Files.writeString(site.resolve("snapshot/level.dat"), "world settings");
        var publisher = new EntryGalleryPublisher(root.resolve("gallery"), List.of());
        try (var server = new GalleryHttpServer(0, publisher, root.resolve("assets"), site)) {
            server.start();
            var client = HttpClient.newHttpClient();
            String base = "http://127.0.0.1:" + server.port();
            for (String route : List.of("/provenance.json", "/snapshot/level.dat", "/map/sql.php",
                    "/map/../provenance.json", "/map/%2e%2e/provenance.json", "/downloads/other.zip", "/map/private.conf")) {
                assertEquals(404, client.send(HttpRequest.newBuilder(URI.create(base + route)).build(), HttpResponse.BodyHandlers.ofString()).statusCode(), route);
            }
            var download = client.send(HttpRequest.newBuilder(URI.create(base + "/downloads/hill-campus.zip")).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(303, download.statusCode());
            assertEquals("/download/", download.headers().firstValue("Location").orElseThrow());
            assertFalse(download.body().contains("prepared world archive"));
            var head = client.send(HttpRequest.newBuilder(URI.create(base + "/downloads/hill-campus.zip")).method("HEAD", HttpRequest.BodyPublishers.noBody()).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(303, head.statusCode());
            assertTrue(head.headers().firstValue("Content-Length").isEmpty());
            assertEquals("", head.body());
            var map = client.send(HttpRequest.newBuilder(URI.create(base + "/map/")).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals("campus map", map.body());
            assertEquals("SAMEORIGIN", map.headers().firstValue("X-Frame-Options").orElseThrow());
            assertTrue(map.headers().firstValue("Content-Security-Policy").orElseThrow().contains("'unsafe-eval'"));
            var language = client.send(HttpRequest.newBuilder(URI.create(base + "/map/lang/en.conf")).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals("map language", language.body());
            var home = client.send(HttpRequest.newBuilder(URI.create(base + "/")).build(), HttpResponse.BodyHandlers.ofString());
            assertTrue(home.body().contains("Hill 175th Anniversary"));
            assertFalse(home.body().contains("THE EXHIBITION"));
            assertFalse(home.headers().firstValue("Content-Security-Policy").orElseThrow().contains("'unsafe-eval'"));
            var legacy = client.send(HttpRequest.newBuilder(URI.create(base + "/gallery")).build(), HttpResponse.BodyHandlers.ofString());
            assertTrue(legacy.body().contains("Build gallery"));
        }
    }
}
