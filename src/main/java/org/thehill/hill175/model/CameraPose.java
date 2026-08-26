package org.thehill.hill175.model;

import org.bukkit.Location;
import org.bukkit.World;

public record CameraPose(
        String worldName,
        double x,
        double y,
        double z,
        float yaw,
        float pitch
) {
    public static CameraPose from(Location location) {
        if (location.getWorld() == null) {
            throw new IllegalArgumentException("Camera pose requires a world");
        }
        return new CameraPose(
                location.getWorld().getName(),
                location.getX(),
                location.getY(),
                location.getZ(),
                location.getYaw(),
                location.getPitch()
        );
    }

    public Location toLocation(World world) {
        if (world == null) {
            throw new IllegalArgumentException("world is required");
        }
        return new Location(world, x, y, z, yaw, pitch);
    }
}
