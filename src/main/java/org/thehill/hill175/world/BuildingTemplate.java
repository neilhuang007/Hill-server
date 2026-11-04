package org.thehill.hill175.world;

import org.thehill.hill175.model.BuildRegion;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.HashSet;
import java.util.Set;

/** Copies only the source Anvil regions around a selected building, without player/entity data. */
final class BuildingTemplate {
    private BuildingTemplate() {
    }

    static void validateSource(Path source, BuildRegion region) {
        CampusTemplateMetadata metadata = CampusTemplateMetadata.read(source).orElseThrow(() ->
                new IllegalStateException("The installed campus needs measured bounds for Place entries."));
        BuildRegion campus = metadata.region("source", -64, 320);
        if (region.minX() < campus.minX() || region.maxX() > campus.maxX()
                || region.minZ() < campus.minZ() || region.maxZ() > campus.maxZ()) {
            throw new IllegalStateException("The chosen building and its outdoor margin are outside the installed campus.");
        }
        for (String name : regionFiles(region)) {
            Path file = source.resolve("region").resolve(name);
            try {
                if (!Files.isRegularFile(file) || Files.size(file) < 8_192) {
                    throw new IllegalStateException("The installed campus is missing building terrain: " + name);
                }
                validateChunks(file, region);
            } catch (IOException exception) {
                throw new IllegalStateException("Could not read building terrain: " + name, exception);
            }
        }
    }

    private static void validateChunks(Path file, BuildRegion region) throws IOException {
        String[] name = file.getFileName().toString().split("\\.");
        int regionX = Integer.parseInt(name[1]);
        int regionZ = Integer.parseInt(name[2]);
        ByteBuffer locations = ByteBuffer.allocate(4_096);
        try (var input = java.nio.channels.FileChannel.open(file)) {
            while (locations.hasRemaining() && input.read(locations) >= 0) {
                // Read the Anvil location table before trusting an existing region filename.
            }
        }
        int minX = Math.max(regionX * 32, Math.floorDiv(region.minX(), 16));
        int maxX = Math.min(regionX * 32 + 31, Math.floorDiv(region.maxX(), 16));
        int minZ = Math.max(regionZ * 32, Math.floorDiv(region.minZ(), 16));
        int maxZ = Math.min(regionZ * 32 + 31, Math.floorDiv(region.maxZ(), 16));
        for (int x = minX; x <= maxX; x++) {
            for (int z = minZ; z <= maxZ; z++) {
                int location = locations.getInt(4 * (Math.floorMod(x, 32) + 32 * Math.floorMod(z, 32)));
                long lastByte = ((long) (location >>> 8) + (location & 255)) * 4_096;
                if ((location >>> 8) < 2 || (location & 255) == 0 || lastByte > Files.size(file)) {
                    throw new IllegalStateException("The installed campus is missing building chunk " + x + ", " + z + ".");
                }
            }
        }
    }

    static void copy(Path source, Path target, BuildRegion region) throws IOException {
        validateSource(source, region);
        if (Files.exists(target)) {
            throw new IOException("A building world already exists at " + target);
        }
        Files.createDirectories(target);
        copyMetadata(source, target);
        for (String directory : List.of("region", "poi")) {
            copyRegions(source.resolve(directory), target.resolve(directory), region);
        }
    }

    /** Extends an unloaded saved world only when the original template metadata still matches. */
    static void copyMissingTerrain(Path source, Path target, BuildRegion region) throws IOException {
        Path originalMetadata = target.resolve(CampusTemplateMetadata.FILE_NAME);
        Path sourceMetadata = source.resolve(CampusTemplateMetadata.FILE_NAME);
        if (!Files.isRegularFile(originalMetadata) || !Files.isRegularFile(sourceMetadata)
                || Files.mismatch(originalMetadata, sourceMetadata) != -1) {
            return;
        }
        validateSource(source, region);
        for (String directory : List.of("region", "poi")) {
            copyRegions(source.resolve(directory), target.resolve(directory), region);
        }
    }

    private static void copyMetadata(Path source, Path target) throws IOException {
        for (String name : List.of(CampusTemplateMetadata.FILE_NAME, BuildingCatalog.fileName, CampusAreaCatalog.FILE_NAME)) {
            Path file = source.resolve(name);
            if (Files.isRegularFile(file)) {
                Files.copy(file, target.resolve(name), StandardCopyOption.COPY_ATTRIBUTES);
            }
        }
    }

    private static void copyRegions(Path source, Path target, BuildRegion region) throws IOException {
        if (!Files.isDirectory(source)) {
            return;
        }
        Files.createDirectories(target);
        Set<String> copiedRegions = new HashSet<>();
        for (String name : regionFiles(region)) {
            Path file = source.resolve(name);
            if (Files.isRegularFile(file) && !Files.exists(target.resolve(name))) {
                Files.copy(file, target.resolve(name), StandardCopyOption.COPY_ATTRIBUTES);
                copiedRegions.add(name);
            }
        }
        // Oversized chunks accompany the entire copied region, including chunks outside viewing bounds.
        try (var files = Files.list(source)) {
            for (Path file : files.filter(path -> path.getFileName().toString().matches("c\\.-?\\d+\\.-?\\d+\\.mcc")).toList()) {
                String[] parts = file.getFileName().toString().split("\\.");
                String regionName = "r." + Math.floorDiv(Integer.parseInt(parts[1]), 32) + "."
                        + Math.floorDiv(Integer.parseInt(parts[2]), 32) + ".mca";
                if (copiedRegions.contains(regionName) && !Files.exists(target.resolve(file.getFileName()))) {
                    Files.copy(file, target.resolve(file.getFileName()), StandardCopyOption.COPY_ATTRIBUTES);
                }
            }
        }
    }

    static List<String> regionFiles(BuildRegion region) {
        java.util.ArrayList<String> names = new java.util.ArrayList<>();
        for (int x = Math.floorDiv(region.minX(), 512); x <= Math.floorDiv(region.maxX(), 512); x++) {
            for (int z = Math.floorDiv(region.minZ(), 512); z <= Math.floorDiv(region.maxZ(), 512); z++) {
                names.add("r." + x + "." + z + ".mca");
            }
        }
        return List.copyOf(names);
    }
}
