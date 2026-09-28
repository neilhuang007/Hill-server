package org.thehill.hill175.auth;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scoreboard.Scoreboard;
import org.bukkit.scoreboard.Team;
import org.thehill.hill175.auth.sso.MicrosoftSsoService;
import org.thehill.hill175.auth.sso.SsoException;
import org.thehill.hill175.auth.sso.VerifiedSession;

import java.time.Clock;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import java.util.function.Function;

/** Bukkit boundary. All player mutations and connection bookkeeping run on the server thread. */
public final class SsoPlayerSessions implements AutoCloseable {
    private final JavaPlugin plugin;
    private final MicrosoftSsoService service;
    private final Function<Player, String> identityResolver;
    private final BiConsumer<Player, VerifiedSession> onAuthenticated;
    private final ExecutorService confirmations;
    private final Clock clock;
    private final List<String> npcNames;
    private final Map<UUID, Connection> connections = new HashMap<>();
    private final Map<UUID, VerifiedSession> sessions = new ConcurrentHashMap<>();
    private final Map<String, UUID> activeParticipants = new HashMap<>();
    private final Map<UUID, ViewerBoard> viewerBoards = new HashMap<>();
    private volatile boolean closed;

    public SsoPlayerSessions(JavaPlugin plugin, MicrosoftSsoService service,
                             BiConsumer<Player, VerifiedSession> onAuthenticated) {
        this(plugin, service, new GameIdentityResolver(plugin)::resolve, onAuthenticated,
                new ThreadPoolExecutor(1, 1, 0L, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(128),
                        Thread.ofPlatform().daemon().name("hill175-confirm-", 0).factory()), Clock.systemUTC());
    }

    SsoPlayerSessions(JavaPlugin plugin, MicrosoftSsoService service, Function<Player, String> identityResolver,
                      BiConsumer<Player, VerifiedSession> onAuthenticated, ExecutorService confirmations) {
        this(plugin, service, identityResolver, onAuthenticated, confirmations, Clock.systemUTC());
    }

    SsoPlayerSessions(JavaPlugin plugin, MicrosoftSsoService service, Function<Player, String> identityResolver,
                      BiConsumer<Player, VerifiedSession> onAuthenticated, ExecutorService confirmations, Clock clock) {
        this.plugin = plugin;
        this.service = service;
        this.identityResolver = identityResolver;
        this.onAuthenticated = onAuthenticated;
        this.confirmations = confirmations;
        this.clock = clock;
        this.npcNames = List.of("journey", "place", "people", "survival").stream()
                .map(category -> plugin.getConfig().getString("worlds.hub-npcs." + category + ".profile-name", ""))
                .filter(name -> !name.isBlank()).toList();
    }

    public boolean connect(Player player) {
        removeConnection(player);
        // New viewers cannot receive an existing student's player-info/name packets before their join event.
        player.setVisibleByDefault(false);
        player.displayName(Component.text(player.getName()));
        player.playerListName(null);
        try {
            connections.put(player.getUniqueId(), new Connection(UUID.randomUUID(), identityResolver.apply(player)));
            synchronizeViewer(player);
            updateSubject(player);
            return true;
        } catch (RuntimeException exception) {
            updateSubject(player);
            plugin.getLogger().warning("Rejected a connection because its authenticated game identity was unavailable.");
            player.kick(Component.text("Your Minecraft identity could not be verified. Please contact Hill IT."));
            return false;
        }
    }

    public void disconnect(Player player) {
        removeConnection(player);
        updateSubject(player);
        if (player.isOnline()) {
            // Clear the departing/expired viewer's private real-name packets as well.
            synchronizeViewer(player);
            viewerBoards.remove(player.getUniqueId());
        }
    }

    private void removeConnection(Player player) {
        Connection connection = connections.remove(player.getUniqueId());
        if (connection != null) {
            service.cancel(connection.id);
        }
        VerifiedSession old = sessions.remove(player.getUniqueId());
        if (old != null) {
            activeParticipants.remove(old.participantKey(), player.getUniqueId());
        }
        viewerBoards.remove(player.getUniqueId());
    }

