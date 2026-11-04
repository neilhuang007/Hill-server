package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.thehill.hill175.world.BuildingCatalog.Building;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Function;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class BuildingLocationServiceTest {
    private final Building chapel = new Building("chapel", "Chapel", 1, 0, 0, 9, 9);
    private final Building library = new Building("library", "Ryan Library", 2, 30, 0, 39, 9);
    private final List<Building> buildings = List.of(chapel, library);
    private final World campus = mock(World.class);
    private final World other = mock(World.class);
    private final Player player = mock(Player.class);
    private final JavaPlugin plugin = mock(JavaPlugin.class);
    private final AtomicBoolean eligible = new AtomicBoolean(true);
    private int catalogReads;
    private final Function<World, List<Building>> catalog = world -> { catalogReads++; return world == campus ? buildings : List.of(); };
    private final BuildingLocationService service = new BuildingLocationService(plugin, catalog,
            world -> world == campus, ignored -> eligible.get());

    @BeforeEach void setup() {
        when(campus.getUID()).thenReturn(UUID.randomUUID());
        when(other.getUID()).thenReturn(UUID.randomUUID());
        when(player.getUniqueId()).thenReturn(UUID.randomUUID());
        when(player.getWorld()).thenReturn(campus);
        when(player.isOnline()).thenReturn(true);
        at(5, 5);
    }

    @Test void detectsNearestFootprintInsteadOfDistanceToCenter() {
        Building wide = new Building("wide", "Wide Building", 3, 0, 0, 200, 20);
        assertEquals(0.0, BuildingLocationService.distance(wide, new Location(campus, 199, 80, 10)));
        assertEquals(wide, BuildingLocationService.nearest(List.of(wide), new Location(campus, 215, 80, 10), null));
        assertNull(BuildingLocationService.nearest(List.of(wide), new Location(campus, 220, 80, 10), null));
    }

    @Test void hysteresisAvoidsOscillationBetweenNearbyBuildings() {
        assertEquals(chapel, BuildingLocationService.nearest(buildings, new Location(campus, 21, 80, 5), chapel));
        assertEquals(library, BuildingLocationService.nearest(buildings, new Location(campus, 24, 80, 5), chapel));
        assertEquals(chapel, BuildingLocationService.nearest(List.of(chapel), new Location(campus, -22, 80, 5), chapel));
        assertNull(BuildingLocationService.nearest(List.of(chapel), new Location(campus, -25, 80, 5), chapel));
    }

    @Test void sendsCaptionOnlyWhenBuildingChangesAndCachesCatalog() {
        service.refresh(player);
        service.refresh(player);
        at(35, 5);
        service.refresh(player);
        ArgumentCaptor<Component> captions = ArgumentCaptor.forClass(Component.class);
        verify(player, times(2)).sendActionBar(captions.capture());
        assertEquals(Component.text("Chapel", net.kyori.adventure.text.format.NamedTextColor.GOLD), captions.getAllValues().getFirst());
        assertEquals(Component.text("Ryan Library", net.kyori.adventure.text.format.NamedTextColor.GOLD), captions.getAllValues().getLast());
        assertEquals(1, catalogReads);
    }

    @Test void leavingCampusClearsCaption() {
        service.refresh(player);
        when(player.getWorld()).thenReturn(other);
        service.refresh(player);
        service.refresh(player);
        verify(player, times(2)).sendActionBar(any(Component.class));
        verify(player).sendActionBar(Component.empty());
        assertEquals(1, catalogReads);
    }

    @Test void losingAuthenticationOrOpeningCameraDoesNotEraseTheNewHint() {
        service.refresh(player);
        eligible.set(false);
        service.refresh(player);
        service.refresh(player);
        verify(player, times(1)).sendActionBar(any(Component.class));
        verify(player, never()).sendActionBar(Component.empty());
    }

    @Test void vanillaCaptionIsTransientAndDoesNotOverwriteOtherHintsEveryTick() {
        service.refresh(player);
        service.refresh(player);
        eligible.set(false);
        service.refresh(player);
        verify(player, times(1)).sendActionBar(any(Component.class));
    }

    @Test void worldChangesAndReconnectsCannotRetainAStaleBuilding() {
        service.refresh(player);
        service.onWorldChange(new PlayerChangedWorldEvent(player, campus));
        service.refresh(player);
        PlayerQuitEvent quit = mock(PlayerQuitEvent.class);
        when(quit.getPlayer()).thenReturn(player);
        service.onQuit(quit);
        service.onJoin(new PlayerJoinEvent(player, Component.empty()));
        service.refresh(player);
        verify(player, times(4)).sendActionBar(any(Component.class));
    }

    @Test void leavingTheBuildingClearsAndReturningShowsTheCaptionAgain() {
        service.refresh(player);
        at(-25, 5);
        service.refresh(player);
        at(5, 5);
        service.refresh(player);
        verify(player, times(3)).sendActionBar(any(Component.class));
        verify(player).sendActionBar(Component.empty());
    }

    private void at(double x, double z) { when(player.getLocation()).thenReturn(new Location(campus, x, 80, z)); }

}
