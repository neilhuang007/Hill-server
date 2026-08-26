package org.thehill.hill175.world;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.block.data.BlockData;

import java.io.BufferedInputStream;
import java.io.Closeable;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.PushbackInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.GZIPInputStream;

final class StructureNbtLoader implements Closeable {
    private static final byte TAG_END = 0;
    private static final byte TAG_BYTE = 1;
    private static final byte TAG_SHORT = 2;
    private static final byte TAG_INT = 3;
    private static final byte TAG_LONG = 4;
    private static final byte TAG_FLOAT = 5;
    private static final byte TAG_DOUBLE = 6;
    private static final byte TAG_BYTE_ARRAY = 7;
    private static final byte TAG_STRING = 8;
    private static final byte TAG_LIST = 9;
    private static final byte TAG_COMPOUND = 10;
    private static final byte TAG_INT_ARRAY = 11;
    private static final byte TAG_LONG_ARRAY = 12;
    private static final Pattern DUSTED_BLOCK_PATTERN = Pattern.compile("^minecraft:(suspicious_(?:gravel|sand))_([0-3])$");

    private final DataInputStream input;
    private final World world;
    private final int originX;
    private final int originY;
    private final int originZ;
    private final List<BlockData> palette;
    private final Metadata metadata;
    private int remainingBlocks;

    private StructureNbtLoader(
            DataInputStream input,
            World world,
            int originX,
            int originY,
            int originZ,
            List<BlockData> palette,
            Metadata metadata,
            int remainingBlocks
    ) {
        this.input = input;
        this.world = world;
        this.originX = originX;
        this.originY = originY;
        this.originZ = originZ;
        this.palette = palette;
        this.metadata = metadata;
        this.remainingBlocks = remainingBlocks;
    }

    static Metadata readMetadata(Path path) throws IOException {
        try (DataInputStream input = openInput(path)) {
            Header header = readHeader(input, false);
            return new Metadata(path, header.sizeX(), header.sizeY(), header.sizeZ(), header.blockCount());
        }
    }

    static StructureNbtLoader open(Path path, World world, int originX, int originY, int originZ) throws IOException {
        DataInputStream input = openInput(path);
        Header header;
        try {
            header = readHeader(input, true);
        } catch (IOException exception) {
            input.close();
            throw exception;
        }
        Metadata metadata = new Metadata(path, header.sizeX(), header.sizeY(), header.sizeZ(), header.blockCount());
        return new StructureNbtLoader(input, world, originX, originY, originZ, header.palette(), metadata, header.blockCount());
    }

    Metadata metadata() {
        return metadata;
    }

    boolean isFinished() {
        return remainingBlocks <= 0;
    }

    int importNextBlocks(int maxBlocks) throws IOException {
        int imported = 0;
        while (imported < maxBlocks && remainingBlocks > 0) {
            importSingleBlock();
            remainingBlocks--;
            imported++;
        }
        return imported;
    }

    @Override
    public void close() throws IOException {
        input.close();
    }

    private void importSingleBlock() throws IOException {
        int stateIndex = -1;
        int x = 0;
        int y = 0;
        int z = 0;
        while (true) {
            byte tagType = input.readByte();
            if (tagType == TAG_END) {
                break;
            }
            String name = input.readUTF();
            switch (name) {
                case "state" -> {
                    if (tagType != TAG_INT) {
                        throw new IOException("Unexpected block state tag type: " + tagType);
                    }
                    stateIndex = input.readInt();
                }
                case "pos" -> {
                    if (tagType != TAG_LIST) {
                        throw new IOException("Unexpected block pos tag type: " + tagType);
                    }
                    int[] position = readIntList(input);
                    if (position.length < 3) {
                        throw new IOException("Block position list was too short");
                    }
                    x = position[0];
                    y = position[1];
                    z = position[2];
                }
                default -> skipPayload(input, tagType);
            }
        }
        if (stateIndex < 0 || stateIndex >= palette.size()) {
            throw new IOException("Block referenced invalid palette index " + stateIndex);
        }
        int worldX = originX + x;
        int worldY = originY + y;
        int worldZ = originZ + z;
        world.getChunkAt(worldX >> 4, worldZ >> 4);
        world.getBlockAt(worldX, worldY, worldZ).setBlockData(palette.get(stateIndex), false);
    }

