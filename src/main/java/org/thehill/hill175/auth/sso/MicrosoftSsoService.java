package org.thehill.hill175.auth.sso;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;

/** Browser callbacks cannot grant game access. Only the bound connection can consume a browser-only code. */
public final class MicrosoftSsoService implements AutoCloseable {
    static final Duration CHALLENGE_LIFETIME = Duration.ofMinutes(5);
    private static final Duration LEASE_LIFETIME = Duration.ofMinutes(30);
    private static final String COOKIE = "__Host-hill175";
    private static final int MAX_PENDING = 1024;
    private final SsoConfig config;
    private final Clock clock;
    private final OidcClient oidc;
    private final SchoolIdentityStore identities;
    private final SecureRandom random = new SecureRandom();
    private final byte[] hashKey = new byte[32];
    private final Map<UUID, Challenge> challenges = new HashMap<>();
    private final Map<String, Instant> lastRequests = new HashMap<>();
    private final ThreadPoolExecutor workers;
    private final ScheduledExecutorService housekeeping;
    private HttpServer server;
    private boolean closed;

    public MicrosoftSsoService(SsoConfig config, Path identityStore) throws IOException {
        this(config, identityStore, Clock.systemUTC(), new MicrosoftOidcClient(config, Clock.systemUTC()));
    }

    MicrosoftSsoService(SsoConfig config, Path identityStore, Clock clock, OidcClient oidc) throws IOException {
        this.config = config;
        this.clock = clock;
        this.oidc = oidc;
        identities = new SchoolIdentityStore(identityStore);
        random.nextBytes(hashKey);
        workers = new ThreadPoolExecutor(4, 4, 0, TimeUnit.SECONDS, new ArrayBlockingQueue<>(32), task -> {
            Thread thread = new Thread(task, "hill175-sso-browser");
            thread.setDaemon(true);
            return thread;
        }, new ThreadPoolExecutor.AbortPolicy());
        housekeeping = Executors.newSingleThreadScheduledExecutor(task -> {
            Thread thread = new Thread(task, "hill175-sso-expiry");
            thread.setDaemon(true);
            return thread;
        });
        housekeeping.scheduleAtFixedRate(this::purgeExpired, 30, 30, TimeUnit.SECONDS);
    }

    public synchronized void start() throws IOException {
        ensureOpen();
        if (server != null) throw new IllegalStateException("SSO web service already started.");
        HttpServer created = HttpServer.create(new InetSocketAddress("127.0.0.1", config.port()), 32);
        created.createContext("/", this::handle);
        created.setExecutor(workers);
        created.start();
        server = created;
    }

    public synchronized String begin(UUID connectionId, String gameIdentity, String gameLabel) {
        ensureOpen();
        if (connectionId == null) throw new IllegalArgumentException("Connection identifier is required.");
        GameIdentity.validate(gameIdentity);
        if (gameLabel == null || gameLabel.isBlank() || gameLabel.length() > 64) throw new IllegalArgumentException("Invalid game account label.");
        purgeExpired();
        Instant now = clock.instant();
        Instant previous = lastRequests.get(gameIdentity);
        if (previous != null && previous.plusSeconds(10).isAfter(now)) {
            throw new SsoException("Please wait ten seconds before requesting another sign-in link.");
        }
        if (challenges.size() >= MAX_PENDING && !challenges.containsKey(connectionId)) {
            throw new SsoException("School sign-in is busy. Try again shortly.");
        }
        if (lastRequests.size() >= MAX_PENDING && !lastRequests.containsKey(gameIdentity)) {
            throw new SsoException("School sign-in is busy. Try again shortly.");
        }
        challenges.remove(connectionId);
        Challenge challenge = new Challenge(connectionId, gameIdentity, gameLabel, token(), now.plus(CHALLENGE_LIFETIME));
        challenges.put(connectionId, challenge);
        lastRequests.put(gameIdentity, now);
        return config.publicUrl() + "/auth/start?ticket=" + challenge.ticket;
    }

