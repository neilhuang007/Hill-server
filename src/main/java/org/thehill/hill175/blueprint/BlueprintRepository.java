package org.thehill.hill175.blueprint;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Properties;
import java.util.UUID;

public final class BlueprintRepository {
    static final int MAXIMUM_CHANGES = 65_536;
    private static final int FORMAT = 0x48425031;
    private static final int MAXIMUM_STRUCTURE_BYTES = 1_048_576;
    private static final long MAXIMUM_CHANGE_BYTES = 268_435_456L;
    private final Path folder;
    private volatile List<Summary> summaries = List.of();
    private IOException cacheFailure;

    public enum Status { PENDING, APPROVED, REJECTED, WITHDRAWN }

    public record Summary(UUID id, UUID entryId, String author, String title, String baseRevision,
                          Instant createdAt, Status status, String reviewer, String reason, int changedBlocks) {
        public Summary {
            java.util.Objects.requireNonNull(id);
            java.util.Objects.requireNonNull(entryId);
            java.util.Objects.requireNonNull(createdAt);
            java.util.Objects.requireNonNull(status);
            java.util.Objects.requireNonNull(reviewer);
            java.util.Objects.requireNonNull(reason);
            if (author == null || author.isBlank() || title == null || title.isBlank() || baseRevision == null || baseRevision.isBlank()
                    || changedBlocks < 1 || changedBlocks > MAXIMUM_CHANGES) throw new IllegalArgumentException("Invalid proposal summary metadata.");
        }
    }

    public record Submission(UUID id, UUID entryId, String author, String title, String baseRevision,
                             Instant createdAt, Status status, String reviewer, String reason, List<BlockChange> changes) {
        public Submission {
            java.util.Objects.requireNonNull(id);
            java.util.Objects.requireNonNull(entryId);
            java.util.Objects.requireNonNull(createdAt);
            java.util.Objects.requireNonNull(status);
            java.util.Objects.requireNonNull(reviewer);
            java.util.Objects.requireNonNull(reason);
            if (author == null || author.isBlank() || title == null || title.isBlank() || baseRevision == null || baseRevision.isBlank()) {
                throw new IllegalArgumentException("Submission author, title and baseline revision are required.");
            }
            changes = List.copyOf(changes);
        }
        public Submission decide(Status decision, String actor, String detail) {
            if (status != Status.PENDING || decision == Status.PENDING) throw new IllegalStateException("Submission is already decided.");
            return new Submission(id, entryId, author, title, baseRevision, createdAt, decision, actor, detail, changes);
        }
    }

    public BlueprintRepository(Path folder) throws IOException {
        this.folder = folder;
        Files.createDirectories(folder);
        try { loadSummaries(); }
        catch (IOException exception) { cacheFailure = exception; }
    }

    public List<Summary> summaries() throws IOException { requireCache(); return summaries; }

    private void requireCache() throws IOException {
        if (cacheFailure != null) throw new IOException("Blueprint repository cache could not be initialized safely. Restart after resolving the saved data error.", cacheFailure);
    }

    public boolean exists(UUID id) { return Files.isDirectory(folder.resolve(id.toString())); }

    public void create(Submission submission) throws IOException {
        requireCache();
        if (submission.status() != Status.PENDING || submission.changes().isEmpty()) throw new IllegalArgumentException("Invalid proposal.");
        Path target = folder.resolve(submission.id().toString());
        if (Files.exists(target)) throw new IOException("Submission already exists.");
        Path staged = folder.resolve(submission.id() + ".partial");
        Files.createDirectory(staged);
        BlueprintFiles.atomicWrite(staged.resolve("changes.bin"), encode(submission.changes()));
        saveMetadata(submission, staged);
        BlueprintFiles.move(staged, target);
        cacheCommitted(submission);
    }

    public void saveDecision(Submission submission) throws IOException {
        Submission original = read(submission.id());
        if (original.status() != Status.PENDING || submission.status() == Status.PENDING
                || !original.decide(submission.status(), submission.reviewer(), submission.reason()).equals(submission)) {
            throw new IllegalStateException("Invalid submission decision.");
        }
        saveMetadata(submission, folder.resolve(submission.id().toString()));
        cacheCommitted(submission);
    }

    private void saveMetadata(Submission submission, Path target) throws IOException {
        Properties values = new Properties();
        values.setProperty("id", submission.id().toString());
        values.setProperty("entry", submission.entryId().toString());
        values.setProperty("author", submission.author());
        values.setProperty("title", submission.title());
        values.setProperty("baseRevision", submission.baseRevision());
        values.setProperty("createdAt", submission.createdAt().toString());
        values.setProperty("status", submission.status().name());
        values.setProperty("reviewer", submission.reviewer());
        values.setProperty("reason", submission.reason());
        values.setProperty("changedBlocks", Integer.toString(submission.changes().size()));
        values.setProperty("changesSha256", BlueprintFiles.digest(target.resolve("changes.bin")));
        BlueprintFiles.writeProperties(target.resolve("submission.properties"), values);
    }

