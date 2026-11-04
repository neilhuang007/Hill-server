package org.thehill.hill175.gallery;

import org.thehill.hill175.model.CameraPose;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Path;

/** CPU perspective renderer. Its input is immutable and must never query a live world. */
public final class VoxelPerspectiveRenderer {
    public static final int imageWidth = 800;
    public static final int imageHeight = 450;
    public static final int viewDistance = 80;

    public void render(Scene scene, CameraPose pose, Path output) throws IOException {
        BufferedImage image = new BufferedImage(imageWidth, imageHeight, BufferedImage.TYPE_INT_RGB);
        double yaw = Math.toRadians(pose.yaw());
        double pitch = Math.toRadians(pose.pitch());
        double[] forward = {-Math.sin(yaw) * Math.cos(pitch), -Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch)};
        double[] right = {Math.cos(yaw), 0, Math.sin(yaw)};
        double[] up = {-Math.sin(yaw) * Math.sin(pitch), Math.cos(pitch), Math.cos(yaw) * Math.sin(pitch)};
        double scale = Math.tan(Math.toRadians(70) / 2);
        for (int row = 0; row < imageHeight; row++) {
            if (Thread.currentThread().isInterrupted()) {
                throw new IOException("Camera rendering was stopped.");
            }
            renderRow(scene, pose, image, row, forward, right, up, scale);
        }
        if (!ImageIO.write(image, "png", output.toFile())) {
            throw new IOException("No PNG image writer is available.");
        }
    }

    private void renderRow(Scene scene, CameraPose pose, BufferedImage image, int row,
                           double[] forward, double[] right, double[] up, double scale) {
        double vertical = (1 - 2 * (row + 0.5) / imageHeight) * scale;
        for (int column = 0; column < imageWidth; column++) {
            double horizontal = (2 * (column + 0.5) / imageWidth - 1) * scale * imageWidth / imageHeight;
            double x = forward[0] + right[0] * horizontal + up[0] * vertical;
            double y = forward[1] + right[1] * horizontal + up[1] * vertical;
            double z = forward[2] + right[2] * horizontal + up[2] * vertical;
            double length = Math.sqrt(x * x + y * y + z * z);
            image.setRGB(column, row, trace(scene, pose, x / length, y / length, z / length));
        }
    }

    private int trace(Scene scene, CameraPose pose, double dx, double dy, double dz) {
        int x = (int) Math.floor(pose.x());
        int y = (int) Math.floor(pose.y());
        int z = (int) Math.floor(pose.z());
        double nextX = nextBoundary(pose.x(), dx);
        double nextY = nextBoundary(pose.y(), dy);
        double nextZ = nextBoundary(pose.z(), dz);
        double distance = 0;
        int face = 1;
        int sky = sky(dy);
        for (int step = 0; step < viewDistance * 4 && distance <= viewDistance; step++) {
            int voxel = scene.colorAt(x, y, z);
            if ((voxel >>> 24) != 0 && distance > 0.05) {
                double shading = face == 1 ? 1.0 : face == 0 ? 0.79 : 0.65;
                double grain = 0.96 + Math.floorMod(x * 31 + y * 13 + z * 17, 9) / 100.0;
                return fog(shade(voxel, shading * grain), sky, distance / viewDistance);
            }
            if (nextX < nextY && nextX < nextZ) {
                distance = nextX; nextX += 1 / Math.abs(dx); x += dx > 0 ? 1 : -1; face = 0;
                continue;
            }
            if (nextY < nextZ) {
                distance = nextY; nextY += 1 / Math.abs(dy); y += dy > 0 ? 1 : -1; face = 1;
                continue;
            }
            distance = nextZ; nextZ += 1 / Math.abs(dz); z += dz > 0 ? 1 : -1; face = 2;
        }
        return sky;
    }

    private static double nextBoundary(double coordinate, double direction) {
        if (Math.abs(direction) < 1.0e-10) {
            return Double.POSITIVE_INFINITY;
        }
        double boundary = direction > 0 ? Math.floor(coordinate) + 1 : Math.floor(coordinate);
        return (boundary - coordinate) / direction;
    }

    private static int shade(int color, double factor) {
        int red = Math.min(255, (int) (((color >> 16) & 255) * factor));
        int green = Math.min(255, (int) (((color >> 8) & 255) * factor));
        int blue = Math.min(255, (int) ((color & 255) * factor));
        return red << 16 | green << 8 | blue;
    }

    private static int sky(double directionY) {
        return mix(0xb7d7df, 0x79a9cf, Math.max(0, Math.min(1, directionY)));
    }

    private static int fog(int color, int sky, double normalizedDistance) {
        return mix(color, sky, Math.max(0, normalizedDistance - 0.45) * 0.7);
    }

    private static int mix(int first, int second, double weight) {
        int red = (int) (((first >> 16) & 255) * (1 - weight) + ((second >> 16) & 255) * weight);
        int green = (int) (((first >> 8) & 255) * (1 - weight) + ((second >> 8) & 255) * weight);
        int blue = (int) ((first & 255) * (1 - weight) + (second & 255) * weight);
        return red << 16 | green << 8 | blue;
    }

    @FunctionalInterface
    public interface Scene {
        /** ARGB block color; alpha zero means empty. */
        int colorAt(int x, int y, int z);
    }
}
