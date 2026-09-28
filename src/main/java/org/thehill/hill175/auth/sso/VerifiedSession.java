package org.thehill.hill175.auth.sso;

import java.time.Instant;

public record VerifiedSession(String participantKey, String displayName, Instant expiresAt) { }
