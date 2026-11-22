package org.thehill.hill175.blueprint;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;

public final class BlueprintBackupStore {
    private final Path folder;

    public BlueprintBackupStore(Path folder) throws IOException {
        this.folder = folder.toAbsolutePath().normalize();
        Files.createDirectories(this.folder);
    }

    public String capture(Map<String, Path> sources, String reason) throws IOException {
        String id = Instant.now().toString().replace(':', '_') + "_" + UUID.randomUUID().toString().substring(0, 8);
        Path pending = BlueprintFiles.child(folder, id + ".partial");
        Files.createDirectory(pending);
        Properties manifest = new Properties();
        manifest.setProperty("createdAt", Instant.now().toString());
        manifest.setProperty("reason", reason);
        for (var source : sources.entrySet()) captureSource(pending, source.getKey(), source.getValue(), manifest);
        BlueprintFiles.writeProperties(pending.resolve("manifest.properties"), manifest);
        BlueprintFiles.move(pending, BlueprintFiles.child(folder, id));
        verify(id);
        return id;
    }

    private void captureSource(Path pending, String name, Path source, Properties manifest) throws IOException {
        Path normalized = source.toAbsolutePath().normalize();
        if (normalized.startsWith(folder) || folder.startsWith(normalized) || Files.isSymbolicLink(source)) {
            throw new IOException("Unsafe blueprint backup source.");
        }
        Path target = BlueprintFiles.child(pending, name);
        if (Files.isDirectory(source)) BlueprintFiles.copyTree(source, target);
        else Files.copy(source, target);
        manifest.setProperty("source." + name, normalized.toString());
        try (var paths = Files.walk(target)) {
            for (Path file : paths.filter(Files::isRegularFile).toList()) {
                String relative = pending.relativize(file).toString().replace('\\', '/');
                manifest.setProperty("sha256." + relative, BlueprintFiles.digest(file));
            }
        }
    }

    public void verify(String id) throws IOException {
        Path backup = BlueprintFiles.child(folder, id);
        Properties manifest = BlueprintFiles.readProperties(backup.resolve("manifest.properties"));
        int count = 0;
        for (String name : manifest.stringPropertyNames()) {
            if (!name.startsWith("sha256.")) continue;
            count++;
            Path file = backup.resolve(name.substring(7)).normalize();
            if (!file.startsWith(backup) || Files.isSymbolicLink(file)
                    || !BlueprintFiles.digest(file).equals(manifest.getProperty(name))) {
                throw new IOException("Backup checksum mismatch: " + name);
            }
        }
        if (count == 0) throw new IOException("Blueprint backup contains no files.");
        try (var paths = Files.walk(backup)) {
            for (Path file : paths.toList()) {
                if (Files.isSymbolicLink(file)) throw new IOException("Symbolic link in backup.");
                if (!Files.isRegularFile(file)) continue;
                String relative = backup.relativize(file).toString().replace('\\', '/');
                if (!relative.equals("manifest.properties") && !manifest.containsKey("sha256." + relative)) {
                    throw new IOException("Unlisted backup file: " + relative);
                }
            }
        }
    }

    public List<String> list() throws IOException {
        try (var files = Files.list(folder)) {
            return files.filter(Files::isDirectory).filter(path -> !path.getFileName().toString().endsWith(".partial"))
                    .filter(path -> Files.isRegularFile(path.resolve("manifest.properties")))
                    .map(path -> path.getFileName().toString()).sorted(Comparator.reverseOrder()).toList();
        }
    }
}
