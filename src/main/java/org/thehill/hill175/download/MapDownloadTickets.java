package org.thehill.hill175.download;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;

final class MapDownloadTickets {
    static final Duration LIFETIME = Duration.ofMinutes(15);
    private static final Duration WINDOW = Duration.ofHours(1);
    private static final long MAX_AUDIT_BYTES = 64L * 1024 * 1024;
    private final SecureRandom random = new SecureRandom();
    private final Path audit;
    private final Map<String, Ticket> active = new HashMap<>();
    private final Map<UUID, ArrayDeque<Instant>> issued = new HashMap<>();

    MapDownloadTickets(Path audit) {
        this.audit = audit;
    }

    synchronized Issue issue(UUID player, Instant now) throws IOException {
        purge(now);
        for (Ticket ticket : active.values()) {
            if (ticket.player().equals(player)) return new Issue(ticket, false);
        }
        if (active.size() >= 64) throw new IllegalStateException("Too many active downloads. Try again later.");
        ArrayDeque<Instant> history = issued.computeIfAbsent(player, ignored -> new ArrayDeque<>());
        if (history.size() >= 3) throw new IllegalStateException("Download limit reached. Try again in an hour.");
        String token = randomBase64(32);
        String fingerprint = randomBase64(24);
        Ticket ticket = new Ticket(player, token, fingerprint, now.plus(LIFETIME));
        String line = now + "\t" + player + "\t" + fingerprint + System.lineSeparator();
        if (Files.isSymbolicLink(audit)) throw new IOException("Audit file cannot be a symlink.");
        byte[] record = line.getBytes(StandardCharsets.UTF_8);
        try (FileChannel channel = FileChannel.open(audit, StandardOpenOption.CREATE, StandardOpenOption.WRITE,
                StandardOpenOption.APPEND, LinkOption.NOFOLLOW_LINKS)) {
            StudentMapDownloadService.privatePermissions(audit, false);
            if (channel.size() + record.length > MAX_AUDIT_BYTES) throw new IOException("Fingerprint audit file is full.");
            ByteBuffer buffer = ByteBuffer.wrap(record);
            while (buffer.hasRemaining()) channel.write(buffer);
            channel.force(true);
        }
        history.addLast(now);
        active.put(token, ticket);
        return new Issue(ticket, true);
    }

    synchronized Ticket lookup(String token, Instant now) {
        purge(now);
        return active.get(token);
    }

    synchronized void revoke(String token) {
        active.remove(token);
    }

    synchronized void purge(Instant now) {
        active.values().removeIf(ticket -> !now.isBefore(ticket.expires()));
        Iterator<Map.Entry<UUID, ArrayDeque<Instant>>> iterator = issued.entrySet().iterator();
        while (iterator.hasNext()) {
            ArrayDeque<Instant> times = iterator.next().getValue();
            while (!times.isEmpty() && !times.peekFirst().plus(WINDOW).isAfter(now)) times.removeFirst();
            if (times.isEmpty()) iterator.remove();
        }
    }

    private String randomBase64(int bytes) {
        byte[] value = new byte[bytes];
        random.nextBytes(value);
        return java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    record Ticket(UUID player, String token, String fingerprint, Instant expires) { }
    record Issue(Ticket ticket, boolean fresh) { }
}
