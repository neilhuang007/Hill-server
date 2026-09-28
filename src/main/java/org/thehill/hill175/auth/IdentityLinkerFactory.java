package org.thehill.hill175.auth;

import org.bukkit.configuration.ConfigurationSection;

/** Keeps an unimplemented provider from silently falling back to development approval. */
public final class IdentityLinkerFactory {
    private IdentityLinkerFactory() {
    }

    public static IdentityLinker create(ConfigurationSection config) {
        String provider = config.getString("authentication.provider", "");
        if (!"always-approve-development-stub".equals(provider)) {
            throw new IllegalStateException("Unsupported authentication.provider: " + provider
                    + ". Microsoft SSO is planned but is not implemented in this release.");
        }
        if (!config.getBoolean("authentication.development-stub-acknowledged", false)) {
            throw new IllegalStateException("Development identity linking must be explicitly acknowledged.");
        }
        return new AlwaysApproveIdentityLinker(config.getString(
                "authentication.stub-link-base-url", "https://example.invalid/hill175/link"));
    }
}
