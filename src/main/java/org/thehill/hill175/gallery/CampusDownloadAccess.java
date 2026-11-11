package org.thehill.hill175.gallery;

import com.sun.net.httpserver.HttpExchange;
import org.thehill.hill175.auth.PasswordHasher;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Base64;
import java.util.Properties;

/** One password submission authorizes one download. No reusable browser credential is issued. */
final class CampusDownloadAccess {
    private final Path passwordFile;
    private final PasswordHasher hasher = new PasswordHasher();
    private long windowStart = System.nanoTime();
    private int attempts;

    CampusDownloadAccess(Path passwordFile) { this.passwordFile = passwordFile; }

    void showForm(HttpExchange exchange) throws IOException {
        if (settings() == null) {
            form(exchange, 503, "Downloads are not available yet. Please try again later.", true);
        } else {
            form(exchange, 200, "Enter the password shared by the organizer.", false);
        }
    }

    boolean authorize(HttpExchange exchange) throws IOException {
        if (!exchange.getRequestMethod().equals("POST")) {
            exchange.getResponseHeaders().set("Location", "/download/");
            exchange.sendResponseHeaders(303, -1);
            return false;
        }
        Properties config = settings();
        if (config == null) {
            form(exchange, 503, "Downloads are not available yet. Please try again later.", true);
            return false;
        }
        if ("cross-site".equals(exchange.getRequestHeaders().getFirst("Sec-Fetch-Site"))) {
            form(exchange, 403, "Please open the download page and try again.", false);
            return false;
        }
        String type = exchange.getRequestHeaders().getFirst("Content-Type");
        if (type == null || !type.split(";", 2)[0].trim().equalsIgnoreCase("application/x-www-form-urlencoded")) {
            form(exchange, 415, "Please use the password form below.", false);
            return false;
        }
        byte[] body = exchange.getRequestBody().readNBytes(4097);
        if (body.length > 4096) {
            form(exchange, 413, "That password is too long.", false);
            return false;
        }
        String encoded = new String(body, StandardCharsets.UTF_8);
        Arrays.fill(body, (byte) 0);
        String password;
        try {
            if (!encoded.startsWith("password=") || encoded.contains("&")) throw new IllegalArgumentException();
            password = URLDecoder.decode(encoded.substring(9), StandardCharsets.UTF_8);
            if (password.isEmpty() || password.length() > 256) throw new IllegalArgumentException();
        } catch (IllegalArgumentException exception) {
            form(exchange, 400, "Enter a password to download the map.", false);
            return false;
        }
        if (!takeAttempt()) {
            exchange.getResponseHeaders().set("Retry-After", "60");
            form(exchange, 429, "Too many attempts. Please wait a minute and try again.", false);
            return false;
        }
        char[] secret = password.toCharArray();
        boolean accepted;
        try {
            accepted = hasher.verify(secret, config.getProperty("salt"), config.getProperty("hash"),
                    Integer.parseInt(config.getProperty("iterations")));
        } finally {
            Arrays.fill(secret, '\0');
        }
        if (!accepted) form(exchange, 403, "That password did not match. Please try again.", false);
        return accepted;
    }

    // A service-wide bound also applies behind the loopback proxy, without trusting spoofed IP headers.
    private synchronized boolean takeAttempt() {
        long now = System.nanoTime();
        if (now - windowStart >= 60_000_000_000L) { windowStart = now; attempts = 0; }
        if (attempts >= 30) return false;
        attempts++;
        return true;
    }

    private Properties settings() {
        try {
            if (!Files.isRegularFile(passwordFile, LinkOption.NOFOLLOW_LINKS) || Files.size(passwordFile) > 2048) return null;
            Properties properties = new Properties();
            try (var reader = Files.newBufferedReader(passwordFile, StandardCharsets.UTF_8)) { properties.load(reader); }
            int iterations = Integer.parseInt(properties.getProperty("iterations"));
            if (iterations < 600_000 || iterations > 1_000_000
                    || Base64.getDecoder().decode(properties.getProperty("salt")).length != 16
                    || Base64.getDecoder().decode(properties.getProperty("hash")).length != 32) return null;
            return properties;
        } catch (IOException | IllegalArgumentException | NullPointerException exception) {
            return null;
        }
    }

    private void form(HttpExchange exchange, int status, String message, boolean disabled) throws IOException {
        try (var stream = CampusDownloadAccess.class.getResourceAsStream("/gallery/download.html")) {
            if (stream == null) throw new IOException("Download form unavailable.");
            String html = new String(stream.readAllBytes(), StandardCharsets.UTF_8)
                    .replace("{{message}}", message).replace("{{disabled}}", disabled ? "disabled" : "");
            byte[] bytes = html.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
            exchange.getResponseHeaders().set("Content-Length", Integer.toString(bytes.length));
            boolean head = exchange.getRequestMethod().equals("HEAD");
            exchange.sendResponseHeaders(status, head ? -1 : bytes.length);
            if (!head) exchange.getResponseBody().write(bytes);
        }
    }
}
