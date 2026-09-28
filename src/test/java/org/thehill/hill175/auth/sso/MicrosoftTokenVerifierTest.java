package org.thehill.hill175.auth.sso;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.RemoteJWKSet;
import com.nimbusds.jose.util.DefaultResourceRetriever;
import com.sun.net.httpserver.HttpServer;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class MicrosoftTokenVerifierTest {
    private static RSAKey key;
    private static RSAKey otherKey;
    private static final String NONCE = "expected-browser-nonce";
    private final SsoConfig config = SsoConfigTest.config();

    @BeforeAll static void keys() throws Exception {
        key = new RSAKeyGenerator(2048).keyID("first").generate();
        otherKey = new RSAKeyGenerator(2048).keyID("next").generate();
    }

    private JWTClaimsSet.Builder claims() {
        return new JWTClaimsSet.Builder().issuer(config.issuer()).subject("app-specific-subject")
                .audience(config.clientId().toString()).issueTime(Date.from(Instant.now().minusSeconds(2)))
                .expirationTime(Date.from(Instant.now().plusSeconds(3600))).notBeforeTime(Date.from(Instant.now().minusSeconds(2)))
                .claim("nonce", NONCE).claim("tid", config.tenantId().toString())
                .claim("oid", "8ef143d9-8b69-43b8-b1fb-5ddc68f8b4e4").claim("roles", List.of(config.requiredRole()))
                .claim("name", "Alex O’Neill 李");
    }

    private String sign(JWTClaimsSet claims, RSAKey signer, String kid) throws Exception {
        SignedJWT jwt = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(kid).build(), claims);
        jwt.sign(new RSASSASigner(signer));
        return jwt.serialize();
    }
    private MicrosoftTokenVerifier verifier() {
        return new MicrosoftTokenVerifier(config, Clock.systemUTC(), new ImmutableJWKSet<>(new JWKSet(key.toPublicJWK())));
    }

    @Test void validTokenUsesImmutableSchoolIdentifiersAndPlainUnicodeName() throws Exception {
        SchoolIdentity identity = verifier().verify(sign(claims().build(), key, "first"), NONCE);
        assertEquals("entra:" + config.tenantId() + ":8ef143d9-8b69-43b8-b1fb-5ddc68f8b4e4", identity.participantKey());
        assertEquals("Alex O’Neill 李", identity.displayName());
    }

    @Test void rejectsWrongClaimsAndMissingEntitlements() throws Exception {
        List<Consumer<JWTClaimsSet.Builder>> mutations = List.of(
                b -> b.issuer("https://evil.test"), b -> b.audience(UUID.randomUUID().toString()),
                b -> b.audience(List.of(config.clientId().toString(), "another-client")),
                b -> b.claim("azp", "another-client"), b -> b.claim("nonce", "wrong"),
                b -> b.claim("tid", UUID.randomUUID().toString()), b -> b.claim("oid", "not-uuid"),
                b -> b.claim("roles", List.of("Teacher")), b -> b.claim("roles", null),
                b -> b.claim("name", "\u202e\n\u0000"), b -> b.expirationTime(Date.from(Instant.now().minusSeconds(5))),
                b -> b.expirationTime(null), b -> b.issueTime(Date.from(Instant.now().plusSeconds(60))),
                b -> b.notBeforeTime(Date.from(Instant.now().plusSeconds(60))));
        for (var mutation : mutations) {
            var builder = claims(); mutation.accept(builder);
            String encoded = sign(builder.build(), key, "first");
            assertThrows(SsoException.class, () -> verifier().verify(encoded, NONCE));
        }
    }

    @Test void rejectsUnsignedForgedAndUnknownKeysAndPermitsRotation() throws Exception {
        String forged = sign(claims().build(), otherKey, "first");
        assertThrows(SsoException.class, () -> verifier().verify(forged, NONCE));
        String unknown = sign(claims().build(), otherKey, "next");
        assertThrows(SsoException.class, () -> verifier().verify(unknown, NONCE));
        assertThrows(SsoException.class, () -> verifier().verify(new PlainJWT(claims().build()).serialize(), NONCE));
        var rotated = new MicrosoftTokenVerifier(config, Clock.systemUTC(),
                new ImmutableJWKSet<>(new JWKSet(List.of(key.toPublicJWK(), otherKey.toPublicJWK()))));
        assertNotNull(rotated.verify(unknown, NONCE));
    }

    @Test void cachedRemoteKeysRefreshOnMicrosoftStyleSigningKeyRotation() throws Exception {
        AtomicReference<String> currentKeys = new AtomicReference<>(new JWKSet(key.toPublicJWK()).toString());
        AtomicInteger requests = new AtomicInteger();
        HttpServer keyServer = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 8);
        keyServer.createContext("/keys", exchange -> {
            try (exchange) {
                requests.incrementAndGet();
                byte[] json = currentKeys.get().getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, json.length);
                exchange.getResponseBody().write(json);
            }
        });
        keyServer.start();
        try {
            var remoteKeys = new RemoteJWKSet<com.nimbusds.jose.proc.SecurityContext>(
                    URI.create("http://127.0.0.1:" + keyServer.getAddress().getPort() + "/keys").toURL(),
                    new DefaultResourceRetriever(1000, 1000, 256 * 1024));
            var verifier = new MicrosoftTokenVerifier(config, Clock.systemUTC(), remoteKeys);
            assertNotNull(verifier.verify(sign(claims().build(), key, "first"), NONCE));
            assertEquals(1, requests.get());
            currentKeys.set(new JWKSet(otherKey.toPublicJWK()).toString());
            assertNotNull(verifier.verify(sign(claims().build(), otherKey, "next"), NONCE));
            assertEquals(2, requests.get());
        } finally { keyServer.stop(0); }
    }
}
