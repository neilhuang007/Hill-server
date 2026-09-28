package org.thehill.hill175.listener;

import com.destroystokyo.paper.event.server.PaperServerListPingEvent;
import net.kyori.adventure.audience.Audience;
import io.papermc.paper.event.player.AsyncChatEvent;
import org.bukkit.entity.Player;
import org.bukkit.event.entity.PlayerDeathEvent;
import org.bukkit.event.player.PlayerAdvancementDoneEvent;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SchoolPrivacyTest {
    @Test
    void suppressesGlobalDeathAndAdvancementMessagesForSchoolAccounts() {
        ServerListener listener = listener(true);
        PlayerDeathEvent death = mock(PlayerDeathEvent.class);
        PlayerAdvancementDoneEvent advancement = mock(PlayerAdvancementDoneEvent.class);
        listener.onDeathAnnouncement(death);
        listener.onAdvancementAnnouncement(advancement);
        verify(death).deathMessage(null);
        verify(death).setShowDeathMessages(false);
        verify(advancement).message(null);
    }

    @Test
    void preservesExistingDevelopmentAnnouncements() {
        ServerListener listener = listener(false);
        PlayerDeathEvent death = mock(PlayerDeathEvent.class);
        PlayerAdvancementDoneEvent advancement = mock(PlayerAdvancementDoneEvent.class);
        listener.onDeathAnnouncement(death);
        listener.onAdvancementAnnouncement(advancement);
        verify(death, never()).deathMessage(null);
        verify(advancement, never()).message(null);
    }

    @Test
    void hidesPlayerSamplesOnThePublicServerList() {
        PaperServerListPingEvent event = mock(PaperServerListPingEvent.class);
        listener(true).onServerListPing(event);
        verify(event).setHidePlayers(true);
    }

    @Test
    void schoolChatOnlyReachesVerifiedPlayerViewersAndTheAdministrativeConsole() {
        CompetitionModule competition = mock(CompetitionModule.class);
        when(competition.usesMicrosoftAuthentication()).thenReturn(true);
        Player sender = mock(Player.class);
        Player student = mock(Player.class);
        Player unverified = mock(Player.class);
        Audience console = mock(Audience.class);
        when(competition.isAuthenticated(sender)).thenReturn(true);
        when(competition.isAuthenticated(student)).thenReturn(true);
        Set<Audience> viewers = new HashSet<>(Set.of(sender, student, unverified, console));
        AsyncChatEvent event = mock(AsyncChatEvent.class);
        when(event.getPlayer()).thenReturn(sender);
        when(event.viewers()).thenReturn(viewers);
        new ServerListener(mock(JavaPlugin.class), competition, mock(MenuModule.class), mock(WorldModule.class)).onChat(event);
        assertEquals(Set.of(sender, student, console), viewers);
    }

    @Test
    void survivalCommandsCannotBypassSchoolChatVisibility() {
        for (boolean microsoft : new boolean[]{true, false}) {
            CompetitionModule competition = mock(CompetitionModule.class);
            WorldModule worlds = mock(WorldModule.class);
            Player player = mock(Player.class);
            when(player.getUniqueId()).thenReturn(UUID.randomUUID());
            when(competition.usesMicrosoftAuthentication()).thenReturn(microsoft);
            when(competition.isAuthenticated(player)).thenReturn(true);
            when(worlds.isSurvivalWorld(player.getWorld())).thenReturn(true);
            ServerListener listener = new ServerListener(mock(JavaPlugin.class), competition, mock(MenuModule.class), worlds);
            for (String command : new String[]{"/me waves", "/msg Visitor hello", "/minecraft:tell Visitor hello"}) {
                PlayerCommandPreprocessEvent event = mock(PlayerCommandPreprocessEvent.class);
                when(event.getPlayer()).thenReturn(player);
                when(event.getMessage()).thenReturn(command);
                listener.onCommand(event);
                if (microsoft) {
                    verify(event).setCancelled(true);
                } else {
                    verify(event, never()).setCancelled(true);
                }
            }
        }
    }

    private static ServerListener listener(boolean microsoft) {
        CompetitionModule competition = mock(CompetitionModule.class);
        when(competition.usesMicrosoftAuthentication()).thenReturn(microsoft);
        return new ServerListener(mock(JavaPlugin.class), competition, mock(MenuModule.class), mock(WorldModule.class));
    }
}
