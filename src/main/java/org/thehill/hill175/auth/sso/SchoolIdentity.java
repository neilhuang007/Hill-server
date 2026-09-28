package org.thehill.hill175.auth.sso;

import java.time.Instant;

record SchoolIdentity(String participantKey, String displayName, Instant tokenExpiresAt) { }
