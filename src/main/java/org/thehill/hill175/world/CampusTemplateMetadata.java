package org.thehill.hill175.world;

import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.configuration.file.YamlConfiguration;
import org.thehill.hill175.model.BuildRegion;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

/** Geometry travels with each template clone so old entries keep their own map. */
record CampusTemplateMetadata(List<Integer> bounds, List<Integer> spawn) {
    static final String FILE_NAME = "hill-campus-template.yml";

    static Optional<CampusTemplateMetadata> read(Path worldFolder) {
        Path file = worldFolder.resolve(FILE_NAME);
        if (!Files.isRegularFile(file)) {
            return Optional.empty();
        }
        YamlConfiguration yaml = YamlConfiguration.loadConfiguration(file.toFile());
        List<Integer> bounds = yaml.getIntegerList("block-bounds");
        List<Integer> spawn = yaml.getIntegerList("spawn");
        if (bounds.size() != 6 || spawn.size() != 3) {
            throw new IllegalStateException("Invalid campus bounds/spawn in " + file);
        }
        CampusTemplateMetadata metadata = new CampusTemplateMetadata(List.copyOf(bounds), List.copyOf(spawn));
        if (!metadata.region("template", -64, 320).contains(spawn.get(0), spawn.get(1), spawn.get(2))) {
            throw new IllegalStateException("Campus spawn is outside the template bounds: " + file);
        }
        return Optional.of(metadata);
    }

    BuildRegion region(String worldName, int minHeight, int maxHeight) {
        return new BuildRegion(worldName, bounds.get(0), Math.max(minHeight, bounds.get(1)), bounds.get(2),
                bounds.get(3), Math.min(maxHeight - 1, bounds.get(4)), bounds.get(5));
    }

    Location spawnLocation(World world) {
        return new Location(world, spawn.get(0), spawn.get(1), spawn.get(2));
    }
}
