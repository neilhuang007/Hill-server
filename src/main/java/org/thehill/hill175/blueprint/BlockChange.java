package org.thehill.hill175.blueprint;

import java.util.Objects;

public record BlockChange(BlockPosition position, BlockSnapshot before, BlockSnapshot after) {
    public BlockChange {
        Objects.requireNonNull(position);
        Objects.requireNonNull(before);
        Objects.requireNonNull(after);
        if (before.equals(after)) throw new IllegalArgumentException("A change must change the block.");
    }
}
