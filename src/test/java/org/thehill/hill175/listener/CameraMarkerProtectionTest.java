package org.thehill.hill175.listener;

import org.bukkit.entity.Item;
import org.bukkit.event.entity.EntityPickupItemEvent;
import org.bukkit.event.entity.ItemDespawnEvent;
import org.bukkit.event.entity.ItemMergeEvent;
import org.bukkit.event.inventory.InventoryPickupItemEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import java.util.Set;

import static org.mockito.Mockito.*;

class CameraMarkerProtectionTest {
    private final ServerListener listener = new ServerListener(mock(JavaPlugin.class),
            mock(CompetitionModule.class), mock(MenuModule.class), mock(WorldModule.class));

    private Item item(boolean marker) {
        Item item = mock(Item.class);
        when(item.getScoreboardTags()).thenReturn(marker ? Set.of("hill175_camera_marker") : Set.of());
        return item;
    }

    @Test void playersAndHoppersCannotCollectTheFloatingCamera() {
        Item camera = item(true);
        EntityPickupItemEvent playerPickup = mock(EntityPickupItemEvent.class);
        when(playerPickup.getItem()).thenReturn(camera);
        InventoryPickupItemEvent hopperPickup = mock(InventoryPickupItemEvent.class);
        when(hopperPickup.getItem()).thenReturn(camera);
        listener.onCameraItemPickup(playerPickup);
        listener.onCameraHopperPickup(hopperPickup);
        verify(playerPickup).setCancelled(true);
        verify(hopperPickup).setCancelled(true);
    }

    @Test void anOrdinaryItemCannotMergeIntoACameraOrRemoveItByDespawn() {
        Item camera = item(true);
        Item ordinary = item(false);
        ItemMergeEvent merge = mock(ItemMergeEvent.class);
        when(merge.getEntity()).thenReturn(ordinary);
        when(merge.getTarget()).thenReturn(camera);
        listener.onCameraItemMerge(merge);
        verify(merge).setCancelled(true);
        ItemDespawnEvent despawn = mock(ItemDespawnEvent.class);
        when(despawn.getEntity()).thenReturn(camera);
        listener.onCameraItemDespawn(despawn);
        verify(despawn).setCancelled(true);
    }

    @Test void ordinaryDroppedItemsKeepNormalPickupAndMerging() {
        Item ordinary = item(false);
        Item another = item(false);
        EntityPickupItemEvent pickup = mock(EntityPickupItemEvent.class);
        when(pickup.getItem()).thenReturn(ordinary);
        ItemMergeEvent merge = mock(ItemMergeEvent.class);
        when(merge.getEntity()).thenReturn(ordinary);
        when(merge.getTarget()).thenReturn(another);
        listener.onCameraItemPickup(pickup);
        listener.onCameraItemMerge(merge);
        verify(pickup, never()).setCancelled(true);
        verify(merge, never()).setCancelled(true);
    }
}
