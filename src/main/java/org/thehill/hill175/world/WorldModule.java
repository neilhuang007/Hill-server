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
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Level;

public final class WorldModule {
    public static final int BUILD_BASE_Y = 64;
    private static final int PLOTS_PER_ROW = 10;
    private static final String PEOPLE_READY_MARKER = ".hill175-people-ready";
    private static final String GENERATED_READY_MARKER = "generated";
    private static final String PEOPLE_TEMPLATE_BUILD_WORLD = "hill_people_template_build";

    private final JavaPlugin plugin;
    private final VoidChunkGenerator voidGenerator = new VoidChunkGenerator();
    private final Set<UUID> resettingEntries = new HashSet<>();
    private final Set<String> readyPeopleWorlds = new HashSet<>();
    private final Map<String, List<Runnable>> waitingPeopleWorldCallbacks = new HashMap<>();
    private World authenticationWorld;
    private World hubWorld;
    private World journeyWorld;
    private World placeWorld;
    private StructureNbtLoader.Metadata peopleStructureMetadata;
    private boolean peopleStructureMetadataResolved;
    private boolean peopleTemplatePreparing;
    private boolean peopleTemplateReady;
    private long peopleTemplateBuildStartedAtMillis;

    public WorldModule(JavaPlugin plugin) {
        this.plugin = plugin;
    }

    public void initialize() {
        authenticationWorld = loadImportedWorld(plugin.getConfig().getString("worlds.authentication", "hill_auth"));
        journeyWorld = loadVoidWorld(plugin.getConfig().getString("worlds.journey", "hill_journey"));
        placeWorld = loadVoidWorld(plugin.getConfig().getString("worlds.place", "hill_place"));

        String hubName = plugin.getConfig().getString("worlds.hub", "hill_hub");
        hubWorld = loadImportedWorld(hubName);
        if (hubWorld == null) {
            throw new IllegalStateException("Could not load hub world " + hubName);
        }

        configureWorld(authenticationWorld);
        configureWorld(hubWorld);
        configureWorld(journeyWorld);
        configureWorld(placeWorld);
        if (isNearlyEmpty(authenticationWorld)) {
            buildAuthenticationLobby();
        }
        if (isNearlyEmpty(hubWorld)) {
            buildFallbackHub();
        }
        resolvePeopleStructureMetadata();
        beginPeopleTemplatePreparation();
    }

    public boolean isPeopleWorldReady(String worldName) {
        return readyPeopleWorlds.contains(worldName);
    }

    public void whenPeopleWorldReady(String worldName, Runnable callback) {
        if (isPeopleWorldReady(worldName)) {
            callback.run();
            return;
        }
        waitingPeopleWorldCallbacks.computeIfAbsent(worldName, ignored -> new ArrayList<>()).add(callback);
    }

    public Location authenticationSpawn() {
        Location configuredOverride = configuredSpawn(authenticationWorld, "worlds.authentication-spawn");
        if (configuredOverride != null) {
            return configuredOverride;
        }
        Location configured = authenticationWorld.getSpawnLocation().clone().add(0.5, 0.1, 0.5);
        if (configured.getY() < authenticationWorld.getMinHeight() + 2
                || configured.getY() > authenticationWorld.getMaxHeight() - 2) {
            return new Location(authenticationWorld, 0.5, BUILD_BASE_Y + 2, 0.5, 0.0f, 0.0f);
        }
        return configured;
    }