    private static Header readHeader(DataInputStream input, boolean parsePalette) throws IOException {
        byte rootType = input.readByte();
        if (rootType != TAG_COMPOUND) {
            throw new IOException("Structure file root was not a compound tag");
        }
        input.readUTF();

        int sizeX = 0;
        int sizeY = 0;
        int sizeZ = 0;
        List<BlockData> palette = List.of();
        while (true) {
            byte tagType = input.readByte();
            if (tagType == TAG_END) {
                break;
            }
            String name = input.readUTF();
            switch (name) {
                case "size" -> {
                    if (tagType != TAG_LIST) {
                        throw new IOException("Unexpected size tag type: " + tagType);
                    }
                    int[] size = readIntList(input);
                    if (size.length < 3) {
                        throw new IOException("Structure size list was too short");
                    }
                    sizeX = size[0];
                    sizeY = size[1];
                    sizeZ = size[2];
                }
                case "palette" -> {
                    if (tagType != TAG_LIST) {
                        throw new IOException("Unexpected palette tag type: " + tagType);
                    }
                    byte elementType = input.readByte();
                    int length = input.readInt();
                    if (elementType != TAG_COMPOUND) {
                        throw new IOException("Structure palette did not contain compounds");
                    }
                    if (parsePalette) {
                        palette = readPaletteEntries(input, length);
                    } else {
                        skipListElements(input, elementType, length);
                    }
                }
                case "blocks" -> {
                    if (tagType != TAG_LIST) {
                        throw new IOException("Unexpected blocks tag type: " + tagType);
                    }
                    byte elementType = input.readByte();
                    int length = input.readInt();
                    if (elementType != TAG_COMPOUND) {
                        throw new IOException("Structure blocks list did not contain compounds");
                    }
                    return new Header(sizeX, sizeY, sizeZ, length, palette);
                }
                default -> skipPayload(input, tagType);
            }
        }
        throw new IOException("Structure file did not contain a blocks list");
    }

    private static List<BlockData> readPaletteEntries(DataInputStream input, int length) throws IOException {
        List<BlockData> palette = new ArrayList<>(length);
        for (int index = 0; index < length; index++) {
            String blockName = null;
            Map<String, String> properties = new TreeMap<>();
            while (true) {
                byte tagType = input.readByte();
                if (tagType == TAG_END) {
                    break;
                }
                String name = input.readUTF();
                switch (name) {
                    case "Name" -> {
                        if (tagType != TAG_STRING) {
                            throw new IOException("Unexpected palette Name tag type: " + tagType);
                        }
                        blockName = input.readUTF();
                    }
                    case "Properties" -> {
                        if (tagType != TAG_COMPOUND) {
                            throw new IOException("Unexpected palette Properties tag type: " + tagType);
                        }
                        readStringProperties(input, properties);
                    }
                    default -> skipPayload(input, tagType);
                }
            }
            if (blockName == null || blockName.isBlank()) {
                throw new IOException("Palette entry " + index + " was missing a block name");
            }
            normalizeSpecialBlocks(blockName, properties);
            String blockDataString = toBlockDataString(blockName, properties);
            palette.add(Bukkit.createBlockData(blockDataString));
        }
        return palette;
    }

    private static void readStringProperties(DataInputStream input, Map<String, String> target) throws IOException {
        while (true) {
            byte tagType = input.readByte();
            if (tagType == TAG_END) {
                return;
            }
            String name = input.readUTF();
            if (tagType != TAG_STRING) {
                skipPayload(input, tagType);
                continue;
            }
            target.put(name, input.readUTF());
        }
    }

