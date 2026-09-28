package org.thehill.hill175.data;

import org.bukkit.Location;
import org.bukkit.World;

import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

public record SurvivalLocationSnapshot(
        String worldName,
        double x,
        double y,
        double z,
        float yaw,
        float pitch
) {
    public SurvivalLocationSnapshot {
        worldName = Objects.requireNonNull(worldName, "worldName").trim();
        if (worldName.isBlank()) {
            throw new IllegalArgumentException("worldName cannot be blank");
        }
        if (!Double.isFinite(x) || !Double.isFinite(y) || !Double.isFinite(z)
                || !Float.isFinite(yaw) || !Float.isFinite(pitch)) {
            throw new IllegalArgumentException("location coordinates must be finite");
        }
    }

    static Optional<SurvivalLocationSnapshot> from(Location location) {
        if (location == null || location.getWorld() == null) {
            return Optional.empty();
        }
        return Optional.of(new SurvivalLocationSnapshot(
                location.getWorld().getName(),
                location.getX(),
                location.getY(),
                location.getZ(),
                location.getYaw(),
                location.getPitch()
        ));
    }

    public Optional<Location> resolve(Function<String, World> worlds) {
        World world = worlds.apply(worldName);
        if (world == null) {
            return Optional.empty();
        }
        return Optional.of(new Location(world, x, y, z, yaw, pitch));
    }
}