    public Location hubSpawn() {
        Location configuredOverride = configuredSpawn(hubWorld, "worlds.hub-spawn");
        if (configuredOverride != null) {
            return configuredOverride;
        }
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
            world = createPeopleWorld(entry.worldName());
        }
        if (world == null && entry.category() != Category.PEOPLE) {
            throw new IllegalStateException("Plot world is unavailable: " + entry.worldName());
        }
        if (world != null) {
            configureWorld(world);
            if (entry.category() == Category.PEOPLE) {
                applyPeopleWorldSettings(world);
            }
        }
    }

    public Location entrySpawn(Entry entry) {
        ensureEntryWorld(entry);
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) {
            return hubSpawn();
        }
        if (entry.category() == Category.PEOPLE) {
            return world.getSpawnLocation().clone().add(0.5, 0.1, 0.5);
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
        readyPeopleWorlds.remove(entry.worldName());
        waitingPeopleWorldCallbacks.remove(entry.worldName());
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

    private World loadImportedWorld(String worldName) {
        World loaded = Bukkit.getWorld(worldName);
        if (loaded != null) {
            return loaded;
        }

        File legacyImport = new File(Bukkit.getWorldContainer(), worldName);
        File migratedWorld = migratedWorldFolder(worldName);
        if (migratedWorld.isDirectory()) {
            deleteMigratedHubImport(legacyImport.toPath(), worldName);
            return WorldCreator.name(worldName).createWorld();
        }
        if (!legacyImport.isDirectory()) {
            return loadVoidWorld(worldName);
        }

        World imported = WorldCreator.name(worldName).createWorld();
        if (imported != null) {
            deleteMigratedHubImport(legacyImport.toPath(), worldName);
        }
        return imported;
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
        if (resolvePeopleStructureMetadata() != null && !isPeopleTemplateReady()) {
            beginPeopleTemplatePreparation();
            throw new IllegalStateException("The People template is still preparing from structure.nbt. Try again in about a minute.");
        }
        World world = createPeopleWorld(worldName);
        BuildRegion region = peopleRegion(worldName, world);
        return new Allocation(worldName, region, 0);
    }

    private World createPeopleWorld(String worldName) {
        StructureNbtLoader.Metadata metadata = resolvePeopleStructureMetadata();
        World existing = Bukkit.getWorld(worldName);
        if (existing != null) {
            configureWorld(existing);
            applyPeopleWorldSettings(existing);
            if (metadata != null && !hasMatchingPeopleReadyMarker(existing.getWorldFolder().toPath(), metadata)) {
                for (org.bukkit.entity.Player player : existing.getPlayers()) {
                    player.teleport(hubSpawn());
                }
                Path existingPath = existing.getWorldFolder().toPath();
                Bukkit.unloadWorld(existing, false);
                deleteDirectorySafely(existingPath);
                readyPeopleWorlds.remove(worldName);
                return createPeopleWorld(worldName);
            }
            markPeopleWorldReady(existing, metadata);
            return existing;
        }

        readyPeopleWorlds.remove(worldName);
        waitingPeopleWorldCallbacks.putIfAbsent(worldName, new ArrayList<>());

        File target = new File(Bukkit.getWorldContainer(), worldName);
        File migrated = migratedWorldFolder(worldName);
        deleteStalePeopleWorldIfNecessary(target.toPath(), metadata);
        deleteStalePeopleWorldIfNecessary(migrated.toPath(), metadata);
        boolean hadSavedWorldBeforeCreate = migrated.isDirectory() || target.isDirectory();
        File template = resolveTemplateFolder();
        boolean templateReady = metadata != null && template != null && hasMatchingPeopleReadyMarker(template.toPath(), metadata);

        if (migrated.isDirectory()) {
            World migratedWorld = WorldCreator.name(worldName).createWorld();
            if (migratedWorld == null) {
                throw new IllegalStateException("Could not load migrated People world " + worldName);
            }
            configureWorld(migratedWorld);
            applyPeopleWorldSettings(migratedWorld);
            if (hasMatchingPeopleReadyMarker(migratedWorld.getWorldFolder().toPath(), metadata) || metadata == null) {
                markPeopleWorldReady(migratedWorld, metadata);
            } else if (templateReady) {
                Bukkit.unloadWorld(migratedWorld, false);
                deleteDirectorySafely(migratedWorld.getWorldFolder().toPath());
                return createPeopleWorld(worldName);
            } else {
                throw new IllegalStateException("The People template is still preparing from structure.nbt. Try again in about a minute.");
            }
            return migratedWorld;
        }

        boolean copiedTemplate = false;
        if (!target.exists() && templateReady) {
            try {
                copyWorldFolder(template.toPath(), target.toPath());
                copiedTemplate = true;
            } catch (IOException exception) {
                plugin.getLogger().log(Level.SEVERE, "Could not copy People template; falling back to generated terrain", exception);
            }
        }
        if (copiedTemplate && metadata != null && !hasMatchingPeopleReadyMarker(target.toPath(), metadata)) {
            deleteDirectorySafely(target.toPath());
            copiedTemplate = false;
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
        applyPeopleWorldSettings(world);

        if (copiedTemplate || (hadSavedWorldBeforeCreate && hasMatchingPeopleReadyMarker(world.getWorldFolder().toPath(), metadata))) {
            markPeopleWorldReady(world, metadata);
            return world;
        }

        if (metadata != null) {
            Bukkit.unloadWorld(world, false);
            deleteDirectorySafely(world.getWorldFolder().toPath());
            beginPeopleTemplatePreparation();
            throw new IllegalStateException("The People template is still preparing from structure.nbt. Try again in about a minute.");
        }

        buildPeopleFallback(world);
        markPeopleWorldReady(world, null);
        return world;
    }

    private void applyPeopleWorldSettings(World world) {
        BuildRegion region = peopleRegion(world.getName(), world);
        double borderCenterX = (region.minX() + region.maxX() + 1) / 2.0;
        double borderCenterZ = (region.minZ() + region.maxZ() + 1) / 2.0;
        double computedSize = Math.max(region.maxX() - region.minX() + 1, region.maxZ() - region.minZ() + 1) + 64.0;
        double configuredMinimum = plugin.getConfig().getDouble("people.world-border-size", 0.0);
        world.getWorldBorder().setCenter(borderCenterX, borderCenterZ);
        world.getWorldBorder().setSize(Math.max(computedSize, configuredMinimum));
        world.setSpawnLocation(region.centerX(), Math.min(world.getMaxHeight() - 2, region.minY() + 2), region.centerZ());
    }

    private BuildRegion peopleRegion(String worldName, World world) {
        StructureNbtLoader.Metadata metadata = resolvePeopleStructureMetadata();
        if (metadata != null) {
            int minX = -Math.floorDiv(metadata.sizeX(), 2);
            int minY = Math.max(world.getMinHeight(), plugin.getConfig().getInt("people.structure-origin-y", BUILD_BASE_Y));
            int minZ = -Math.floorDiv(metadata.sizeZ(), 2);
            return new BuildRegion(
                    worldName,
                    minX,
                    minY,
                    minZ,
                    minX + metadata.sizeX() - 1,
                    Math.min(world.getMaxHeight() - 1, minY + metadata.sizeY() - 1),
                    minZ + metadata.sizeZ() - 1
            );
        }
        int radius = plugin.getConfig().getInt("people.build-radius", 256);
        return new BuildRegion(
                worldName,
                -radius,
                Math.max(world.getMinHeight(), BUILD_BASE_Y),
                -radius,
                radius,
                Math.min(world.getMaxHeight() - 1, BUILD_BASE_Y + Category.PEOPLE.height()),
                radius
        );
    }

    private void resetPeople(Entry entry, Runnable completion) {
        for (org.bukkit.entity.Player player : Bukkit.getOnlinePlayers()) {
            if (player.getWorld().getName().equals(entry.worldName())) {
                player.teleport(hubSpawn());
            }
        }
        deletePrivateWorld(entry);
        World world = createPeopleWorld(entry.worldName());
        Runnable whenReady = () -> {
            configureWorld(world);
            applyPeopleWorldSettings(world);
            resettingEntries.remove(entry.id());
            completion.run();
        };
        if (isPeopleWorldReady(entry.worldName())) {
            whenReady.run();
        } else {
            whenPeopleWorldReady(entry.worldName(), whenReady);
        }
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

    private File resolvePeopleStructureFile() {
        String configured = plugin.getConfig().getString("people.structure-file", "structure.nbt");
        if (configured == null || configured.isBlank()) {
            return null;
        }
        File file = new File(configured);
        if (!file.isAbsolute()) {
            file = new File(Bukkit.getWorldContainer(), configured);
        }
        return file;
    }

    private StructureNbtLoader.Metadata resolvePeopleStructureMetadata() {
        if (peopleStructureMetadataResolved) {
            return peopleStructureMetadata;
        }
        peopleStructureMetadataResolved = true;
        File structureFile = resolvePeopleStructureFile();
        if (structureFile == null || !structureFile.isFile()) {
            return null;
        }
        try {
            peopleStructureMetadata = StructureNbtLoader.readMetadata(structureFile.toPath());
            plugin.getLogger().info("Loaded structure.nbt metadata from " + structureFile.getAbsolutePath()
                    + " (" + peopleStructureMetadata.sizeX() + "x"
                    + peopleStructureMetadata.sizeY() + "x"
                    + peopleStructureMetadata.sizeZ() + ", "
                    + peopleStructureMetadata.blockCount() + " blocks).");
        } catch (IOException exception) {
            plugin.getLogger().log(Level.SEVERE, "Could not read structure.nbt metadata for People entries", exception);
        }
        return peopleStructureMetadata;
    }

    private boolean isPeopleTemplateReady() {
        StructureNbtLoader.Metadata metadata = resolvePeopleStructureMetadata();
        File templateFolder = resolveTemplateFolder();
        peopleTemplateReady = metadata != null
                && templateFolder != null
                && hasMatchingPeopleReadyMarker(templateFolder.toPath(), metadata);
        return peopleTemplateReady;
    }

    private void beginPeopleTemplatePreparation() {
        StructureNbtLoader.Metadata metadata = resolvePeopleStructureMetadata();
        File templateFolder = resolveTemplateFolder();
        if (metadata == null || templateFolder == null) {
            return;
        }
        if (isPeopleTemplateReady() || peopleTemplatePreparing) {
            return;
        }
        peopleTemplatePreparing = true;
        peopleTemplateBuildStartedAtMillis = System.currentTimeMillis();
        Bukkit.getScheduler().runTask(plugin, () -> preparePeopleTemplateWorld(metadata, templateFolder.toPath()));
    }

    private void preparePeopleTemplateWorld(StructureNbtLoader.Metadata metadata, Path templateFolder) {
        try {
            deleteStalePeopleWorldIfNecessary(templateFolder, metadata);
            World loadedBuildWorld = Bukkit.getWorld(PEOPLE_TEMPLATE_BUILD_WORLD);
            if (loadedBuildWorld != null) {
                Bukkit.unloadWorld(loadedBuildWorld, false);
            }
            deleteDirectorySafely(locateWorldFolder(PEOPLE_TEMPLATE_BUILD_WORLD, loadedBuildWorld));
            deleteDirectorySafely(new File(Bukkit.getWorldContainer(), PEOPLE_TEMPLATE_BUILD_WORLD).toPath());
            deleteDirectorySafely(migratedWorldFolder(PEOPLE_TEMPLATE_BUILD_WORLD).toPath());

            World buildWorld = loadVoidWorld(PEOPLE_TEMPLATE_BUILD_WORLD);
            configureWorld(buildWorld);
            applyPeopleWorldSettings(buildWorld);
            BuildRegion region = peopleRegion(PEOPLE_TEMPLATE_BUILD_WORLD, buildWorld);
            int blocksPerTick = Math.max(1_000, plugin.getConfig().getInt(
                    "people.structure-import-blocks-per-tick",
                    plugin.getConfig().getInt("people.import-blocks-per-tick", 12_000)
            ));
            new PeopleStructureImportTask(
                    buildWorld,
                    metadata,
                    region,
                    blocksPerTick,
                    loadedMetadata -> finalizePeopleTemplate(buildWorld, loadedMetadata, templateFolder),
                    () -> {
                        peopleTemplatePreparing = false;
                        plugin.getLogger().severe("People template import failed. The template was not prepared.");
                    }
            ).runTaskTimer(plugin, 1L, 1L);
            plugin.getLogger().info("Preparing cached People template from structure.nbt using "
                    + metadata.blockCount() + " blocks at " + blocksPerTick + " blocks/tick.");
        } catch (IOException exception) {
            peopleTemplatePreparing = false;
            plugin.getLogger().log(Level.SEVERE, "Could not start cached People template preparation", exception);
        }
    }

    private void finalizePeopleTemplate(World templateWorld, StructureNbtLoader.Metadata metadata, Path templateFolder) {
        try {
            alignPeopleSpawn(templateWorld);
            templateWorld.save();
            deleteDirectorySafely(templateFolder);
            copyWorldFolder(templateWorld.getWorldFolder().toPath(), templateFolder);
            writePeopleReadyMarker(templateFolder, metadata);
            long durationMillis = Math.max(0L, System.currentTimeMillis() - peopleTemplateBuildStartedAtMillis);
            plugin.getLogger().info("Prepared cached People template at " + templateFolder
                    + " in " + durationMillis + "ms.");
        } catch (IOException exception) {
            plugin.getLogger().log(Level.SEVERE, "Could not finalize cached People template at " + templateFolder, exception);
        } finally {
            Path buildWorldPath = templateWorld.getWorldFolder().toPath();
            Bukkit.unloadWorld(templateWorld, false);
            deleteDirectorySafely(buildWorldPath);
            peopleTemplatePreparing = false;
            peopleTemplateReady = hasMatchingPeopleReadyMarker(templateFolder, metadata);
        }
    }

    private void markPeopleWorldReady(World world, StructureNbtLoader.Metadata metadata) {
        alignPeopleSpawn(world);
        writePeopleReadyMarker(world.getWorldFolder().toPath(), metadata);
        readyPeopleWorlds.add(world.getName());
        List<Runnable> callbacks = waitingPeopleWorldCallbacks.remove(world.getName());
        if (callbacks == null) {
            return;
        }
        for (Runnable callback : callbacks) {
            try {
                callback.run();
            } catch (RuntimeException exception) {
                plugin.getLogger().log(Level.WARNING, "People-world ready callback failed for " + world.getName(), exception);
            }
        }
    }

    private void alignPeopleSpawn(World world) {
        BuildRegion region = peopleRegion(world.getName(), world);
        int centerX = region.centerX();
        int centerZ = region.centerZ();
        int spawnY = Math.max(region.minY() + 2, world.getHighestBlockYAt(centerX, centerZ) + 2);
        world.setSpawnLocation(centerX, Math.min(world.getMaxHeight() - 2, spawnY), centerZ);
    }

    private void writePeopleReadyMarker(Path worldFolder, StructureNbtLoader.Metadata metadata) {
        try {
            Files.writeString(worldFolder.resolve(PEOPLE_READY_MARKER), readyMarkerValue(metadata));
        } catch (IOException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not write People-world ready marker in " + worldFolder, exception);
        }
    }

    private void deleteStalePeopleWorldIfNecessary(Path worldFolder, StructureNbtLoader.Metadata metadata) {
        if (metadata == null || !Files.isDirectory(worldFolder) || hasMatchingPeopleReadyMarker(worldFolder, metadata)) {
            return;
        }
        deleteDirectorySafely(worldFolder);
    }

    private boolean hasMatchingPeopleReadyMarker(Path worldFolder, StructureNbtLoader.Metadata metadata) {
        Path marker = worldFolder.resolve(PEOPLE_READY_MARKER);
        if (!Files.isRegularFile(marker)) {
            return metadata == null;
        }
        if (metadata == null) {
            return true;
        }
        try {
            return Files.readString(marker).trim().equals(readyMarkerValue(metadata));
        } catch (IOException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not read People-world ready marker in " + worldFolder, exception);
            return false;
        }
    }

    private static String readyMarkerValue(StructureNbtLoader.Metadata metadata) {
        if (metadata == null) {
            return GENERATED_READY_MARKER;
        }
        return metadata.sizeX() + "," + metadata.sizeY() + "," + metadata.sizeZ() + "," + metadata.blockCount();
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
            plugin.getLogger().info("Removed completed legacy world import at " + normalized);
        } catch (IOException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not remove migrated world import " + normalized, exception);
        }
    }

    private Location configuredSpawn(World world, String path) {
        if (!plugin.getConfig().isConfigurationSection(path)) {
            return null;
        }
        if (!plugin.getConfig().contains(path + ".x")
                || !plugin.getConfig().contains(path + ".y")
                || !plugin.getConfig().contains(path + ".z")) {
            return null;
        }
        return new Location(
                world,
                plugin.getConfig().getDouble(path + ".x"),
                plugin.getConfig().getDouble(path + ".y"),
                plugin.getConfig().getDouble(path + ".z"),
                (float) plugin.getConfig().getDouble(path + ".yaw", 0.0),
                (float) plugin.getConfig().getDouble(path + ".pitch", 0.0)
        );
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

    private final class PeopleStructureImportTask extends BukkitRunnable {
        private final ImportSuccess onSuccess;
        private final Runnable onFailure;
        private final World world;
        private final StructureNbtLoader loader;
        private final int blocksPerTick;

        private PeopleStructureImportTask(
                World world,
                StructureNbtLoader.Metadata metadata,
                BuildRegion region,
                int blocksPerTick,
                ImportSuccess onSuccess,
                Runnable onFailure
        ) throws IOException {
            this.world = world;
            this.loader = StructureNbtLoader.open(metadata.source(), world, region.minX(), region.minY(), region.minZ());
            this.blocksPerTick = blocksPerTick;
            this.onSuccess = onSuccess;
            this.onFailure = onFailure;
        }

        @Override
        public void run() {
            try {
                loader.importNextBlocks(blocksPerTick);
                if (!loader.isFinished()) {
                    return;
                }
                loader.close();
                world.save();
                onSuccess.complete(loader.metadata());
                cancel();
            } catch (Exception exception) {
                try {
                    loader.close();
                } catch (IOException ignored) {
                }
                plugin.getLogger().log(Level.SEVERE, "People structure import failed for " + world.getName(), exception);
                onFailure.run();
                cancel();
            }
        }
    }

    @FunctionalInterface
    private interface ImportSuccess {
        void complete(StructureNbtLoader.Metadata metadata) throws Exception;
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
