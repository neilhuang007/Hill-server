package org.thehill.hill175.blueprint;

import org.bukkit.Bukkit;
import org.bukkit.GameRules;
import org.bukkit.World;
import org.bukkit.WorldCreator;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.configuration.file.YamlConfiguration;
import org.thehill.hill175.world.VoidChunkGenerator;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.Properties;
import java.util.UUID;

final class BlueprintWorldFiles {
    static final String REVISION_MARKER = "hill-blueprint-revision.properties";

    private BlueprintWorldFiles() { }

    /** Exports record their revision so a campus copied from one knows which blueprint updates it already has. */
    static void writeRevisionMarker(Path export, long revision) throws IOException {
        Properties marker = new Properties();
        marker.setProperty("revision", Long.toString(revision));
        BlueprintFiles.writeProperties(export.resolve(REVISION_MARKER), marker);
    }

    static java.util.OptionalLong revisionMarker(Path world) throws IOException {
        Path marker = world.resolve(REVISION_MARKER);
        if (!Files.isRegularFile(marker)) return java.util.OptionalLong.empty();
        return java.util.OptionalLong.of(Long.parseLong(BlueprintFiles.readProperties(marker).getProperty("revision")));
    }

    static Path prepareTemplate(JavaPlugin plugin) throws IOException {
        Path folder = plugin.getDataFolder().toPath().resolve("blueprint");
        Path pointer = folder.resolve("current.properties");
        if (!Files.exists(pointer)) seed(plugin, folder, pointer);
        Properties current = BlueprintFiles.readProperties(pointer);
        if (Long.parseLong(current.getProperty("revision")) < 0) throw new IOException("Invalid accepted revision.");
        Path export = BlueprintFiles.child(folder.resolve("exports"), current.getProperty("export"));
        validateWorld(export);
        validateWorld(worldFolder(plugin, "hill_blueprint"));
        plugin.getConfig().set("people.template-folder", export.toAbsolutePath().toString());
        return export;
    }

    private static void seed(JavaPlugin plugin, Path folder, Path pointer) throws IOException {
        Path server = plugin.getServer().getWorldContainer().toPath();
        String configured = plugin.getConfig().getString("blueprint.source-folder", "");
        if (configured == null || configured.isBlank()) configured = plugin.getConfig().getString("people.template-folder", "world-templates/hill_people_template");
        if (configured == null || configured.isBlank()) throw new IOException("No campus source is selected.");
        Path source = Path.of(configured);
        if (!source.isAbsolute()) source = server.resolve(source);
        validateWorld(source);
        Path blueprint = worldFolder(plugin, "hill_blueprint");
        if (Files.exists(blueprint)) throw new IOException("Unregistered hill_blueprint exists. Preserve it and resolve initialization before retrying.");
        copyWorld(source, blueprint);
        Path export = folder.resolve("exports/revision-0");
        copyWorld(source, export);
        writeRevisionMarker(export, 0);
        Properties current = new Properties();
        current.setProperty("revision", "0");
        current.setProperty("export", "revision-0");
        current.setProperty("source", source.toAbsolutePath().normalize().toString());
        BlueprintFiles.writeProperties(pointer, current);
    }

    static void validateWorld(Path source) throws IOException {
        if (Files.isSymbolicLink(source) || Files.isSymbolicLink(source.resolve("region")) || !Files.isDirectory(source.resolve("region"))) {
            throw new IOException("Missing saved campus world: " + source);
        }
        try (var paths = Files.list(source.resolve("region"))) {
            List<Path> regions = paths.filter(path -> path.getFileName().toString().matches("r\\.-?\\d+\\.-?\\d+\\.mca")).toList();
            if (regions.isEmpty()) throw new IOException("Campus contains no saved region files: " + source);
            for (Path region : regions) {
                if (!Files.isRegularFile(region) || Files.isSymbolicLink(region) || Files.size(region) < 8192) {
                    throw new IOException("Invalid campus region file: " + region);
                }
            }
        }
    }

