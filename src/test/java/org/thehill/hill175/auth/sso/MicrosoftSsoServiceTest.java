package org.thehill.hill175.auth.sso;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.HttpURLConnection;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class MicrosoftSsoServiceTest {
    @TempDir Path directory;
    private final MutableClock clock = new MutableClock();
    private final SchoolIdentity person = SchoolIdentityStoreTest.identity("Hill Student");

    private MicrosoftSsoService service() throws Exception {
        return new MicrosoftSsoService(SsoConfigTest.config(), directory.resolve("identities.json"), clock, (c, v, n) -> person);
    }
    private static String ticket(String url) { return URI.create(url).getQuery().substring("ticket=".length()); }
    private static Map<String, String> query(String url) {
        Map<String, String> values = new HashMap<>();
        for (String piece : URI.create(url).getRawQuery().split("&")) {
            String[] pair = piece.split("=", 2);
            values.put(URLDecoder.decode(pair[0], StandardCharsets.UTF_8), URLDecoder.decode(pair[1], StandardCharsets.UTF_8));
        }
        return values;
    }
    private MicrosoftSsoService.BrowserProof authorize(MicrosoftSsoService service, UUID connection, String gameIdentity) {
        var browser = service.openBrowser(ticket(service.begin(connection, gameIdentity, "GameName")));
        return service.completeBrowser(query(browser.url()).get("state"), browser.cookie(), "authorization-code");
    }

    @Test void browserAloneCannotAuthenticateAndCodeOnlyWorksOnceForBoundConnection() throws Exception {
        try (var service = service()) {
            UUID connection = UUID.randomUUID();
            var proof = authorize(service, connection, "java:" + UUID.randomUUID());
            assertTrue(service.nameLookup(person.participantKey()).isEmpty());
            assertThrows(SsoException.class, () -> service.confirm(UUID.randomUUID(), proof.code()));
            var session = service.confirm(connection, proof.code());
            assertEquals(person.participantKey(), session.participantKey());
            assertEquals(clock.instant().plusSeconds(1800), session.expiresAt());
            assertEquals(person.displayName(), service.nameLookup(person.participantKey()).orElseThrow());
            assertThrows(SsoException.class, () -> service.confirm(connection, proof.code()));
        }
    }

    @Test void stateCookieAndReplayAreCheckedAndPkceMatchesExchange() throws Exception {
        String[] usedVerifier = {null}; String[] usedNonce = {null};
        try (var service = new MicrosoftSsoService(SsoConfigTest.config(), directory.resolve("identities.json"), clock,
                (code, verifier, nonce) -> { usedVerifier[0] = verifier; usedNonce[0] = nonce; return person; })) {
            var browser = service.openBrowser(ticket(service.begin(UUID.randomUUID(), "bedrock:12345", "GameName")));
            var params = query(browser.url());
            assertEquals("openid profile", params.get("scope"));
            assertEquals("S256", params.get("code_challenge_method"));
            assertEquals("select_account", params.get("prompt"));
            assertThrows(SsoException.class, () -> service.completeBrowser(params.get("state"), "x".repeat(43), "code"));
            assertThrows(SsoException.class, () -> service.completeBrowser("x".repeat(43), browser.cookie(), "code"));
            service.completeBrowser(params.get("state"), browser.cookie(), "code");
            assertEquals(params.get("nonce"), usedNonce[0]);
            assertEquals(params.get("code_challenge"), Base64.getUrlEncoder().withoutPadding().encodeToString(
                    MessageDigest.getInstance("SHA-256").digest(usedVerifier[0].getBytes(StandardCharsets.US_ASCII))));
            assertThrows(SsoException.class, () -> service.completeBrowser(params.get("state"), browser.cookie(), "code"));
        }
    }

    @Test void guessesExpireAndDisconnectCannotBeReplayedAfterRejoin() throws Exception {
        try (var service = service()) {
            UUID connection = UUID.randomUUID();
            var proof = authorize(service, connection, "bedrock:12345");
            for (int i = 0; i < 5; i++) assertThrows(SsoException.class, () -> service.confirm(connection, "wrong"));
            assertThrows(SsoException.class, () -> service.confirm(connection, proof.code()));
            clock.advance(11);
            var next = authorize(service, connection, "bedrock:12345");
            service.cancel(connection);
            assertThrows(SsoException.class, () -> service.confirm(connection, next.code()));
            clock.advance(11);
            var rejoined = UUID.randomUUID();
            authorize(service, rejoined, "bedrock:12345");
            assertThrows(SsoException.class, () -> service.confirm(rejoined, next.code()));
        }
    }

    @Test void challengeAndTokenExpiryBothLimitAuthorization() throws Exception {
        try (var service = service()) {
            UUID connection = UUID.randomUUID();
            var proof = authorize(service, connection, "bedrock:12345");
            clock.advance(300);
            assertThrows(SsoException.class, () -> service.confirm(connection, proof.code()));
        }
        SchoolIdentity expiring = new SchoolIdentity(person.participantKey(), person.displayName(), clock.instant().plusSeconds(60));
        try (var service = new MicrosoftSsoService(SsoConfigTest.config(), directory.resolve("identities.json"), clock, (c, v, n) -> expiring)) {
            UUID connection = UUID.randomUUID();
            var proof = authorize(service, connection, "bedrock:12345");
            assertEquals(expiring.tokenExpiresAt(), service.confirm(connection, proof.code()).expiresAt());
        }
    }

    @Test void cancelDoesNotWaitForMicrosoftNetworkAndStaleCallbackDoesNotComplete() throws Exception {
        CountDownLatch entered = new CountDownLatch(1); CountDownLatch release = new CountDownLatch(1);
        try (var service = new MicrosoftSsoService(SsoConfigTest.config(), directory.resolve("identities.json"), clock,
                (c, v, n) -> { entered.countDown(); try { release.await(5, TimeUnit.SECONDS); } catch (InterruptedException e) { throw new SsoException("Interrupted"); } return person; });
             var executor = Executors.newSingleThreadExecutor()) {
            UUID connection = UUID.randomUUID();
            var browser = service.openBrowser(ticket(service.begin(connection, "bedrock:12345", "GameName")));
            var completion = executor.submit(() -> service.completeBrowser(query(browser.url()).get("state"), browser.cookie(), "code"));
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            assertTimeout(java.time.Duration.ofMillis(200), () -> service.cancel(connection));
            release.countDown();
            assertThrows(java.util.concurrent.ExecutionException.class, completion::get);
            assertTrue(service.nameLookup(person.participantKey()).isEmpty());
        } finally { release.countDown(); }
    }

    @Test void embeddedServerIsLoopbackAndRejectsUntrustedHostAndMalformedQueries() throws Exception {
        int port;
        try (var socket = new ServerSocket(0)) { port = socket.getLocalPort(); }
        var base = SsoConfigTest.config();
        var config = new SsoConfig(base.tenantId(), base.clientId(), base.clientSecret(), base.requiredRole(), base.publicUrl(), port, 4);
        try (var service = new MicrosoftSsoService(config, directory.resolve("identities.json"), clock, (c, v, n) -> person)) {
            service.start();
            var connection = (HttpURLConnection) URI.create("http://127.0.0.1:" + port + "/").toURL().openConnection();
            connection.setConnectTimeout(2000); connection.setReadTimeout(2000);
            assertEquals(400, connection.getResponseCode());
            assertEquals("no-store, max-age=0", connection.getHeaderField("Cache-Control"));
            connection.disconnect();
            assertTrue(http(port, "GET", "/auth/start?ticket=one&ticket=two", null).startsWith("HTTP/1.1 400"));
            assertTrue(http(port, "POST", "/auth/start", null).startsWith("HTTP/1.1 405"));
            UUID gameConnection = UUID.randomUUID();
            String browserUrl = service.begin(gameConnection, "bedrock:123456", "<Game&Name>");
            String redirect = http(port, "GET", URI.create(browserUrl).getRawPath() + "?" + URI.create(browserUrl).getRawQuery(), null);
            assertTrue(redirect.startsWith("HTTP/1.1 302"));
            String cookie = responseHeader(redirect, "set-cookie");
            assertTrue(cookie.contains("Secure; HttpOnly; SameSite=Lax; Path=/"));
            String state = query(responseHeader(redirect, "location")).get("state");
            String page = http(port, "GET", "/auth/microsoft/callback?state=" + state + "&code=browser-code", cookie.split(";", 2)[0]);
            assertTrue(page.startsWith("HTTP/1.1 200"));
            assertEquals("no-store, max-age=0", responseHeader(page, "cache-control"));
            assertEquals("no-referrer", responseHeader(page, "referrer-policy"));
            assertTrue(responseHeader(page, "content-security-policy").contains("frame-ancestors 'none'"));
            assertTrue(page.contains("&lt;Game&amp;Name&gt;"));
            var codeMatcher = java.util.regex.Pattern.compile("/verify ([A-HJ-NP-Z2-9]{10})").matcher(page);
            assertTrue(codeMatcher.find());
            assertEquals(person.participantKey(), service.confirm(gameConnection, codeMatcher.group(1)).participantKey());
            assertTrue(http(port, "GET", "/auth/microsoft/callback?state=" + state + "&code=browser-code", cookie.split(";", 2)[0]).startsWith("HTTP/1.1 400"));
        }
    }

    private static String http(int port, String method, String path, String cookie) throws Exception {
        try (Socket socket = new Socket("127.0.0.1", port)) {
            socket.setSoTimeout(3000);
            String request = method + " " + path + " HTTP/1.1\r\nHost: auth.example.test\r\nX-Forwarded-Proto: https\r\nConnection: close\r\n"
                    + (cookie == null ? "" : "Cookie: " + cookie + "\r\n") + "\r\n";
            socket.getOutputStream().write(request.getBytes(StandardCharsets.US_ASCII));
            return new String(socket.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static String responseHeader(String response, String name) {
        return response.lines().filter(line -> line.regionMatches(true, 0, name + ": ", 0, name.length() + 2))
                .map(line -> line.substring(name.length() + 2)).findFirst().orElseThrow();
    }

    private static final class MutableClock extends Clock {
        private volatile Instant now = Instant.now();
        void advance(long seconds) { now = now.plusSeconds(seconds); }
        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) { return this; }
        @Override public Instant instant() { return now; }
    }
}
