package org.thehill.hill175.replay;

import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;

/** Removes hidden/untracked coordinates before movement is retained in an archive. */
final class PacketReplayMovement {
    private PacketReplayMovement() { }

    static byte[] visible(Player viewer, byte[] payload) {
        Set<Integer> allowed = new HashSet<>();
        allowed.add(viewer.getEntityId());
        for (Entity entity : viewer.getNearbyEntities(128, 128, 128)) {
            if (PacketReplayBootstrap.mayCapture(viewer, entity)) allowed.add(entity.getEntityId());
        }
        return filter(payload, allowed);
    }

    static byte[] filter(byte[] payload, Set<Integer> allowed) {
        ByteBuffer input = ByteBuffer.wrap(payload);
        if (readVarInt(input) != 1) throw new IllegalArgumentException("Unsupported movement dimension count");
        int nameBytes = readVarInt(input);
        if (nameBytes < 1 || nameBytes > 256 || input.remaining() < nameBytes) throw new IllegalArgumentException("Invalid movement dimension");
        input.position(input.position() + nameBytes);
        int headerEnd = input.position();
        int count = readVarInt(input);
        if (count < 0 || count > 100_000) throw new IllegalArgumentException("Invalid movement entity count");
        ArrayList<int[]> records = new ArrayList<>();
        for (int index = 0; index < count; index++) {
            int start = input.position();
            int id = readVarInt(input);
            if (input.remaining() < 37) throw new IllegalArgumentException("Truncated movement record");
            input.position(input.position() + 37);
            if (allowed.contains(id)) records.add(new int[]{start, input.position()});
        }
        if (input.hasRemaining()) throw new IllegalArgumentException("Trailing movement data");
        if (records.isEmpty()) return null;
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write(payload, 0, headerEnd);
        writeVarInt(output, records.size());
        for (int[] record : records) output.write(payload, record[0], record[1] - record[0]);
        return output.toByteArray();
    }

    private static int readVarInt(ByteBuffer input) {
        int result = 0;
        for (int shift = 0; shift < 35; shift += 7) {
            if (!input.hasRemaining()) throw new IllegalArgumentException("Truncated movement varint");
            int next = input.get() & 255;
            result |= (next & 127) << shift;
            if ((next & 128) == 0) return result;
        }
        throw new IllegalArgumentException("Oversized movement varint");
    }

    private static void writeVarInt(ByteArrayOutputStream output, int value) {
        while ((value & ~127) != 0) {
            output.write((value & 127) | 128);
            value >>>= 7;
        }
        output.write(value);
    }
}
