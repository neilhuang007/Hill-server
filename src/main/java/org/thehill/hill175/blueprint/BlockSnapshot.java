package org.thehill.hill175.blueprint;

import java.util.Arrays;
import java.util.Objects;

public final class BlockSnapshot {
    private final String blockData;
    private final byte[] structure;

    public BlockSnapshot(String blockData, byte[] structure) {
        this.blockData = Objects.requireNonNull(blockData);
        if (blockData.isBlank()) throw new IllegalArgumentException("Block data is required.");
        this.structure = structure == null ? new byte[0] : structure.clone();
    }

    public String blockData() { return blockData; }
    public byte[] structure() { return structure.clone(); }

    @Override
    public boolean equals(Object other) {
        return other instanceof BlockSnapshot snapshot && blockData.equals(snapshot.blockData)
                && Arrays.equals(structure, snapshot.structure);
    }

    @Override
    public int hashCode() { return 31 * blockData.hashCode() + Arrays.hashCode(structure); }
}
