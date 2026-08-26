package org.thehill.hill175.auth;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordHasherTest {
    @Test
    void verifiesTheOriginalPasswordAndRejectsAnotherPassword() {
        PasswordHasher hasher = new PasswordHasher();
        PasswordHasher.PasswordRecord record = hasher.hash("correct horse battery staple".toCharArray());

        assertTrue(hasher.verify(
                "correct horse battery staple".toCharArray(),
                record.saltBase64(),
                record.hashBase64(),
                record.iterations()
        ));
        assertFalse(hasher.verify(
                "wrong password".toCharArray(),
                record.saltBase64(),
                record.hashBase64(),
                record.iterations()
        ));
    }
}
