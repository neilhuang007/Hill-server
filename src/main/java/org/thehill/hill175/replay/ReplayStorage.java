package org.thehill.hill175.replay;

import org.bukkit.plugin.java.JavaPlugin;

import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

final class ReplayStorage {
    @FunctionalInterface interface IOAction { void run() throws IOException; }
    static final class Full extends IOException {
        Full() { this("Build replay storage budget or free-space reserve reached."); }
        Full(String message) { super(message); }
    }

    private static final long MIN_ALLOCATION_UNIT = 4096;
    private static final long MIB = 1024L * 1024;
    private final Path root;
    private final long limit;
    private final long reserve;
    private final long headroom;
    private FileStore volume;
    private long allocationUnit = MIN_ALLOCATION_UNIT;
    private long used;
    private long blockedWrite;
    private volatile boolean paused;

    ReplayStorage(JavaPlugin plugin) {
        this(plugin.getDataFolder().toPath().resolve("build-replays"),
                Math.clamp(plugin.getConfig().getLong("build-replay.max-storage-mib", 1024), 16L, Integer.MAX_VALUE) * MIB,
                minimumFreeBytes(plugin));
    }

    static long minimumFreeBytes(JavaPlugin plugin) {
        return Math.clamp(plugin.getConfig().getLong("build-replay.min-free-mib", 2048), 1L, Integer.MAX_VALUE) * MIB;
    }

    ReplayStorage(Path root, long limit, long reserve) {
        this.root = root.toAbsolutePath().normalize();
        this.limit = limit;
        this.reserve = reserve;
        headroom = Math.min(64 * MIB, limit / 10);
    }

    synchronized void initialize() throws IOException {
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Missing or linked build replay archive.");
        volume = Files.getFileStore(root);
        try { allocationUnit = Math.max(MIN_ALLOCATION_UNIT, volume.getBlockSize()); }
        catch (UnsupportedOperationException ignored) { }
        recount();
    }

    boolean paused() { return paused; }

    long footprint(long bytes) { return Math.multiplyExact(Math.ceilDiv(bytes, allocationUnit), allocationUnit); }

    synchronized void write(Path target, long bytes, IOAction action) throws IOException {
        if (bytes < 0 || volume == null) throw new IOException("Build replay storage is not ready.");
        if (paused) throw new Full();
        long previous;
        try { previous = Files.readAttributes(target, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).size(); }
        catch (NoSuchFileException absent) { previous = 0; }
        long growth = footprint(Math.addExact(previous, bytes)) - footprint(previous);
        if (!fits(growth, volume.getUsableSpace())) {
            blockedWrite = Math.max(blockedWrite, growth);
            paused = true;
            throw new Full();
        }
        try {
            action.run();
        } catch (IOException failure) {
            recount();
            if (!fits(growth, volume.getUsableSpace())) {
                paused = true;
                blockedWrite = Math.max(blockedWrite, growth);
                Full full = new Full();
                full.addSuppressed(failure);
                throw full;
            }
            throw failure;
        }
        used += growth;
    }

    synchronized void remove(IOAction action) throws IOException {
        try { action.run(); }
        finally { recount(); }
    }

    synchronized boolean needsPrune() throws IOException { return reclaimTarget() > 0; }

    synchronized long reclaimTarget() throws IOException {
        long free = volume.getUsableSpace();
        long margin = Math.max(headroom, blockedWrite);
        if (!paused && used < limit - headroom / 4 && free >= reserve + headroom / 4) return 0;
        return Math.max(0, Math.max(used - (limit - margin), reserve + margin - free));
    }

    synchronized void checkSpace(boolean mayResume) throws IOException {
        if (!fits(Math.max(1, blockedWrite), volume.getUsableSpace())) paused = true;
        else if (mayResume) {
            blockedWrite = 0;
            paused = false;
        }
    }

    private boolean fits(long bytes, long free) { return bytes <= limit - used && bytes <= free - reserve - 3 * allocationUnit; }

    synchronized void recount() throws IOException {
        long[] total = {0};
        Files.walkFileTree(root, new SimpleFileVisitor<>() {
            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) {
                if (attributes.isRegularFile()) total[0] = Math.addExact(total[0], footprint(attributes.size()));
                return FileVisitResult.CONTINUE;
            }
        });
        used = total[0];
    }
}
