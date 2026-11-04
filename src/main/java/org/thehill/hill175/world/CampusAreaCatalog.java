package org.thehill.hill175.world;

import org.bukkit.configuration.file.YamlConfiguration;
import org.thehill.hill175.model.BuildRegion;

import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/** Exact unions of the campus construction work rectangles. */
public final class CampusAreaCatalog {
    public static final String FILE_NAME = "hill-areas.yml";
    private final List<Area> areas;

    private CampusAreaCatalog(List<Area> areas) { this.areas = List.copyOf(areas); }

    public static CampusAreaCatalog read(Path folder) {
        Path supplied = folder.resolve(FILE_NAME);
        if (Files.isRegularFile(supplied)) {
            return parse(YamlConfiguration.loadConfiguration(supplied.toFile()));
        }
        YamlConfiguration metadata = YamlConfiguration.loadConfiguration(
                folder.resolve(CampusTemplateMetadata.FILE_NAME).toFile());
        if (metadata.getDouble("blocks-per-metre", 0) != 2
                || !metadata.getString("revision", "").startsWith("campus-")) {
            throw new IllegalStateException("This campus needs its own " + FILE_NAME + " before area selection is available.");
        }
        try (var stream = CampusAreaCatalog.class.getResourceAsStream("/" + FILE_NAME)) {
            if (stream == null) throw new IllegalStateException("The campus area catalog is missing.");
            return parse(YamlConfiguration.loadConfiguration(new InputStreamReader(stream, StandardCharsets.UTF_8)));
        } catch (IOException exception) {
            throw new IllegalStateException("Could not read campus areas.", exception);
        }
    }

    static CampusAreaCatalog parse(YamlConfiguration yaml) {
        if (!"hill-local-east-south-2x".equals(yaml.getString("coordinate-frame"))) {
            throw new IllegalStateException("Unsupported campus area coordinate frame.");
        }
        var section = yaml.getConfigurationSection("areas");
        if (section == null || section.getKeys(false).isEmpty()) throw new IllegalStateException("No campus areas configured.");
        List<Area> areas = new ArrayList<>();
        List<BuildRegion> claimed = new ArrayList<>();
        for (String id : section.getKeys(false)) {
            String name = section.getString(id + ".name", "");
            if (!id.matches("area-[a-z0-9-]+") || name.isBlank()) throw new IllegalStateException("Invalid campus area: " + id);
            List<?> boxes = section.getList(id + ".boxes", List.of());
            if (boxes.isEmpty()) throw new IllegalStateException("Campus area needs boundaries: " + id);
            List<BuildRegion> parts = new ArrayList<>();
            for (Object raw : boxes) {
                if (!(raw instanceof List<?> values) || values.size() != 4
                        || values.stream().anyMatch(value -> !(value instanceof Integer))) {
                    throw new IllegalStateException("Area bounds need four integer coordinates: " + id);
                }
                BuildRegion part = new BuildRegion("source", (Integer) values.get(0), -64, (Integer) values.get(1),
                        (Integer) values.get(2), 319, (Integer) values.get(3));
                if (claimed.stream().anyMatch(other -> part.minX() <= other.maxX() && part.maxX() >= other.minX()
                        && part.minZ() <= other.maxZ() && part.maxZ() >= other.minZ())) {
                    throw new IllegalStateException("Campus area boundaries overlap: " + id);
                }
                claimed.add(part);
                parts.add(part);
            }
            areas.add(new Area(id, name, section.getString(id + ".description", ""), List.copyOf(parts)));
        }
        return new CampusAreaCatalog(areas);
    }

    public List<Area> areas() { return areas; }
    public Optional<Area> find(String id) { return areas.stream().filter(area -> area.id().equals(id)).findFirst(); }

    public record Area(String id, String name, String description, List<BuildRegion> parts) {
        public Area { parts = List.copyOf(parts); }
        public List<BuildRegion> regions(String world) {
            return parts.stream().map(part -> new BuildRegion(world, part.minX(), part.minY(), part.minZ(),
                    part.maxX(), part.maxY(), part.maxZ())).toList();
        }
        public BuildingCatalog.Building envelope() {
            return new BuildingCatalog.Building(id, name, 1,
                    parts.stream().mapToInt(BuildRegion::minX).min().orElseThrow(),
                    parts.stream().mapToInt(BuildRegion::minZ).min().orElseThrow(),
                    parts.stream().mapToInt(BuildRegion::maxX).max().orElseThrow(),
                    parts.stream().mapToInt(BuildRegion::maxZ).max().orElseThrow());
        }
        public long blocks() {
            return parts.stream().mapToLong(part -> (long) (part.maxX() - part.minX() + 1)
                    * (part.maxZ() - part.minZ() + 1)).sum();
        }
    }
}
