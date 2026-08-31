package org.thehill.hill175.world;

import org.bukkit.Bukkit;
import org.bukkit.Difficulty;
import org.bukkit.GameRules;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.WorldCreator;
import org.bukkit.block.Block;
import org.bukkit.block.data.BlockData;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitRunnable;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.logging.Level;

public final class WorldModule {
    public static final int BUILD_BASE_Y = 64;
    private static final int PLOTS_PER_ROW = 10;
    private static final String PEOPLE_READY_MARKER = ".hill175-people-ready";
    private static final String GENERATED_READY_MARKER = "generated";
    private static final String PEOPLE_TEMPLATE_BUILD_WORLD = "hill_people_template_build";

    private final JavaPlugin plugin;
    private final VoidChunkGenerator voidGenerator = new VoidChunkGenerator();
    private final long survivalSeed;
    private final Map<UUID, ResetOperation> resetOperations = new HashMap<>();
    private final Set<String> readyPeopleWorlds = new HashSet<>();
    private final Map<String, List<Runnable>> waitingPeopleWorldCallbacks = new HashMap<>();
    private World authenticationWorld;
    private World hubWorld;
    private World journeyWorld;
    private World placeWorld;
    private World survivalWorld;
    private World survivalNetherWorld;
    private World survivalEndWorld;
    private StructureNbtLoader.Metadata peopleStructureMetadata;
    private boolean peopleStructureMetadataResolved;
    private boolean peopleTemplatePreparing;
    private boolean peopleTemplateReady;
    private long peopleTemplateBuildStartedAtMillis;

    public WorldModule(JavaPlugin plugin) {
        this.plugin = plugin;
        this.survivalSeed = loadOrCreateSurvivalSeed();
    }

