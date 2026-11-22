package org.thehill.hill175.replay;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Locale;
import java.util.UUID;

record IncidentRecord(long time, UUID actor, String name, Kind kind, UUID world, String worldName,
                      int x, int y, int z, String detail) {
    enum Kind { BREAK, PLACE, BUCKET_FILL, BUCKET_EMPTY, DAMAGE, DEATH, EXPLOSION, POSITION }

    private static String encode(String text) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(text.getBytes(StandardCharsets.UTF_8));
    }

    private static String decode(String text) {
        String result = new String(Base64.getUrlDecoder().decode(text), StandardCharsets.UTF_8);
        if (result.length() > 160 || result.chars().anyMatch(c -> Character.isISOControl(c))) throw new IllegalArgumentException("Invalid incident text");
        return result;
    }

    String serialize() {
        return "1\t" + time + "\t" + actor + "\t" + encode(name) + "\t" + kind + "\t" + world + "\t"
                + encode(worldName) + "\t" + x + "\t" + y + "\t" + z + "\t" + encode(detail);
    }

    static IncidentRecord parse(String line) {
        if (line.length() > 2048) throw new IllegalArgumentException("Oversized incident line");
        String[] fields = line.split("\t", -1);
        if (fields.length != 11 || !fields[0].equals("1")) throw new IllegalArgumentException("Unknown incident format");
        return new IncidentRecord(Long.parseLong(fields[1]), UUID.fromString(fields[2]), decode(fields[3]),
                Kind.valueOf(fields[4]), UUID.fromString(fields[5]), decode(fields[6]),
                Integer.parseInt(fields[7]), Integer.parseInt(fields[8]), Integer.parseInt(fields[9]), decode(fields[10]));
    }

    boolean matches(long since, String actorFilter) {
        if (time < since) return false;
        return actorFilter == null || actor.toString().equalsIgnoreCase(actorFilter)
                || name.toLowerCase(Locale.ROOT).equals(actorFilter.toLowerCase(Locale.ROOT));
    }
}
