package org.thehill.hill175.backup;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;

/** Immutable file snapshots with verified staging and resumable directory replacement. */
public final class CampusBackupStore {
    private final Path folder;

    public CampusBackupStore(Path folder) throws IOException {
        this.folder = folder.toAbsolutePath().normalize();
        Files.createDirectories(this.folder);
    }

    public String capture(Map<String, Path> sources, String reason) throws IOException {
        String id = Instant.now().toString().replace(':', '_') + "_" + UUID.randomUUID().toString().substring(0, 8);
        Path pending = BackupFiles.child(folder, id + ".partial");
        Files.createDirectory(pending);
        Properties manifest = new Properties();
        manifest.setProperty("createdAt", Instant.now().toString());
        manifest.setProperty("reason", reason);
        for (var source : sources.entrySet()) captureSource(pending, source.getKey(), source.getValue(), manifest);
        BackupFiles.writeProperties(pending.resolve("manifest.properties"), manifest);
        BackupFiles.move(pending, BackupFiles.child(folder, id));
        verify(id);
        return id;
    }

    private void captureSource(Path pending, String name, Path source, Properties manifest) throws IOException {
        Path target = BackupFiles.child(pending, name);
        if (source.toAbsolutePath().normalize().startsWith(folder) || folder.startsWith(source.toAbsolutePath().normalize())) {
            throw new IOException("Backup source overlaps backup storage.");
        }
        BackupFiles.copyTree(source, target);
        manifest.setProperty("source." + name, "directory");
        try (var paths = Files.walk(target)) {
            for (Path file : paths.filter(Files::isRegularFile).toList()) {
                String relative = pending.relativize(file).toString().replace('\\', '/');
                manifest.setProperty("sha256." + relative, BackupFiles.digest(file));
            }
        }
    }

    public void verify(String id) throws IOException {
        Path backup = BackupFiles.child(folder, id);
        Properties manifest = BackupFiles.readProperties(backup.resolve("manifest.properties"));
        for (String name : manifest.stringPropertyNames()) {
            if (!name.startsWith("sha256.")) continue;
            Path file = backup.resolve(name.substring(7)).normalize();
            if (!file.startsWith(backup) || Files.isSymbolicLink(file)
                    || !BackupFiles.digest(file).equals(manifest.getProperty(name))) {
                throw new IOException("Backup checksum mismatch: " + name);
            }
        }
        try (var paths = Files.walk(backup)) {
            for (Path file : paths.toList()) {
                if (Files.isSymbolicLink(file)) throw new IOException("Symbolic links are not accepted in backups: " + file);
                if (Files.isRegularFile(file)) verifyListedFile(backup, manifest, file);
            }
        }
    }

    private void verifyListedFile(Path backup, Properties manifest, Path file) throws IOException {
        String relative = backup.relativize(file).toString().replace('\\', '/');
        if (!relative.equals("manifest.properties") && !manifest.containsKey("sha256." + relative)) {
            throw new IOException("Unlisted backup file: " + relative);
        }
    }

    public List<String> list() throws IOException {
        try (var files = Files.list(folder)) {
            return files.filter(Files::isDirectory).filter(path -> !path.getFileName().toString().endsWith(".partial"))
                    .filter(path -> Files.isRegularFile(path.resolve("manifest.properties")))
                    .map(path -> path.getFileName().toString()).sorted(Comparator.reverseOrder()).toList();
        }
    }

    public Map<String, Path> stageRestore(String id, Path stage) throws IOException {
        verify(id);
        Files.createDirectory(stage);
        Path backup = BackupFiles.child(folder, id);
        Properties manifest = BackupFiles.readProperties(backup.resolve("manifest.properties"));
        Map<String, Path> result = new LinkedHashMap<>();
        for (String key : manifest.stringPropertyNames().stream().sorted().toList()) {
            if (!key.startsWith("source.")) continue;
            String name = key.substring(7);
            Path target = BackupFiles.child(stage, name);
            BackupFiles.copyTree(BackupFiles.child(backup, name), target);
            result.put(name, target);
        }
        if (result.isEmpty()) throw new IOException("Backup has no restorable sources.");
        verifyStagedFiles(stage, manifest);
        return result;
    }

    private static void verifyStagedFiles(Path stage, Properties manifest) throws IOException {
        for (String key : manifest.stringPropertyNames()) {
            if (!key.startsWith("sha256.")) continue;
            Path file = stage.resolve(key.substring(7)).normalize();
            if (!file.startsWith(stage) || !BackupFiles.digest(file).equals(manifest.getProperty(key))) {
                throw new IOException("Staged restore checksum mismatch: " + key);
            }
        }
    }

    /** All targets are provided by the operator, never taken from backup absolute paths. */
    public static void replaceStaged(Map<String, Path> staged, Map<String, Path> destinations, Path preserved) throws IOException {
        Files.createDirectories(preserved);
        for (var source : staged.entrySet()) replaceOne(source.getKey(), source.getValue(), destinations, preserved);
    }

    private static void replaceOne(String name, Path stage, Map<String, Path> destinations, Path preserved) throws IOException {
        Path destination = destinations.get(name);
        if (destination == null) throw new IOException("No approved restore destination for " + name);
        Path previous = BackupFiles.child(preserved, name);
        if (!Files.exists(stage)) {
            if (!Files.isDirectory(destination)) throw new IOException("Incomplete restore for " + name);
            return;
        }
        if (Files.exists(destination)) {
            if (Files.exists(previous)) throw new IOException("Ambiguous restore state for " + name);
            BackupFiles.move(destination, previous);
        }
        Files.createDirectories(destination.getParent());
        BackupFiles.move(stage, destination);
    }
}
