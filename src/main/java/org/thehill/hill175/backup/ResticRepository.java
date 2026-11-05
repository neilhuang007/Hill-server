package org.thehill.hill175.backup;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

/** An adapter to Restic. Storage, compression, encryption and deduplication belong to Restic. */
public final class ResticRepository {
    private static final String TAG = "hill175-campus";
    private final Path server;
    private final Path executable;
    private final Path repository;
    private final Path password;

    public ResticRepository(Path server) {
        this.server = server.toAbsolutePath().normalize();
        executable = this.server.resolve("tools/" + (System.getProperty("os.name").startsWith("Windows") ? "restic.exe" : "restic"));
        repository = this.server.resolve("campus-backups/restic");
        password = this.server.resolve("campus-backups/restic-password");
    }

    public void checkInstalled() throws IOException {
        if (!Files.isRegularFile(executable) || !Files.isRegularFile(password) || !Files.isRegularFile(repository.resolve("config"))) {
            throw new IOException("Install campus recovery dependencies with ops/install-campus-recovery.py before starting Paper.");
        }
    }

    public String capture(Path world, String reason) throws IOException {
        Path relative = server.relativize(world.toAbsolutePath().normalize());
        if (relative.startsWith("..") || relative.toString().isEmpty()) throw new IOException("Campus world must be inside the server folder.");
        String output = run(List.of("backup", "--json", "--tag", TAG, "--tag", reason,
                "--exclude", "**/session.lock", relative.toString()), Duration.ofMinutes(10));
        for (String line : output.lines().toList()) {
            JsonObject event = JsonParser.parseString(line).getAsJsonObject();
            if (event.has("snapshot_id")) return event.get("snapshot_id").getAsString();
        }
        throw new IOException("Restic did not report a completed snapshot.");
    }

    public List<Snapshot> list() throws IOException {
        JsonArray data = JsonParser.parseString(run(List.of("snapshots", "--json", "--tag", TAG), Duration.ofMinutes(1))).getAsJsonArray();
        List<Snapshot> snapshots = new ArrayList<>();
        data.forEach(raw -> {
            JsonObject entry = raw.getAsJsonObject();
            snapshots.add(new Snapshot(entry.get("id").getAsString(), java.time.OffsetDateTime.parse(entry.get("time").getAsString()).toInstant().toString()));
        });
        return snapshots.reversed();
    }

    public Snapshot requireSnapshot(String id) throws IOException {
        if (!id.matches("[a-f0-9]{8}|[a-f0-9]{64}")) throw new IOException("Choose an exact snapshot ID from /campusbackup list.");
        var matches = list().stream().filter(snapshot -> snapshot.id().startsWith(id)).toList();
        if (matches.size() != 1) throw new IOException("Snapshot ID is unknown or ambiguous.");
        return matches.getFirst();
    }

    /** Restic verifies restored file contents before WorldEdit is allowed to read them. */
    public Path stage(String id, Path relativeWorld, Path target) throws IOException {
        Snapshot snapshot = requireSnapshot(id);
        if (relativeWorld.isAbsolute() || relativeWorld.normalize().startsWith("..")) throw new IOException("Invalid world path.");
        Files.createDirectories(target);
        run(List.of("restore", snapshot.id(), "--target", target.toString(), "--verify"), Duration.ofMinutes(10));
        Path world = target.resolve(relativeWorld).normalize();
        if (!world.startsWith(target) || !Files.isDirectory(world.resolve("region"))) throw new IOException("Snapshot campus region data is missing.");
        return world;
    }

    public String run(List<String> arguments, Duration timeout) throws IOException {
        List<String> command = new ArrayList<>(List.of(executable.toString(), "--repo", repository.toString(),
                "--password-file", password.toString(), "--compression", "auto"));
        command.addAll(arguments);
        Path log = Files.createTempFile(server.resolve("campus-backups"), "restic-operation-", ".log");
        Process process = null;
        try {
            process = new ProcessBuilder(command).directory(server.toFile()).redirectErrorStream(true).redirectOutput(log.toFile()).start();
            if (!process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS)) {
                process.destroyForcibly();
                process.waitFor();
                throw new IOException("Restic operation timed out. Previous snapshots are preserved.");
            }
            String output = Files.readString(log, StandardCharsets.UTF_8);
            if (process.exitValue() != 0) throw new IOException("Restic failed (" + process.exitValue() + "): " + output.substring(Math.max(0, output.length() - 1500)));
            return output;
        } catch (InterruptedException exception) {
            if (process != null) process.destroyForcibly();
            Thread.currentThread().interrupt();
            throw new IOException("Restic operation interrupted.", exception);
        } finally { Files.deleteIfExists(log); }
    }

    public record Snapshot(String id, String time) { public String shortId() { return id.substring(0, 8); } }
}
