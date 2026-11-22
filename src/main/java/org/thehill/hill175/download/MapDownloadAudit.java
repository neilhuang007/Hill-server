package org.thehill.hill175.download;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

final class MapDownloadAudit {
    private static final long MAX_FILE_BYTES = 64L * 1024 * 1024;
    private static final Set<String> EVENTS = Set.of("ISSUED", "READY", "BUILD_FAILED", "STARTED", "COMPLETED",
            "LINK_EXPIRED", "EXPIRED", "DISCONNECTED");
    private static final int OUTCOME_RESERVATION = 512;
    private final Path file;
    private final long maximumBytes;
    private final java.util.Map<String, Integer> activeTransfers = new java.util.HashMap<>();
    private long reservedBytes;

    MapDownloadAudit(Path file) { this(file, MAX_FILE_BYTES); }

    MapDownloadAudit(Path file, long maximumBytes) {
        this.file = file;
        this.maximumBytes = maximumBytes;
    }

    synchronized void append(Instant time, String event, UUID player, String fingerprint, String mapDigest, long bytes) throws IOException {
        if (!EVENTS.contains(event) || !fingerprint.matches("[A-Za-z0-9_-]{32}")
                || !(mapDigest.equals("PENDING") || mapDigest.matches("[0-9a-f]{64}")) || bytes < 0)
            throw new IllegalArgumentException("Invalid download audit entry.");
        byte[] line = (time + "\t" + event + "\t" + player + "\t" + fingerprint + "\t" + mapDigest + "\t" + bytes + "\n")
                .getBytes(StandardCharsets.UTF_8);
        boolean starts = event.equals("STARTED");
        boolean finishes = Set.of("COMPLETED", "EXPIRED", "DISCONNECTED").contains(event)
                && activeTransfers.getOrDefault(fingerprint, 0) > 0;
        long nextReserved = reservedBytes + (starts ? OUTCOME_RESERVATION : 0)
                - (finishes ? OUTCOME_RESERVATION : 0);
        if (line.length > OUTCOME_RESERVATION) throw new IOException("Download audit entry exceeds reserved size.");
        if (Files.isSymbolicLink(file)) throw new IOException("Download audit file cannot be a symlink.");
        try (FileChannel channel = FileChannel.open(file, StandardOpenOption.CREATE, StandardOpenOption.WRITE,
                StandardOpenOption.APPEND, LinkOption.NOFOLLOW_LINKS)) {
            StudentMapDownloadService.privatePermissions(file, false);
            if (channel.size() + line.length + nextReserved > maximumBytes)
                throw new IOException("Download audit file is full; archive it under the retention policy before resuming downloads.");
            ByteBuffer buffer = ByteBuffer.wrap(line);
            while (buffer.hasRemaining()) channel.write(buffer);
            channel.force(true);
            reservedBytes = nextReserved;
            if (starts) activeTransfers.merge(fingerprint, 1, Integer::sum);
            if (finishes) activeTransfers.computeIfPresent(fingerprint,
                    (ignored, count) -> count == 1 ? null : count - 1);
        }
    }
}
