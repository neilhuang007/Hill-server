package org.thehill.hill175.listener;

import org.bukkit.entity.Player;
import org.bukkit.event.block.Action;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.inventory.ItemStack;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import static org.mockito.Mockito.*;

class CampusToolsTest {
    private final CompetitionModule competition = mock(CompetitionModule.class);
    private final ServerListener listener = new ServerListener(mock(JavaPlugin.class), competition,
            mock(MenuModule.class), mock(WorldModule.class));
    private final Player player = mock(Player.class);
    private final ItemStack clock = mock(ItemStack.class);

    private PlayerInteractEvent click(Action action) {
        PlayerInteractEvent event = mock(PlayerInteractEvent.class);
        when(event.getPlayer()).thenReturn(player);
        when(event.getHand()).thenReturn(EquipmentSlot.HAND);
        when(event.getItem()).thenReturn(clock);
        when(event.getAction()).thenReturn(action);
        when(competition.isCompetitionItem(clock, CompetitionModule.CAMPUS_UNDO_ITEM_ID)).thenReturn(true);
        return event;
    }

    @Test void authenticatedRightClickInvokesUndoWithoutUsingTheHeldItem() {
        when(competition.isAuthenticated(player)).thenReturn(true);
        PlayerInteractEvent event = click(Action.RIGHT_CLICK_AIR);
        listener.onInteract(event);
        verify(event).setCancelled(true);
        verify(competition).undoRecentBuild(player);
    }

    @Test void leftClickAndUnauthenticatedClicksCannotUndo() {
        when(competition.isAuthenticated(player)).thenReturn(true);
        PlayerInteractEvent left = click(Action.LEFT_CLICK_BLOCK);
        listener.onInteract(left);
        verify(left).setCancelled(true);
        when(competition.isAuthenticated(player)).thenReturn(false);
        PlayerInteractEvent locked = click(Action.RIGHT_CLICK_AIR);
        listener.onInteract(locked);
        verify(locked).setCancelled(true);
        verify(competition, never()).undoRecentBuild(any());
    }
}