    /** Safe for the asynchronous chat listener; expires even before the next server tick. */
    public Optional<VerifiedSession> session(Player player) {
        VerifiedSession session = sessions.get(player.getUniqueId());
        return session != null && session.expiresAt().isAfter(clock.instant()) ? Optional.of(session) : Optional.empty();
    }

    public Optional<String> nameLookup(String participantKey) {
        return service.nameLookup(participantKey);
    }

    public void requestLink(Player player) {
        if (session(player).isPresent()) {
            player.sendMessage(Component.text("Your Hill account is already verified for this connection.", NamedTextColor.YELLOW));
            return;
        }
        Connection connection = connections.get(player.getUniqueId());
        if (connection == null || connection.confirming || closed) {
            return;
        }
        try {
            String url = service.begin(connection.id, connection.gameIdentity, player.getName());
            player.sendMessage(Component.text("Sign in with your Hill Microsoft account: ", NamedTextColor.GOLD)
                    .append(Component.text(url, NamedTextColor.AQUA).clickEvent(ClickEvent.openUrl(url))));
            player.sendMessage(Component.text("After signing in, type /verify followed by the code shown only in your browser.", NamedTextColor.WHITE));
            player.sendMessage(Component.text("Your school name will be visible to other verified participants. Never enter a code supplied by someone else.", NamedTextColor.GRAY));
        } catch (SsoException exception) {
            player.sendMessage(Component.text(exception.getMessage(), NamedTextColor.RED));
        }
    }

    public void confirm(Player player, String code) {
        Connection connection = connections.get(player.getUniqueId());
        if (connection == null || connection.confirming || closed || session(player).isPresent()) {
            return;
        }
        connection.confirming = true;
        try {
            confirmations.execute(() -> {
                VerifiedSession result = null;
                String failure = null;
                try {
                    result = service.confirm(connection.id, code);
                } catch (SsoException exception) {
                    failure = exception.getMessage();
                } catch (RuntimeException exception) {
                    failure = "Verification could not be saved. Request a new link or contact Hill IT.";
                    plugin.getLogger().warning("A school verification could not be completed safely.");
                }
                VerifiedSession verified = result;
                String error = failure;
                if (!closed) {
                    try {
                        plugin.getServer().getScheduler().runTask(plugin, () -> complete(player, connection, verified, error));
                    } catch (RuntimeException ignored) {
                        // Server/plugin shutdown invalidates the connection; never grant off-thread.
                    }
                }
            });
        } catch (RejectedExecutionException exception) {
            connection.confirming = false;
            player.sendMessage(Component.text("Verification is busy. Try again shortly.", NamedTextColor.YELLOW));
        }
    }

    private void complete(Player player, Connection connection, VerifiedSession verified, String error) {
        if (closed || !player.isOnline() || connections.get(player.getUniqueId()) != connection) {
            return;
        }
        connection.confirming = false;
        if (error != null || verified == null || !verified.expiresAt().isAfter(clock.instant())) {
            player.sendMessage(Component.text(error == null ? "Verification expired. Use /verify for a new link." : error, NamedTextColor.RED));
            return;
        }
        UUID existing = activeParticipants.get(verified.participantKey());
        if (existing != null && !existing.equals(player.getUniqueId())) {
            player.sendMessage(Component.text("This Hill account is already playing on another connection. Disconnect it, then use /verify again.", NamedTextColor.RED));
            return;
        }
        activeParticipants.put(verified.participantKey(), player.getUniqueId());
        sessions.put(player.getUniqueId(), verified);
        try {
            onAuthenticated.accept(player, verified);
            synchronizeViewer(player);
            updateSubject(player);
        } catch (RuntimeException exception) {
            disconnect(player);
            plugin.getLogger().warning("A verified player could not enter safely; the connection was closed.");
            player.kick(Component.text("Hill 175 could not complete your admission. Please reconnect."));
        }
    }

