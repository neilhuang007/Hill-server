package org.thehill.hill175.gallery;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Read-only gallery. The publisher, rather than the filesystem, authorizes every entry and image. */
public final class GalleryHttpServer implements AutoCloseable {
    private static final int maxAssetBytes = 512 * 1024;
    private static final int maxImageBytes = 8 * 1024 * 1024;
    private static final String idPattern = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
    private static final String tokenPattern = "[A-Za-z0-9_-]{22,64}";
    private static final Map<String, String> pageResources = Map.of(
            "/gallery.css", "text/css; charset=utf-8", "/gallery.js", "text/javascript; charset=utf-8");
    private static final Set<String> assetFiles = Set.of(
            "stone.png", "parchment.png", "wood.png", "button.png", "button-active.png", "button-disabled.png",
            "frame.png", "divider.png", "footer-divider.png", "crest.png", "arrow-next.png", "arrow-back.png",
            "divider-left.png", "divider-center.png", "divider-right.png", "divider-fill.png",
            "footer-divider-left.png", "footer-divider-center.png", "footer-divider-right.png", "footer-divider-fill.png",
            "minecraft.woff2");
    private final EntryGalleryPublisher publisher;
    private final Path assetDirectory;
    private final int configuredPort;
    private final ThreadPoolExecutor workers;
    private HttpServer server;
    private boolean isClosed;

    public GalleryHttpServer(int port, EntryGalleryPublisher publisher, Path assetDirectory) {
        if (port < 0 || port > 65535) throw new IllegalArgumentException("Gallery port must be 0..65535.");
        configuredPort = port;
        this.publisher = Objects.requireNonNull(publisher, "Gallery publisher is required.");
        this.assetDirectory = Objects.requireNonNull(assetDirectory, "Gallery asset directory is required.").toAbsolutePath().normalize();
        workers = new ThreadPoolExecutor(2, 2, 0, TimeUnit.SECONDS, new ArrayBlockingQueue<>(32), task -> {
            Thread worker = new Thread(task, "hill175-gallery-browser");
            worker.setDaemon(true);
            return worker;
        }, new ThreadPoolExecutor.AbortPolicy());
    }

    public synchronized void start() throws IOException {
        if (isClosed) throw new IllegalStateException("Gallery service is closed.");
        if (server != null) throw new IllegalStateException("Gallery service is already started.");
        HttpServer created = HttpServer.create(new InetSocketAddress("127.0.0.1", configuredPort), 32);
        created.createContext("/", this::handle);
        created.setExecutor(workers);
        created.start();
        server = created;
    }

    public synchronized int port() {
        return server == null ? configuredPort : server.getAddress().getPort();
    }

