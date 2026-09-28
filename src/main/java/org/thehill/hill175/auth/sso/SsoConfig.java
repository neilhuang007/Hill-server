package org.thehill.hill175.auth.sso;

import java.net.URI;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/** Operator configuration. Credentials are deliberately excluded from diagnostics. */
public record SsoConfig(UUID tenantId, UUID clientId, String clientSecret, String requiredRole,
                        URI publicUrl, int port, int maxLinkedAccounts) {
    public SsoConfig {
        if (tenantId == null || clientId == null || clientSecret == null || clientSecret.isBlank()) {
            throw new IllegalArgumentException("Microsoft SSO requires tenant, client and client secret.");
        }
        if (requiredRole == null || !requiredRole.matches("[A-Za-z0-9._-]{1,100}")) {
            throw new IllegalArgumentException("HILL175_ENTRA_REQUIRED_ROLE must be an app role value.");
        }
        if (publicUrl == null || !"https".equals(publicUrl.getScheme()) || publicUrl.getHost() == null
                || publicUrl.getUserInfo() != null || publicUrl.getQuery() != null || publicUrl.getFragment() != null
                || !(publicUrl.getPath().isEmpty() || publicUrl.getPath().equals("/"))
                || (publicUrl.getPort() != -1 && publicUrl.getPort() != 443)) {
            throw new IllegalArgumentException("HILL175_AUTH_PUBLIC_URL must be an HTTPS origin without a path.");
        }
        publicUrl = URI.create("https://" + publicUrl.getHost().toLowerCase(java.util.Locale.ROOT));
        if (tenantId.equals(new UUID(0, 0)) || clientId.equals(new UUID(0, 0))
                || port < 1024 || port > 65535 || maxLinkedAccounts < 2 || maxLinkedAccounts > 20) {
            throw new IllegalArgumentException("SSO requires nonzero identifiers, port 1024..65535 and linked account cap 2..20.");
        }
    }

    public static Optional<SsoConfig> fromEnvironment(Map<String, String> env) {
        if (!env.containsKey("HILL175_AUTH_MODE") && env.keySet().stream().anyMatch(key -> key.startsWith("HILL175_ENTRA_")
                || key.equals("HILL175_AUTH_PUBLIC_URL") || key.equals("HILL175_AUTH_PORT") || key.equals("HILL175_MAX_LINKED_ACCOUNTS"))) {
            throw new IllegalArgumentException("Set HILL175_AUTH_MODE explicitly when providing Microsoft SSO settings.");
        }
        String mode = env.getOrDefault("HILL175_AUTH_MODE", "development");
        if (mode.equals("development")) return Optional.empty();
        if (!mode.equals("microsoft")) throw new IllegalArgumentException("HILL175_AUTH_MODE must be development or microsoft.");
        try {
            return Optional.of(new SsoConfig(uuid(required(env, "HILL175_ENTRA_TENANT_ID")),
                    uuid(required(env, "HILL175_ENTRA_CLIENT_ID")), required(env, "HILL175_ENTRA_CLIENT_SECRET"),
                    env.getOrDefault("HILL175_ENTRA_REQUIRED_ROLE", "Hill175.Student"),
                    URI.create(required(env, "HILL175_AUTH_PUBLIC_URL")),
                    Integer.parseInt(env.getOrDefault("HILL175_AUTH_PORT", "8087")),
                    Integer.parseInt(env.getOrDefault("HILL175_MAX_LINKED_ACCOUNTS", "4"))));
        } catch (IllegalArgumentException exception) {
            // Do not include supplied values: URI/parser messages can contain credentials.
            throw new IllegalArgumentException("Invalid Microsoft SSO environment configuration. Check the deployment guide.");
        }
    }

    static UUID uuid(String value) {
        UUID result = UUID.fromString(value);
        if (!result.toString().equalsIgnoreCase(value) || result.equals(new UUID(0, 0))) throw new IllegalArgumentException("Expected nonzero canonical UUID.");
        return result;
    }

    private static String required(Map<String, String> env, String key) {
        String value = env.get(key);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("Missing " + key);
        return value;
    }

    public String issuer() { return "https://login.microsoftonline.com/" + tenantId + "/v2.0"; }
    public URI callbackUrl() { return publicUrl.resolve("/auth/microsoft/callback"); }

    @Override public String toString() {
        return "SsoConfig[tenantId=" + tenantId + ", clientId=" + clientId + ", clientSecret=<redacted>, requiredRole="
                + requiredRole + ", publicUrl=" + publicUrl + ", port=" + port + ", maxLinkedAccounts=" + maxLinkedAccounts + "]";
    }
}
