package org.thehill.hill175.auth.sso;

import java.time.Instant;
import org.thehill.hill175.access.ServerRole;

public record VerifiedSession(String participantKey, String displayName, Instant expiresAt, ServerRole role) {
    public VerifiedSession(String participantKey, String displayName, Instant expiresAt) {
        this(participantKey, displayName, expiresAt, ServerRole.PLAYER);
    }
}
