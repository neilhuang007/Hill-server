package org.thehill.hill175.moderation;

import org.bukkit.plugin.java.JavaPlugin;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class CussVocabulary {
    private static final String SHA256 = "1d18ada207c6551513c767492b9441619ceea0dfe0895552410040ee0c937223";
    private static final String SCHOOL_SHA256 = "10ddddadf5d4ec32cc9749ffbbc5ba936bdc4ec0dc6a423a4fa07a53acf38acf";
    private static final Pattern ENTRY = Pattern.compile("  (?:'([^']+)'|([a-zA-Z_$][a-zA-Z0-9_$]*)): ([012]),?");

    private CussVocabulary() {
    }

    static List<String> load(JavaPlugin plugin, int minimumRating) throws IOException {
        byte[] source = resource(plugin, "moderation/cuss-en.js");
        String sourceText = new String(source, StandardCharsets.UTF_8).replace("\r\n", "\n");
        if (!digest(sourceText.getBytes(StandardCharsets.UTF_8)).equals(SHA256)) {
            throw new IOException("Bundled moderation vocabulary integrity check failed.");
        }
        List<String> terms = new ArrayList<>();
        int entries = 0;
        boolean inMap = false;
        boolean closedMap = false;
        for (String line : sourceText.split("\\R")) {
            if (line.equals("export const cuss = {")) {
                inMap = true;
                continue;
            }
            if (line.equals("}")) {
                inMap = false;
                closedMap = true;
                continue;
            }
            if (!inMap) {
                continue;
            }
            Matcher matcher = ENTRY.matcher(line);
            if (!matcher.matches()) {
                throw new IOException("Bundled moderation vocabulary format is invalid.");
            }
            entries++;
            if (Integer.parseInt(matcher.group(3)) >= minimumRating) {
                terms.add(matcher.group(1) == null ? matcher.group(2) : matcher.group(1));
            }
        }
        if (!closedMap || entries != 1795 || terms.isEmpty()) {
            throw new IOException("Bundled moderation vocabulary is incomplete.");
        }
        String additions = new String(resource(plugin, "moderation/school-additions.txt"), StandardCharsets.UTF_8)
                .replace("\r\n", "\n");
        List<String> schoolTerms = additions.lines().filter(line -> !line.isBlank()).toList();
        if (!digest(additions.getBytes(StandardCharsets.UTF_8)).equals(SCHOOL_SHA256)
                || schoolTerms.size() != 88 || schoolTerms.stream().anyMatch(line -> !line.matches("[a-z]+"))) {
            throw new IOException("Bundled school vocabulary is incomplete.");
        }
        terms.addAll(schoolTerms);
        return List.copyOf(terms);
    }

    private static byte[] resource(JavaPlugin plugin, String name) throws IOException {
        try (InputStream stream = plugin.getResource(name)) {
            if (stream == null) {
                throw new IOException("Bundled moderation vocabulary is missing.");
            }
            byte[] bytes = stream.readNBytes(131073);
            if (bytes.length > 131072) {
                throw new IOException("Bundled moderation vocabulary is too large.");
            }
            return bytes;
        }
    }

    private static String digest(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable.");
        }
    }
}
