package org.thehill.hill175.replay;

import org.bukkit.World;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class PacketReplayMovementTest {
    @Test void dropsHiddenCoordinatesAndPreservesVisibleMovement() throws Exception {
        byte[] both = payload(11, 37);
        assertArrayEquals(payload(37), PacketReplayMovement.filter(both, Set.of(37)));
        assertArrayEquals(payload(11), PacketReplayMovement.filter(both, Set.of(11)));
        assertNull(PacketReplayMovement.filter(both, Set.of()));
        assertThrows(IllegalArgumentException.class, () -> PacketReplayMovement.filter(new byte[]{1, -1}, Set.of(11)));
        assertThrows(IllegalArgumentException.class, () -> PacketReplayMovement.filter(java.util.Arrays.copyOf(both, both.length - 1), Set.of(11)));
    }

    @Test void onlyVisibleCurrentlyTrackedSameWorldEntitiesEnterBootstrap() {
        Player viewer = mock(Player.class);
        Entity entity = mock(Entity.class);
        World world = mock(World.class);
        when(viewer.getWorld()).thenReturn(world);
        when(entity.getWorld()).thenReturn(world);
        when(entity.getTrackedBy()).thenReturn(Set.of(viewer));
        when(viewer.canSee(entity)).thenReturn(true);
        assertTrue(PacketReplayBootstrap.mayCapture(viewer, entity));
        when(viewer.canSee(entity)).thenReturn(false);
        assertFalse(PacketReplayBootstrap.mayCapture(viewer, entity));
        when(viewer.canSee(entity)).thenReturn(true);
        when(entity.getTrackedBy()).thenReturn(Set.of());
        assertFalse(PacketReplayBootstrap.mayCapture(viewer, entity));
        when(entity.getTrackedBy()).thenReturn(Set.of(viewer));
        when(entity.getWorld()).thenReturn(mock(World.class));
        assertFalse(PacketReplayBootstrap.mayCapture(viewer, entity));
        assertFalse(PacketReplayBootstrap.mayCapture(viewer, viewer));
    }

    private static byte[] payload(int... ids) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream output = new DataOutputStream(bytes);
        output.writeByte(1);
        byte[] name = "minecraft:overworld".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        output.writeByte(name.length);
        output.write(name);
        output.writeByte(ids.length);
        for (int id : ids) {
            output.writeByte(id);
            output.writeDouble(id + 0.25);
            output.writeDouble(64);
            output.writeDouble(id + 0.5);
            output.writeFloat(90);
            output.writeFloat(0);
            output.writeFloat(90);
            output.writeBoolean(true);
        }
        return bytes.toByteArray();
    }
}
