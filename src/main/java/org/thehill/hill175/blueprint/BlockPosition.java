package org.thehill.hill175.blueprint;

public record BlockPosition(int blockX, int blockY, int blockZ) implements Comparable<BlockPosition> {
    @Override
    public int compareTo(BlockPosition other) {
        int horizontalOrder = Integer.compare(blockX, other.blockX);
        if (horizontalOrder != 0) return horizontalOrder;
        int depthOrder = Integer.compare(blockZ, other.blockZ);
        return depthOrder != 0 ? depthOrder : Integer.compare(blockY, other.blockY);
    }
}
