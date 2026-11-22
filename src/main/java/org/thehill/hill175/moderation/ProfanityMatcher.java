package org.thehill.hill175.moderation;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class ProfanityMatcher {
    private static final int MAX_RULE_LENGTH = 256;
    private static final int MAX_MATCH_SPAN = 256;
    private static final int MAX_RULES = 4096;
    private final List<Rules> variants;
    private final int maxTextLength;

    ProfanityMatcher(Collection<String> terms, Collection<String> allowlist, int maxTextLength) {
        if (terms.size() > MAX_RULES || allowlist.size() > MAX_RULES) {
            throw new IllegalArgumentException("Too many moderation rules.");
        }
        long ruleCharacters = terms.stream().filter(java.util.Objects::nonNull).mapToLong(String::length).sum()
                + allowlist.stream().filter(java.util.Objects::nonNull).mapToLong(String::length).sum();
        if (ruleCharacters > 65536) {
            throw new IllegalArgumentException("Moderation rules exceed the local memory budget.");
        }
        this.maxTextLength = maxTextLength;
        List<Rules> rules = new ArrayList<>();
        for (int mode = 0; mode < 3; mode++) {
            Node blocked = new Node();
            Node allowed = new Node();
            for (String term : terms) {
                add(blocked, normalizeRule(term, mode));
            }
            for (String term : allowlist) {
                add(allowed, normalizeRule(term, mode));
            }
            rules.add(new Rules(blocked, allowed));
        }
        variants = List.copyOf(rules);
    }

    boolean allows(String text) {
        if (text == null || text.isEmpty()) {
            return true;
        }
        if (text.length() > maxTextLength) {
            return false;
        }
        for (int mode = 0; mode < variants.size(); mode++) {
            String normalized = normalize(text, mode);
            if (normalized.length() > maxTextLength) {
                return false;
            }
            Rules rules = variants.get(mode);
            int[] allowedUntil = new int[normalized.length()];
            scan(normalized, rules.allowed(), (start, end) -> {
                allowedUntil[start] = Math.max(allowedUntil[start], end);
                return false;
            });
            for (int index = 1; index < allowedUntil.length; index++) {
                allowedUntil[index] = Math.max(allowedUntil[index], allowedUntil[index - 1]);
            }
            if (scan(normalized, rules.blocked(), (start, end) -> allowedUntil[start] < end)) {
                return false;
            }
        }
        return true;
    }

    private static String normalizeRule(String term, int mode) {
        if (term == null || term.isBlank() || term.length() > MAX_RULE_LENGTH) {
            throw new IllegalArgumentException("Moderation rules must contain 1 to 256 characters.");
        }
        String normalized = normalize(term, mode);
        if (normalized.isBlank() || normalized.length() > MAX_RULE_LENGTH) {
            throw new IllegalArgumentException("Moderation rule has no usable text or is too long.");
        }
        return normalized;
    }

    private static void add(Node root, String term) {
        Node node = root;
        List<Integer> counts = new ArrayList<>();
        char previous = 0;
        for (int index = 0; index < term.length(); index++) {
            char current = term.charAt(index);
            if (current == ' ') {
                continue;
            }
            if (current == previous) {
                int last = counts.size() - 1;
                counts.set(last, counts.get(last) + 1);
            } else {
                node = node.children.computeIfAbsent(current, ignored -> new Node());
                counts.add(1);
                previous = current;
            }
        }
        node.minimumRuns.add(counts.stream().mapToInt(Integer::intValue).toArray());
    }

    private static boolean scan(String text, Node root, Match match) {
        if (root.children.isEmpty()) {
            return false;
        }
        int[] counts = new int[MAX_RULE_LENGTH];
        for (int start = 0; start < text.length(); start++) {
            if (!wordAt(text, start) || (start > 0 && Character.isLetterOrDigit(text.codePointBefore(start)))) {
                continue;
            }
            Node node = root;
            char previous = 0;
            int run = -1;
            int limit = Math.min(text.length(), start + MAX_MATCH_SPAN);
            for (int position = start; position < limit; position++) {
                char current = text.charAt(position);
                if (current == ' ') {
                    continue;
                }
                if (current == previous) {
                    counts[run]++;
                } else {
                    node = node.children.get(current);
                    if (node == null) {
                        break;
                    }
                    previous = current;
                    counts[++run] = 1;
                }
                int end = position + 1;
                if (!node.minimumRuns.isEmpty() && !wordAt(text, end)) {
                    for (int[] required : node.minimumRuns) {
                        boolean enough = required.length == run + 1;
                        for (int index = 0; enough && index < required.length; index++) {
                            enough = counts[index] >= required[index];
                        }
                        if (enough && match.found(start, end)) {
                            return true;
                        }
                    }
                }
            }
        }
        return false;
    }

    private static boolean wordAt(String text, int position) {
        return position < text.length() && Character.isLetterOrDigit(text.codePointAt(position));
    }

    private static String normalize(String text, int mode) {
        String decomposed = Normalizer.normalize(text, Normalizer.Form.NFKD).toLowerCase(Locale.ROOT);
        StringBuilder result = new StringBuilder(decomposed.length());
        for (int offset = 0; offset < decomposed.length();) {
            int point = decomposed.codePointAt(offset);
            offset += Character.charCount(point);
            if (point == '\u00a7' && offset < decomposed.length()
                    && "0123456789abcdefklmnorx".indexOf(decomposed.charAt(offset)) >= 0) {
                offset++;
                continue;
            }
            int type = Character.getType(point);
            if (type == Character.FORMAT || type == Character.NON_SPACING_MARK
                    || type == Character.COMBINING_SPACING_MARK || type == Character.ENCLOSING_MARK) {
                continue;
            }
            if (mode != 0) {
                point = switch (point) {
                    case '0' -> 'o';
                    case '1', '!', '|' -> mode == 1 ? 'i' : 'l';
                    case '2' -> 'z';
                    case '3' -> 'e';
                    case '4', '@' -> 'a';
                    case '5', '$' -> 's';
                    case '6', '9' -> 'g';
                    case '7', '+' -> 't';
                    case '8' -> 'b';
                    default -> point;
                };
            }
            point = switch (point) {
                case '\u0430', '\u03b1' -> 'a';
                case '\u0432' -> 'b';
                case '\u0441', '\u03f2' -> 'c';
                case '\u0435', '\u03b5' -> 'e';
                case '\u04bb', '\u043d' -> 'h';
                case '\u0456', '\u03b9' -> 'i';
                case '\u0458' -> 'j';
                case '\u043a', '\u03ba' -> 'k';
                case '\u04cf' -> 'l';
                case '\u043c', '\u03bc' -> 'm';
                case '\u03b7' -> 'n';
                case '\u043e', '\u03bf', '\u00f8' -> 'o';
                case '\u0440', '\u03c1' -> 'p';
                case '\u0455' -> 's';
                case '\u0442', '\u03c4' -> 't';
                case '\u03bd' -> 'v';
                case '\u0445', '\u03c7' -> 'x';
                case '\u0443', '\u03c5' -> 'y';
                case '\u0142' -> 'l';
                case '\u0111', '\u00f0' -> 'd';
                default -> point;
            };
            if (point == '\u00df') {
                result.append("ss");
            } else if (Character.isLetterOrDigit(point)) {
                result.appendCodePoint(point);
            } else if (!result.isEmpty() && result.charAt(result.length() - 1) != ' ') {
                result.append(' ');
            }
        }
        return result.toString().strip();
    }

    private static final class Node {
        private final Map<Character, Node> children = new HashMap<>();
        private final List<int[]> minimumRuns = new ArrayList<>();
    }

    private record Rules(Node blocked, Node allowed) {
    }

    @FunctionalInterface
    private interface Match {
        boolean found(int start, int end);
    }
}