    /** No network access. Success is returned only after the immutable identity association is durable. */
    public VerifiedSession confirm(UUID connectionId, String code) {
        Challenge challenge;
        Instant expiry;
        synchronized (this) {
        ensureOpen();
        purgeExpired();
        challenge = challenges.get(connectionId);
        if (challenge == null || challenge.identity == null || challenge.confirmationHash == null) {
            throw new SsoException("Finish Microsoft sign-in in your browser, then enter its confirmation code here.");
        }
        String normalized = code == null ? "" : code.replace("-", "").toUpperCase(java.util.Locale.ROOT);
        if (!normalized.matches("[A-HJ-NP-Z2-9]{10}")
                || !MessageDigest.isEqual(challenge.confirmationHash, hash(normalized))) {
            if (++challenge.attempts >= 5) challenges.remove(connectionId);
            throw new SsoException("Invalid confirmation code. After five attempts, request a new sign-in link.");
        }
        expiry = challenge.identity.tokenExpiresAt().isBefore(clock.instant().plus(LEASE_LIFETIME))
                ? challenge.identity.tokenExpiresAt() : clock.instant().plus(LEASE_LIFETIME);
        // Consume even when persistence refuses a conflict; the browser proof cannot be replayed.
        challenges.remove(connectionId);
        if (!expiry.isAfter(clock.instant())) throw new SsoException("School authorization expired. Request a new sign-in link.");
        }
        identities.link(challenge.gameIdentity, challenge.identity, config.maxLinkedAccounts());
        return new VerifiedSession(challenge.identity.participantKey(), challenge.identity.displayName(), expiry);
    }

    public synchronized void cancel(UUID connectionId) { challenges.remove(connectionId); }

    public Optional<String> nameLookup(String participantKey) { return identities.nameLookup(participantKey); }

