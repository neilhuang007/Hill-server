package org.thehill.hill175.world;

import org.bukkit.configuration.file.YamlConfiguration;

import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;

/**
 * A lobby or hub map the operator placed in its designated folder as an ordinary
 * world save. The folder's content selects the map; no name, version or hash is
 * compiled in.
 */
final class SceneryTemplate {
    private static final Set<String> PLAYER_STATE_FOLDERS = Set.of("players", "playerdata", "stats", "advancements");
    private static final Set<String> NOT_WORLD_DATA = Set.of("uid.dat", "session.lock", WorldPlacement.FILE_NAME);

    private SceneryTemplate() {
    }

    static boolean isWorldSave(Path folder) {
        return Files.isDirectory(folder, LinkOption.NOFOLLOW_LINKS)
                && Files.isRegularFile(folder.resolve("level.dat"), LinkOption.NOFOLLOW_LINKS);
    }

    /** Identifies the map's content, so an identical folder is not imported twice. */
    static String fingerprint(Path folder) throws IOException {
        MessageDigest digest = sha256();
        byte[] buffer = new byte[1 << 16];
        for (Path relative : worldFiles(folder)) {
            Path file = folder.resolve(relative);
            digest.update(portableName(relative).getBytes(StandardCharsets.UTF_8));
            digest.update((byte) 0);
            digest.update(ByteBuffer.allocate(Long.BYTES).putLong(Files.size(file)).array());
            try (InputStream input = Files.newInputStream(file)) {
                for (int read = input.read(buffer); read >= 0; read = input.read(buffer)) {
                    digest.update(buffer, 0, read);
                }
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    /**
     * Installs the supplied map as the world Paper will import, keeping any
     * previous copy under {@code retained}. Returns false when the installed
     * world already came from this exact content.
     */
    static boolean install(Path folder, String worldName, Path legacyWorld, Path migratedWorld,
                           Path retained, Path importRecord) throws IOException {
        String fingerprint = fingerprint(folder);
        YamlConfiguration imports = YamlConfiguration.loadConfiguration(importRecord.toFile());
        boolean installed = Files.isDirectory(legacyWorld) || Files.isDirectory(migratedWorld);
        if (installed && fingerprint.equals(imports.getString(worldName))) {
            return false;
        }
        // Copy completely before touching the installed world.
        Path staged = legacyWorld.resolveSibling(worldName + ".importing");
        deleteTree(staged);
        for (Path relative : worldFiles(folder)) {
            Path target = staged.resolve(relative.toString());
            Files.createDirectories(target.getParent());
            Files.copy(folder.resolve(relative), target);
        }
        if (installed) {
            Files.createDirectories(retained);
            if (Files.isDirectory(legacyWorld)) {
                Files.move(legacyWorld, retained.resolve("legacy"));
            }
            if (Files.isDirectory(migratedWorld)) {
                Files.move(migratedWorld, retained.resolve("modern"));
            }
        }
        Files.move(staged, legacyWorld);
        imports.set(worldName, fingerprint);
        Files.createDirectories(importRecord.getParent());
        imports.save(importRecord.toFile());
        return true;
    }

    /** World data only, in a stable order; player state and placement notes stay behind. */
    static List<Path> worldFiles(Path folder) throws IOException {
        List<Path> files = new ArrayList<>();
        try (var paths = Files.walk(folder)) {
            for (Path path : paths.toList()) {
                if (Files.isSymbolicLink(path)) {
                    throw new IOException("Supplied maps must not contain links: " + path);
                }
                Path relative = folder.relativize(path);
                if (!Files.isRegularFile(path)
                        || PLAYER_STATE_FOLDERS.contains(relative.getName(0).toString())
                        || NOT_WORLD_DATA.contains(relative.getFileName().toString())) {
                    continue;
                }
                files.add(relative);
            }
        }
        files.sort(Comparator.comparing(SceneryTemplate::portableName));
        return files;
    }

    private static String portableName(Path relative) {
        return relative.toString().replace('\\', '/');
    }

    private static void deleteTree(Path root) throws IOException {
        if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) {
            return;
        }
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.delete(path);
            }
        }
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
