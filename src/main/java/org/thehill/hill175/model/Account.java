package org.thehill.hill175.model;

import java.time.Instant;

public record Account(
        String nicknameKey,
        String nickname,
        String schoolIdentity,
        String displayName,
        String passwordSalt,
        String passwordHash,
        int passwordIterations,
        Instant registeredAt
) {
}
