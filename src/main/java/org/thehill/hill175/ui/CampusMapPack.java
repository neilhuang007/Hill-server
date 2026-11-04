package org.thehill.hill175.ui;

import org.bukkit.entity.Player;

import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;
import java.util.UUID;

/** Optional server supplied imagery, with a content identified client cache key. */
public final class CampusMapPack {
    private final byte[] sha1;
    private final UUID id;
    private final String url;

    public CampusMapPack(Path assetDirectory, String baseUrl) throws IOException {
        Objects.requireNonNull(assetDirectory);
        URI base = URI.create(Objects.requireNonNull(baseUrl));
        if (!isAllowedBase(base)) throw new IllegalArgumentException("Campus pack requires HTTPS or a local preview address.");
        Path file = assetDirectory.resolve("campus-pack.zip");
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.size(file) > 8 * 1024 * 1024) {
            throw new IOException("Prepare campus-pack.zip in the gallery asset directory first.");
        }
        if (!file.toRealPath().getParent().equals(assetDirectory.toRealPath())) throw new IOException("Campus pack escaped the asset directory.");
        sha1 = sha1(Files.readAllBytes(file));
        id = UUID.nameUUIDFromBytes(sha1);
        url = baseUrl.replaceAll("/+$", "") + "/campus-pack.zip";
    }

    private static boolean isAllowedBase(URI base) {
        if (base.getHost() == null || base.getUserInfo() != null || base.getRawQuery() != null || base.getRawFragment() != null) return false;
        if (base.getPath() != null && !base.getPath().isEmpty() && !base.getPath().equals("/")) return false;
        return "https".equals(base.getScheme()) || "http".equals(base.getScheme())
                && (base.getHost().equals("localhost") || base.getHost().equals("127.0.0.1") || base.getHost().equals("[::1]"));
    }

    private static byte[] sha1(byte[] bytes) {
        try { return MessageDigest.getInstance("SHA-1").digest(bytes); }
        catch (NoSuchAlgorithmException exception) { throw new IllegalStateException("SHA1 is unavailable.", exception); }
    }

    public UUID id() { return id; }
    public String sha1Hex() { return HexFormat.of().formatHex(sha1); }
    public void offer(Player player) {
        player.addResourcePack(id, url, sha1.clone(), "Show the illustrated Hill school map. Numbered building choices also work without this pack.", false);
    }
}
