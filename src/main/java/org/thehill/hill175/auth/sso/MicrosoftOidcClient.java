package org.thehill.hill175.auth.sso;

import com.nimbusds.jose.util.JSONObjectUtils;

import java.net.URI;
import java.net.URLEncoder;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/** Network work is invoked only by the bounded browser worker pool. */
final class MicrosoftOidcClient implements MicrosoftSsoService.OidcClient {
    private final SsoConfig config;
    private final MicrosoftTokenVerifier verifier;

    MicrosoftOidcClient(SsoConfig config, Clock clock) {
        this.config = config;
        verifier = new MicrosoftTokenVerifier(config, clock);
    }

    @Override public SchoolIdentity exchange(String code, String pkceVerifier, String nonce) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) URI.create("https://login.microsoftonline.com/" + config.tenantId()
                    + "/oauth2/v2.0/token").toURL().openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(10000);
            connection.setRequestMethod("POST");
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
            connection.setRequestProperty("Accept", "application/json");
            Map<String, String> values = new LinkedHashMap<>();
            values.put("client_id", config.clientId().toString());
            values.put("client_secret", config.clientSecret());
            values.put("grant_type", "authorization_code");
            values.put("scope", "openid profile");
            values.put("code", code);
            values.put("redirect_uri", config.callbackUrl().toString());
            values.put("code_verifier", pkceVerifier);
            byte[] body = form(values).getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(body.length);
            try (var output = connection.getOutputStream()) { output.write(body); }
            if (connection.getResponseCode() != 200) throw new SsoException("Microsoft sign-in could not be completed. Request a new sign-in link.");
            byte[] response;
            try (var input = connection.getInputStream()) { response = input.readNBytes(64 * 1024 + 1); }
            if (response.length > 64 * 1024) throw new IllegalArgumentException();
            Map<String, Object> tokenResponse = JSONObjectUtils.parse(new String(response, StandardCharsets.UTF_8));
            return verifier.verify(JSONObjectUtils.getString(tokenResponse, "id_token"), nonce);
        } catch (SsoException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new SsoException("Microsoft sign-in is temporarily unavailable. Request a new sign-in link and try again.");
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    static String form(Map<String, String> values) {
        return values.entrySet().stream().map(e -> encode(e.getKey()) + "=" + encode(e.getValue())).collect(Collectors.joining("&"));
    }

    private static String encode(String value) { return URLEncoder.encode(value, StandardCharsets.UTF_8); }
}
