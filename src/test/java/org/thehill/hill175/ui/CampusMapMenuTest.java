package org.thehill.hill175.ui;

import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class CampusMapMenuTest {
    @Test void forgedOwnerAndUnauthenticatedResponsesDoNotConsumeTheOwnersSession() {
        UUID owner = UUID.randomUUID();
        var session = session(owner, 100);
        assertFalse(session.claim(UUID.randomUUID(), session, 101, true));
        assertFalse(session.claim(owner, session, 101, false));
        assertTrue(session.claim(owner, session, 102, true));
        assertFalse(session.claim(owner, session, 103, true));
    }

    @Test void replacedAndClosedDialogsRejectTheirOldButtons() {
        UUID owner = UUID.randomUUID();
        var old = session(owner, 100);
        var current = session(owner, 101);
        assertFalse(old.claim(owner, current, 102, true));
        assertFalse(old.claim(owner, null, 102, true));
        assertTrue(current.claim(owner, current, 102, true));
    }

    @Test void callbackExpiresAtTheConfiguredLifetime() {
        UUID owner = UUID.randomUUID();
        long lifetime = CampusMapMenu.sessionLifetime.toNanos();
        var expired = session(owner, 100);
        assertFalse(expired.claim(owner, expired, 99, true));
        assertFalse(expired.claim(owner, expired, 100 + lifetime, true));
        var active = session(owner, 100);
        assertTrue(active.claim(owner, active, 99 + lifetime, true));
    }

    @Test void onlyArtworkPagesMayRefreshWhenThePackFinishes() {
        UUID owner = UUID.randomUUID();
        assertTrue(new CampusMapMenu.Session(owner, CampusMapMenu.View.main, 0, 100).isMap());
        assertTrue(new CampusMapMenu.Session(owner, CampusMapMenu.View.core, 0, 100).isMap());
        assertFalse(new CampusMapMenu.Session(owner, CampusMapMenu.View.buildings, 1, 100).isMap());
    }

    @Test void queuedCloseCannotBeReplacedByAPackRefresh() {
        UUID owner = UUID.randomUUID();
        var session = session(owner, 100);
        session.markPending(UUID.randomUUID());
        assertTrue(session.canRefresh(101));
        session.markPending(owner);
        assertFalse(session.canRefresh(101));
        assertTrue(session.claim(owner, session, 102, true));
    }

    private static CampusMapMenu.Session session(UUID owner, long openedNanos) {
        return new CampusMapMenu.Session(owner, CampusMapMenu.View.main, 0, openedNanos);
    }
}
