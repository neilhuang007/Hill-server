package org.thehill.hill175.auth.sso;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SsoConfigTest {
    static Map<String, String> environment() {
        return Map.of("HILL175_AUTH_MODE", "microsoft", "HILL175_ENTRA_TENANT_ID", "76b02f9e-4050-43db-807c-e05e683be3de",
                "HILL175_ENTRA_CLIENT_ID", "0c894f18-7fba-4531-8354-a668c07fef69", "HILL175_ENTRA_CLIENT_SECRET", "test-only-secret",
                "HILL175_AUTH_PUBLIC_URL", "https://auth.example.test/");
    }

    static SsoConfig config() { return SsoConfig.fromEnvironment(environment()).orElseThrow(); }

    @Test void modeMustBeExplicitlyRecognizedAndMicrosoftCannotFallBack() {
        assertTrue(SsoConfig.fromEnvironment(Map.of()).isEmpty());
        assertTrue(SsoConfig.fromEnvironment(Map.of("HILL175_AUTH_MODE", "development")).isEmpty());
        assertThrows(IllegalArgumentException.class, () -> SsoConfig.fromEnvironment(Map.of("HILL175_AUTH_MODE", "other")));
        var forgottenMode = new HashMap<>(environment()); forgottenMode.remove("HILL175_AUTH_MODE");
        assertThrows(IllegalArgumentException.class, () -> SsoConfig.fromEnvironment(forgottenMode));
        for (String key : environment().keySet()) {
            if (key.equals("HILL175_AUTH_MODE")) continue;
            var env = new HashMap<>(environment()); env.remove(key);
            assertThrows(IllegalArgumentException.class, () -> SsoConfig.fromEnvironment(env));
        }
    }

    @Test void configRejectsUnsafeOriginsAndDoesNotExposeSecret() {
        for (String url : new String[]{"http://auth.example.test", "https://auth.example.test/path", "https://x@y.test",
                "https://auth.example.test?code=secret", "https://auth.example.test#x", "https://auth.example.test:8443"}) {
            var env = new HashMap<>(environment()); env.put("HILL175_AUTH_PUBLIC_URL", url);
            assertThrows(IllegalArgumentException.class, () -> SsoConfig.fromEnvironment(env));
        }
        assertEquals("https://auth.example.test", config().publicUrl().toString());
        assertEquals(8087, config().port());
        assertEquals(4, config().maxLinkedAccounts());
        assertFalse(config().toString().contains("test-only-secret"));
    }

    @Test void idsAndLimitsAreValidated() {
        for (var invalid : Map.of("HILL175_ENTRA_TENANT_ID", "00000000-0000-0000-0000-000000000000",
                "HILL175_ENTRA_CLIENT_ID", "1-1-1-1-1", "HILL175_AUTH_PORT", "80", "HILL175_MAX_LINKED_ACCOUNTS", "1").entrySet()) {
            var env = new HashMap<>(environment()); env.put(invalid.getKey(), invalid.getValue());
            assertThrows(IllegalArgumentException.class, () -> SsoConfig.fromEnvironment(env));
        }
    }
}