    public void initialize() {
        authenticationWorld = loadImportedWorld(plugin.getConfig().getString("worlds.authentication", "hill_auth"));
        journeyWorld = loadVoidWorld(plugin.getConfig().getString("worlds.journey", "hill_journey"));
        placeWorld = loadVoidWorld(plugin.getConfig().getString("worlds.place", "hill_place"));
        String survivalName = plugin.getConfig().getString("worlds.survival", "world");
        survivalWorld = loadSurvivalWorld(survivalName, World.Environment.NORMAL);
        survivalNetherWorld = loadSurvivalWorld(
                plugin.getConfig().getString("worlds.survival-nether", survivalName + "_nether"),
                World.Environment.NETHER
        );
        survivalEndWorld = loadSurvivalWorld(
                plugin.getConfig().getString("worlds.survival-end", survivalName + "_the_end"),
                World.Environment.THE_END
        );

        String hubName = plugin.getConfig().getString("worlds.hub", "hill_hub");
        hubWorld = loadImportedWorld(hubName);
        if (hubWorld == null) {
            throw new IllegalStateException("Could not load hub world " + hubName);
        }

        configureWorld(authenticationWorld);
        configureWorld(hubWorld);
        configureWorld(journeyWorld);
        configureWorld(placeWorld);
        configureSurvivalWorld(survivalWorld);
        configureSurvivalWorld(survivalNetherWorld);
        configureSurvivalWorld(survivalEndWorld);
        if (isNearlyEmpty(authenticationWorld)) {
            buildAuthenticationLobby();
        }
        if (isNearlyEmpty(hubWorld)) {
            buildFallbackHub();
        }
        Location configuredHubSpawn = configuredSpawn(hubWorld, "worlds.hub-spawn");
        if (configuredHubSpawn != null) {
            hubWorld.setSpawnLocation(configuredHubSpawn);
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

    public World survivalWorld() {
        return survivalWorld;
    }

    public World survivalNetherWorld() {
        return survivalNetherWorld;
    }

    public World survivalEndWorld() {
        return survivalEndWorld;
    }

    public boolean isSurvivalWorld(World world) {
        return sameWorld(world, survivalWorld)
                || sameWorld(world, survivalNetherWorld)
                || sameWorld(world, survivalEndWorld);
    }

    public boolean isSurvivalWorld(Location location) {
        return location != null && isSurvivalWorld(location.getWorld());
    }

    public Location survivalSpawn() {
        Location configuredOverride = configuredSpawn(survivalWorld, "worlds.survival-spawn");
        if (configuredOverride != null) {
            return configuredOverride;
        }
        Location spawn = survivalWorld.getSpawnLocation().clone().add(0.5, 0.1, 0.5);
        return new Location(survivalWorld, spawn.getX(), spawn.getY(), spawn.getZ(), 0.0f, 0.0f);
    }

    public Location survivalNpcLocation() {
        Location configured = configuredSpawn(hubWorld, "worlds.hub-npcs.survival");
        if (configured != null) {
            return configured;
        }
        return new Location(hubWorld, 70.5, 66.0, 31.5, 0.0f, 0.0f);
    }

    public Location hubNpcLocation(Category category) {
        String categoryPath = switch (category) {
            case JOURNEY -> "journey";
            case PLACE -> "place";
            case PEOPLE -> "people";
        };
        Location configured = configuredSpawn(hubWorld, "worlds.hub-npcs." + categoryPath);
        if (configured != null) {
            return configured;
        }
        Location center = hubSpawn();
        return switch (category) {
            case JOURNEY -> center.clone().add(-6, 0, -6);
            case PLACE -> center.clone().add(0, 0, -8);
            case PEOPLE -> center.clone().add(6, 0, -6);
        };
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

    /** Updates older People entries to the current structure/world-height build bounds. */
    public boolean synchronizePeopleRegion(Entry entry) {
        if (entry.category() != Category.PEOPLE) {
            return false;
        }
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) {
            return false;
        }
        BuildRegion expected = peopleRegion(entry.worldName(), world);
        if (expected.equals(entry.region())) {
            return false;
        }
        entry.region(expected);
        return true;
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

    /**
     * Resolves a safe, two-block-tall standing position near the normal entry spawn. The search is
     * intentionally constrained to the entry region so a safety fallback can never grant access to
     * a neighboring plot.
     */
    public Optional<Location> safeEntrySpawn(Entry entry) {
        Location preferred = entrySpawn(entry);
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null || preferred.getWorld() == null || !entry.worldName().equals(preferred.getWorld().getName())) {
            return Optional.empty();
        }
        return SafeSpawnFinder.find(
                entry.region(),
                preferred.getBlockX(),
                preferred.getBlockY(),
                preferred.getBlockZ(),
                new SafeSpawnFinder.CellSafety() {
                    @Override
                    public boolean canOccupy(int x, int y, int z) {
                        Block block = world.getBlockAt(x, y, z);
                        Material material = block.getType();
                        return block.isPassable() && !block.isLiquid() && !isUnsafeBodyMaterial(material);
                    }

                    @Override
                    public boolean canStandOn(int x, int y, int z) {
                        Block block = world.getBlockAt(x, y, z);
                        Material material = block.getType();
                        return material.isSolid() && !block.isPassable() && !isUnsafeFloorMaterial(material);
                    }
                }
        ).map(spawn -> new Location(
                world,
                spawn.x() + 0.5,
                spawn.y() + 0.05,
                spawn.z() + 0.5,
                preferred.getYaw(),
                preferred.getPitch()
        ));
    }

    /**
     * Resolves the safe feet position that reproduces a saved eye-level camera pose without
     * teleporting the player's body into a block, dangerous fluid, another world, or outside the
     * entry/world border.
     */
    public Optional<Location> safeCameraTeleport(Entry entry, CameraPose pose, double eyeHeight) {
        World world = Bukkit.getWorld(pose.worldName());
        if (world == null || !entry.worldName().equals(pose.worldName())) {
            return Optional.empty();
        }
        return CameraPoseResolver.resolve(
                entry.region(),
                pose,
                eyeHeight,
                (x, y, z) -> world.getWorldBorder().isInside(new Location(world, x, y, z)),
                (x, y, z) -> {
                    Block block = world.getBlockAt(x, y, z);
                    return block.isPassable() && !block.isLiquid() && !isUnsafeBodyMaterial(block.getType());
                }
        ).map(resolved -> new Location(
                world,
                resolved.x(),
                resolved.feetY(),
                resolved.z(),
                resolved.yaw(),
                resolved.pitch()
        ));
    }

    private static boolean isUnsafeBodyMaterial(Material material) {
        return switch (material) {
            case FIRE, SOUL_FIRE, WATER, LAVA, POWDER_SNOW, SWEET_BERRY_BUSH, WITHER_ROSE, NETHER_PORTAL,
                    END_PORTAL -> true;
            default -> false;
        };
    }

    private static boolean isUnsafeFloorMaterial(Material material) {
        return switch (material) {
            case FIRE, SOUL_FIRE, WATER, LAVA, POWDER_SNOW, MAGMA_BLOCK, CACTUS, CAMPFIRE, SOUL_CAMPFIRE,
                    SWEET_BERRY_BUSH, WITHER_ROSE, POINTED_DRIPSTONE, NETHER_PORTAL, END_PORTAL -> true;
            default -> false;
        };
    }

    public boolean isResetting(UUID entryId) {
        return resetOperations.containsKey(entryId);
    }

    public void reset(Entry entry, Runnable completion) {
        reset(entry, completion, ignored -> {
        });
    }

    public void reset(Entry entry, Runnable completion, Consumer<RuntimeException> failure) {
        if (!Bukkit.isPrimaryThread()) {
            Bukkit.getScheduler().runTask(plugin, () -> reset(entry, completion, failure));
            return;
        }

        ResetOperation existing = resetOperations.get(entry.id());
        if (existing != null) {
            existing.callbacks.add(new ResetCallback(completion, failure));
            return;
        }

        ResetOperation operation = new ResetOperation(completion, failure);
        resetOperations.put(entry.id(), operation);
        try {
            if (entry.category() == Category.PEOPLE) {
                resetPeople(entry);
                return;
            }
            ensureEntryWorld(entry);
            World world = Bukkit.getWorld(entry.worldName());
            if (world == null) {
                throw new IllegalStateException("Entry world is unavailable: " + entry.worldName());
            }
            new RegionClearTask(
                    entry.id(),
                    world,
                    entry.category(),
                    entry.region()
            ).runTaskTimer(plugin, 1L, 1L);
        } catch (RuntimeException exception) {
            failReset(entry.id(), exception);
        }
    }

    public boolean deletePrivateWorld(Entry entry) {
        if (entry.category() != Category.PEOPLE || !entry.worldName().startsWith("hill_people_")) {
            return false;
        }
        readyPeopleWorlds.remove(entry.worldName());
        waitingPeopleWorldCallbacks.remove(entry.worldName());
        World world = Bukkit.getWorld(entry.worldName());
        Path worldPath = locateWorldFolder(entry.worldName(), world);
        if (world != null) {
            for (org.bukkit.entity.Player player : world.getPlayers()) {
                player.teleport(hubSpawn());
            }
            if (!Bukkit.unloadWorld(world, false)) {
                plugin.getLogger().severe("Could not unload private world " + entry.worldName());
                return false;
            }
        }
        return deleteDirectorySafely(worldPath);
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
            throw new IllegalStateException("The People template is still preparing. Try again in about a minute.");
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
        boolean templateReady = isConfiguredPeopleTemplateReady(template, metadata);

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
                throw new IllegalStateException("The People template is still preparing. Try again in about a minute.");
            }
            return migratedWorld;
        }

        boolean copiedTemplate = false;
        Path cloneDestination = peopleTemplateCloneDestination(target.toPath(), migrated.toPath());
        if (!target.exists() && !migrated.exists() && templateReady) {
            try {
                copyWorldFolder(template.toPath(), cloneDestination);
                copiedTemplate = true;
            } catch (IOException exception) {
                if (!deleteDirectorySafely(cloneDestination)) {
                    throw new IllegalStateException("Could not remove a partial People template clone at "
                            + cloneDestination, exception);
                }
                plugin.getLogger().log(Level.SEVERE, "Could not copy People template", exception);
            }
        }
        if (copiedTemplate && metadata != null && !hasMatchingPeopleReadyMarker(cloneDestination, metadata)) {
            deleteDirectorySafely(cloneDestination);
            copiedTemplate = false;
        }
        if (!target.exists()
                && !migrated.exists()
                && !copiedTemplate
                && metadata == null
                && plugin.getConfig().getBoolean("people.require-template", true)) {
            throw new IllegalStateException("The configured People template is unavailable or invalid: "
                    + (template == null ? "<not configured>" : template.getAbsolutePath()));
        }

        World world;
        if (target.isDirectory() || migrated.isDirectory()) {
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
            throw new IllegalStateException("The People template is still preparing. Try again in about a minute.");
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
                    world.getMaxHeight() - 1,
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

    private void resetPeople(Entry entry) {
        if (!isPeopleRebuildSourceReady()) {
            failReset(entry.id(), new IllegalStateException(
                    "The People template is unavailable or still preparing; the existing entry was preserved."));
            return;
        }
        for (org.bukkit.entity.Player player : Bukkit.getOnlinePlayers()) {
            if (player.getWorld().getName().equals(entry.worldName())) {
                player.teleport(hubSpawn());
            }
        }
        if (!deletePrivateWorld(entry)) {
            failReset(entry.id(), new IllegalStateException(
                    "Private world could not be unloaded and removed: " + entry.worldName()));
            return;
        }
        World world = createPeopleWorld(entry.worldName());
        Runnable whenReady = () -> {
            try {
                configureWorld(world);
                applyPeopleWorldSettings(world);
                completeReset(entry.id());
            } catch (RuntimeException exception) {
                failReset(entry.id(), exception);
            }
        };
        if (isPeopleWorldReady(entry.worldName())) {
            whenReady.run();
        } else {
            whenPeopleWorldReady(entry.worldName(), whenReady);
        }
    }

    private boolean isPeopleRebuildSourceReady() {
        StructureNbtLoader.Metadata metadata = resolvePeopleStructureMetadata();
        if (metadata != null && !isPeopleTemplateReady()) {
            beginPeopleTemplatePreparation();
            return false;
        }
        return metadata != null
                || !plugin.getConfig().getBoolean("people.require-template", true)
                || isPeopleTemplateReady();
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
            plugin.getLogger().info("Loaded People structure metadata from " + structureFile.getAbsolutePath()
                    + " (" + peopleStructureMetadata.sizeX() + "x"
                    + peopleStructureMetadata.sizeY() + "x"
                    + peopleStructureMetadata.sizeZ() + ", "
                    + peopleStructureMetadata.blockCount() + " blocks).");
        } catch (IOException exception) {
            plugin.getLogger().log(Level.SEVERE, "Could not read People structure metadata for People entries", exception);
        }
        return peopleStructureMetadata;
    }

    private boolean isPeopleTemplateReady() {
        StructureNbtLoader.Metadata metadata = resolvePeopleStructureMetadata();
        File templateFolder = resolveTemplateFolder();
        peopleTemplateReady = isConfiguredPeopleTemplateReady(templateFolder, metadata);
        return peopleTemplateReady;
    }

    private boolean isConfiguredPeopleTemplateReady(File templateFolder, StructureNbtLoader.Metadata metadata) {
        if (templateFolder == null || !templateFolder.isDirectory()) {
            return false;
        }
        if (metadata != null) {
            return hasMatchingPeopleReadyMarker(templateFolder.toPath(), metadata);
        }
        int expectedRegionFiles = Math.max(1,
                plugin.getConfig().getInt("people.template-region-file-count", 26));
        int expectedPoiFiles = Math.max(0,
                plugin.getConfig().getInt("people.template-poi-file-count", 11));
        return isGeneratedAnvilTemplateReady(templateFolder.toPath(), expectedRegionFiles, expectedPoiFiles);
    }

    static boolean isGeneratedAnvilTemplateReady(
            Path templateFolder,
            int expectedRegionFiles,
            int expectedPoiFiles
    ) {
        Path marker = templateFolder.resolve(PEOPLE_READY_MARKER);
        Path regionFolder = templateFolder.resolve("region");
        Path poiFolder = templateFolder.resolve("poi");
        Path manifest = templateFolder.resolve("voxelearth-hill-manifest.json");
        if (!Files.isRegularFile(marker)
                || !Files.isRegularFile(manifest)
                || !Files.isDirectory(regionFolder)
                || (expectedPoiFiles > 0 && !Files.isDirectory(poiFolder))
                || Files.exists(templateFolder.resolve("dimensions"))) {
            return false;
        }
        try {
            if (!Files.readString(marker).trim().equals(GENERATED_READY_MARKER)
                    || Files.size(manifest) == 0L) {
                return false;
            }
            return hasExpectedAnvilFiles(regionFolder, expectedRegionFiles)
                    && hasExpectedOptionalAnvilFiles(poiFolder, expectedPoiFiles);
        } catch (IOException exception) {
            return false;
        }
    }

    private static boolean hasExpectedOptionalAnvilFiles(Path folder, int expectedCount) throws IOException {
        if (expectedCount == 0 && !Files.isDirectory(folder)) {
            return true;
        }
        return hasExpectedAnvilFiles(folder, expectedCount);
    }

    private static boolean hasExpectedAnvilFiles(Path folder, int expectedCount) throws IOException {
        try (var paths = Files.list(folder)) {
            List<Path> regionFiles = paths
                    .filter(path -> Files.isRegularFile(path)
                            && path.getFileName().toString().matches("r\\.-?\\d+\\.-?\\d+\\.mca"))
                    .toList();
            if (regionFiles.size() != expectedCount) {
                return false;
            }
            for (Path regionFile : regionFiles) {
                if (Files.size(regionFile) < 8_192L) {
                    return false;
                }
            }
            return true;
        }
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
            long maxNanosPerTick = Math.max(1L,
                    plugin.getConfig().getLong("people.structure-import-max-millis-per-tick", 10L)) * 1_000_000L;
            new PeopleStructureImportTask(
                    buildWorld,
                    metadata,
                    region,
                    blocksPerTick,
                    maxNanosPerTick,
                    loadedMetadata -> finalizePeopleTemplate(buildWorld, loadedMetadata, templateFolder),
                    () -> {
                        peopleTemplatePreparing = false;
                        plugin.getLogger().severe("People template import failed. The template was not prepared.");
                    }
            ).runTaskTimer(plugin, 1L, 1L);
            plugin.getLogger().info("Preparing cached People template from structure file using "
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

    private World loadSurvivalWorld(String name, World.Environment environment) {
        World world = Bukkit.getWorld(name);
        if (world == null) {
            world = WorldCreator.name(name)
                    .environment(environment)
                    .generateStructures(true)
                    .seed(survivalSeed)
                    .createWorld();
        }
        if (world == null) {
            throw new IllegalStateException("Could not create survival world " + name);
        }
        return world;
    }

    private long loadOrCreateSurvivalSeed() {
        if (plugin.getConfig().contains("survival.seed")) {
            return plugin.getConfig().getLong("survival.seed");
        }
        Path seedFile = plugin.getDataFolder().toPath().resolve("survival-seed.txt");
        if (Files.isRegularFile(seedFile)) {
            try {
                return Long.parseLong(Files.readString(seedFile, StandardCharsets.UTF_8).trim());
            } catch (IOException | NumberFormatException exception) {
                throw new IllegalStateException("Could not read persistent survival seed from " + seedFile, exception);
            }
        }
        long seed;
        do {
            seed = new SecureRandom().nextLong();
        } while (seed == 0L);
        Path temporary = null;
        try {
            Files.createDirectories(seedFile.getParent());
            temporary = Files.createTempFile(seedFile.getParent(), "survival-seed-", ".tmp");
            Files.writeString(temporary, Long.toString(seed) + System.lineSeparator(), StandardCharsets.UTF_8);
            try {
                Files.move(temporary, seedFile, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException exception) {
                Files.move(temporary, seedFile, StandardCopyOption.REPLACE_EXISTING);
            }
            plugin.getLogger().info("Generated and persisted a random survival seed.");
            return seed;
        } catch (IOException exception) {
            throw new IllegalStateException("Could not persist random survival seed to " + seedFile, exception);
        } finally {
            if (temporary != null) {
                try {
                    Files.deleteIfExists(temporary);
                } catch (IOException ignored) {
                    // The target seed is already durable; a stale temp file is harmless.
                }
            }
        }
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

    private void configureSurvivalWorld(World world) {
        world.setDifficulty(survivalDifficulty());
        world.setGameRule(GameRules.SPAWN_MOBS, true);
        world.setGameRule(GameRules.SPAWN_MONSTERS, true);
        world.setGameRule(GameRules.MOB_GRIEFING, plugin.getConfig().getBoolean("survival.mob-griefing", true));
        world.setGameRule(GameRules.KEEP_INVENTORY, plugin.getConfig().getBoolean("survival.keep-inventory", false));
        world.setGameRule(GameRules.ADVANCE_TIME, true);
        world.setGameRule(GameRules.ADVANCE_WEATHER, true);
        world.setGameRule(GameRules.SHOW_DEATH_MESSAGES, true);
        world.setGameRule(GameRules.FIRE_DAMAGE, true);
        world.setGameRule(GameRules.FALL_DAMAGE, true);
        world.setGameRule(GameRules.DROWNING_DAMAGE, true);
        world.setGameRule(GameRules.FREEZE_DAMAGE, true);
        world.setGameRule(GameRules.TNT_EXPLODES, true);
        world.setGameRule(GameRules.PVP, plugin.getConfig().getBoolean("survival.pvp", true));
        world.setPVP(plugin.getConfig().getBoolean("survival.pvp", true));
    }

    private Difficulty survivalDifficulty() {
        String configured = plugin.getConfig().getString("survival.difficulty", "NORMAL");
        try {
            return Difficulty.valueOf(configured.trim().toUpperCase(java.util.Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            plugin.getLogger().warning("Invalid survival.difficulty '" + configured + "'; using NORMAL.");
            return Difficulty.NORMAL;
        }
    }

    private static boolean sameWorld(World left, World right) {
        return left != null && right != null && left.getName().equals(right.getName());
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
        BlockData blockData = material.createBlockData();
        for (int x = Math.min(minX, maxX); x <= Math.max(minX, maxX); x++) {
            for (int y = Math.max(worldMinY, Math.min(minY, maxY)); y <= Math.min(worldMaxY, Math.max(minY, maxY)); y++) {
                for (int z = Math.min(minZ, maxZ); z <= Math.max(minZ, maxZ); z++) {
                    Block block = world.getBlockAt(x, y, z);
                    block.setBlockData(blockData, false);
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
                if (shouldSkipWorldClonePath(relative)) {
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

    static boolean shouldSkipWorldClonePath(Path relative) {
        String name = relative.getFileName() == null ? "" : relative.getFileName().toString();
        return name.equals("uid.dat")
                || name.equals("session.lock")
                || name.equals("level.dat")
                || name.equals("level.dat_old")
                || relative.equals(Path.of("data", "paper", "metadata.dat"));
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

    private boolean deleteDirectorySafely(Path target) {
        Path worldContainer = Bukkit.getWorldContainer().toPath().toAbsolutePath().normalize();
        Path normalized = target.toAbsolutePath().normalize();
        if (!normalized.startsWith(worldContainer) || !normalized.getFileName().toString().startsWith("hill_people_")) {
            plugin.getLogger().severe("Refused to delete unexpected world path: " + normalized);
            return false;
        }
        if (!Files.exists(normalized)) {
            return true;
        }
        try (var paths = Files.walk(normalized)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
            return !Files.exists(normalized);
        } catch (IOException exception) {
            plugin.getLogger().log(Level.SEVERE, "Could not delete private world " + normalized, exception);
            return false;
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

    static Path peopleTemplateCloneDestination(Path legacyWorldFolder, Path migratedWorldFolder) {
        return migratedWorldFolder;
    }

    public record Allocation(String worldName, BuildRegion region, int allocationIndex) {
    }

    private final class PeopleStructureImportTask extends BukkitRunnable {
        private final ImportSuccess onSuccess;
        private final Runnable onFailure;
        private final World world;
        private final StructureNbtLoader loader;
        private final int blocksPerTick;
        private final long maxNanosPerTick;

        private PeopleStructureImportTask(
                World world,
                StructureNbtLoader.Metadata metadata,
                BuildRegion region,
                int blocksPerTick,
                long maxNanosPerTick,
                ImportSuccess onSuccess,
                Runnable onFailure
        ) throws IOException {
            this.world = world;
            this.loader = StructureNbtLoader.open(metadata.source(), world, region.minX(), region.minY(), region.minZ());
            this.blocksPerTick = blocksPerTick;
            this.maxNanosPerTick = maxNanosPerTick;
            this.onSuccess = onSuccess;
            this.onFailure = onFailure;
        }

        @Override
        public void run() {
            try {
                loader.importNextBlocks(blocksPerTick, maxNanosPerTick);
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
        private final UUID entryId;
        private final World world;
        private final Category category;
        private final BuildRegion region;
        private int x;
        private int y;
        private int z;

        private RegionClearTask(UUID entryId, World world, Category category, BuildRegion region) {
            this.entryId = entryId;
            this.world = world;
            this.category = category;
            this.region = region;
            this.x = region.minX();
            this.y = region.minY();
            this.z = region.minZ();
        }

        @Override
        public void run() {
            int changed = 0;
            try {
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
                        cancel();
                        completeReset(entryId);
                        return;
                    }
                }
            } catch (RuntimeException exception) {
                cancel();
                failReset(entryId, exception);
            }
        }
    }

    private void completeReset(UUID entryId) {
        ResetOperation operation = resetOperations.remove(entryId);
        if (operation == null) {
            return;
        }
        for (ResetCallback callback : operation.callbacks) {
            try {
                callback.completion.run();
            } catch (RuntimeException exception) {
                plugin.getLogger().log(Level.WARNING, "Reset completion callback failed for " + entryId, exception);
            }
        }
    }

    private void failReset(UUID entryId, RuntimeException exception) {
        ResetOperation operation = resetOperations.remove(entryId);
        if (operation == null) {
            return;
        }
        plugin.getLogger().log(Level.SEVERE, "Reset failed for entry " + entryId, exception);
        for (ResetCallback callback : operation.callbacks) {
            try {
                callback.failure.accept(exception);
            } catch (RuntimeException callbackException) {
                plugin.getLogger().log(Level.WARNING,
                        "Reset failure callback failed for " + entryId, callbackException);
            }
        }
    }

    private static final class ResetOperation {
        private final List<ResetCallback> callbacks = new ArrayList<>();

        private ResetOperation(Runnable completion, Consumer<RuntimeException> failure) {
            callbacks.add(new ResetCallback(completion, failure));
        }
    }

    private record ResetCallback(Runnable completion, Consumer<RuntimeException> failure) {
    }
}
