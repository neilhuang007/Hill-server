package org.thehill.hill175.world;

import org.bukkit.Bukkit;
import org.bukkit.GameRules;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.WorldCreator;
import org.bukkit.block.Block;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitRunnable;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Level;

public final class WorldModule {
    public static final int BUILD_BASE_Y = 64;
    private static final int PLOTS_PER_ROW = 10;

    private final JavaPlugin plugin;
    private final VoidChunkGenerator voidGenerator = new VoidChunkGenerator();
    private final Set<UUID> resettingEntries = new HashSet<>();
    private World authenticationWorld;
    private World hubWorld;
    private World journeyWorld;
    private World placeWorld;

    public WorldModule(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    public void initialize() {
        authenticationWorld = loadVoidWorld(plugin.getConfig().getString("worlds.authentication", "hill_auth"));
        journeyWorld = loadVoidWorld(plugin.getConfig().getString("worlds.journey", "hill_journey"));
        placeWorld = loadVoidWorld(plugin.getConfig().getString("worlds.place", "hill_place"));

        String hubName = plugin.getConfig().getString("worlds.hub", "hill_hub");
        hubWorld = loadHubWorld(hubName);
        if (hubWorld == null) {
            throw new IllegalStateException("Could not load hub world " + hubName);
        }

        configureWorld(authenticationWorld);
        configureWorld(hubWorld);
        configureWorld(journeyWorld);
        configureWorld(placeWorld);
        buildAuthenticationLobby();
        if (isNearlyEmpty(hubWorld)) {
            buildFallbackHub();
        }
    }

    private World loadHubWorld(String hubName) {
        World loaded = Bukkit.getWorld(hubName);
        if (loaded != null) {
            return loaded;
        }

        File legacyImport = new File(Bukkit.getWorldContainer(), hubName);
        File migratedWorld = migratedWorldFolder(hubName);
        if (migratedWorld.isDirectory()) {
            deleteMigratedHubImport(legacyImport.toPath(), hubName);
            return WorldCreator.name(hubName).createWorld();
        }
        if (!legacyImport.isDirectory()) {
            return loadVoidWorld(hubName);
        }

        World imported = WorldCreator.name(hubName).createWorld();
        if (imported != null) {
            deleteMigratedHubImport(legacyImport.toPath(), hubName);
        }
        return imported;
    }

    public Location authenticationSpawn() {
        return new Location(authenticationWorld, 0.5, BUILD_BASE_Y + 2, 0.5, 0.0f, 0.0f);
    }

    public Location hubSpawn() {
        Location configured = hubWorld.getSpawnLocation().clone().add(0.5, 0.1, 0.5);
        if (configured.getY() < hubWorld.getMinHeight() + 2 || configured.getY() > hubWorld.getMaxHeight() - 2) {
            return new Location(hubWorld, 0.5, BUILD_BASE_Y + 2, 0.5, 0.0f, 0.0f);
        }
        return configured;
    }

    public World hubWorld() {
        return hubWorld;
    }

    public Allocation allocate(Category category, int allocationIndex, UUID entryId) {
        return switch (category) {
            case JOURNEY -> allocatePlot(journeyWorld, category, allocationIndex, 96);
            case PLACE -> allocatePlot(placeWorld, category, allocationIndex, 64);
            case PEOPLE -> allocatePeople(entryId);
        };
    }

    public void ensureEntryWorld(Entry entry) {
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null && entry.category() == Category.PEOPLE) {
            createPeopleWorld(entry.worldName());
        }
        if (world == null && entry.category() != Category.PEOPLE) {
            throw new IllegalStateException("Plot world is unavailable: " + entry.worldName());
        }
        if (world != null) {
            configureWorld(world);
        }
    }

