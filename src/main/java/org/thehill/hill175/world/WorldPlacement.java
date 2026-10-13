package org.thehill.hill175.world;

import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.configuration.InvalidConfigurationException;
import org.bukkit.configuration.file.YamlConfiguration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** Where players and hub guides stand in a supplied map. It travels in the map's folder, not in code. */
record WorldPlacement(Optional<Pose> spawn, Map<String, Pose> npcs) {
    static final String FILE_NAME = "hill-world.yml";
    static final WorldPlacement NONE = new WorldPlacement(Optional.empty(), Map.of());
    private static final Set<String> NPC_NAMES = Set.of("journey", "place", "people", "survival");

    record Pose(double x, double y, double z, float yaw, float pitch) {
        Location in(World world) {
            return new Location(world, x, y, z, yaw, pitch);
        }
    }

    static WorldPlacement read(Path templateFolder) {
        Path file = templateFolder.resolve(FILE_NAME);
        if (!Files.isRegularFile(file)) {
            return NONE;
        }
        YamlConfiguration yaml = new YamlConfiguration();
        try {
            yaml.load(file.toFile());
        } catch (IOException | InvalidConfigurationException exception) {
            throw new IllegalStateException("Cannot read " + file, exception);
        }
        // A misspelled key must not silently fall back to another position.
        for (String key : yaml.getKeys(false)) {
            if (!key.equals("spawn") && !key.equals("npcs")) {
                throw new IllegalStateException("Unknown entry '" + key + "' in " + file);
            }
        }
        Optional<Pose> spawn = yaml.contains("spawn") ? Optional.of(pose(yaml, "spawn", file)) : Optional.empty();
        Map<String, Pose> npcs = new HashMap<>();
        var section = yaml.getConfigurationSection("npcs");
        if (section == null && yaml.contains("npcs")) {
            throw new IllegalStateException("npcs must list positions by name in " + file);
        }
        if (section != null) {
            for (String name : section.getKeys(false)) {
                if (!NPC_NAMES.contains(name)) {
                    throw new IllegalStateException("Unknown npc '" + name + "' in " + file);
                }
                npcs.put(name, pose(yaml, "npcs." + name, file));
            }
        }
        return new WorldPlacement(spawn, Map.copyOf(npcs));
    }

    private static Pose pose(YamlConfiguration yaml, String path, Path file) {
        List<?> values = yaml.getList(path);
        if (values == null || (values.size() != 3 && values.size() != 5)
                || !values.stream().allMatch(Number.class::isInstance)) {
            throw new IllegalStateException(path + " must be [x, y, z] or [x, y, z, yaw, pitch] in " + file);
        }
        double[] numbers = values.stream().mapToDouble(value -> ((Number) value).doubleValue()).toArray();
        return new Pose(numbers[0], numbers[1], numbers[2],
                numbers.length == 5 ? (float) numbers[3] : 0.0f,
                numbers.length == 5 ? (float) numbers[4] : 0.0f);
    }
}
