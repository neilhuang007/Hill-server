package org.thehill.hill175.competition;

import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.PlayerInventory;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.MockedStatic;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.data.SurvivalInventoryStore;
import org.thehill.hill175.data.SurvivalLocationSnapshot;
import org.thehill.hill175.data.SurvivalPlayerState;
import org.thehill.hill175.world.WorldModule;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SurvivalTransitionTest {
    @TempDir Path directory;
    private final UUID playerId = UUID.randomUUID();
    private final Player player = mock(Player.class);
    private final PlayerInventory inventory = mock(PlayerInventory.class);
    private final World survival = mock(World.class);
    private final World hub = mock(World.class);
    private final WorldModule worlds = mock(WorldModule.class);
    private SurvivalInventoryStore snapshots;
    private CompetitionModule competition;
    private Location spawn;

    @BeforeEach
    void setUp() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        when(plugin.getName()).thenReturn("Hill175");
        when(plugin.namespace()).thenReturn("hill175");
        when(plugin.getDataFolder()).thenReturn(directory.toFile());
        when(plugin.getConfig()).thenReturn(new YamlConfiguration());
        when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
        competition = spy(new CompetitionModule(plugin, mock(CompetitionStore.class), worlds,
                mock(PasswordHasher.class), mock(IdentityLinker.class)));
        doReturn(true).when(competition).isAuthenticated(player);
        snapshots = new SurvivalInventoryStore(directory.toFile(), Logger.getAnonymousLogger());

        when(survival.getName()).thenReturn("hill_survival");
        when(hub.getName()).thenReturn("hill_hub");
        when(worlds.isSurvivalWorld(survival)).thenReturn(true);
        spawn = new Location(survival, 0, 70, 0);
        when(worlds.survivalSpawn()).thenReturn(spawn);
        when(player.getUniqueId()).thenReturn(playerId);
        when(player.getWorld()).thenReturn(hub);
        when(player.getInventory()).thenReturn(inventory);
        Inventory enderChest = mock(Inventory.class);
        when(enderChest.getSize()).thenReturn(27);
        when(player.getEnderChest()).thenReturn(enderChest);
        when(player.teleport(any(Location.class))).thenReturn(true);
    }

    @Test
    void restoresTheSameSnapshotUsedToChooseTheDestination() {
        snapshots.save(playerId, state(7, "hill_survival"));
        doAnswer(invocation -> {
            // A teleport listener can change persisted state while the transition is in progress.
            snapshots.save(playerId, state(99, "hill_survival"));
            return true;
        }).when(player).teleport(any(Location.class));

        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld("hill_survival")).thenReturn(survival);
            competition.teleportSurvival(player);
        }

        verify(player).teleport(new Location(survival, 15, 75, 25, 30, 10));
        verify(player).setLevel(7);
        verify(player).setGameMode(GameMode.SURVIVAL);
        assertTrue(snapshots.isActive(playerId));
    }

    @Test
    void interruptedTeleportPreservesInventoryAndPersistentIntent() {
        snapshots.save(playerId, state(7, "hill_survival"));
        snapshots.markDeathPending(playerId);
        when(player.teleport(any(Location.class))).thenReturn(false);

        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld("hill_survival")).thenReturn(survival);
            competition.teleportSurvival(player);
        }

        verify(inventory, never()).clear();
        verify(player, never()).setLevel(anyInt());
        verify(player, never()).setGameMode(any());
        assertTrue(snapshots.isDeathPending(playerId));
        assertFalse(snapshots.isActive(playerId));
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void missingOrCorruptSnapshotUsesSpawnAndFirstEntryDefaults(boolean corrupt) throws Exception {
        if (corrupt) {
            Path file = directory.resolve("survival-inventories").resolve(playerId + ".yml");
            Files.createDirectories(file.getParent());
            Files.writeString(file, "inventory: [unterminated");
        }

        competition.teleportSurvival(player);

        verify(player).teleport(spawn);
        verify(player).setLevel(0);
        verify(player).setFoodLevel(20);
        assertTrue(snapshots.isActive(playerId));
    }

    @Test
    void storedLocationOutsideSurvivalFallsBackToSurvivalSpawn() {
        snapshots.save(playerId, state(7, "hill_hub"));
        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getWorld("hill_hub")).thenReturn(hub);
            competition.teleportSurvival(player);
        }

        verify(player).teleport(spawn);
        verify(player).setLevel(7);
    }

    private static SurvivalPlayerState state(int level, String world) {
        return new SurvivalPlayerState(List.of(), List.of(), null, List.of(), List.of(),
                level, 0, 0, 20, 5, 0, 20, 300, 0,
                new SurvivalLocationSnapshot(world, 15, 75, 25, 30, 10), null);
    }
}
