package org.thehill.hill175.auth.sso;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.JWSVerificationKeySelector;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.util.DefaultResourceRetriever;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.nimbusds.oauth2.sdk.id.ClientID;
import com.nimbusds.oauth2.sdk.id.Issuer;
import com.nimbusds.openid.connect.sdk.Nonce;
import com.nimbusds.openid.connect.sdk.validators.IDTokenValidator;

import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.util.List;

final class MicrosoftTokenVerifier {
    private final SsoConfig config;
    private final IDTokenValidator validator;
    private final Clock clock;

    MicrosoftTokenVerifier(SsoConfig config, Clock clock) {
        this.config = config;
        this.clock = clock;
        try {
            validator = new IDTokenValidator(new Issuer(config.issuer()), new ClientID(config.clientId().toString()),
                    JWSAlgorithm.RS256, URI.create("https://login.microsoftonline.com/" + config.tenantId()
                    + "/discovery/v2.0/keys").toURL(), new DefaultResourceRetriever(5000, 5000, 256 * 1024));
        } catch (java.net.MalformedURLException exception) {
            throw new IllegalArgumentException("Invalid Microsoft signing key endpoint.");
        }
        validator.setMaxClockSkew(0);
    }

    MicrosoftTokenVerifier(SsoConfig config, Clock clock, JWKSource<SecurityContext> keys) {
        this.config = config;
        this.clock = clock;
        validator = new IDTokenValidator(new Issuer(config.issuer()), new ClientID(config.clientId().toString()),
                new JWSVerificationKeySelector<>(JWSAlgorithm.RS256, keys), null);
        validator.setMaxClockSkew(0);
    }

    SchoolIdentity verify(String encoded, String expectedNonce) {
        try {
            if (encoded == null || encoded.length() > 32 * 1024 || expectedNonce == null || expectedNonce.isBlank()) {
                throw new IllegalArgumentException();
            }
            SignedJWT token = SignedJWT.parse(encoded);
            if (!JWSAlgorithm.RS256.equals(token.getHeader().getAlgorithm())) throw new IllegalArgumentException();
            validator.validate(token, new Nonce(expectedNonce));
            JWTClaimsSet claims = token.getJWTClaimsSet();
            Instant now = clock.instant();
            if (!config.tenantId().equals(SsoConfig.uuid(claims.getStringClaim("tid")))
                    || claims.getExpirationTime() == null || !claims.getExpirationTime().toInstant().isAfter(now)
                    || claims.getIssueTime() == null || claims.getIssueTime().toInstant().isAfter(now)
                    || (claims.getNotBeforeTime() != null && claims.getNotBeforeTime().toInstant().isAfter(now))
                    || (claims.getStringClaim("azp") != null && !claims.getStringClaim("azp").equals(config.clientId().toString()))
                    || !claims.getAudience().equals(List.of(config.clientId().toString()))) {
                throw new IllegalArgumentException();
            }
            List<String> roles = claims.getStringListClaim("roles");
            if (roles == null || !roles.contains(config.requiredRole())) throw new IllegalArgumentException();
            String objectId = SsoConfig.uuid(claims.getStringClaim("oid")).toString();
            String name = sanitizeName(claims.getStringClaim("name"));
            return new SchoolIdentity("entra:" + config.tenantId() + ":" + objectId, name,
                    claims.getExpirationTime().toInstant());
        } catch (Exception exception) {
            throw new SsoException("Microsoft could not verify an eligible Hill student account. Check the account and contact Hill IT.");
        }
    }

    static String sanitizeName(String name) {
        if (name == null || name.length() > 256) throw new IllegalArgumentException("Missing or invalid school name.");
        StringBuilder safe = new StringBuilder();
        name.codePoints().filter(c -> !Character.isISOControl(c) && Character.getType(c) != Character.FORMAT
                && c != 0x00a7).forEach(safe::appendCodePoint);
        String result = safe.toString().strip().replaceAll("\\s+", " ");
        if (result.isBlank() || result.codePointCount(0, result.length()) > 100) {
            throw new IllegalArgumentException("Missing or invalid school name.");
        }
        return result;
    }
}
