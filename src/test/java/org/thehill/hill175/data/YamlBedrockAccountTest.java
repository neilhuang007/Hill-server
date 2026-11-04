package org.thehill.hill175.data;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.Account;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.*;

class YamlBedrockAccountTest {
    @TempDir Path directory;

    @Test
    void keepsPrefixedAndJavaAccountsSeparateAcrossRestarts() {
        YamlCompetitionStore store = open();
        for (String name : new String[]{"builder", ".builder", "*builder", "~builder", ".a.b"}) {
            store.saveAccount(new Account(name, name, "stub:" + name, name,
                    "salt-" + name, "hash-" + name, 310_000, Instant.EPOCH));
        }
        for (int restart = 0; restart < 2; restart++) {
            store = open();
            for (String name : new String[]{"builder", ".builder", "*builder", "~builder", ".a.b"}) {
                Account restored = store.account(name).orElseThrow();
                assertEquals(name, restored.nicknameKey());
                assertEquals("hash-" + name, restored.passwordHash());
            }
            store.flush();
        }
    }

    @Test
    void readsLegacyJavaAccountsWithoutTheNewExplicitKey() throws Exception {
        Files.writeString(directory.resolve("competition-data.yml"), """
                accounts:
                  builder:
                    nickname: Builder
                    password-hash: legacy-hash
                """);
        Account account = open().account("builder").orElseThrow();
        assertEquals("Builder", account.nickname());
        assertEquals("legacy-hash", account.passwordHash());
    }

    private YamlCompetitionStore open() {
        return new YamlCompetitionStore(directory.toFile(), Logger.getAnonymousLogger());
    }
}
