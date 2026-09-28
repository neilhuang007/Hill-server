package org.thehill.hill175.world;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.when;

final class WorldModulePeopleCloneTest {
    @Test
    void deletingPrivateWorldEvictsItsCachedCampusMetadata(@TempDir Path runtime) throws IOException {
        Path folder = Files.createDirectories(runtime.resolve("hill_people_test"));
        Files.writeString(folder.resolve(CampusTemplateMetadata.FILE_NAME), """
                block-bounds: [-576, 18, -1600, 1407, 319, 415]
                spawn: [228, 91, 154]
                """);
        JavaPlugin plugin = mock(JavaPlugin.class);
        when(plugin.getDataFolder()).thenReturn(runtime.toFile());
        when(plugin.getConfig()).thenReturn(new YamlConfiguration());
        when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
        World world = mock(World.class);
        when(world.getName()).thenReturn("hill_people_test");
        when(world.getWorldFolder()).thenReturn(folder.toFile());
        when(world.getUID()).thenReturn(UUID.randomUUID());
        when(world.getMinHeight()).thenReturn(-64);
        when(world.getMaxHeight()).thenReturn(320);
        when(world.getPlayers()).thenReturn(List.of());
        WorldModule worlds = new WorldModule(plugin);
        assertTrue(worlds.campusChartRegion(world).isPresent());
        Entry entry = new Entry(UUID.randomUUID(), Category.PEOPLE, Set.of("builder"), "hill_people_test",
                new BuildRegion("hill_people_test", -576, 18, -1600, 1407, 319, 415), 0);
        try (var bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld("hill_people_test")).thenReturn(world);
            bukkit.when(Bukkit::getWorldContainer).thenReturn(runtime.toFile());
            bukkit.when(() -> Bukkit.unloadWorld(world, false)).thenReturn(true);
            assertTrue(worlds.deletePrivateWorld(entry));
        }
        assertFalse(worlds.campusChartRegion(world).isPresent(), "deleted world's metadata must not remain cached");
    }

    @Test
    void clonesTheTemplateIntoPapersActiveCustomDimensionFolder() {
        Path legacy = Path.of("server", "hill_people_example");
        Path migrated = Path.of("server", "world", "dimensions", "minecraft", "hill_people_example");

        assertEquals(migrated, WorldModule.peopleTemplateCloneDestination(legacy, migrated));
    }

    @Test
    void acceptsGeneratedAnvilTemplateWithoutPoiFilesWhenConfigured(@TempDir Path template) throws IOException {
        Files.writeString(template.resolve(".hill175-people-ready"), "generated\n");
        Path region = Files.createDirectories(template.resolve("region"));
        Files.writeString(template.resolve("voxelearth-hill-manifest.json"), "{}\n");
        for (int index = 0; index < 20; index++) {
            Files.write(region.resolve("r." + index + ".0.mca"), new byte[8_192]);
        }

        assertTrue(WorldModule.isGeneratedAnvilTemplateReady(template, 20, 0));
    }

    @Test
    void excludesIdentityMetadataWhenCloningPaperWorlds() {
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("uid.dat")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("session.lock")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("level.dat")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("level.dat_old")));
        assertTrue(WorldModule.shouldSkipWorldClonePath(Path.of("data", "paper", "metadata.dat")));
        assertFalse(WorldModule.shouldSkipWorldClonePath(Path.of("region", "r.0.0.mca")));
        assertFalse(WorldModule.shouldSkipWorldClonePath(Path.of("data", "paper", "unrelated.dat")));
    }

    @Test
    void validatesGeneratedAnvilTemplateShape(@TempDir Path template) throws IOException {
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        Files.writeString(template.resolve(".hill175-people-ready"), "generated\n");
        Path region = Files.createDirectories(template.resolve("region"));
        Path poi = Files.createDirectories(template.resolve("poi"));
        Files.writeString(template.resolve("voxelearth-hill-manifest.json"), "{}\n");
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        Files.write(region.resolve("r.0.-1.mca"), new byte[] {0});
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        for (int index = 0; index < 26; index++) {
            Files.write(region.resolve("r." + index + ".0.mca"), new byte[8_192]);
        }
        for (int index = 0; index < 11; index++) {
            Files.write(poi.resolve("r." + index + ".0.mca"), new byte[8_192]);
        }
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));
        Files.delete(region.resolve("r.0.-1.mca"));
        assertTrue(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));

        Files.createDirectories(template.resolve("dimensions"));
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));
        Files.delete(template.resolve("dimensions"));

        Files.writeString(template.resolve(".hill175-people-ready"), "wrong\n");
        assertFalse(WorldModule.isGeneratedAnvilTemplateReady(template, 26, 11));
    }

}
