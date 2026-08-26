package org.thehill.hill175.auth;

import java.util.UUID;

public interface IdentityLinker {
    LinkTicket begin(String nickname, UUID playerId);

    LinkResult complete(LinkTicket ticket);

    record LinkTicket(String token, String url) {
    }

    record LinkResult(boolean approved, String schoolIdentity, String displayName, String message) {
    }
}
