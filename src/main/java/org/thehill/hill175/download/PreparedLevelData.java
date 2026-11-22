package org.thehill.hill175.download;

import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.zip.GZIPInputStream;

final class PreparedLevelData {
    private static final int MAX_BYTES = 32 * 1024 * 1024;
    private PreparedLevelData() { }

    static void verify(Path level) throws IOException {
        if (Files.size(level) > MAX_BYTES) throw new IOException("level.dat is too large to audit.");
        byte[] bytes;
        try (InputStream input = Files.newInputStream(level, LinkOption.NOFOLLOW_LINKS)) {
            byte[] compressed = input.readNBytes(MAX_BYTES + 1);
            if (compressed.length > MAX_BYTES) throw new IOException("level.dat is too large to audit.");
            if (compressed.length >= 2 && (compressed[0] & 255) == 31 && (compressed[1] & 255) == 139) {
                try (GZIPInputStream gzip = new GZIPInputStream(new ByteArrayInputStream(compressed))) {
                    bytes = gzip.readNBytes(MAX_BYTES + 1);
                }
            } else bytes = compressed;
        }
        if (bytes.length > MAX_BYTES) throw new IOException("Expanded level.dat is too large to audit.");
        try (DataInputStream data = new DataInputStream(new ByteArrayInputStream(bytes))) {
            if (data.readUnsignedByte() != 10) throw new IOException("Invalid level.dat NBT root.");
            readName(data);
            payload(data, 10, 0);
            if (data.available() != 0) throw new IOException("Unexpected trailing level.dat data.");
        }
    }

    private static void payload(DataInputStream data, int tag, int depth) throws IOException {
        if (depth > 64) throw new IOException("level.dat exceeds safe NBT depth.");
        switch (tag) {
            case 0 -> { }
            case 1 -> data.skipNBytes(1);
            case 2 -> data.skipNBytes(2);
            case 3, 5 -> data.skipNBytes(4);
            case 4, 6 -> data.skipNBytes(8);
            case 7 -> data.skipNBytes(length(data.readInt()));
            case 8 -> readName(data);
            case 9 -> {
                int itemTag = data.readUnsignedByte();
                int count = length(data.readInt());
                if (itemTag > 12 || (itemTag == 0 && count != 0)) throw new IOException("Invalid NBT list.");
                for (int i = 0; i < count; i++) payload(data, itemTag, depth + 1);
            }
            case 10 -> {
                int count = 0;
                int child;
                while ((child = data.readUnsignedByte()) != 0) {
                    if (++count > 100000 || child > 12) throw new IOException("Invalid level.dat NBT compound.");
                    String name = readName(data);
                    if (name.equalsIgnoreCase("Player")) throw new IOException("Prepared level.dat still contains player data.");
                    payload(data, child, depth + 1);
                }
            }
            case 11 -> data.skipNBytes((long) length(data.readInt()) * 4);
            case 12 -> data.skipNBytes((long) length(data.readInt()) * 8);
            default -> throw new IOException("Unsupported NBT tag.");
        }
    }

    private static int length(int value) throws IOException {
        if (value < 0 || value > MAX_BYTES) throw new IOException("Invalid level.dat NBT length.");
        return value;
    }

    private static String readName(DataInputStream data) throws IOException {
        int length = data.readUnsignedShort();
        return new String(data.readNBytes(length), StandardCharsets.UTF_8);
    }
}
