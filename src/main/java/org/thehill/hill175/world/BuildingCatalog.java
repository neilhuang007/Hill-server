package org.thehill.hill175.world;

import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.configuration.file.YamlConfiguration;
import org.thehill.hill175.model.BuildRegion;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

/** Source footprints in the campus' measured east/south block coordinate frame. */
public final class BuildingCatalog {
    public static final String fileName = "hill-buildings.yml";
    private final List<Building> buildings;

    private BuildingCatalog(List<Building> buildings) {
        this.buildings = List.copyOf(buildings);
    }

    public static BuildingCatalog read(Path templateFolder) {
        Path supplied = templateFolder.resolve(fileName);
        if (Files.isRegularFile(supplied)) {
            return parse(YamlConfiguration.loadConfiguration(supplied.toFile()), supplied.toString());
        }
        requireMeasuredCampusFrame(templateFolder);
        try (InputStream resource = BuildingCatalog.class.getResourceAsStream("/hill-buildings.yml")) {
            if (resource == null) {
                throw new IllegalStateException("The Hill building catalog is missing from the plugin.");
            }
            return parse(YamlConfiguration.loadConfiguration(
                    new InputStreamReader(resource, StandardCharsets.UTF_8)), "bundled Hill building catalog");
        } catch (IOException exception) {
            throw new IllegalStateException("Could not read the Hill building catalog.", exception);
        }
    }

    private static void requireMeasuredCampusFrame(Path folder) {
        YamlConfiguration metadata = YamlConfiguration.loadConfiguration(
                folder.resolve(CampusTemplateMetadata.FILE_NAME).toFile());
        if (metadata.getDouble("blocks-per-metre", 0) != 2
                || !metadata.getString("revision", "").startsWith("campus-")) {
            throw new IllegalStateException("This template needs its own " + fileName
                    + " with measured building bounds before Place entries can be created.");
        }
    }

    static BuildingCatalog parse(YamlConfiguration yaml, String source) {
        ConfigurationSection section = yaml.getConfigurationSection("buildings");
        if (section == null || section.getKeys(false).isEmpty()) {
            throw new IllegalStateException("No measured buildings in " + source);
        }
        List<Building> buildings = new ArrayList<>();
        for (String id : section.getKeys(false)) {
            buildings.add(readBuilding(section.getConfigurationSection(id), id, source));
        }
        buildings.sort(Comparator.comparingInt(Building::mapNumber).thenComparing(Building::name));
        return new BuildingCatalog(buildings);
    }

    private static Building readBuilding(ConfigurationSection section, String id, String source) {
        if (section == null) {
            throw new IllegalStateException("Invalid building " + id + " in " + source);
        }
        List<Integer> bounds = section.getIntegerList("bounds-xz");
        if (bounds.size() != 4) {
            throw new IllegalStateException("Building " + id + " needs four bounds-xz coordinates in " + source);
        }
        return new Building(id, section.getString("name", ""), section.getInt("map-number"),
                bounds.get(0), bounds.get(1), bounds.get(2), bounds.get(3));
    }

    public List<Building> buildings() {
        return buildings;
    }

    public Optional<Building> find(String id) {
        if (id == null || id.isBlank()) {
            return Optional.empty();
        }
        String normalized = id.strip().toLowerCase(Locale.ROOT);
        return buildings.stream().filter(building -> building.id().equals(normalized)
                || Integer.toString(building.mapNumber()).equals(normalized)).findFirst();
    }

    public record Building(String id, String name, int mapNumber, int minX, int minZ, int maxX, int maxZ) {
        public Building {
            if (id == null || !id.matches("[a-z0-9][a-z0-9-]*") || name == null || name.isBlank()
                    || mapNumber < 1 || minX > maxX || minZ > maxZ) {
                throw new IllegalStateException("Invalid measured building metadata: " + id);
            }
        }

        public int width() { return maxX - minX + 1; }
        public int depth() { return maxZ - minZ + 1; }
        public int centerX() { return minX + (maxX - minX) / 2; }
        public int centerZ() { return minZ + (maxZ - minZ) / 2; }

        public BuildRegion region(String worldName, int minHeight, int maxHeight, int margin) {
            return new BuildRegion(worldName, minX - margin, minHeight, minZ - margin,
                    maxX + margin, maxHeight - 1, maxZ + margin);
        }
    }
}
