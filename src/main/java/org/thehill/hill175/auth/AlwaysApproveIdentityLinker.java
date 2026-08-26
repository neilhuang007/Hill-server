package org.thehill.hill175.auth;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

public final class AlwaysApproveIdentityLinker implements IdentityLinker {
    private final String baseUrl;

    public AlwaysApproveIdentityLinker(String baseUrl) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
    }

    @Override
    public LinkTicket begin(String nickname, UUID playerId) {
        String token = UUID.randomUUID().toString();
        String url = baseUrl + "/" + token + "?nickname="
                + URLEncoder.encode(nickname, StandardCharsets.UTF_8);
        return new LinkTicket(token, url);
    }

    @Override
    public LinkResult complete(LinkTicket ticket) {
        String nickname = extractNickname(ticket.url());
        return new LinkResult(
                true,
                "stub:" + nickname.toLowerCase(Locale.ROOT),
                readableName(nickname),
                "Development identity link approved automatically."
        );
    }

    private static String extractNickname(String url) {
        int marker = url.indexOf("?nickname=");
        if (marker < 0) {
            return "Participant";
        }
        return java.net.URLDecoder.decode(url.substring(marker + 10), StandardCharsets.UTF_8);
    }

    private static String readableName(String nickname) {
        String spaced = nickname.replace('_', ' ').trim();
        if (spaced.isEmpty()) {
            return "Participant";
        }
        StringBuilder result = new StringBuilder(spaced.length());
        boolean capitalize = true;
        for (char character : spaced.toCharArray()) {
            if (Character.isWhitespace(character)) {
                result.append(character);
                capitalize = true;
            } else if (capitalize) {
                result.append(Character.toUpperCase(character));
                capitalize = false;
            } else {
                result.append(character);
            }
        }
        return result.toString();
    }
}
