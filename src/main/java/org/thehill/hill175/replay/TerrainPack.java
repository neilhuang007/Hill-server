package org.thehill.hill175.replay;

import java.io.ByteArrayInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.HashMap;
import java.util.Map;

final class TerrainPack {
    static final String NAME = "terrain-v1.pack";
    static final int MAX_CHUNKS = 768;
    static final int MAX_CHUNK_BYTES = 4 * 1024 * 1024;
    private static final int RECORD_MAGIC = 0x48545001;
    private static final int HEADER_BYTES = 4 * Integer.BYTES;
    private static final long MAX_PACK_BYTES = MAX_CHUNKS * (HEADER_BYTES + (long) MAX_CHUNK_BYTES);

    private record Entry(long offset, int length) { }

    private final Path file;
    private final Map<Long, Entry> entries = new HashMap<>();
    private long indexed;

    TerrainPack(Path sceneFolder) {
        file = sceneFolder.resolve(NAME);
    }

    synchronized void append(ReplayStorage storage, int x, int z, byte[] compressed) throws IOException {
        if (compressed.length == 0 || compressed.length > MAX_CHUNK_BYTES) throw new IOException("Invalid terrain chunk length");
        long previous = size();
        if (indexed != previous) {
            try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
                scan(channel, previous, null);
            }
            if (indexed != previous) throw new IOException("Cannot append past an incomplete terrain record");
        }
        long key = key(x, z);
        if (entries.containsKey(key)) return;
        if (entries.size() >= MAX_CHUNKS) throw new IOException("Too many chunks in terrain pack");
        int added = HEADER_BYTES + compressed.length;
        storage.write(file, added, () -> {
            Files.createDirectories(file.getParent());
            try (FileChannel channel = FileChannel.open(file, StandardOpenOption.CREATE, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
                if (channel.size() != previous) throw new IOException("Terrain pack changed before append");
                channel.position(previous);
                try {
                    ByteBuffer header = ByteBuffer.allocate(HEADER_BYTES).putInt(RECORD_MAGIC).putInt(x).putInt(z).putInt(compressed.length).flip();
                    ByteBuffer[] record = {header, ByteBuffer.wrap(compressed)};
                    while (record[1].hasRemaining()) channel.write(record);
                } catch (IOException failure) {
                    try { channel.truncate(previous); }
                    catch (IOException rollback) { failure.addSuppressed(rollback); }
                    throw failure;
                }
            }
        });
        entries.put(key, new Entry(previous + HEADER_BYTES, compressed.length));
        indexed = previous + added;
    }

    synchronized InputStream open(int x, int z) throws IOException {
        long length = size();
        if (length == 0) return null;
        long key = key(x, z);
        if (indexed == length && !entries.containsKey(key)) return null;
        try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
            if (!entries.containsKey(key)) scan(channel, length, key);
            Entry entry = entries.get(key);
            if (entry == null) return null;
            byte[] payload = new byte[entry.length];
            channel.position(entry.offset);
            readFully(channel, ByteBuffer.wrap(payload));
            return new ByteArrayInputStream(payload);
        }
    }

    private void scan(FileChannel channel, long length, Long wanted) throws IOException {
        if (length < indexed) throw new IOException("Terrain pack shrank during playback");
        ByteBuffer header = ByteBuffer.allocate(HEADER_BYTES);
        while (length - indexed >= HEADER_BYTES) {
            channel.position(indexed);
            readFully(channel, header.clear());
            header.flip();
            if (header.getInt() != RECORD_MAGIC) throw new IOException("Invalid terrain pack header");
            long key = key(header.getInt(), header.getInt());
            int size = header.getInt();
            if (size <= 0 || size > MAX_CHUNK_BYTES) throw new IOException("Invalid packed terrain length");
            long offset = indexed + HEADER_BYTES;
            if (size > length - offset) break;
            if (entries.size() >= MAX_CHUNKS || entries.putIfAbsent(key, new Entry(offset, size)) != null) {
                throw new IOException("Too many or duplicate chunks in terrain pack");
            }
            indexed = offset + size;
            if (wanted != null && wanted == key) break;
        }
    }

    private long size() throws IOException {
        try {
            BasicFileAttributes attrs = Files.readAttributes(file, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attrs.isRegularFile() || attrs.size() > MAX_PACK_BYTES) throw new IOException("Invalid terrain pack type or size");
            return attrs.size();
        } catch (NoSuchFileException absent) {
            return 0;
        }
    }

    private static long key(int x, int z) { return ((long) x << 32) | Integer.toUnsignedLong(z); }

    private static void readFully(FileChannel channel, ByteBuffer buffer) throws IOException {
        while (buffer.hasRemaining()) if (channel.read(buffer) < 0) throw new EOFException("Truncated terrain pack");
    }
}
