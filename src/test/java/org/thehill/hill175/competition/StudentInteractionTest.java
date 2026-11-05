package org.thehill.hill175.competition;

import org.bukkit.Bukkit;
import org.bukkit.Chunk;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Item;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitScheduler;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.mockito.MockedConstruction;
import org.mockito.MockedStatic;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.model.Account;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.world.WorldModule;

import java.lang.reflect.Field;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class StudentInteractionTest {
    @TempDir Path directory;

    @Test
    void recoveryPreviewBlocksEditingEvenForAnAuthenticatedBuilder() throws Exception {
        Fixture fixture = new Fixture("PreviewStaff");
        fixture.<Set<UUID>>state("authenticatedSessions").add(fixture.player.getUniqueId());
        when(fixture.worlds.isSurvivalWorld(any(Location.class))).thenReturn(true);
        Location location = new Location(fixture.world, 20, 72, 20);
        assertTrue(fixture.competition.mayBuild(fixture.player, location));
        fixture.competition.recoveryPreview(player -> true);
        assertFalse(fixture.competition.mayBuild(fixture.player, location));
    }

    @Test
    void sharedCampusAllowsEveryAuthenticatedStudentWithinItsBoundary() throws Exception {
        Fixture fixture = new Fixture("Builder");
        Entry campus = new Entry(UUID.randomUUID(), Category.PEOPLE, Set.of(), "hill_journey",
                new BuildRegion("hill_journey", 0, 0, 0, 63, 127, 63), 0);
        when(fixture.worlds.sharedCampusEntry()).thenReturn(Optional.of(campus));
        when(fixture.worlds.isSharedCampus(fixture.world)).thenReturn(true);
        Location inside = new Location(fixture.world, 20, 72, 20);
        assertFalse(fixture.competition.mayBuild(fixture.player, inside));
        fixture.<Set<UUID>>state("authenticatedSessions").add(fixture.player.getUniqueId());
        assertTrue(fixture.competition.mayBuild(fixture.player, inside));
        Player second = mock(Player.class);
        when(second.getUniqueId()).thenReturn(UUID.randomUUID());
        fixture.<Set<UUID>>state("authenticatedSessions").add(second.getUniqueId());
        assertTrue(fixture.competition.mayBuild(second, inside));
        assertFalse(fixture.competition.mayBuild(second, new Location(fixture.world, 64, 72, 20)));
        assertSame(campus, fixture.competition.entryAt(inside).orElseThrow());
        assertTrue(fixture.competition.entryAt(new Location(fixture.world, 64, 72, 20)).isEmpty());
        assertTrue(fixture.entries.isEmpty(), "The shared campus must not become a student submission.");
        verify(fixture.store, never()).saveEntry(any());
    }

    @ParameterizedTest
    @ValueSource(strings = {"JavaBuilder", ".BedrockBuilder1234"})
    void passwordOnlyRegistrationUsesTheActualConnectedIdentity(String playerName) {
        Fixture fixture = new Fixture(playerName);
        IdentityLinker.LinkTicket ticket = new IdentityLinker.LinkTicket("ticket", "https://example.invalid/link");
        when(fixture.linker.begin(playerName, fixture.player.getUniqueId())).thenReturn(ticket);
        when(fixture.linker.complete(ticket)).thenReturn(new IdentityLinker.LinkResult(true, "development", "Student", "Approved"));
        when(fixture.hasher.hash(any())).thenReturn(new PasswordHasher.PasswordRecord("salt", "hash", 10));
        BukkitScheduler scheduler = mock(BukkitScheduler.class);
        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(Bukkit::getScheduler).thenReturn(scheduler);
            fixture.competition.register(fixture.player, "testPassword", "testPassword");
            ArgumentCaptor<Runnable> callback = ArgumentCaptor.forClass(Runnable.class);
            verify(scheduler).runTaskLater(eq(fixture.plugin), callback.capture(), anyLong());
            callback.getValue().run();
        }
        ArgumentCaptor<Account> account = ArgumentCaptor.forClass(Account.class);
        verify(fixture.store).saveAccount(account.capture());
        assertEquals(playerName, account.getValue().nickname());
        assertEquals(playerName.toLowerCase(java.util.Locale.ROOT), account.getValue().nicknameKey());
        verify(fixture.linker).begin(playerName, fixture.player.getUniqueId());
    }

    @Test
    void legacyRegistrationCannotChooseAnotherPlayersIdentity() {
        Fixture fixture = new Fixture(".BedrockBuilder");
        fixture.competition.register(fixture.player, "BedrockBuilder", "testPassword", "testPassword");
        verifyNoInteractions(fixture.linker, fixture.hasher);
        verify(fixture.store, never()).saveAccount(any());
    }

    @Test
    void exteriorCameraSaveDoesNotGrantExteriorBuildingPermission() throws Exception {
        Fixture fixture = new Fixture("Builder");
        Entry entry = fixture.authenticateAt(new Location(fixture.world, 75, 72, 30));
        Location position = fixture.player.getLocation();
        when(fixture.worlds.safeCameraTeleport(eq(entry), any(), anyDouble()))
                .thenReturn(Optional.of(position));
        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(Bukkit::getScheduler).thenReturn(mock(BukkitScheduler.class));
            assertTrue(fixture.competition.recordCamera(fixture.player, 1));
        }
        assertFalse(fixture.competition.mayBuild(fixture.player, fixture.player.getLocation()));
        assertEquals(CameraPose.from(fixture.player.getEyeLocation()), entry.cameraPose(1).orElseThrow());
        verify(fixture.store).saveEntry(entry);
    }

    @Test
    void photoAreaRejectsDistantAndOtherWorldCameraSaves() throws Exception {
        Fixture fixture = new Fixture("Builder");
        Entry entry = fixture.authenticateAt(new Location(fixture.world, 88, 72, 30));
        assertFalse(fixture.competition.recordCamera(fixture.player, 1));
        World otherWorld = mock(World.class);
        when(otherWorld.getName()).thenReturn("another_world");
        when(fixture.player.getLocation()).thenReturn(new Location(otherWorld, 30, 72, 30));
        assertFalse(fixture.competition.recordCamera(fixture.player, 1));
        assertTrue(entry.cameraPoses().isEmpty());
        verify(fixture.worlds, never()).safeCameraTeleport(any(), any(), anyDouble());
        verify(fixture.store, never()).saveEntry(any());
    }

    @Test
    void crossingTheBuildBoundaryKeepsCameraControlsAndTheSelectedEntry() throws Exception {
        Fixture fixture = new Fixture("Builder");
        Entry entry = fixture.authenticateAt(new Location(fixture.world, 75, 72, 30));
        fixture.entries.add(new Entry(UUID.randomUUID(), Category.JOURNEY, Set.of("other"), "hill_journey",
                new BuildRegion("hill_journey", 70, 0, 0, 130, 127, 63), 1));
        fixture.competition.refreshMovementMode(fixture.player, fixture.player.getLocation());
        assertEquals(entry, fixture.competition.currentEntry(fixture.player).orElseThrow());
        assertFalse(fixture.competition.mayBuild(fixture.player, fixture.player.getLocation()));
        verify(fixture.player).setGameMode(GameMode.ADVENTURE);
        verify(fixture.player).setAllowFlight(true);
        verify(fixture.player).setFlying(true);
        verify(fixture.player, never()).getInventory();
    }

    @Test
    void mapTravelPreservesTheCurrentProjectAndItsInventory() throws Exception {
        Fixture fixture = new Fixture("Builder");
        Entry entry = fixture.authenticateAt(new Location(fixture.world, 10, 72, 30));
        entry.category(Category.PEOPLE);
        Location destination = new Location(fixture.world, 50, 72, 30);
        when(fixture.worlds.buildingDestination(entry, "chapel")).thenReturn(Optional.of(destination));
        when(fixture.player.teleport(destination)).thenReturn(true);
        assertTrue(fixture.competition.travelToBuilding(fixture.player, "chapel"));
        assertEquals(entry, fixture.competition.currentEntry(fixture.player).orElseThrow());
        verify(fixture.player).teleport(destination);
        verify(fixture.player, never()).getInventory();
    }

    @Test
    void mapTravelCannotEscapeTheProjectsPhotoBoundary() throws Exception {
        Fixture fixture = new Fixture("Builder");
        Entry entry = fixture.authenticateAt(new Location(fixture.world, 10, 72, 30));
        entry.category(Category.PEOPLE);
        Location destination = new Location(fixture.world, 200, 72, 30);
        when(fixture.worlds.buildingDestination(entry, "chapel")).thenReturn(Optional.of(destination));
        assertFalse(fixture.competition.travelToBuilding(fixture.player, "chapel"));
        verify(fixture.player, never()).teleport(any(Location.class));
    }

    @Test
    void rebuildingCameraMarkersCreatesAVisibleNonCollectibleEyeItem() {
        Fixture fixture = new Fixture("Builder");
        Entry entry = fixture.entry();
        entry.setCameraPose(1, new CameraPose("hill_journey", 30, 74, 30, 0, 0));
        when(fixture.world.getChunkAt(anyInt(), anyInt())).thenReturn(mock(Chunk.class));
        when(fixture.world.getChunkAt(any(Location.class))).thenReturn(mock(Chunk.class));
        Item marker = mock(Item.class);
        Set<String> tags = new HashSet<>();
        when(marker.getScoreboardTags()).thenReturn(tags);
        when(marker.addScoreboardTag(anyString())).thenAnswer(call -> tags.add(call.getArgument(0)));
        when(marker.getWorld()).thenReturn(fixture.world);
        when(fixture.world.dropItem(any(), any(), any())).thenAnswer(call -> {
            Consumer<Item> configure = call.getArgument(2);
            configure.accept(marker);
            return marker;
        });
        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class);
             MockedConstruction<ItemStack> items = mockConstruction(ItemStack.class, (item, context) ->
                     assertEquals(Material.ENDER_EYE, context.arguments().getFirst()))) {
            bukkit.when(() -> Bukkit.getWorld("hill_journey")).thenReturn(fixture.world);
            fixture.competition.rebuildAllCameraMarkers();
            verify(fixture.world).dropItem(eq(new Location(fixture.world, 30, 73.75, 30)),
                    eq(items.constructed().getFirst()), any());
            Chunk reloadedChunk = mock(Chunk.class);
            when(reloadedChunk.getWorld()).thenReturn(fixture.world);
            when(reloadedChunk.getX()).thenReturn(1);
            when(reloadedChunk.getZ()).thenReturn(1);
            ArmorStand oldLabel = mock(ArmorStand.class);
            when(oldLabel.getScoreboardTags()).thenReturn(tags);
            when(reloadedChunk.getEntities()).thenReturn(new Entity[]{oldLabel});
            fixture.competition.restoreCameraMarkers(reloadedChunk);
            verify(oldLabel).remove();
            assertEquals(2, items.constructed().size());
            when(reloadedChunk.getEntities()).thenReturn(new Entity[]{marker});
            fixture.competition.restoreCameraMarkers(reloadedChunk);
            assertEquals(2, items.constructed().size(), "An existing visible marker must not be duplicated");
        }
        assertTrue(CompetitionModule.isCameraMarker(marker));
        verify(marker, times(2)).setGravity(false);
        verify(marker, times(2)).setInvulnerable(true);
        verify(marker, times(2)).setPersistent(false);
        verify(marker, times(2)).setUnlimitedLifetime(true);
        verify(marker, times(2)).setCanPlayerPickup(false);
        verify(marker, times(2)).setCanMobPickup(false);
        verify(marker, times(2)).setPickupDelay(Integer.MAX_VALUE);
    }

    private final class Fixture {
        private final JavaPlugin plugin = mock(JavaPlugin.class);
        private final CompetitionStore store = mock(CompetitionStore.class);
        private final WorldModule worlds = mock(WorldModule.class);
        private final PasswordHasher hasher = mock(PasswordHasher.class);
        private final IdentityLinker linker = mock(IdentityLinker.class);
        private final Player player = mock(Player.class);
        private final World world = mock(World.class);
        private final List<Entry> entries = new ArrayList<>();
        private final CompetitionModule competition;

        private Fixture(String playerName) {
            when(plugin.getName()).thenReturn("Hill175");
            when(plugin.namespace()).thenReturn("hill175");
            when(plugin.getDataFolder()).thenReturn(directory.toFile());
            when(plugin.getConfig()).thenReturn(new YamlConfiguration());
            when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
            when(player.getUniqueId()).thenReturn(UUID.randomUUID());
            when(player.getName()).thenReturn(playerName);
            when(player.getWorld()).thenReturn(world);
            when(world.getName()).thenReturn("hill_journey");
            when(store.entries()).thenReturn(entries);
            when(store.entry(any())).thenAnswer(call -> entries.stream()
                    .filter(entry -> entry.id().equals(call.getArgument(0))).findFirst());
            competition = new CompetitionModule(plugin, store, worlds, hasher, linker);
        }

        private Entry entry() {
            Entry entry = new Entry(UUID.randomUUID(), Category.JOURNEY, Set.of("builder"), "hill_journey",
                    new BuildRegion("hill_journey", 0, 0, 0, 63, 127, 63), 0);
            entries.add(entry);
            when(worlds.cameraRegion(entry)).thenReturn(new BuildRegion("hill_journey", -24, -64, -24, 87, 319, 87));
            return entry;
        }

        private Entry authenticateAt(Location location) throws Exception {
            Entry entry = entry();
            when(player.getLocation()).thenReturn(location);
            when(player.getEyeLocation()).thenReturn(location.clone().add(0, 1.62, 0));
            when(player.getEyeHeight()).thenReturn(1.62);
            this.<Set<UUID>>state("authenticatedSessions").add(player.getUniqueId());
            this.<Map<UUID, UUID>>state("currentEntryByPlayer").put(player.getUniqueId(), entry.id());
            this.<Map<UUID, String>>state("activeKitByPlayer").put(player.getUniqueId(), "owner:" + entry.id());
            return entry;
        }

        @SuppressWarnings("unchecked")
        private <T> T state(String name) throws Exception {
            Field field = CompetitionModule.class.getDeclaredField(name);
            field.setAccessible(true);
            return (T) field.get(competition);
        }
    }
}