    private static int[] readIntList(DataInputStream input) throws IOException {
        byte elementType = input.readByte();
        int length = input.readInt();
        if (elementType != TAG_INT) {
            throw new IOException("Expected an int list but found element type " + elementType);
        }
        int[] values = new int[length];
        for (int index = 0; index < length; index++) {
            values[index] = input.readInt();
        }
        return values;
    }

    private static void normalizeSpecialBlocks(String blockName, Map<String, String> properties) {
        Matcher matcher = DUSTED_BLOCK_PATTERN.matcher(blockName.toLowerCase(Locale.ROOT));
        if (matcher.matches()) {
            properties.put("dusted", matcher.group(2));
        }
    }

    private static String toBlockDataString(String blockName, Map<String, String> properties) {
        String normalizedName = normalizeSpecialBlockName(blockName);
        if (properties.isEmpty()) {
            return normalizedName;
        }
        String joined = properties.entrySet().stream()
                .map(entry -> entry.getKey() + "=" + entry.getValue())
                .reduce((left, right) -> left + "," + right)
                .orElse("");
        return normalizedName + "[" + joined + "]";
    }

    private static String normalizeSpecialBlockName(String blockName) {
        Matcher matcher = DUSTED_BLOCK_PATTERN.matcher(blockName.toLowerCase(Locale.ROOT));
        if (matcher.matches()) {
            return "minecraft:" + matcher.group(1);
        }
        return blockName;
    }

    private static DataInputStream openInput(Path path) throws IOException {
        InputStream raw = Files.newInputStream(path);
        PushbackInputStream pushback = new PushbackInputStream(new BufferedInputStream(raw), 2);
        int first = pushback.read();
        int second = pushback.read();
        if (first == -1 || second == -1) {
            throw new IOException("Structure file was empty: " + path);
        }
        pushback.unread(new byte[]{(byte) first, (byte) second});
        InputStream resolved = first == 0x1f && second == 0x8b ? new GZIPInputStream(pushback) : pushback;
        return new DataInputStream(new BufferedInputStream(resolved));
    }

    private static void skipPayload(DataInputStream input, byte tagType) throws IOException {
        switch (tagType) {
            case TAG_END -> {
            }
            case TAG_BYTE -> input.readByte();
            case TAG_SHORT -> input.readShort();
            case TAG_INT -> input.readInt();
            case TAG_LONG -> input.readLong();
            case TAG_FLOAT -> input.readFloat();
            case TAG_DOUBLE -> input.readDouble();
            case TAG_BYTE_ARRAY -> input.skipNBytes((long) input.readInt());
            case TAG_STRING -> input.readUTF();
            case TAG_LIST -> {
                byte elementType = input.readByte();
                int length = input.readInt();
                skipListElements(input, elementType, length);
            }
            case TAG_COMPOUND -> {
                while (true) {
                    byte nestedType = input.readByte();
                    if (nestedType == TAG_END) {
                        break;
                    }
                    input.readUTF();
                    skipPayload(input, nestedType);
                }
            }
            case TAG_INT_ARRAY -> input.skipNBytes((long) input.readInt() * Integer.BYTES);
            case TAG_LONG_ARRAY -> input.skipNBytes((long) input.readInt() * Long.BYTES);
            default -> throw new IOException("Unknown NBT tag type " + tagType);
        }
    }

    private static void skipListElements(DataInputStream input, byte elementType, int length) throws IOException {
        for (int index = 0; index < length; index++) {
            skipPayload(input, elementType);
        }
    }

    record Metadata(Path source, int sizeX, int sizeY, int sizeZ, int blockCount) {
    }

    private record Header(int sizeX, int sizeY, int sizeZ, int blockCount, List<BlockData> palette) {
    }
}
