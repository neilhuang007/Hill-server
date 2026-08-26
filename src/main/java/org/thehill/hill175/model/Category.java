package org.thehill.hill175.model;

import org.bukkit.Material;

import java.util.Locale;
import java.util.Optional;

public enum Category {
    JOURNEY("The Journey", Material.BRICKS, 64, 64, 48),
    PLACE("The Place", Material.BOOKSHELF, 32, 32, 20),
    PEOPLE("The People", Material.COMPASS, 512, 512, 192);

    private final String displayName;
    private final Material icon;
    private final int width;
    private final int depth;
    private final int height;

    Category(String displayName, Material icon, int width, int depth, int height) {
        this.displayName = displayName;
        this.icon = icon;
        this.width = width;
        this.depth = depth;
        this.height = height;
    }

    public String displayName() {
        return displayName;
    }

    public Material icon() {
        return icon;
    }

    public int width() {
        return width;
    }

    public int depth() {
        return depth;
    }

    public int height() {
        return height;
    }

    public static Optional<Category> parse(String raw) {
        if (raw == null) {
            return Optional.empty();
        }
        try {
            return Optional.of(valueOf(raw.trim().toUpperCase(Locale.ROOT)));
        } catch (IllegalArgumentException ignored) {
            return Optional.empty();
        }
    }
}
