package org.thehill.hill175.auth;

import net.kyori.adventure.text.Component;
import org.bukkit.Server;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitScheduler;
import org.bukkit.scheduler.BukkitTask;
import org.bukkit.scoreboard.Scoreboard;
import org.bukkit.scoreboard.ScoreboardManager;
import org.bukkit.scoreboard.Team;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.auth.sso.MicrosoftSsoService;
import org.thehill.hill175.auth.sso.VerifiedSession;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SsoPlayerSessionsTest {
    private static final String PARTICIPANT = "entra:tenant:student";

    @Test
    void waitsForDurableConfirmationBeforePublishingTheVerifiedSession() {
        Fixture f = new Fixture();
        Player player = f.player("Builder");
        f.sessions.connect(player);
        f.sessions.confirm(player, "browser-code");
        assertTrue(f.sessions.session(player).isEmpty());
        assertTrue(f.admitted.isEmpty());
        f.worker.runNext();
        assertTrue(f.sessions.session(player).isEmpty());
        f.main.remove().run();
        assertEquals(PARTICIPANT, f.sessions.session(player).orElseThrow().participantKey());
        assertEquals(List.of(player), f.admitted);
    }

    @Test
    void rejectsAConfirmationAfterDisconnectAndRejoinWithTheSameMinecraftUuid() {
        Fixture f = new Fixture();
        Player player = f.player("Builder");
        f.sessions.connect(player);
        f.sessions.confirm(player, "browser-code");
        f.worker.runNext();
        f.sessions.disconnect(player);
        f.sessions.connect(player);
        f.main.remove().run();
        assertTrue(f.sessions.session(player).isEmpty());
        assertTrue(f.admitted.isEmpty());
    }

    @Test
    void linkedJavaAndBedrockAccountsCannotPlayConcurrentlyAsTwoPeople() {
        Fixture f = new Fixture();
        Player java = f.player("JavaBuilder");
        Player bedrock = f.player(".BedrockBuilder");
        f.sessions.connect(java);
        f.sessions.connect(bedrock);
        f.confirm(java);
        f.confirm(bedrock);
        assertTrue(f.sessions.session(java).isPresent());
        assertTrue(f.sessions.session(bedrock).isEmpty());
        f.sessions.disconnect(java);
        f.confirm(bedrock);
        assertEquals(PARTICIPANT, f.sessions.session(bedrock).orElseThrow().participantKey());
    }

    @Test
    void expiryRevokesAuthorizationImmediatelyAndThenClosesTheConnection() {
        Fixture f = new Fixture();
        Player player = f.player("Builder");
        f.sessions.connect(player);
        f.confirm(player);
        f.clock.now = f.clock.now.plusSeconds(1800);
        assertTrue(f.sessions.session(player).isEmpty());
        List<Player> savedBeforeClosing = new ArrayList<>();
        doAnswer(ignored -> {
            assertEquals(List.of(player), savedBeforeClosing);
            return null;
        }).when(player).kick(any(Component.class));
        f.sessions.expireSessions(savedBeforeClosing::add);
        verify(player).kick(any(Component.class));
    }

    @Test
    void authenticationDoesNotRevealPlayersToAnUnauthenticatedViewer() {
        Fixture f = new Fixture();
        Player verified = f.player("Builder");
        Player unverified = f.player("Visitor");
        f.sessions.connect(verified);
        f.sessions.connect(unverified);
        f.confirm(verified);
        verify(unverified, never()).showPlayer(f.plugin, verified);
        verify(verified).setVisibleByDefault(false);
        assertFalse(f.sessions.session(unverified).isPresent());
    }

    @Test
    void closingTheControllerInvalidatesQueuedConfirmationCallbacks() {
        Fixture f = new Fixture();
        Player player = f.player("Builder");
        f.sessions.connect(player);
        f.sessions.confirm(player, "browser-code");
        f.worker.runNext();
        f.sessions.close();
        f.main.remove().run();
        assertTrue(f.admitted.isEmpty());
    }

    private static final class Fixture {
        private final JavaPlugin plugin = mock(JavaPlugin.class);
        private final MicrosoftSsoService backend = mock(MicrosoftSsoService.class);
        private final List<Player> online = new ArrayList<>();
        private final List<Player> admitted = new ArrayList<>();
        private final ArrayDeque<Runnable> main = new ArrayDeque<>();
        private final ManualExecutor worker = new ManualExecutor();
        private final MutableClock clock = new MutableClock();
        private final SsoPlayerSessions sessions;

        private Fixture() {
            Server server = mock(Server.class);
            when(plugin.getServer()).thenReturn(server);
            when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
            when(plugin.getConfig()).thenReturn(new YamlConfiguration());
            doReturn(online).when(server).getOnlinePlayers();
            ScoreboardManager manager = mock(ScoreboardManager.class);
            when(server.getScoreboardManager()).thenReturn(manager);
            when(manager.getNewScoreboard()).thenAnswer(ignored -> {
                Scoreboard board = mock(Scoreboard.class);
                when(board.registerNewTeam(anyString())).thenAnswer(invocation -> mock(Team.class));
                return board;
            });
            BukkitScheduler scheduler = mock(BukkitScheduler.class);
            when(server.getScheduler()).thenReturn(scheduler);
            doAnswer(invocation -> {
                main.add(invocation.getArgument(1, Runnable.class));
                return mock(BukkitTask.class);
            }).when(scheduler).runTask(eq(plugin), any(Runnable.class));
            when(backend.confirm(any(UUID.class), anyString())).thenAnswer(ignored ->
                    new VerifiedSession(PARTICIPANT, "Student Name", clock.now.plusSeconds(1800)));
            sessions = new SsoPlayerSessions(plugin, backend, player -> "java:" + player.getUniqueId(),
                    (player, identity) -> admitted.add(player), worker, clock);
        }

        private Player player(String name) {
            Player player = mock(Player.class);
            when(player.getUniqueId()).thenReturn(UUID.randomUUID());
            when(player.getName()).thenReturn(name);
            when(player.isOnline()).thenReturn(true);
            online.add(player);
            return player;
        }

        private void confirm(Player player) {
            sessions.confirm(player, "browser-code");
            worker.runNext();
            main.remove().run();
        }
    }

    private static final class MutableClock extends Clock {
        private Instant now = Instant.parse("2026-09-28T20:00:00Z");
        @Override public ZoneId getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(ZoneId zone) { return this; }
        @Override public Instant instant() { return now; }
    }

    private static final class ManualExecutor extends AbstractExecutorService {
        private final ArrayDeque<Runnable> tasks = new ArrayDeque<>();
        private boolean shutdown;
        void runNext() { tasks.remove().run(); }
        @Override public void shutdown() { shutdown = true; }
        @Override public List<Runnable> shutdownNow() { shutdown = true; return List.copyOf(tasks); }
        @Override public boolean isShutdown() { return shutdown; }
        @Override public boolean isTerminated() { return shutdown && tasks.isEmpty(); }
        @Override public boolean awaitTermination(long timeout, TimeUnit unit) { return isTerminated(); }
        @Override public void execute(Runnable command) { tasks.add(command); }
    }
}