    private void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
          try {
            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                page(exchange, 405, "Request not supported", "Use the sign-in link provided by the Minecraft server.");
                return;
            }
            if (!config.publicUrl().getHost().equalsIgnoreCase(exchange.getRequestHeaders().getFirst("Host"))
                    || !"https".equals(exchange.getRequestHeaders().getFirst("X-Forwarded-Proto"))) {
                page(exchange, 400, "Invalid authentication host", "Open the HTTPS link provided in the game.");
                return;
            }
            Map<String, String> query = query(exchange.getRequestURI().getRawQuery());
            switch (exchange.getRequestURI().getPath()) {
                case "/" -> page(exchange, 200, "Hill 175 school sign-in", "Join the Hill 175 Minecraft server and use /verify to receive your personal sign-in link.");
                case "/auth/start" -> startBrowser(exchange, query.get("ticket"));
                case "/auth/microsoft/callback" -> callback(exchange, query);
                default -> page(exchange, 404, "Page not found", "Use the sign-in link provided in the game.");
            }
          } catch (SsoException | IllegalArgumentException exception) {
              page(exchange, 400, "Invalid sign-in request", "Use /verify in the game to request a new sign-in link.");
          }
        } catch (IOException exception) {
            // A disconnected browser does not grant access; do not log callback URLs or response bodies.
        } catch (Exception exception) {
            // All expected errors are handled before closing the exchange. No token-bearing diagnostics.
        }
    }

    private void startBrowser(HttpExchange exchange, String ticket) throws IOException {
        BrowserStart started;
        try { started = openBrowser(ticket); }
        catch (SsoException exception) { page(exchange, 410, "Sign-in link unavailable", exception.getMessage()); return; }
        securityHeaders(exchange);
        exchange.getResponseHeaders().set("Set-Cookie", COOKIE + "=" + started.cookie
                + "; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=300");
        exchange.getResponseHeaders().set("Location", started.url);
        exchange.sendResponseHeaders(302, -1);
    }

    synchronized BrowserStart openBrowser(String ticket) {
        ensureOpen();
        purgeExpired();
        if (ticket == null || !ticket.matches("[A-Za-z0-9_-]{43}")) throw unavailable();
        Challenge challenge = challenges.values().stream().filter(c -> c.ticket.equals(ticket)).findFirst().orElseThrow(MicrosoftSsoService::unavailable);
        if (challenge.state != null) throw unavailable();
        challenge.state = token();
        challenge.nonce = token();
        challenge.verifier = token();
        String cookie = token();
        challenge.cookieHash = hash(cookie);
        String pkce;
        try { pkce = Base64.getUrlEncoder().withoutPadding().encodeToString(MessageDigest.getInstance("SHA-256").digest(challenge.verifier.getBytes(StandardCharsets.US_ASCII))); }
        catch (java.security.NoSuchAlgorithmException exception) { throw new IllegalStateException(); }
        String url = "https://login.microsoftonline.com/" + config.tenantId() + "/oauth2/v2.0/authorize?"
                + MicrosoftOidcClient.form(Map.of("client_id", config.clientId().toString(), "response_type", "code",
                "redirect_uri", config.callbackUrl().toString(), "scope", "openid profile", "response_mode", "query",
                "state", challenge.state, "nonce", challenge.nonce, "code_challenge", pkce,
                "code_challenge_method", "S256", "prompt", "select_account"));
        return new BrowserStart(url, cookie);
    }

    private void callback(HttpExchange exchange, Map<String, String> query) throws IOException {
        try {
            String cookie = cookie(exchange);
            BrowserProof proof = completeBrowser(query.get("state"), cookie, query.get("code"));
            exchange.getResponseHeaders().set("Set-Cookie", COOKIE + "=; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=0");
            page(exchange, 200, "Confirm your Hill 175 sign-in", "Signed in as " + proof.displayName + ". Game account: "
                    + proof.gameLabel + ". Only continue if this is your own Minecraft connection. Return to that game and type /verify "
                    + proof.code + ". Do not share this code. This page does not sign the game in automatically.");
        } catch (SsoException exception) {
            page(exchange, 400, "Sign-in not completed", exception.getMessage());
        }
    }

    BrowserProof completeBrowser(String state, String cookie, String code) {
        Challenge challenge;
        synchronized (this) {
            ensureOpen();
            purgeExpired();
            if (state == null || cookie == null || state.length() != 43 || cookie.length() != 43) throw unavailable();
            challenge = challenges.values().stream().filter(c -> state.equals(c.state)).findFirst().orElseThrow(MicrosoftSsoService::unavailable);
            if (challenge.exchanging || !MessageDigest.isEqual(challenge.cookieHash, hash(cookie))) throw unavailable();
            // A state may exchange a code once, including provider denial or network failure.
            challenge.exchanging = true;
            if (code == null || code.isBlank() || code.length() > 8192) { challenges.remove(challenge.connectionId); throw unavailable(); }
        }
        SchoolIdentity identity;
        try { identity = oidc.exchange(code, challenge.verifier, challenge.nonce); }
        catch (RuntimeException exception) {
            synchronized (this) { challenges.remove(challenge.connectionId, challenge); }
            if (exception instanceof SsoException safe) throw safe;
            throw new SsoException("School sign-in is unavailable. Request a new link and try again.");
        }
        synchronized (this) {
            ensureOpen();
            purgeExpired();
            if (challenges.get(challenge.connectionId) != challenge) throw unavailable();
            if (!identity.tokenExpiresAt().isAfter(clock.instant())) { challenges.remove(challenge.connectionId); throw unavailable(); }
            String confirmation = confirmationCode();
            challenge.confirmationHash = hash(confirmation);
            challenge.identity = identity;
            challenge.verifier = null;
            challenge.nonce = null;
            challenge.cookieHash = null;
            return new BrowserProof(identity.displayName(), challenge.gameLabel, confirmation);
        }
    }

    private synchronized void purgeExpired() {
        Instant now = clock.instant();
        challenges.values().removeIf(challenge -> !challenge.expiresAt.isAfter(now));
        lastRequests.values().removeIf(created -> !created.plusSeconds(10).isAfter(now));
    }

    private void ensureOpen() { if (closed) throw new SsoException("School sign-in is unavailable. Contact event staff."); }
    private static SsoException unavailable() { return new SsoException("This sign-in request is invalid, already used or expired. Use /verify in the game for a new link."); }
    private String token() { byte[] bytes = new byte[32]; random.nextBytes(bytes); return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes); }
    private String confirmationCode() {
        String alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        StringBuilder code = new StringBuilder();
        for (int i = 0; i < 10; i++) code.append(alphabet.charAt(random.nextInt(alphabet.length())));
        return code.toString();
    }
    private byte[] hash(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hashKey, "HmacSHA256"));
            return mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
        } catch (java.security.GeneralSecurityException exception) { throw new IllegalStateException(); }
    }

    private static Map<String, String> query(String raw) {
        Map<String, String> result = new HashMap<>();
        if (raw == null) return result;
        if (raw.length() > 12 * 1024) throw unavailable();
        for (String part : raw.split("&")) {
            String[] pair = part.split("=", 2);
            if (pair.length != 2) throw unavailable();
            String name = URLDecoder.decode(pair[0], StandardCharsets.UTF_8);
            String value = URLDecoder.decode(pair[1], StandardCharsets.UTF_8);
            if (result.putIfAbsent(name, value) != null) throw unavailable();
        }
        return result;
    }

    private static String cookie(HttpExchange exchange) {
        String found = null;
        for (String header : exchange.getRequestHeaders().getOrDefault("Cookie", java.util.List.of())) {
            for (String part : header.split(";")) {
                String[] pair = part.strip().split("=", 2);
                if (pair.length == 2 && pair[0].equals(COOKIE)) {
                    if (found != null) throw unavailable();
                    found = pair[1];
                }
            }
        }
        return found;
    }

    private static void securityHeaders(HttpExchange exchange) {
        var headers = exchange.getResponseHeaders();
        headers.set("Cache-Control", "no-store, max-age=0");
        headers.set("Pragma", "no-cache");
        headers.set("Referrer-Policy", "no-referrer");
        headers.set("X-Content-Type-Options", "nosniff");
        headers.set("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
        headers.set("Content-Type", "text/html; charset=utf-8");
    }

    private static void page(HttpExchange exchange, int status, String title, String message) throws IOException {
        securityHeaders(exchange);
        String html = "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                + "<title>" + escape(title) + "</title><style>body{font:18px/1.6 system-ui,sans-serif;max-width:42rem;margin:12vh auto;padding:1.5rem;color:#172b43;background:#faf9f5}h1{line-height:1.2}</style>"
                + "<main><p>THE HILL SCHOOL · 175</p><h1>" + escape(title) + "</h1><p>" + escape(message) + "</p></main></html>";
        byte[] bytes = html.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
    private static String escape(String value) { return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#39;"); }

    @Override public synchronized void close() {
        if (closed) return;
        closed = true;
        challenges.clear();
        lastRequests.clear();
        if (server != null) server.stop(0);
        workers.shutdownNow();
        housekeeping.shutdownNow();
        try { identities.close(); } catch (IOException ignored) { }
        java.util.Arrays.fill(hashKey, (byte) 0);
    }

    interface OidcClient { SchoolIdentity exchange(String code, String pkceVerifier, String nonce); }
    record BrowserStart(String url, String cookie) { }
    record BrowserProof(String displayName, String gameLabel, String code) { }
    private static final class Challenge {
        final UUID connectionId;
        final String gameIdentity;
        final String gameLabel;
        final String ticket;
        final Instant expiresAt;
        String state;
        String nonce;
        String verifier;
        byte[] cookieHash;
        byte[] confirmationHash;
        SchoolIdentity identity;
        boolean exchanging;
        int attempts;
        Challenge(UUID connectionId, String gameIdentity, String gameLabel, String ticket, Instant expiresAt) {
            this.connectionId = connectionId; this.gameIdentity = gameIdentity; this.gameLabel = gameLabel;
            this.ticket = ticket; this.expiresAt = expiresAt;
        }
    }
}
