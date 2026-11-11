package org.thehill.hill175.gallery;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CampusDownloadAccessTest {
    @TempDir Path root;
    private final HttpClient client = HttpClient.newHttpClient();
    private static final String PASSWORD = "Test campus + & secret";

    @Test void passwordProtectsTheArchiveAndNeverAppearsInPublicResources() throws Exception {
        configure(PASSWORD);
        try (var server = server()) {
            assertEquals(200, request(server, "/", "GET", null).statusCode());
            var form = request(server, "/download/", "GET", null);
            assertEquals(200, form.statusCode());
            assertFalse(form.body().contains(PASSWORD));
            assertTrue(form.headers().firstValue("Content-Security-Policy").orElseThrow().contains("form-action 'self'"));
            for (String method : List.of("GET", "HEAD")) {
                var direct = request(server, "/downloads/hill-campus.zip", method, null);
                assertEquals(303, direct.statusCode());
                assertEquals("/download/", direct.headers().firstValue("Location").orElseThrow());
                assertFalse(direct.body().contains("world data"));
            }
            assertEquals(403, post(server, "wrong").statusCode());
            assertEquals(400, request(server, "/downloads/hill-campus.zip", "POST", "password=a&password=b").statusCode());
            assertEquals(413, request(server, "/downloads/hill-campus.zip", "POST", "password=" + "a".repeat(4096)).statusCode());
            assertEquals(404, request(server, "/downloads/hill-campus.zip?password=secret", "POST", "password=a").statusCode());
            var download = post(server, PASSWORD);
            assertEquals(200, download.statusCode());
            assertEquals("world data", download.body());
            assertEquals("application/zip", download.headers().firstValue("Content-Type").orElseThrow());
            assertTrue(download.headers().firstValue("Content-Disposition").orElseThrow().contains("attachment"));
            assertTrue(download.headers().firstValue("Cache-Control").orElseThrow().contains("no-store"));
            assertTrue(download.headers().firstValue("Set-Cookie").isEmpty());
            assertEquals(404, request(server, "/download-password.properties", "GET", null).statusCode());
            assertEquals(405, request(server, "/map/", "POST", "password=a").statusCode());
            configure("Replacement campus secret");
            assertEquals(403, post(server, PASSWORD).statusCode());
            assertEquals(200, post(server, "Replacement campus secret").statusCode());
        }
    }

    @Test void missingAndInvalidPasswordConfigurationFailClosed() throws Exception {
        try (var server = server()) {
            assertEquals(503, request(server, "/download/", "GET", null).statusCode());
            assertEquals(503, post(server, PASSWORD).statusCode());
            Files.writeString(root.resolve("download-password.properties"), "iterations=999999999\nsalt=wrong\nhash=wrong\n");
            assertEquals(503, post(server, PASSWORD).statusCode());
        }
    }

    @Test void repeatedAttemptsAreBoundedEvenWithSpoofedForwardingHeaders() throws Exception {
        configure(PASSWORD);
        try (var server = server()) {
            for (int attempt = 0; attempt < 30; attempt++) assertEquals(403, post(server, "wrong").statusCode());
            var response = client.send(HttpRequest.newBuilder(uri(server, "/downloads/hill-campus.zip"))
                    .header("Content-Type", "application/x-www-form-urlencoded")
                    .header("X-Forwarded-For", "192.0.2.99")
                    .POST(HttpRequest.BodyPublishers.ofString("password=wrong")).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(429, response.statusCode());
            assertEquals("60", response.headers().firstValue("Retry-After").orElseThrow());
            assertEquals(200, request(server, "/", "GET", null).statusCode());
        }
    }

    private void configure(String password) throws Exception {
        byte[] salt = "test salt 16byte".getBytes(StandardCharsets.UTF_8);
        // A deterministic salt is used only for this isolated fixture.
        salt = java.util.Arrays.copyOf(salt, 16);
        var spec = new PBEKeySpec(password.toCharArray(), salt, 600_000, 256);
        byte[] hash = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        spec.clearPassword();
        Files.writeString(root.resolve("download-password.properties"), "iterations=600000\nsalt="
                + Base64.getEncoder().encodeToString(salt) + "\nhash=" + Base64.getEncoder().encodeToString(hash) + "\n");
    }

    private GalleryHttpServer server() throws Exception {
        Files.createDirectories(root.resolve("downloads"));
        Files.writeString(root.resolve("downloads/hill-campus.zip"), "world data");
        var server = new GalleryHttpServer(0, new EntryGalleryPublisher(root.resolve("gallery"), List.of()), root.resolve("assets"), root);
        server.start();
        return server;
    }

    private URI uri(GalleryHttpServer server, String path) { return URI.create("http://127.0.0.1:" + server.port() + path); }
    private HttpResponse<String> post(GalleryHttpServer server, String password) throws Exception {
        return request(server, "/downloads/hill-campus.zip", "POST", "password=" + URLEncoder.encode(password, StandardCharsets.UTF_8));
    }
    private HttpResponse<String> request(GalleryHttpServer server, String path, String method, String body) throws Exception {
        var request = HttpRequest.newBuilder(uri(server, path));
        if (body != null) request.header("Content-Type", "application/x-www-form-urlencoded");
        return client.send(request.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }
}
