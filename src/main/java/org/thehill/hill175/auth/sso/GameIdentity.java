package org.thehill.hill175.auth.sso;

/** Canonical transport identifiers shared by the game boundary and durable link store. */
public final class GameIdentity {
    private GameIdentity() {
    }

    public static String bedrock(String xuid) {
        String identity = "bedrock:" + xuid;
        validate(identity);
        return identity;
    }

    public static void validate(String value) {
        if (value != null && value.startsWith("java:")) {
            String id = value.substring(5);
            if (SsoConfig.uuid(id).toString().equals(id)) {
                return;
            }
        } else if (value != null && value.matches("bedrock:[1-9][0-9]{0,19}")) {
            try {
                Long.parseUnsignedLong(value.substring(8));
                return;
            } catch (NumberFormatException ignored) {
                // Reject values outside the unsigned XUID range.
            }
        }
        throw new IllegalArgumentException("Expected a verified Java UUID or Bedrock XUID.");
    }
}
