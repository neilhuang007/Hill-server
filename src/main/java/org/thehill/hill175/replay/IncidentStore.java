package org.thehill.hill175.replay;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.stream.Stream;

final class IncidentStore implements AutoCloseable {
    static final int SEGMENT_BYTES = 8 * 1024 * 1024;
    static final long TOTAL_BYTES = 128L * 1024 * 1024;
    static final long QUERY_BYTES = 16L * 1024 * 1024;
    private static final int QUEUE_SIZE = 4096;
    private final Path directory;
    private final Logger logger;
    private final ArrayBlockingQueue<IncidentRecord> pending = new ArrayBlockingQueue<>(QUEUE_SIZE);
    private final AtomicLong lastWarning = new AtomicLong();
    private final Thread writer;
    private volatile boolean running = true;
    private BufferedWriter output;
    private Path current;
    private long size;

    IncidentStore(Path directory, Logger logger) {
        this.directory = directory;
        this.logger = logger;
        writer = Thread.ofPlatform().daemon(true).name("hill-incident-writer").start(this::writeLoop);
    }

    boolean append(IncidentRecord record) {
        if (running && pending.offer(record)) return true;
        warn("Incident replay overloaded: event not recorded; check disk and server load", null);
        return false;
    }

    private void warn(String message, Exception error) {
        long now = System.currentTimeMillis();
        long before = lastWarning.get();
        if (now - before >= 60_000 && lastWarning.compareAndSet(before, now)) {
            if (error == null) logger.warning(message);
            else logger.log(Level.WARNING, message, error);
        }
    }

    private void writeLoop() {
        try {
            Files.createDirectories(directory);
            prune();
            while (running || !pending.isEmpty()) {
                IncidentRecord record = pending.poll(250, TimeUnit.MILLISECONDS);
                if (record == null) continue;
                try {
                    String line = record.serialize() + "\n";
                    int bytes = line.getBytes(StandardCharsets.UTF_8).length;
                    open(record.time(), bytes);
                    output.write(line);
                    output.flush();
                    size += bytes;
                } catch (IOException error) {
                    warn("Incident replay disk write failed: event not recorded", error);
                    closeOutput();
                }
            }
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        } catch (IOException error) {
            warn("Incident replay storage unavailable: recording disabled", error);
        } finally {
            closeOutput();
            if (!pending.isEmpty()) logger.warning("Incident replay stopped with " + pending.size() + " unrecorded events");
        }
    }

    private void open(long time, int bytes) throws IOException {
        String day = LocalDate.ofInstant(Instant.ofEpochMilli(time), ZoneOffset.UTC).toString();
        if (output != null && current.getFileName().toString().startsWith("incident-" + day + "-") && size + bytes <= SEGMENT_BYTES) return;
        closeOutput();
        Files.createDirectories(directory);
        int index = 0;
        Path candidate;
        do {
            candidate = directory.resolve("incident-" + day + "-" + String.format("%05d", index++) + ".log");
        } while (Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS) && Files.size(candidate) + bytes > SEGMENT_BYTES);
        current = candidate;
        size = Files.exists(candidate, LinkOption.NOFOLLOW_LINKS) ? Files.size(candidate) : 0;
        output = Files.newBufferedWriter(candidate, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        prune();
    }

    private void closeOutput() {
        if (output == null) return;
        try { output.close(); }
        catch (IOException error) { warn("Incident replay failed to flush recording", error); }
        output = null;
    }

    private List<Path> segments() throws IOException {
        if (!Files.isDirectory(directory)) return List.of();
        try (Stream<Path> files = Files.list(directory)) {
            return files.filter(file -> Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS))
                    .filter(file -> file.getFileName().toString().matches("incident-\\d{4}-\\d{2}-\\d{2}-\\d{5}\\.log"))
                    .sorted(Comparator.comparing(file -> file.getFileName().toString())).toList();
        }
    }

    private void prune() throws IOException {
        List<Path> files = segments();
        long total = 0;
        long cutoff = System.currentTimeMillis() - TimeUnit.DAYS.toMillis(7);
        for (Path file : files) total += Files.size(file);
        for (Path file : files) {
            long bytes = Files.size(file);
            String day = file.getFileName().toString().substring(9, 19);
            boolean expired;
            try { expired = LocalDate.parse(day).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli() < cutoff - TimeUnit.DAYS.toMillis(1); }
            catch (RuntimeException ignored) { expired = true; }
            if (file.equals(current) || (!expired && total <= TOTAL_BYTES)) continue;
            Files.deleteIfExists(file);
            total -= bytes;
        }
    }

    Result query(long since, String actor, int limit) throws IOException {
        ArrayDeque<IncidentRecord> matches = new ArrayDeque<>();
        List<Path> files = new ArrayList<>(segments());
        files.sort(Comparator.comparing((Path path) -> path.getFileName().toString()).reversed());
        long inspected = 0;
        boolean partial = false;
        for (Path file : files) {
            long bytes;
            try { bytes = Files.size(file); }
            catch (IOException ignored) { continue; }
            if (inspected + bytes > QUERY_BYTES) { partial = true; break; }
            inspected += bytes;
            ArrayDeque<IncidentRecord> inFile = new ArrayDeque<>();
            try (var reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    try {
                        IncidentRecord record = IncidentRecord.parse(line);
                        if (record.matches(since, actor)) {
                            inFile.addLast(record);
                            if (inFile.size() > limit) inFile.removeFirst();
                        }
                    } catch (IllegalArgumentException ignored) { }
                }
            } catch (java.nio.file.NoSuchFileException ignored) { }
            for (var iterator = inFile.descendingIterator(); iterator.hasNext();) {
                matches.addFirst(iterator.next());
                if (matches.size() > limit) matches.removeFirst();
            }
            if (file.getFileName().toString().substring(9, 19).compareTo(LocalDate.ofInstant(Instant.ofEpochMilli(since), ZoneOffset.UTC).toString()) < 0) break;
        }
        List<IncidentRecord> records = new ArrayList<>(matches);
        records.sort(Comparator.comparingLong(IncidentRecord::time));
        return new Result(records, partial);
    }

    record Result(List<IncidentRecord> records, boolean partial) { }

    @Override public void close() {
        running = false;
        try { writer.join(5000); }
        catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
        if (writer.isAlive()) logger.warning("Incident replay writer has not finished draining its queue; check incident logs");
    }
}
