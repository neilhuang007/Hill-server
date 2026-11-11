package org.thehill.hill175.gallery;

import com.sun.net.httpserver.HttpExchange;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;

/** Serves only the prepared public campus export, never its source world or provenance. */
final class CampusSiteFiles {
    private static final Set<String> artwork = Set.of("hill-175-gold.png", "campus-hero.png", "campus-detail.png",
            "campus-quad.png", "campus-chapel.png", "campus-grounds.png", "minecraft.woff2",
            "hill-school-logo-light.svg", "hill-school-icon.svg", "campus-photo-01.jpg",
            "campus-photo-02.jpg", "campus-photo-03.jpg", "campus-photo-04.jpg", "campus-photo-05.jpg",
            "join-java-servers.jpg", "join-java-address.jpg", "join-bedrock-servers.jpg", "join-bedrock-address.jpg");
    private static final Map<String, String> types = Map.ofEntries(
            Map.entry("html", "text/html; charset=utf-8"), Map.entry("js", "text/javascript; charset=utf-8"),
            Map.entry("css", "text/css; charset=utf-8"), Map.entry("json", "application/json; charset=utf-8"),
            Map.entry("png", "image/png"), Map.entry("jpg", "image/jpeg"), Map.entry("webp", "image/webp"),
            Map.entry("svg", "image/svg+xml"), Map.entry("ico", "image/x-icon"), Map.entry("woff2", "font/woff2"),
            Map.entry("woff", "font/woff"), Map.entry("ttf", "font/ttf"), Map.entry("wasm", "application/wasm"),
            Map.entry("gz", "application/octet-stream"), Map.entry("prbm", "application/octet-stream"),
            Map.entry("webmanifest", "application/manifest+json"));
    private final Path root;
    private final CampusDownloadAccess downloadAccess;

    CampusSiteFiles(Path root) {
        this.root = root.toAbsolutePath().normalize();
        downloadAccess = new CampusDownloadAccess(this.root.resolve("download-password.properties"));
    }

    boolean serve(HttpExchange exchange, String route) throws IOException {
        if (route.equals("/download/")) {
            downloadAccess.showForm(exchange);
            return true;
        }
        String relative;
        String contentType;
        boolean download = route.equals("/downloads/hill-campus.zip");
        boolean map = route.startsWith("/map/");
        long limit = 16L * 1024 * 1024;
        if (download) {
            if (!downloadAccess.authorize(exchange)) return true;
            relative = "downloads/hill-campus.zip";
            contentType = "application/zip";
            limit = 512L * 1024 * 1024;
        } else if (route.equals("/campus.json")) {
            relative = "campus.json";
            contentType = "application/json; charset=utf-8";
            limit = 16384;
        } else if (route.startsWith("/site-assets/") && artwork.contains(route.substring(13))) {
            relative = "assets/" + route.substring(13);
            contentType = route.endsWith("woff2") ? "font/woff2"
                    : route.endsWith("svg") ? "image/svg+xml" : route.endsWith("jpg") ? "image/jpeg" : "image/png";
        } else if (map) {
            relative = route.equals("/map/") ? "map/index.html" : route.substring(1);
            if (!relative.matches("[A-Za-z0-9_./-]+")) return false;
            contentType = relative.matches("map/lang/[A-Za-z0-9_-]+\\.conf")
                    ? "text/plain; charset=utf-8" : types.get(relative.substring(relative.lastIndexOf('.') + 1));
            if (contentType == null) return false;
        } else return false;
        Path file = root.resolve(relative).normalize();
        if (!file.startsWith(root) || !Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) return false;
        // Checking the real path also rejects links in any parent directory.
        if (!file.toRealPath().startsWith(root.toRealPath())) return false;
        long length = Files.size(file);
        if (length > limit) return false;
        var headers = exchange.getResponseHeaders();
        headers.set("Content-Type", contentType);
        headers.set("Content-Length", Long.toString(length));
        if (download) headers.set("Content-Disposition", "attachment; filename=\"Hill-175-Campus-Java.zip\"");
        if (map) {
            headers.set("X-Frame-Options", "SAMEORIGIN");
            // BlueMap's bundled message formatter compiles its local language files at runtime.
            // This exception belongs only to the isolated map, never to gallery or login pages.
            headers.set("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-eval'; "
                    + "worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                    + "connect-src 'self'; font-src 'self'; base-uri 'self'; frame-ancestors 'self'; form-action 'none'");
            // Exported map geometry is public and already rendered. Let BlueMap reuse it.
            // Keep live data and protected downloads outside this cache policy.
            if (!relative.contains("/live/")) {
                BasicFileAttributes attributes = Files.readAttributes(file, BasicFileAttributes.class);
                String etag = "W/\"" + Long.toHexString(attributes.lastModifiedTime().toMillis())
                        + "-" + Long.toHexString(length) + "\"";
                headers.remove("Pragma");
                headers.set("Cache-Control", relative.endsWith(".json") || relative.endsWith(".html")
                        ? "public, no-cache" : "public, max-age=3600");
                headers.set("ETag", etag);
                headers.set("Last-Modified", DateTimeFormatter.RFC_1123_DATE_TIME.format(
                        attributes.lastModifiedTime().toInstant().atZone(ZoneOffset.UTC)));
                String condition = exchange.getRequestHeaders().getFirst("If-None-Match");
                if (condition != null && Arrays.stream(condition.split(","))
                        .map(String::trim).anyMatch(tag -> tag.equals("*") || tag.replaceFirst("^W/", "").equals(etag.substring(2)))) {
                    headers.remove("Content-Length");
                    exchange.sendResponseHeaders(304, -1);
                    return true;
                }
            }
        }
        boolean head = exchange.getRequestMethod().equals("HEAD");
        exchange.sendResponseHeaders(200, head ? -1 : length);
        if (!head) {
            try (var input = Files.newInputStream(file)) { input.transferTo(exchange.getResponseBody()); }
        }
        return true;
    }
}
