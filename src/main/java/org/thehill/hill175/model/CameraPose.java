package org.thehill.hill175.model;

import org.bukkit.Location;

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
}
