package org.thehill.hill175.world;

import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;

import java.util.Optional;

/**
 * Converts a saved eye-level camera pose into the feet position required by a player teleport.
 */
final class CameraPoseResolver {
    private static final double SUBJECT_DISTANCE = 6.0;

    private CameraPoseResolver() {
    }

    static Optional<ResolvedPose> resolve(
            BuildRegion region,
            CameraPose pose,
            double eyeHeight,
            Boundary boundary,
            CellSafety safety
    ) {
        if (!region.worldName().equals(pose.worldName())
                || !Double.isFinite(pose.x())
                || !Double.isFinite(pose.y())
                || !Double.isFinite(pose.z())
                || !Float.isFinite(pose.yaw())
                || !Float.isFinite(pose.pitch())
                || !Double.isFinite(eyeHeight)
                || eyeHeight <= 0.0
                || !pointsIntoOwnedRegion(region, pose)) {
            return Optional.empty();
        }

        double feetY = pose.y() - eyeHeight;
        if (!contains(region, pose.x(), pose.y(), pose.z())
                || !contains(region, pose.x(), feetY, pose.z())
                || !boundary.contains(pose.x(), pose.y(), pose.z())
                || !boundary.contains(pose.x(), feetY, pose.z())) {
            return Optional.empty();
        }

        int x = floor(pose.x());
        int feetBlockY = floor(feetY);
        int eyeBlockY = floor(pose.y());
        int z = floor(pose.z());
        if (!safety.canOccupy(x, feetBlockY, z) || !safety.canOccupy(x, eyeBlockY, z)) {
            return Optional.empty();
        }
        return Optional.of(new ResolvedPose(pose.x(), feetY, pose.z(), pose.yaw(), pose.pitch()));
    }

    private static boolean contains(BuildRegion region, double x, double y, double z) {
        return region.contains(floor(x), floor(y), floor(z));
    }

    private static boolean pointsIntoOwnedRegion(BuildRegion region, CameraPose pose) {
        double yawRadians = Math.toRadians(pose.yaw());
        double pitchRadians = Math.toRadians(pose.pitch());
        double horizontal = Math.cos(pitchRadians);
        double targetX = pose.x() - Math.sin(yawRadians) * horizontal * SUBJECT_DISTANCE;
        double targetY = pose.y() - Math.sin(pitchRadians) * SUBJECT_DISTANCE;
        double targetZ = pose.z() + Math.cos(yawRadians) * horizontal * SUBJECT_DISTANCE;
        return contains(region, targetX, targetY, targetZ);
    }

    private static int floor(double value) {
        return (int) Math.floor(value);
    }

    @FunctionalInterface
    interface Boundary {
        boolean contains(double x, double y, double z);
    }

    @FunctionalInterface
    interface CellSafety {
        boolean canOccupy(int x, int y, int z);
    }

    record ResolvedPose(double x, double feetY, double z, float yaw, float pitch) {
    }
}