    public Location entrySpawn(Entry entry) {
        ensureEntryWorld(entry);
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) {
            return hubSpawn();
        }
        int y = entry.category() == Category.PLACE ? BUILD_BASE_Y + 2 : BUILD_BASE_Y + 3;
        return new Location(world, entry.region().centerX() + 0.5, y, entry.region().centerZ() + 0.5, 0.0f, 0.0f);
    }

    public boolean isResetting(UUID entryId) {
        return resettingEntries.contains(entryId);
    }

    public void reset(Entry entry, Runnable completion) {
        if (!resettingEntries.add(entry.id())) {
            return;
        }
        if (entry.category() == Category.PEOPLE) {
            resetPeople(entry, completion);
            return;
        }
        ensureEntryWorld(entry);
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) {
            resettingEntries.remove(entry.id());
            return;
        }
        new RegionClearTask(entry, world, completion).runTaskTimer(plugin, 1L, 1L);
    }

    public void deletePrivateWorld(Entry entry) {
        if (entry.category() != Category.PEOPLE || !entry.worldName().startsWith("hill_people_")) {
            return;
        }
        World world = Bukkit.getWorld(entry.worldName());
        Path worldPath = locateWorldFolder(entry.worldName(), world);
        if (world != null) {
            for (org.bukkit.entity.Player player : world.getPlayers()) {
                player.teleport(hubSpawn());
            }
            Bukkit.unloadWorld(world, false);
        }
        deleteDirectorySafely(worldPath);
    }

    private Allocation allocatePlot(World world, Category category, int allocationIndex, int spacing) {
        int column = allocationIndex % PLOTS_PER_ROW;
        int row = allocationIndex / PLOTS_PER_ROW;
        int minX = column * spacing;
        int minZ = row * spacing;
        BuildRegion region = new BuildRegion(
                world.getName(),
                minX,
                BUILD_BASE_Y,
                minZ,
                minX + category.width() - 1,
                BUILD_BASE_Y + category.height() - 1,
                minZ + category.depth() - 1
        );
        preparePlot(world, category, region);
        return new Allocation(world.getName(), region, allocationIndex);
    }

    private Allocation allocatePeople(UUID entryId) {
        String worldName = "hill_people_" + entryId.toString().replace("-", "").substring(0, 12);
        World world = createPeopleWorld(worldName);
        int radius = plugin.getConfig().getInt("people.build-radius", 256);
        BuildRegion region = new BuildRegion(
                worldName,
                -radius,
                world.getMinHeight(),
                -radius,
                radius,
                Math.min(world.getMaxHeight() - 1, BUILD_BASE_Y + Category.PEOPLE.height()),
                radius
        );
        return new Allocation(worldName, region, 0);
    }

    private World createPeopleWorld(String worldName) {
        World existing = Bukkit.getWorld(worldName);
        if (existing != null) {
            return existing;
        }
        File target = new File(Bukkit.getWorldContainer(), worldName);
        File migrated = migratedWorldFolder(worldName);
        if (migrated.isDirectory()) {
            World migratedWorld = WorldCreator.name(worldName).createWorld();
            if (migratedWorld == null) {
                throw new IllegalStateException("Could not load migrated People world " + worldName);
            }
            configureWorld(migratedWorld);
            return migratedWorld;
        }
        File template = resolveTemplateFolder();
        if (!target.exists() && template != null && template.isDirectory()) {
            try {
                copyWorldFolder(template.toPath(), target.toPath());
            } catch (IOException exception) {
                plugin.getLogger().log(Level.SEVERE, "Could not copy People template; using generated fallback", exception);
            }
        }
        World world;
        if (target.isDirectory()) {
            world = WorldCreator.name(worldName).createWorld();
        } else {
            world = WorldCreator.name(worldName)
                    .generator(voidGenerator)
                    .generateStructures(false)
                    .seed(plugin.getConfig().getLong("people.fallback-seed", 175L))
                    .createWorld();
        }
        if (world == null) {
            throw new IllegalStateException("Could not create People world " + worldName);
        }
        configureWorld(world);
        if (template == null || !template.isDirectory()) {
            buildPeopleFallback(world);
        }
        world.getWorldBorder().setCenter(-0.5, -0.5);
        world.getWorldBorder().setSize(plugin.getConfig().getDouble("people.world-border-size", 544.0));
        world.setSpawnLocation(0, BUILD_BASE_Y + 2, 0);
        return world;
    }

    private void resetPeople(Entry entry, Runnable completion) {
        for (org.bukkit.entity.Player player : Bukkit.getOnlinePlayers()) {
            if (player.getWorld().getName().equals(entry.worldName())) {
                player.teleport(hubSpawn());
            }
        }
        deletePrivateWorld(entry);
        World world = createPeopleWorld(entry.worldName());
        configureWorld(world);
        resettingEntries.remove(entry.id());
        completion.run();
    }

    private File resolveTemplateFolder() {
        String configured = plugin.getConfig().getString("people.template-folder", "world-templates/hill_people_template");
        if (configured == null || configured.isBlank()) {
            return null;
        }
        File file = new File(configured);
        if (!file.isAbsolute()) {
            file = new File(Bukkit.getWorldContainer(), configured);
        }
        return file;
    }

    private World loadVoidWorld(String name) {
        World world = Bukkit.getWorld(name);
        if (world == null) {
            world = WorldCreator.name(name)
                    .generator(voidGenerator)
                    .generateStructures(false)
                    .createWorld();
        }
        if (world == null) {
            throw new IllegalStateException("Could not create world " + name);
        }
        return world;
    }

    private void configureWorld(World world) {
        world.setGameRule(GameRules.SPAWN_MOBS, false);
        world.setGameRule(GameRules.FIRE_SPREAD_RADIUS_AROUND_PLAYER, 0);
        world.setGameRule(GameRules.MOB_GRIEFING, false);
        world.setGameRule(GameRules.KEEP_INVENTORY, true);
        world.setGameRule(GameRules.ADVANCE_TIME, false);
        world.setGameRule(GameRules.ADVANCE_WEATHER, false);
        world.setGameRule(GameRules.SHOW_DEATH_MESSAGES, false);
        world.setTime(6_000L);
        world.setStorm(false);
        world.setThundering(false);
    }

    private void buildAuthenticationLobby() {
        int y = BUILD_BASE_Y;
        fill(authenticationWorld, -8, y, -8, 8, y, 8, Material.POLISHED_DEEPSLATE);
        fill(authenticationWorld, -8, y + 1, -8, 8, y + 5, -8, Material.TINTED_GLASS);
        fill(authenticationWorld, -8, y + 1, 8, 8, y + 5, 8, Material.TINTED_GLASS);
        fill(authenticationWorld, -8, y + 1, -7, -8, y + 5, 7, Material.TINTED_GLASS);
        fill(authenticationWorld, 8, y + 1, -7, 8, y + 5, 7, Material.TINTED_GLASS);
        fill(authenticationWorld, -8, y + 6, -8, 8, y + 6, 8, Material.COPPER_BLOCK);
        authenticationWorld.setSpawnLocation(0, y + 2, 0);
    }

    private void buildFallbackHub() {
        int y = BUILD_BASE_Y;
        fill(hubWorld, -25, y, -25, 25, y, 25, Material.SMOOTH_QUARTZ);
        fill(hubWorld, -25, y + 1, -25, 25, y + 8, -25, Material.QUARTZ_BRICKS);
        fill(hubWorld, -25, y + 1, 25, 25, y + 8, 25, Material.QUARTZ_BRICKS);
        fill(hubWorld, -25, y + 1, -24, -25, y + 8, 24, Material.QUARTZ_BRICKS);
        fill(hubWorld, 25, y + 1, -24, 25, y + 8, 24, Material.QUARTZ_BRICKS);
        for (int x = -21; x <= 21; x += 7) {
            fill(hubWorld, x, y + 1, -24, x, y + 7, -24, Material.WAXED_COPPER_BLOCK);
            fill(hubWorld, x, y + 1, 24, x, y + 7, 24, Material.WAXED_COPPER_BLOCK);
        }
        fill(hubWorld, -4, y + 1, -4, 4, y + 1, 4, Material.DEEPSLATE_TILES);
        fill(hubWorld, -2, y + 2, -1, 2, y + 5, 1, Material.COPPER_BLOCK);
        hubWorld.setSpawnLocation(0, y + 2, 15);
    }

    private void buildPeopleFallback(World world) {
        int radius = plugin.getConfig().getInt("people.build-radius", 256);
        fill(world, -radius, BUILD_BASE_Y - 3, -radius, radius, BUILD_BASE_Y - 3, radius, Material.STONE);
        fill(world, -radius, BUILD_BASE_Y - 2, -radius, radius, BUILD_BASE_Y - 1, radius, Material.DIRT);
        fill(world, -radius, BUILD_BASE_Y, -radius, radius, BUILD_BASE_Y, radius, Material.GRASS_BLOCK);
        for (int coordinate = -radius; coordinate <= radius; coordinate += 32) {
            fill(world, coordinate, BUILD_BASE_Y + 1, -radius, coordinate + 2, BUILD_BASE_Y + 1, radius, Material.LIGHT_GRAY_CONCRETE);
            fill(world, -radius, BUILD_BASE_Y + 1, coordinate, radius, BUILD_BASE_Y + 1, coordinate + 2, Material.LIGHT_GRAY_CONCRETE);
        }
    }

    private void preparePlot(World world, Category category, BuildRegion region) {
        if (category == Category.JOURNEY) {
            fill(world, region.minX(), BUILD_BASE_Y - 2, region.minZ(), region.maxX(), BUILD_BASE_Y - 2, region.maxZ(), Material.STONE);
            fill(world, region.minX(), BUILD_BASE_Y - 1, region.minZ(), region.maxX(), BUILD_BASE_Y - 1, region.maxZ(), Material.DIRT);
            fill(world, region.minX(), BUILD_BASE_Y, region.minZ(), region.maxX(), BUILD_BASE_Y, region.maxZ(), Material.GRASS_BLOCK);
            outline(world, region.minX(), BUILD_BASE_Y + 1, region.minZ(), region.maxX(), region.maxZ(), Material.YELLOW_CONCRETE);
        } else if (category == Category.PLACE) {
            fill(world, region.minX(), BUILD_BASE_Y, region.minZ(), region.maxX(), BUILD_BASE_Y, region.maxZ(), Material.SMOOTH_STONE);
            fill(world, region.minX(), BUILD_BASE_Y + 1, region.minZ(), region.maxX(), BUILD_BASE_Y + 9, region.minZ(), Material.QUARTZ_BRICKS);
            fill(world, region.minX(), BUILD_BASE_Y + 1, region.maxZ(), region.maxX(), BUILD_BASE_Y + 9, region.maxZ(), Material.QUARTZ_BRICKS);
            fill(world, region.minX(), BUILD_BASE_Y + 1, region.minZ(), region.minX(), BUILD_BASE_Y + 9, region.maxZ(), Material.QUARTZ_BRICKS);
            fill(world, region.maxX(), BUILD_BASE_Y + 1, region.minZ(), region.maxX(), BUILD_BASE_Y + 9, region.maxZ(), Material.QUARTZ_BRICKS);
            fill(world, region.minX(), BUILD_BASE_Y + 10, region.minZ(), region.maxX(), BUILD_BASE_Y + 10, region.maxZ(), Material.SMOOTH_QUARTZ);
            fill(world, region.centerX() - 1, BUILD_BASE_Y + 1, region.minZ(), region.centerX() + 1, BUILD_BASE_Y + 3, region.minZ(), Material.AIR);
        }
    }

    private static boolean isNearlyEmpty(World world) {
        Location spawn = world.getSpawnLocation();
        int solid = 0;
        for (int x = spawn.getBlockX() - 8; x <= spawn.getBlockX() + 8; x++) {
            for (int z = spawn.getBlockZ() - 8; z <= spawn.getBlockZ() + 8; z++) {
                if (!world.getBlockAt(x, spawn.getBlockY() - 1, z).getType().isAir()) {
                    solid++;
                }
            }
        }
        return solid < 8;
    }

    private static void fill(World world, int minX, int minY, int minZ, int maxX, int maxY, int maxZ, Material material) {
        int worldMinY = world.getMinHeight();
        int worldMaxY = world.getMaxHeight() - 1;
        for (int x = Math.min(minX, maxX); x <= Math.max(minX, maxX); x++) {
            for (int y = Math.max(worldMinY, Math.min(minY, maxY)); y <= Math.min(worldMaxY, Math.max(minY, maxY)); y++) {
                for (int z = Math.min(minZ, maxZ); z <= Math.max(minZ, maxZ); z++) {
                    Block block = world.getBlockAt(x, y, z);
                    block.setType(material, false);
                }
            }
        }
    }

    private static void outline(World world, int minX, int y, int minZ, int maxX, int maxZ, Material material) {
        fill(world, minX, y, minZ, maxX, y, minZ, material);
        fill(world, minX, y, maxZ, maxX, y, maxZ, material);
        fill(world, minX, y, minZ, minX, y, maxZ, material);
        fill(world, maxX, y, minZ, maxX, y, maxZ, material);
    }

    private static void copyWorldFolder(Path source, Path target) throws IOException {
        try (var paths = Files.walk(source)) {
            for (Path sourcePath : paths.toList()) {
                Path relative = source.relativize(sourcePath);
                String name = relative.getFileName() == null ? "" : relative.getFileName().toString();
                if (name.equals("uid.dat") || name.equals("session.lock")) {
                    continue;
                }
                Path targetPath = target.resolve(relative);
                if (Files.isDirectory(sourcePath)) {
                    Files.createDirectories(targetPath);
                } else {
                    Files.createDirectories(targetPath.getParent());
                    Files.copy(sourcePath, targetPath, StandardCopyOption.REPLACE_EXISTING);
                }
            }
        }
    }

    private void deleteMigratedHubImport(Path target, String hubName) {
        Path worldContainer = Bukkit.getWorldContainer().toPath().toAbsolutePath().normalize();
        Path normalized = target.toAbsolutePath().normalize();
        Path expected = worldContainer.resolve(hubName).normalize();
        Path migrated = migratedWorldFolder(hubName).toPath().toAbsolutePath().normalize();
        boolean safeName = hubName.startsWith("hill_") && hubName.matches("[a-z0-9_]+$");
        if (!safeName
                || !normalized.equals(expected)
                || !normalized.startsWith(worldContainer)
                || normalized.equals(migrated)
                || !Files.isDirectory(migrated)
                || !Files.isRegularFile(normalized.resolve("level.dat"))) {
            return;
        }
        try (var paths = Files.walk(normalized)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
            plugin.getLogger().info("Removed completed legacy hub import at " + normalized);
        } catch (IOException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not remove migrated hub import " + normalized, exception);
        }
    }

    private void deleteDirectorySafely(Path target) {
        Path worldContainer = Bukkit.getWorldContainer().toPath().toAbsolutePath().normalize();
        Path normalized = target.toAbsolutePath().normalize();
        if (!normalized.startsWith(worldContainer) || !normalized.getFileName().toString().startsWith("hill_people_")) {
            plugin.getLogger().severe("Refused to delete unexpected world path: " + normalized);
            return;
        }
        if (!Files.exists(normalized)) {
            return;
        }
        try (var paths = Files.walk(normalized)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        } catch (IOException exception) {
            plugin.getLogger().log(Level.SEVERE, "Could not delete private world " + normalized, exception);
        }
    }

    private Path locateWorldFolder(String worldName, World loadedWorld) {
        if (loadedWorld != null) {
            return loadedWorld.getWorldFolder().toPath();
        }
        File direct = new File(Bukkit.getWorldContainer(), worldName);
        if (direct.exists()) {
            return direct.toPath();
        }
        return migratedWorldFolder(worldName).toPath();
    }

    private File migratedWorldFolder(String worldName) {
        World primary = Bukkit.getWorlds().getFirst();
        File primaryLevelRoot = new File(Bukkit.getWorldContainer(), primary.getName());
        return new File(primaryLevelRoot, "dimensions/minecraft/" + worldName);
    }

    public record Allocation(String worldName, BuildRegion region, int allocationIndex) {
    }

    private final class RegionClearTask extends BukkitRunnable {
        private static final int BLOCKS_PER_TICK = 8_000;
        private final Entry entry;
        private final World world;
        private final Runnable completion;
        private final Category category;
        private final BuildRegion region;
        private int x;
        private int y;
        private int z;

        private RegionClearTask(Entry entry, World world, Runnable completion) {
            this.entry = entry;
            this.world = world;
            this.completion = completion;
            this.category = entry.category();
            this.region = entry.region();
            this.x = region.minX();
            this.y = region.minY();
            this.z = region.minZ();
        }

        @Override
        public void run() {
            int changed = 0;
            while (changed < BLOCKS_PER_TICK) {
                world.getBlockAt(x, y, z).setType(Material.AIR, false);
                changed++;
                z++;
                if (z > region.maxZ()) {
                    z = region.minZ();
                    y++;
                }
                if (y > region.maxY()) {
                    y = region.minY();
                    x++;
                }
                if (x > region.maxX()) {
                    preparePlot(world, category, region);
                    resettingEntries.remove(entry.id());
                    completion.run();
                    cancel();
                    return;
                }
            }
        }
    }
}