    public Submission read(UUID id) throws IOException {
        requireCache();
        Path target = folder.resolve(id.toString());
        Properties values = BlueprintFiles.readProperties(target.resolve("submission.properties"));
        if (!id.toString().equals(values.getProperty("id"))) throw new IOException("Submission identity mismatch.");
        if (Files.size(target.resolve("changes.bin")) > MAXIMUM_CHANGE_BYTES
                || !BlueprintFiles.digest(target.resolve("changes.bin")).equals(values.getProperty("changesSha256"))) {
            throw new IOException("Submission snapshot size or checksum mismatch.");
        }
        try {
            List<BlockChange> changes = decode(Files.readAllBytes(target.resolve("changes.bin")));
            if (changes.isEmpty()) throw new IOException("Submission has no changes.");
            if (Integer.parseInt(values.getProperty("changedBlocks", Integer.toString(changes.size()))) != changes.size()) {
                throw new IOException("Submission changed-block count mismatch.");
            }
            return new Submission(id, UUID.fromString(values.getProperty("entry")), values.getProperty("author"),
                    values.getProperty("title"), values.getProperty("baseRevision"), Instant.parse(values.getProperty("createdAt")),
                    Status.valueOf(values.getProperty("status")), values.getProperty("reviewer"), values.getProperty("reason"), changes);
        } catch (RuntimeException exception) { throw new IOException("Invalid submission metadata: " + id, exception); }
    }

    public List<Submission> list() throws IOException {
        List<Submission> result = new ArrayList<>();
        for (Summary summary : summaries()) result.add(read(summary.id()));
        return List.copyOf(result);
    }

    private void loadSummaries() throws IOException {
        List<Summary> loaded = new ArrayList<>();
        try (var entries = Files.list(folder)) {
            for (Path entry : entries.filter(Files::isDirectory).toList()) {
                String name = entry.getFileName().toString();
                if (name.endsWith(".partial")) continue;
                try { loaded.add(summarize(read(UUID.fromString(name)))); }
                catch (IllegalArgumentException exception) { throw new IOException("Invalid submission directory: " + name, exception); }
            }
        }
        loaded.sort(Comparator.comparing(Summary::createdAt).reversed());
        summaries = List.copyOf(loaded);
    }

    private void cacheCommitted(Submission submission) {
        List<Summary> updated = new ArrayList<>(summaries);
        updated.removeIf(summary -> summary.id().equals(submission.id()));
        updated.add(summarize(submission));
        updated.sort(Comparator.comparing(Summary::createdAt).reversed());
        summaries = List.copyOf(updated);
    }

    private static Summary summarize(Submission submission) {
        return new Summary(submission.id(), submission.entryId(), submission.author(), submission.title(), submission.baseRevision(),
                submission.createdAt(), submission.status(), submission.reviewer(), submission.reason(), submission.changes().size());
    }

    static byte[] encode(List<BlockChange> changes) throws IOException { return encode(changes, MAXIMUM_CHANGES); }

    static byte[] encode(List<BlockChange> changes, int maximumCount) throws IOException {
        long maximumBytes = maximumBytes(maximumCount);
        if (changes.size() > maximumCount) throw new IOException("Submission is too large.");
        var bytes = new ByteArrayOutputStream();
        try (var output = new DataOutputStream(bytes)) {
            output.writeInt(FORMAT);
            output.writeInt(changes.size());
            for (BlockChange change : changes) {
                output.writeInt(change.position().blockX());
                output.writeInt(change.position().blockY());
                output.writeInt(change.position().blockZ());
                writeSnapshot(output, change.before());
                writeSnapshot(output, change.after());
                if (bytes.size() > maximumBytes) throw new IOException("Block entity proposal data is too large.");
            }
        }
        return bytes.toByteArray();
    }

    private static void writeSnapshot(DataOutputStream output, BlockSnapshot snapshot) throws IOException {
        output.writeUTF(snapshot.blockData());
        byte[] structure = snapshot.structure();
        if (structure.length > MAXIMUM_STRUCTURE_BYTES) throw new IOException("Block entity snapshot is too large.");
        output.writeInt(structure.length);
        output.write(structure);
    }

    static List<BlockChange> decode(byte[] bytes) throws IOException { return decode(bytes, MAXIMUM_CHANGES); }

    static List<BlockChange> decode(byte[] bytes, int maximumCount) throws IOException {
        if (bytes.length > maximumBytes(maximumCount)) throw new IOException("Snapshot data is too large.");
        try (var input = new DataInputStream(new ByteArrayInputStream(bytes))) {
            if (input.readInt() != FORMAT) throw new IOException("Unsupported blueprint snapshot.");
            int count = input.readInt();
            if (count < 0 || count > maximumCount) throw new IOException("Invalid blueprint change count.");
            List<BlockChange> changes = new ArrayList<>(count);
            var positions = new java.util.HashSet<BlockPosition>();
            for (int index = 0; index < count; index++) {
                BlockPosition position = new BlockPosition(input.readInt(), input.readInt(), input.readInt());
                if (!positions.add(position)) throw new IOException("Duplicate blueprint position.");
                changes.add(new BlockChange(position, readSnapshot(input), readSnapshot(input)));
            }
            if (input.read() != -1) throw new IOException("Unexpected trailing blueprint data.");
            return List.copyOf(changes);
        }
    }

    private static long maximumBytes(int maximumCount) {
        return Math.max(MAXIMUM_CHANGE_BYTES, MAXIMUM_CHANGE_BYTES / MAXIMUM_CHANGES * (long) maximumCount);
    }

    private static BlockSnapshot readSnapshot(DataInputStream input) throws IOException {
        String data = input.readUTF();
        int length = input.readInt();
        if (length < 0 || length > MAXIMUM_STRUCTURE_BYTES) throw new IOException("Invalid block entity size.");
        byte[] structure = input.readNBytes(length);
        if (structure.length != length) throw new IOException("Incomplete block entity snapshot.");
        return new BlockSnapshot(data, structure);
    }
}
