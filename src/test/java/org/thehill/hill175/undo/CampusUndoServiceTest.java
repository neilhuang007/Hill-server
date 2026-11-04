package org.thehill.hill175.undo;

import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.Server;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.BlockState;
import org.bukkit.block.data.BlockData;
import org.bukkit.entity.Player;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.block.BlockFromToEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitScheduler;
import org.bukkit.scheduler.BukkitTask;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class CampusUndoServiceTest {
    private final JavaPlugin plugin = mock(JavaPlugin.class);
    private final Server server = mock(Server.class);
    private final World world = mock(World.class);
    private final Block block = mock(Block.class);
    private final Player player = mock(Player.class);
    private final AtomicLong clock = new AtomicLong(100_000);
    private final Location location = new Location(world, 1, 80, 2);
    private Runnable tick;
    private BlockData current;
    private boolean allowed = true;
    private boolean campus = true;
    private CampusUndoService service;

    @BeforeEach void setup() {
        BukkitScheduler scheduler = mock(BukkitScheduler.class);
        when(plugin.getServer()).thenReturn(server);
        when(server.isPrimaryThread()).thenReturn(true);
        when(server.getScheduler()).thenReturn(scheduler);
        doAnswer(call -> { tick = call.getArgument(1); return mock(BukkitTask.class); })
                .when(scheduler).runTaskTimer(eq(plugin), any(Runnable.class), eq(1L), eq(1L));
        UUID worldId = UUID.randomUUID();
        when(world.getUID()).thenReturn(worldId);
        when(server.getWorld(worldId)).thenReturn(world);
        when(world.isChunkLoaded(anyInt(), anyInt())).thenReturn(true);
        when(world.getBlockAt(any(Location.class))).thenReturn(block);
        when(block.getWorld()).thenReturn(world);
        when(block.getLocation()).thenReturn(location);
        when(block.getBlockData()).thenAnswer(ignored -> current);
        when(block.getState()).thenAnswer(ignored -> state(current));
        doAnswer(call -> { current = call.getArgument(0); return null; }).when(block).setBlockData(any(BlockData.class), eq(false));
        when(player.getUniqueId()).thenReturn(UUID.randomUUID());
        when(player.getGameMode()).thenReturn(GameMode.CREATIVE);
        when(player.isOnline()).thenReturn(true);
        when(player.getLocation()).thenReturn(location);
        when(player.getWorld()).thenReturn(world);
        service = new CampusUndoService(plugin, (actor, target) -> allowed, target -> campus, clock::get);
    }

    @Test void restoresARealPlacementOnlyAfterVanillaHasSettled() {
        service.onPlace(placement(false));
        service.undo(player);
        tick.run();
        assertEquals("minecraft:stone", current.getAsString());
        tick.run();
        assertEquals("minecraft:air", current.getAsString());
    }

    @Test void ignoresCancelledPlacements() {
        service.onPlace(placement(true));
        undoAndTick();
        assertEquals("minecraft:stone", current.getAsString());
        verify(block, never()).setBlockData(any(), anyBoolean());
    }

    @Test void doesNotRecordUnauthenticatedOrOutsideBoundsEdits() {
        allowed = false;
        service.onPlace(placement(false));
        allowed = true;
        undoAndTick();
        assertEquals("minecraft:stone", current.getAsString());
    }

    @Test void doesNotRecordOutsideTheSharedCampus() {
        campus = false;
        service.onPlace(placement(false));
        campus = true;
        undoAndTick();
        assertEquals("minecraft:stone", current.getAsString());
    }

    @Test void rechecksPermissionAtUndoTime() {
        service.onPlace(placement(false));
        tick.run(); tick.run();
        service.undo(player);
        allowed = false;
        tick.run();
        assertEquals("minecraft:stone", current.getAsString());
    }

    @Test void refusesSurvivalModeToAvoidDuplicatingDroppedItems() {
        when(player.getGameMode()).thenReturn(GameMode.SURVIVAL);
        service.onPlace(placement(false));
        when(player.getGameMode()).thenReturn(GameMode.CREATIVE);
        undoAndTick();
        assertEquals("minecraft:stone", current.getAsString());
    }

    @Test void cancelledEnvironmentEventsDoNotInvalidateAnEdit() {
        service.onPlace(placement(false));
        tick.run(); tick.run();
        BlockFromToEvent flow = mock(BlockFromToEvent.class);
        when(flow.isCancelled()).thenReturn(true);
        service.onFlow(flow);
        undoAndTick();
        assertEquals("minecraft:air", current.getAsString());
    }

    @Test void environmentChangeInvalidatesEvenWhenMaterialReturns() {
        service.onPlace(placement(false));
        tick.run(); tick.run();
        BlockFromToEvent flow = mock(BlockFromToEvent.class);
        when(flow.getBlock()).thenReturn(block);
        when(flow.getToBlock()).thenReturn(block);
        service.onFlow(flow);
        undoAndTick();
        assertEquals("minecraft:stone", current.getAsString());
    }

    @Test void neverLoadsAChunkToUndoAndRejectsAsyncCalls() {
        service.onPlace(placement(false));
        tick.run(); tick.run();
        when(world.isChunkLoaded(anyInt(), anyInt())).thenReturn(false);
        undoAndTick();
        assertEquals("minecraft:stone", current.getAsString());
        when(server.isPrimaryThread()).thenReturn(false);
        assertThrows(IllegalStateException.class, () -> service.undo(player));
    }

    private void undoAndTick() { service.undo(player); tick.run(); tick.run(); tick.run(); }

    private BlockPlaceEvent placement(boolean cancelled) {
        BlockState before = state(data(Material.AIR));
        current = data(Material.STONE);
        BlockPlaceEvent event = mock(BlockPlaceEvent.class);
        when(event.isCancelled()).thenReturn(cancelled);
        when(event.getPlayer()).thenReturn(player);
        when(event.getBlockReplacedState()).thenReturn(before);
        return event;
    }

    private BlockState state(BlockData data) {
        BlockState state = mock(BlockState.class);
        Material material = data.getMaterial();
        when(state.getBlockData()).thenReturn(data);
        when(state.getType()).thenReturn(material);
        when(state.getLocation()).thenReturn(location);
        when(state.getWorld()).thenReturn(world);
        when(state.getBlock()).thenReturn(block);
        return state;
    }

    private BlockData data(Material material) {
        BlockData data = mock(BlockData.class);
        Material snapshotMaterial = mock(Material.class);
        when(snapshotMaterial.hasGravity()).thenReturn(false);
        when(data.clone()).thenReturn(data);
        when(data.getMaterial()).thenReturn(snapshotMaterial);
        when(data.getAsString()).thenReturn("minecraft:" + material.name().toLowerCase());
        return data;
    }
}
