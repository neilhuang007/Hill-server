package org.thehill.hill175.gallery;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.ui.CampusMapPack;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class GalleryCampusPackTest {
    @TempDir Path directory;
    private final HttpClient client = HttpClient.newHttpClient();

    @Test void onlyFixedPackAndImageRoutesAreServedAndShaMatchesExactly() throws Exception {
        Path assets = Files.createDirectories(directory.resolve("assets"));
        byte[] zip = {80, 75, 3, 4, 1, 2};
        Files.write(assets.resolve("campus-pack.zip"), zip);
        Files.write(assets.resolve("campus-map.png"), new byte[]{(byte)137, 80, 78, 71});
        Files.writeString(assets.resolve("campus-map-source.json"), "private provenance");
        var publisher = new EntryGalleryPublisher(directory.resolve("gallery"), List.of());
        try (var server = new GalleryHttpServer(0, publisher, assets)) {
            server.start();
            String base = "http://127.0.0.1:" + server.port();
            var pack = new CampusMapPack(assets, base);
            var response = get(base + "/campus-pack.zip");
            assertEquals(200, response.statusCode());
            assertEquals("application/zip", response.headers().firstValue("Content-Type").orElseThrow());
            assertArrayEquals(zip, response.body());
            assertEquals(pack.sha1Hex(), HexFormat.of().formatHex(MessageDigest.getInstance("SHA-1").digest(response.body())));
            assertEquals("image/png", get(base + "/campus-map.png").headers().firstValue("Content-Type").orElseThrow());
            for (String path : List.of("/campus-map-source.json", "/campus-pack.zip?file=secret", "/campus-pack.zip/../secret", "/%63ampus-pack.zip")) {
                assertEquals(404, get(base + path).statusCode());
            }
        }
    }

    @Test void oversizedFilesAndInsecurePublicAddressesAreRejected() throws Exception {
        Path assets = Files.createDirectories(directory.resolve("assets"));
        Files.write(assets.resolve("campus-pack.zip"), new byte[8 * 1024 * 1024 + 1]);
        var publisher = new EntryGalleryPublisher(directory.resolve("gallery"), List.of());
        try (var server = new GalleryHttpServer(0, publisher, assets)) {
            server.start();
            assertEquals(404, get("http://127.0.0.1:" + server.port() + "/campus-pack.zip").statusCode());
            assertThrows(java.io.IOException.class, () -> new CampusMapPack(assets, "http://localhost:8789"));
            assertThrows(IllegalArgumentException.class, () -> new CampusMapPack(assets, "http://example.org"));
        }
    }

    private HttpResponse<byte[]> get(String url) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create(url)).build(), HttpResponse.BodyHandlers.ofByteArray());
    }
}
