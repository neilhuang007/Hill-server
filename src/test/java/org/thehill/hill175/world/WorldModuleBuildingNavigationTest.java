package org.thehill.hill175.world;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.WorldBorder;
import org.bukkit.block.Block;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.*;

final class WorldModuleBuildingNavigationTest {
    @TempDir Path runtime;

    @Test
    void savedSharedCampusWithMissingMetadataStopsInsteadOfReplacingStudentWork() throws IOException {
        Fixture fixture = new Fixture(Category.PEOPLE, "hill_campus");
        Path folder = runtime.resolve("hill_campus");
        Files.delete(folder.resolve(CampusTemplateMetadata.FILE_NAME));
        Files.writeString(folder.resolve("student-build"), "preserve this build");
        World primary = mock(World.class);
        when(primary.getName()).thenReturn("world");
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(Bukkit::getWorldContainer).thenReturn(runtime.toFile());
            bukkit.when(Bukkit::getWorlds).thenReturn(java.util.List.of(primary));
            assertThrows(IllegalStateException.class, fixture.worlds::loadSharedCampus);
            assertEquals("preserve this build", Files.readString(folder.resolve("student-build")));
        }
    }

    @Test
    void privatePlaceArrivesAtSelectedBuildingInsteadOfInheritedCampusSpawn() throws IOException {
        Fixture fixture = new Fixture(Category.PLACE, "hill_place_012345abcdef");
        Entry entry = fixture.entry;
        entry.selectedBuildingId("library");
        when(fixture.world.getSpawnLocation()).thenReturn(new Location(fixture.world, -400, 90, -900));

        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld(entry.worldName())).thenReturn(fixture.world);
            Location spawn = fixture.worlds.entrySpawn(entry);
            Location safe = fixture.worlds.safeEntrySpawn(entry).orElseThrow();

            assertEquals(120.5, spawn.getX());
            assertEquals(243.5, spawn.getZ());
            assertEquals(81.05, safe.getY(), 0.001);
            assertTrue(entry.region().contains(spawn));
            assertEquals(-180.0f, spawn.getYaw(), 0.001);
            verify(fixture.world, never()).getSpawnLocation();
        }
    }

    @Test
    void unknownLegacyBuildingStaysInsideItsOwnedRegion() throws IOException {
        Fixture fixture = new Fixture(Category.PLACE, "hill_place_012345abcdef");
        fixture.entry.selectedBuildingId("removed-from-catalog");
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld(fixture.entry.worldName())).thenReturn(fixture.world);
            Location safe = fixture.worlds.safeEntrySpawn(fixture.entry).orElseThrow();
            assertEquals(fixture.entry.region().centerX() + 0.5, safe.getX());
            assertEquals(fixture.entry.region().centerZ() + 0.5, safe.getZ());
            assertTrue(fixture.entry.region().contains(safe));
        }
    }

    @Test
    void exteriorCameraUsesPhotoMarginWithoutChangingEditableBounds() throws IOException {
        Fixture fixture = new Fixture(Category.PLACE, "hill_place_012345abcdef");
        BuildRegion original = fixture.entry.region();
        CameraPose exterior = new CameraPose(original.worldName(), 50.5, 100, 220.5, -90, 0);
        CameraPose outsideCampus = new CameraPose(original.worldName(), 5.5, 100, 220.5, -90, 0);
        CameraPose outsideMargin = new CameraPose(original.worldName(), 260.5, 100, 220.5, 90, 0);
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld(original.worldName())).thenReturn(fixture.world);
            BuildRegion viewing = fixture.worlds.cameraRegion(fixture.entry);
            assertEquals(new BuildRegion(original.worldName(), 10, -64, 88, 252, 319, 352), viewing);
            assertFalse(original.contains(50, 100, 220));
            assertTrue(fixture.worlds.safeCameraTeleport(fixture.entry, exterior, 1.62).isPresent());
            assertTrue(fixture.worlds.safeCameraTeleport(fixture.entry, outsideCampus, 1.62).isEmpty());
            assertTrue(fixture.worlds.safeCameraTeleport(fixture.entry, outsideMargin, 1.62).isEmpty());
            assertEquals(original, fixture.entry.region());
        }
    }

    @Test
    void sharedPlotsHaveAModestCameraMarginAndLegalWorldHeight() throws IOException {
        Fixture fixture = new Fixture(Category.JOURNEY, "hill_journey");
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld(fixture.entry.worldName())).thenReturn(fixture.world);
            BuildRegion viewing = fixture.worlds.cameraRegion(fixture.entry);
            assertEquals(60, viewing.minX());
            assertEquals(180, viewing.maxX());
            assertEquals(-64, viewing.minY());
            assertEquals(319, viewing.maxY());
        }
    }

    @Test
    void mapDestinationsRequireAnAvailableBuildingInsideViewingBounds() throws IOException {
        Fixture fixture = new Fixture(Category.PLACE, "hill_place_012345abcdef");
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld(fixture.entry.worldName())).thenReturn(fixture.world);
            Location destination = fixture.worlds.buildingDestination(fixture.entry, "library").orElseThrow();
            assertTrue(fixture.worlds.cameraRegion(fixture.entry).contains(destination));
            assertTrue(fixture.worlds.buildingDestination(fixture.entry, "far-building").isEmpty());
            assertTrue(fixture.worlds.buildingDestination(fixture.entry, "unknown").isEmpty());
        }
    }

    private final class Fixture {
        private final World world = mock(World.class);
        private final WorldBorder border = mock(WorldBorder.class);
        private final WorldModule worlds;
        private final Entry entry;

        private Fixture(Category category, String worldName) throws IOException {
            Path folder = Files.createDirectories(runtime.resolve(worldName));
            Files.writeString(folder.resolve(CampusTemplateMetadata.FILE_NAME), """
                    block-bounds: [10, 18, -1000, 700, 319, 800]
                    spawn: [20, 90, -900]
                    """);
            Files.writeString(folder.resolve(BuildingCatalog.fileName), """
                    buildings:
                      library:
                        name: Library
                        map-number: 1
                        bounds-xz: [100, 200, 140, 240]
                      far-building:
                        name: Distant Hall
                        map-number: 2
                        bounds-xz: [500, 600, 540, 640]
                    """);
            JavaPlugin plugin = mock(JavaPlugin.class);
            when(plugin.getDataFolder()).thenReturn(runtime.toFile());
            when(plugin.getConfig()).thenReturn(new YamlConfiguration());
            when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
            worlds = spy(new WorldModule(plugin));
            entry = new Entry(UUID.randomUUID(), category, Set.of("builder"), worldName,
                    new BuildRegion(worldName, 84, -64, 184, 156, 319, 256), 0);
            doNothing().when(worlds).ensureEntryWorld(entry);
            when(world.getName()).thenReturn(worldName);
            when(world.getUID()).thenReturn(UUID.randomUUID());
            when(world.getWorldFolder()).thenReturn(folder.toFile());
            when(world.getMinHeight()).thenReturn(-64);
            when(world.getMaxHeight()).thenReturn(320);
            when(world.getWorldBorder()).thenReturn(border);
            when(border.isInside(any(Location.class))).thenReturn(true);
            when(world.getHighestBlockYAt(anyInt(), anyInt())).thenReturn(80);
            Block solid = mock(Block.class);
            Material solidMaterial = mock(Material.class);
            when(solidMaterial.isSolid()).thenReturn(true);
            when(solid.getType()).thenReturn(solidMaterial);
            Block air = mock(Block.class);
            when(air.getType()).thenReturn(Material.AIR);
            when(air.isPassable()).thenReturn(true);
            when(world.getBlockAt(anyInt(), anyInt(), anyInt())).thenAnswer(call ->
                    (int) call.getArgument(1) == 80 ? solid : air);
        }
    }
}
