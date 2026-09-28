package org.thehill.hill175.auth;

import org.bukkit.configuration.file.YamlConfiguration;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

class IdentityLinkerFactoryTest {
    @Test
    void developmentRequiresBothProviderAndAcknowledgement() {
        YamlConfiguration config = new YamlConfiguration();
        assertThrows(IllegalStateException.class, () -> IdentityLinkerFactory.create(config));
        config.set("authentication.provider", "always-approve-development-stub");
        assertThrows(IllegalStateException.class, () -> IdentityLinkerFactory.create(config));
        config.set("authentication.development-stub-acknowledged", true);
        assertInstanceOf(AlwaysApproveIdentityLinker.class, IdentityLinkerFactory.create(config));
    }

    @Test
    void unimplementedMicrosoftProviderNeverUsesAutomaticApproval() {
        YamlConfiguration config = new YamlConfiguration();
        config.set("authentication.provider", "microsoft");
        config.set("authentication.development-stub-acknowledged", true);
        assertThrows(IllegalStateException.class, () -> IdentityLinkerFactory.create(config));
    }
}