    static void copyWorld(Path source, Path target) throws IOException {
        validateWorld(source);
        if (Files.exists(target)) throw new IOException("Snapshot destination already exists: " + target);
        Path staged = target.resolveSibling(target.getFileName() + ".partial-" + UUID.randomUUID());
        Files.createDirectories(staged);
        for (String name : List.of("region", "poi")) {
            if (Files.isDirectory(source.resolve(name))) BlueprintFiles.copyTree(source.resolve(name), staged.resolve(name));
        }
        Path data = source.resolve("data");
        if (Files.isDirectory(data)) {
            if (Files.isSymbolicLink(data)) throw new IOException("Symbolic link data folder is not accepted.");
            try (var paths = Files.walk(data)) {
                for (Path file : paths.toList()) {
                    if (Files.isSymbolicLink(file)) throw new IOException("Symbolic link world data is not accepted.");
                    Path relative = data.relativize(file);
                    if (relative.equals(Path.of("paper", "metadata.dat"))) continue;
                    Path destination = staged.resolve("data").resolve(relative);
                    if (Files.isDirectory(file)) Files.createDirectories(destination);
                    else Files.copy(file, destination, StandardCopyOption.COPY_ATTRIBUTES);
                }
            }
        }
        for (String name : List.of("level.dat", "hill-campus-template.yml", "hill-buildings.yml", "hill-areas.yml", ".hill175-people-ready")) {
            Path file = source.resolve(name);
            if (Files.isSymbolicLink(file)) throw new IOException("Symbolic link world metadata is not accepted.");
            if (Files.isRegularFile(file)) Files.copy(file, staged.resolve(name), StandardCopyOption.COPY_ATTRIBUTES);
        }
        BlueprintFiles.move(staged, target);
    }

    static World load(JavaPlugin plugin, String name, boolean readOnly) throws IOException {
        if (name == null || !name.equals("hill_blueprint") && !name.matches("hill_bp_(base|review|preview)_[a-f0-9]{32}")) {
            throw new IOException("Invalid blueprint world reference.");
        }
        Path saved = worldFolder(plugin, name);
        validateWorld(saved);
        World world = Bukkit.getWorld(name);
        if (world == null) {
            var creator = WorldCreator.name(name).generator(new VoidChunkGenerator()).generateStructures(false);
            Path metadata = saved.resolve("hill-campus-template.yml");
            if (Files.isRegularFile(metadata)) {
                List<Integer> spawn = YamlConfiguration.loadConfiguration(metadata.toFile()).getIntegerList("spawn");
                if (spawn.size() != 3) throw new IOException("Invalid saved campus spawn metadata.");
                creator.forcedSpawnPosition(io.papermc.paper.math.Position.block(spawn.get(0), spawn.get(1), spawn.get(2)), 0.0f, 0.0f);
            } else {
                creator.forcedSpawnPosition(io.papermc.paper.math.Position.block(0, 100, 0), 0.0f, 0.0f);
            }
            world = creator.createWorld();
        }
        if (world == null) throw new IOException("Cannot load saved blueprint world: " + name);
        validateWorld(world.getWorldFolder().toPath());
        world.setAutoSave(!readOnly);
        world.setGameRule(GameRules.SPAWN_MOBS, false);
        world.setGameRule(GameRules.ADVANCE_TIME, false);
        world.setGameRule(GameRules.ADVANCE_WEATHER, false);
        world.setGameRule(GameRules.MOB_GRIEFING, false);
        world.setGameRule(GameRules.TNT_EXPLODES, false);
        world.setGameRule(GameRules.RANDOM_TICK_SPEED, 0);
        world.setGameRule(GameRules.FIRE_SPREAD_RADIUS_AROUND_PLAYER, 0);
        return world;
    }

    /** Deletes a temporary preview copy. Only folders named like previews can be deleted. */
    static void deletePreview(Path folder) throws IOException {
        if (folder.getFileName() == null || !folder.getFileName().toString().matches("hill_bp_preview_[a-f0-9]{32}")) {
            throw new IOException("Refusing to delete a folder that is not a blueprint preview: " + folder);
        }
        if (!Files.exists(folder)) return;
        if (Files.isSymbolicLink(folder)) throw new IOException("Refusing to delete a linked preview folder.");
        try (var paths = Files.walk(folder)) {
            for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.delete(path);
        }
    }

    static Path dimensionFolder(JavaPlugin plugin) {
        Path server = plugin.getServer().getWorldContainer().toPath().toAbsolutePath().normalize();
        if (Bukkit.getWorlds().isEmpty()) throw new IllegalStateException("The primary world is not ready.");
        String primary = Bukkit.getWorlds().getFirst().getName();
        return BlueprintFiles.child(server, primary).resolve("dimensions/minecraft");
    }

    static Path worldFolder(JavaPlugin plugin, String name) {
        World loaded = Bukkit.getWorld(name);
        if (loaded != null) return loaded.getWorldFolder().toPath().toAbsolutePath().normalize();
        Path legacy = BlueprintFiles.child(plugin.getServer().getWorldContainer().toPath(), name);
        Path migrated = BlueprintFiles.child(dimensionFolder(plugin), name);
        if (Files.exists(legacy) && Files.exists(migrated)) throw new IllegalStateException("Ambiguous saved world locations: " + name);
        return Files.exists(legacy) ? legacy : migrated;
    }
}
