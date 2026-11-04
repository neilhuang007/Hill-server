package org.thehill.hill175.listener;

import org.bukkit.entity.Player;
import org.bukkit.event.player.PlayerKickEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import static org.mockito.Mockito.*;

class CameraSelfInteractionTest {
    private final CompetitionModule competition = mock(CompetitionModule.class);
    private final Player player = mock(Player.class);
    private final ServerListener listener = new ServerListener(mock(JavaPlugin.class),
            competition, mock(MenuModule.class), mock(WorldModule.class));

    private PlayerKickEvent event(PlayerKickEvent.Cause cause, boolean previewing) {
        PlayerKickEvent event = mock(PlayerKickEvent.class);
        when(event.getCause()).thenReturn(cause);
        when(event.getPlayer()).thenReturn(player);
        when(competition.isCameraPreviewing(player)).thenReturn(previewing);
        return event;
    }

    @Test void detachedCameraSelfInteractionExitsWithoutDisconnecting() {
        PlayerKickEvent event = event(PlayerKickEvent.Cause.SELF_INTERACTION, true);
        listener.onCameraSelfInteraction(event);
        verify(event).setCancelled(true);
        verify(competition).exitCameraPreview(player);
    }

    @Test void selfInteractionOutsideCameraStillUsesTheServerRule() {
        PlayerKickEvent event = event(PlayerKickEvent.Cause.SELF_INTERACTION, false);
        listener.onCameraSelfInteraction(event);
        verify(event, never()).setCancelled(true);
        verify(competition, never()).exitCameraPreview(any());
    }

    @Test void cameraDoesNotSuppressOtherKickReasons() {
        for (PlayerKickEvent.Cause cause : PlayerKickEvent.Cause.values()) {
            if (cause == PlayerKickEvent.Cause.SELF_INTERACTION) continue;
            PlayerKickEvent event = event(cause, true);
            listener.onCameraSelfInteraction(event);
            verify(event, never()).setCancelled(true);
        }
        verify(competition, never()).exitCameraPreview(any());
    }
}
