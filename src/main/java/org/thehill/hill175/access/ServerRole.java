package org.thehill.hill175.access;

import java.util.Locale;

/** Server capabilities, never Minecraft operator status. */
public enum ServerRole {
    PLAYER, STAFF, MODERATOR, ADMINISTRATOR;

    public boolean atLeast(ServerRole role) { return ordinal() >= role.ordinal(); }
    public String label() {
        String value = name().toLowerCase(Locale.ROOT);
        return Character.toUpperCase(value.charAt(0)) + value.substring(1);
    }
    public static ServerRole parse(String value) { return valueOf(value.toUpperCase(Locale.ROOT)); }
}