    public void expireSessions(Consumer<Player> beforeClosing) {
        for (Player player : plugin.getServer().getOnlinePlayers()) {
            if (sessions.containsKey(player.getUniqueId()) && session(player).isEmpty()) {
                // Save gameplay state before either kick or the next authentication-lock teleport.
                try {
                    beforeClosing.accept(player);
                } catch (RuntimeException exception) {
                    plugin.getLogger().severe("Could not save gameplay state before an expired school session was closed.");
                }
                disconnect(player);
                player.kick(Component.text("Your Hill verification expired. Reconnect and sign in again."));
            }
        }
    }

    private void synchronizeViewer(Player viewer) {
        ViewerBoard board = viewerBoards.get(viewer.getUniqueId());
        if (board == null) {
            Scoreboard scoreboard = plugin.getServer().getScoreboardManager().getNewScoreboard();
            Team npcs = scoreboard.registerNewTeam("hill175_npcs");
            npcs.setOption(Team.Option.NAME_TAG_VISIBILITY, Team.OptionStatus.NEVER);
            npcs.setOption(Team.Option.COLLISION_RULE, Team.OptionStatus.NEVER);
            npcNames.forEach(npcs::addEntry);
            board = new ViewerBoard(scoreboard);
            viewerBoards.put(viewer.getUniqueId(), board);
            // A private scoreboard prevents real-name team packets from reaching unverified viewers.
            viewer.setScoreboard(scoreboard);
        }
        for (Player subject : plugin.getServer().getOnlinePlayers()) {
            updateSubjectForViewer(viewer, subject, board);
        }
    }

    /** Login/logout touches one subject on each viewer's retained board, rather than rebuilding N boards. */
    private void updateSubject(Player subject) {
        for (Player viewer : plugin.getServer().getOnlinePlayers()) {
            ViewerBoard board = viewerBoards.get(viewer.getUniqueId());
            if (board != null) {
                updateSubjectForViewer(viewer, subject, board);
            } else if (!subject.getUniqueId().equals(viewer.getUniqueId())) {
                viewer.hidePlayer(plugin, subject);
            }
        }
    }

    private void updateSubjectForViewer(Player viewer, Player subject, ViewerBoard board) {
        Optional<VerifiedSession> identity = session(subject);
        boolean visible = session(viewer).isPresent() && identity.isPresent();
        if (!subject.getUniqueId().equals(viewer.getUniqueId())) {
            if (visible) {
                viewer.showPlayer(plugin, subject);
            } else {
                viewer.hidePlayer(plugin, subject);
            }
        }
        if (visible) {
            Team team = board.subjectTeams.computeIfAbsent(subject.getUniqueId(),
                    ignored -> board.scoreboard.registerNewTeam("h175p" + board.nextTeam++));
            team.prefix(Component.text(identity.orElseThrow().displayName(), NamedTextColor.GOLD)
                    .append(Component.text(" · ", NamedTextColor.GRAY)));
            team.addEntry(subject.getName());
        } else {
            Team removed = board.subjectTeams.remove(subject.getUniqueId());
            if (removed != null) {
                removed.unregister();
            }
        }
    }

    @Override
    public void close() {
        closed = true;
        confirmations.shutdownNow();
        for (Connection connection : connections.values()) {
            service.cancel(connection.id);
        }
        connections.clear();
        sessions.clear();
        activeParticipants.clear();
        viewerBoards.clear();
    }

    private static final class Connection {
        private final UUID id;
        private final String gameIdentity;
        private boolean confirming;

        private Connection(UUID id, String gameIdentity) {
            this.id = id;
            this.gameIdentity = gameIdentity;
        }
    }

    private static final class ViewerBoard {
        private final Scoreboard scoreboard;
        private final Map<UUID, Team> subjectTeams = new HashMap<>();
        private int nextTeam;

        private ViewerBoard(Scoreboard scoreboard) {
            this.scoreboard = scoreboard;
        }
    }
}