    private void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            securityHeaders(exchange);
            if (!exchange.getRequestMethod().equals("GET") && !exchange.getRequestMethod().equals("HEAD")) {
                exchange.getResponseHeaders().set("Allow", "GET, HEAD");
                respond(exchange, 405, "text/plain; charset=utf-8", "Method not allowed.");
                return;
            }
            try {
                route(exchange);
            } catch (IllegalArgumentException exception) {
                notFound(exchange);
            } catch (IOException | RuntimeException exception) {
                respond(exchange, 503, "application/json; charset=utf-8", "{\"error\":\"Gallery temporarily unavailable.\"}");
            }
        }
    }

    private void route(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getRawPath();
        if (path == null || path.length() > 256 || path.contains("%") || path.contains("\\") || path.contains("..")) {
            notFound(exchange);
            return;
        }
        if (path.startsWith("/api/")) { api(exchange, path); return; }
        if (exchange.getRequestURI().getRawQuery() != null) { notFound(exchange); return; }
        if (path.equals("/health")) { respond(exchange, 200, "application/json; charset=utf-8", "{\"status\":\"ok\"}"); return; }
        if (path.equals("/robots.txt")) { respond(exchange, 200, "text/plain; charset=utf-8", "User-agent: *\nDisallow: /\n"); return; }
        if (path.equals("/campus-pack.zip") || path.equals("/campus-map.png")) { campusAsset(exchange, path); return; }
        if (pageResources.containsKey(path)) { resource(exchange, path, pageResources.get(path)); return; }
        if (path.startsWith("/assets/")) { asset(exchange, path.substring(8)); return; }
        if (path.equals("/") || path.matches("/entries/" + idPattern) || path.matches("/preview/" + tokenPattern)) {
            resource(exchange, "/index.html", "text/html; charset=utf-8");
            return;
        }
        notFound(exchange);
    }

    private void api(HttpExchange exchange, String path) throws IOException {
        String query = exchange.getRequestURI().getRawQuery();
        if (path.matches("/api/entries/" + idPattern + "/images/[1-3]")) {
            image(exchange, path, query);
            return;
        }
        if (query != null) { notFound(exchange); return; }
        if (path.equals("/api/entries")) {
            respond(exchange, 200, "application/json; charset=utf-8", publisher.publicIndexJson());
            return;
        }
        if (path.matches("/api/entries/" + idPattern)) {
            json(exchange, publisher.entryManifest(UUID.fromString(path.substring(13))));
            return;
        }
        if (path.matches("/api/preview/" + tokenPattern)) {
            json(exchange, publisher.previewManifest(path.substring(13)));
            return;
        }
        notFound(exchange);
    }

    private void image(HttpExchange exchange, String path, String query) throws IOException {
        String[] parts = path.split("/");
        String token = imageToken(query);
        Optional<byte[]> image = publisher.image(UUID.fromString(parts[3]), Integer.parseInt(parts[5]), token);
        if (image.isEmpty() || image.get().length > maxImageBytes) { notFound(exchange); return; }
        respond(exchange, 200, "image/png", image.get());
    }

    private String imageToken(String query) {
        if (query == null) return null;
        if (query.length() > 160) throw new IllegalArgumentException("Invalid gallery image query.");
        String token = null;
        boolean hasVersion = false;
        for (String part : query.split("&", -1)) {
            if (token == null && part.matches("token=" + tokenPattern)) { token = part.substring(6); continue; }
            if (!hasVersion && part.matches("version=[a-fA-F0-9]{64}")) { hasVersion = true; continue; }
            throw new IllegalArgumentException("Invalid gallery image query.");
        }
        return token;
    }

    private void json(HttpExchange exchange, Optional<String> json) throws IOException {
        if (json.isEmpty()) { notFound(exchange); return; }
        respond(exchange, 200, "application/json; charset=utf-8", json.get());
    }

    private void resource(HttpExchange exchange, String path, String contentType) throws IOException {
        try (InputStream stream = GalleryHttpServer.class.getResourceAsStream("/gallery" + path)) {
            if (stream == null) { notFound(exchange); return; }
            byte[] bytes = stream.readNBytes(maxAssetBytes + 1);
            if (bytes.length > maxAssetBytes) throw new IOException("Gallery resource is too large.");
            respond(exchange, 200, contentType, bytes);
        }
    }

    private void asset(HttpExchange exchange, String name) throws IOException {
        if (!assetFiles.contains(name)) { notFound(exchange); return; }
        Path target = assetDirectory.resolve(name);
        if (!Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)) { notFound(exchange); return; }
        Path realRoot = assetDirectory.toRealPath();
        if (!target.toRealPath().getParent().equals(realRoot)) { notFound(exchange); return; }
        try (InputStream stream = Files.newInputStream(target)) {
            byte[] bytes = stream.readNBytes(maxAssetBytes + 1);
            if (bytes.length > maxAssetBytes) { notFound(exchange); return; }
            respond(exchange, 200, name.equals("minecraft.woff2") ? "font/woff2" : "image/png", bytes);
        }
    }

    private void campusAsset(HttpExchange exchange, String path) throws IOException {
        Path target = assetDirectory.resolve(path.substring(1));
        if (!Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)) { notFound(exchange); return; }
        if (!target.toRealPath().getParent().equals(assetDirectory.toRealPath())) { notFound(exchange); return; }
        try (InputStream stream = Files.newInputStream(target)) {
            byte[] bytes = stream.readNBytes(maxImageBytes + 1);
            if (bytes.length > maxImageBytes) { notFound(exchange); return; }
            respond(exchange, 200, path.endsWith(".zip") ? "application/zip" : "image/png", bytes);
        }
    }

    private void securityHeaders(HttpExchange exchange) {
        var headers = exchange.getResponseHeaders();
        headers.set("Cache-Control", "no-store, max-age=0");
        headers.set("Pragma", "no-cache");
        headers.set("Referrer-Policy", "no-referrer");
        headers.set("X-Content-Type-Options", "nosniff");
        headers.set("X-Frame-Options", "DENY");
        headers.set("X-Robots-Tag", "noindex, nofollow, noarchive");
        headers.set("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
        headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
    }

    private void notFound(HttpExchange exchange) throws IOException {
        respond(exchange, 404, "application/json; charset=utf-8", "{\"error\":\"Not found.\"}");
    }

    private void respond(HttpExchange exchange, int status, String contentType, String text) throws IOException {
        respond(exchange, status, contentType, text.getBytes(StandardCharsets.UTF_8));
    }

    private void respond(HttpExchange exchange, int status, String contentType, byte[] bytes) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.getResponseHeaders().set("Content-Length", Integer.toString(bytes.length));
        boolean isHead = exchange.getRequestMethod().equals("HEAD");
        exchange.sendResponseHeaders(status, isHead ? -1 : bytes.length);
        if (!isHead) exchange.getResponseBody().write(bytes);
    }

    @Override public synchronized void close() {
        if (isClosed) return;
        isClosed = true;
        if (server != null) server.stop(0);
        workers.shutdownNow();
    }
}
