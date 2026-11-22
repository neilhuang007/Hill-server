package org.thehill.hill175.auth.sso;

import java.time.Instant;
import org.thehill.hill175.access.ServerRole;

record SchoolIdentity(String participantKey, String displayName, Instant tokenExpiresAt, ServerRole role) {
    SchoolIdentity(String participantKey, String displayName, Instant tokenExpiresAt) {
        this(participantKey, displayName, tokenExpiresAt, ServerRole.PLAYER);
    }
}
