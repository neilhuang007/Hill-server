package org.thehill.hill175.ui;

import org.bukkit.Server;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.PluginManager;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitScheduler;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.IntConsumer;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class BedrockFormsTest {
    @Test
    void missingFloodgateKeepsJavaMenusAvailableRegardlessOfPlayerName() {
        Fixture fixture = new Fixture();
        when(fixture.player.getName()).thenReturn(".BedrockLookingName");
        BedrockForms forms = new BedrockForms(fixture.plugin);
        assertFalse(forms.isBedrock(fixture.player));
        assertFalse(forms.show(fixture.player, "Menu", "", List.of("Build"), ignored -> fail(), () -> fail()));
    }

    @Test
    void installedButDisabledOrIncompatibleApiDoesNotSilentlyBecomeJava() {
        Fixture fixture = new Fixture();
        Plugin floodgate = mock(Plugin.class);
        when(fixture.server.getPluginManager().getPlugin("floodgate")).thenReturn(floodgate);
        assertThrows(IllegalStateException.class, () -> new BedrockForms(fixture.plugin));
        when(floodgate.isEnabled()).thenReturn(true);
        assertThrows(IllegalStateException.class, () -> new BedrockForms(fixture.plugin));
    }

    @Test
    void callbacksWaitForTheMainThreadAndCanRunOnlyOnce() {
        Fixture fixture = new Fixture();
        AtomicInteger selected = new AtomicInteger(-1);
        fixture.open(selected::set);
        fixture.transport.response.accept(1);
        fixture.transport.response.accept(0);
        assertEquals(-1, selected.get());
        fixture.flush();
        assertEquals(1, selected.get());
    }

    @Test
    void replacingAnIdenticalFormInvalidatesItsPreviousToken() {
        Fixture fixture = new Fixture();
        AtomicInteger selected = new AtomicInteger(-1);
        fixture.open(ignored -> fail("Stale form acted"));
        IntConsumer previous = fixture.transport.response;
        fixture.open(selected::set);
        previous.accept(0);
        fixture.transport.response.accept(1);
        fixture.flush();
        assertEquals(1, selected.get());
        assertEquals(1, fixture.transport.closed);
    }

    @Test
    void responseFromAnEarlierConnectionCannotAffectAReconnectedPlayer() {
        Fixture fixture = new Fixture();
        fixture.open(ignored -> fail("Previous connection acted"));
        Player replacement = mock(Player.class);
        when(fixture.server.getPlayer(fixture.playerId)).thenReturn(replacement);
        fixture.transport.response.accept(0);
        fixture.flush();
    }

    @Test
    void clearingAndShutdownInvalidateQueuedResponsesWithoutCallingCloseHandlers() {
        Fixture fixture = new Fixture();
        fixture.open(ignored -> fail("Cleared form acted"));
        fixture.transport.response.accept(0);
        fixture.forms.clear(fixture.player);
        fixture.flush();
        fixture.open(ignored -> fail("Stopped form acted"));
        fixture.transport.response.accept(0);
        fixture.forms.close();
        fixture.flush();
        assertEquals(2, fixture.transport.closed);
        assertFalse(fixture.open(ignored -> fail()));
    }

    @Test
    void invalidButtonIndexReturnsToTheCloseAction() {
        Fixture fixture = new Fixture();
        AtomicInteger closes = new AtomicInteger();
        fixture.forms.show(fixture.player, "Menu", "", List.of("Build"), ignored -> fail(), closes::incrementAndGet);
        fixture.transport.response.accept(99);
        fixture.flush();
        assertEquals(1, closes.get());
    }

    @Test
    void fieldsPreserveInputOrderAndRejectOverlengthResponsesWithoutTruncating() {
        Fixture fixture = new Fixture();
        List<BedrockForms.Field> fields = List.of(new BedrockForms.Field("title", "Title", "Current", 12),
                new BedrockForms.Field("note", "Note", "", 20));
        List<List<String>> results = new ArrayList<>();
        AtomicInteger closes = new AtomicInteger();
        fixture.forms.showFields(fixture.player, "Edit details", "", fields, results::add, closes::incrementAndGet);
        fixture.transport.fieldResponse.accept(List.of("New title", "My note"));
        fixture.flush();
        assertEquals(List.of(List.of("New title", "My note")), results);
        fixture.forms.showFields(fixture.player, "Edit details", "", fields, results::add, closes::incrementAndGet);
        fixture.transport.fieldResponse.accept(List.of("A title exceeding the limit", "My note"));
        fixture.flush();
        assertEquals(1, results.size());
        assertEquals(1, closes.get());
        verify(fixture.player).sendMessage("Keep Title to 12 characters, then try again.");
    }

    @Test
    void offlinePlayerAndFailedSendsCannotLeaveAnActionableForm() {
        Fixture fixture = new Fixture();
        when(fixture.player.isOnline()).thenReturn(false);
        assertFalse(fixture.open(ignored -> fail()));
        when(fixture.player.isOnline()).thenReturn(true);
        fixture.transport.shouldSend = false;
        assertFalse(fixture.open(ignored -> fail()));
        fixture.transport.response.accept(0);
        fixture.flush();
    }

    private static final class Fixture {
        private final JavaPlugin plugin = mock(JavaPlugin.class);
        private final Server server = mock(Server.class);
        private final Player player = mock(Player.class);
        private final UUID playerId = UUID.randomUUID();
        private final FakeTransport transport = new FakeTransport();
        private final List<Runnable> tasks = new ArrayList<>();
        private final BedrockForms forms;

        private Fixture() {
            when(plugin.getServer()).thenReturn(server);
            when(plugin.isEnabled()).thenReturn(true);
            when(plugin.getLogger()).thenReturn(Logger.getLogger("BedrockFormsTest"));
            when(server.getPluginManager()).thenReturn(mock(PluginManager.class));
            BukkitScheduler scheduler = mock(BukkitScheduler.class);
            when(server.getScheduler()).thenReturn(scheduler);
            when(player.getUniqueId()).thenReturn(playerId);
            when(player.isOnline()).thenReturn(true);
            when(server.getPlayer(playerId)).thenReturn(player);
            doAnswer(invocation -> { tasks.add(invocation.getArgument(1, Runnable.class)); return null; })
                    .when(scheduler).runTask(eq(plugin), any(Runnable.class));
            forms = new BedrockForms(plugin, transport);
        }

        private boolean open(IntConsumer response) {
            return forms.show(player, "Menu", "Choose", List.of("Build", "Visit"), response, () -> fail("Unexpected close"));
        }

        private void flush() {
            List<Runnable> pending = List.copyOf(tasks);
            tasks.clear();
            pending.forEach(Runnable::run);
        }
    }

    private static final class FakeTransport implements BedrockForms.FormTransport {
        private IntConsumer response;
        private Consumer<List<String>> fieldResponse;
        private int closed;
        private boolean shouldSend = true;

        public boolean isBedrock(UUID playerId) { return true; }

        public boolean show(UUID playerId, String title, String content, List<String> buttons,
                            IntConsumer response, Runnable close) {
            this.response = response;
            return shouldSend;
        }

        public boolean showFields(UUID playerId, String title, String content, List<BedrockForms.Field> fields,
                                  Consumer<List<String>> response, Runnable close) {
            fieldResponse = response;
            return shouldSend;
        }

        public void close(UUID playerId) { closed++; }
    }
}
