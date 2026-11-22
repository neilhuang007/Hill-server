package org.thehill.hill175.replay;

import org.bukkit.Bukkit;
import org.bukkit.command.PluginCommand;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.logging.Level;

/** Optional bounded visual capture. Requires the exact hardened upstream artifact. */
public final class PacketReplayService implements Listener, AutoCloseable {
    private final JavaPlugin plugin;
    private final Predicate<Player> authenticated;
    private final Map<UUID, Session> sessions = new HashMap<>();
    private final Map<UUID, Long> retryAfter = new HashMap<>();
    private final java.util.Set<UUID> firstSegmentStarted = new java.util.HashSet<>();
    private final java.util.Set<UUID> saving = ConcurrentHashMap.newKeySet();
    private final java.util.Set<CompletableFuture<?>> writes = ConcurrentHashMap.newKeySet();
    private final AtomicInteger finalizing = new AtomicInteger();
    private Object recording;
    private PacketReplayBootstrap bootstrap;
    private Method start;
    private Method stop;
    private Method consumeGap;
    private Method movementFilter;
    private PacketReplayFiles files;
    private BukkitTask task;
    private int maxRecorders;
    private long lastWarning;
    private long lastPrune;
    private volatile boolean closing;
    private record Session(Player player, long rotateAt, Path file) {}

    public PacketReplayService(JavaPlugin plugin, Predicate<Player> authenticated) {
        this.plugin = plugin;
        this.authenticated = authenticated;
    }

    public void start() {
        boolean enabled = plugin.getConfig().getBoolean("packet-replay.enabled", false);
        Plugin upstream = Bukkit.getPluginManager().getPlugin("FlashbackServer");
        if (upstream instanceof JavaPlugin javaPlugin) {
            PluginCommand command = javaPlugin.getCommand("replay");
            if (command != null) {
                command.setExecutor((sender, ignored, label, arguments) -> {
                    sender.sendMessage("Raw replay controls are disabled. Staff use /hillreplay for the incident timeline; visual archives require authorized server operators.");
                    return true;
                });
                command.setTabCompleter((sender, ignored, alias, arguments) -> List.of());
            }
        }
        if (!enabled) return;
        if (upstream == null || !upstream.isEnabled()) throw new IllegalStateException("Packet replay enabled but hardened FlashbackServer is absent/disabled");
        if (!"26.2".equals(Bukkit.getMinecraftVersion())) throw new IllegalStateException("Pinned packet recorder supports only Minecraft 26.2");
        try {
            Class<?> policy = Class.forName("dev.zeffut.flashbackserver.record.HillRecordingPolicy", true, upstream.getClass().getClassLoader());
            if (!Integer.valueOf(1).equals(policy.getMethod("version").invoke(null))
                    || policy.getField("MAX_RETAINED_BYTES").getLong(null) != 16L * 1024 * 1024
                    || policy.getField("MAX_RETAINED_ACTIONS").getInt(null) != 100_000) {
                throw new IllegalStateException("Packet recorder hardening policy mismatch");
            }
            if (upstream instanceof JavaPlugin javaPlugin && (javaPlugin.getConfig().getBoolean("telemetry.enabled", true)
                    || javaPlugin.getConfig().getBoolean("clips.auto-clip-on-death", true))) {
                throw new IllegalStateException("Hardened recorder requires telemetry and automatic clips disabled");
            }
            consumeGap = policy.getMethod("consumeGap", UUID.class);
            movementFilter = policy.getMethod("setMovementFilter", UUID.class, java.util.function.UnaryOperator.class);
            recording = upstream.getClass().getMethod("getRecordingService").invoke(upstream);
            if (recording == null) throw new IllegalStateException("Packet recorder API is unavailable");
            start = recording.getClass().getMethod("start", Player.class);
            stop = recording.getClass().getMethod("stop", Player.class, Path.class);
            bootstrap = new PacketReplayBootstrap(upstream, recording);
            maxRecorders = plugin.getConfig().getInt("packet-replay.max-recorders", 32);
            if (maxRecorders < 1 || maxRecorders > 64) throw new IllegalStateException("packet-replay.max-recorders must be 1-64");
            files = new PacketReplayFiles(plugin.getDataFolder().toPath().resolve("packet-replay"));
            files.prune();
        } catch (ReflectiveOperationException | IOException error) {
            throw new IllegalStateException("Cannot enable packet replay: install the pinned Hill-hardened artifact", error);
        }
        Bukkit.getPluginManager().registerEvents(this, plugin);
        task = Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 1L, 1L);
        plugin.getLogger().info("Private packet replay enabled: authenticated player POVs, 60s segments, " + maxRecorders
                + " concurrent active/finalizing slots; 16MiB/100000 retained-action limits. Gaps are possible and reported.");
    }

    private void tick() {
        long now = System.currentTimeMillis();
        for (Session session : new ArrayList<>(sessions.values())) {
            if (now < retryAfter.getOrDefault(session.player().getUniqueId(), 0L)) continue;
            try {
                boolean gap = Boolean.TRUE.equals(consumeGap.invoke(null, session.player().getUniqueId()));
                if (gap) warning("REPLAY GAP: payload/action cap or snapshot limit reached for " + session.player().getUniqueId());
                if (gap || now >= session.rotateAt() || !session.player().isOnline() || !authenticated.test(session.player())) {
                    finish(session, gap ? "LIMIT_GAP" : "SEGMENT_END");
                }
            } catch (ReflectiveOperationException error) {
                warning("REPLAY GAP: hardened recorder status failed: " + error.getClass().getSimpleName());
                finish(session, "STATUS_FAILED");
            }
        }
        int wanted = 0;
        Player next = null;
        for (Player player : Bukkit.getOnlinePlayers()) {
            if (!authenticated.test(player)) continue;
            wanted++;
            if (next == null && !sessions.containsKey(player.getUniqueId()) && !saving.contains(player.getUniqueId())
                    && now >= retryAfter.getOrDefault(player.getUniqueId(), 0L)) next = player;
        }
        if (wanted > maxRecorders && now - lastWarning >= 60_000) warning("REPLAY GAP: " + wanted
                + " authenticated players exceed " + maxRecorders + " recorder slots; not all POVs are recorded");
        if (next != null && sessions.size() + finalizing.get() < maxRecorders) begin(next, now);
        if (now - lastPrune >= 60_000) {
            lastPrune = now;
            Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
                try { files.prune(); }
                catch (IOException error) { plugin.getLogger().log(Level.WARNING, "Replay retention failed", error); }
            });
        }
    }

    private void begin(Player player, long now) {
        UUID uuid = player.getUniqueId();
        Path path = files.reserve(uuid);
        try {
            files.event("STARTED", uuid, path, "authenticated server-visible POV");
            java.util.function.UnaryOperator<byte[]> filter = payload -> PacketReplayMovement.visible(player, payload);
            movementFilter.invoke(null, uuid, filter);
            long interval = firstSegmentStarted.add(uuid) ? 30_000 + Math.floorMod(uuid.hashCode(), 30_001) : 60_000;
            sessions.put(uuid, new Session(player, now + interval, path));
            if (!Boolean.TRUE.equals(start.invoke(recording, player))) {
                finish(sessions.get(uuid), "START_REFUSED_CLEANUP");
                retryAfter.put(uuid, now + 10_000);
            } else {
                int entities = bootstrap.capture(player);
                files.event("BOOTSTRAPPED", uuid, path, "visible tracked entity pairing packets=" + entities);
            }
        } catch (ReflectiveOperationException | IOException | RuntimeException error) {
            retryAfter.put(uuid, now + 10_000);
            Session possibleOrphan = sessions.get(uuid);
            if (possibleOrphan != null) finish(possibleOrphan, "START_EXCEPTION_CLEANUP");
            plugin.getLogger().log(Level.WARNING, "REPLAY GAP: could not start " + uuid, unwrap(error));
        }
    }

    private void finish(Session session, String reason) {
        UUID uuid = session.player().getUniqueId();
        if (!sessions.remove(uuid, session)) return;
        finalizing.incrementAndGet();
        saving.add(uuid);
        Path pending = session.file().resolveSibling(session.file().getFileName() + ".pending");
        files.beginWrite(pending);
        try {
            files.event(reason, uuid, session.file(), "segment capture stopped; async save pending");
        } catch (IOException error) {
            plugin.getLogger().log(Level.WARNING, "Replay segment outcome index unavailable", error);
        }
        try {
            Object result = stop.invoke(recording, session.player(), pending);
            if (!(result instanceof CompletableFuture<?> future)) throw new IllegalStateException("Unexpected recorder stop result");
            CompletableFuture<?> completion = future.whenComplete((output, error) -> {
                try {
                    if (error != null || !(output instanceof Path written)) {
                        files.event("SAVE_FAILED", uuid, session.file(), error == null ? "no output" : error.getClass().getSimpleName());
                        plugin.getLogger().warning("REPLAY GAP: segment save failed for " + uuid);
                    } else {
                        PacketReplayFiles.protect(written, false);
                        Files.move(written, session.file(), StandardCopyOption.ATOMIC_MOVE);
                        files.saved(session.file());
                        boolean gap = Boolean.TRUE.equals(consumeGap.invoke(null, uuid)) || !(reason.equals("SEGMENT_END") || reason.equals("DISCONNECTED") || reason.equals("SHUTDOWN"));
                        files.event(gap ? "SAVED_WITH_GAP" : "SAVED", uuid, session.file(), reason + ";bytes=" + Files.size(session.file()));
                        files.prune();
                    }
                } catch (IOException | ReflectiveOperationException io) { plugin.getLogger().log(Level.WARNING, "REPLAY GAP: segment finalization failed for " + uuid, io); }
                finally {
                    try { movementFilter.invoke(null, uuid, null); }
                    catch (ReflectiveOperationException cleanup) { plugin.getLogger().warning("Replay movement-filter cleanup failed for " + uuid); }
                    files.endWrite(pending); finalizing.decrementAndGet(); saving.remove(uuid);
                }
            });
            writes.add(completion);
            completion.whenComplete((ignored, error) -> writes.remove(completion));
        } catch (ReflectiveOperationException | RuntimeException error) {
            files.endWrite(pending);
            finalizing.decrementAndGet();
            saving.remove(uuid);
            retryAfter.put(uuid, System.currentTimeMillis() + 10_000);
            if (!closing) sessions.put(uuid, new Session(session.player(), System.currentTimeMillis() + 10_000, session.file()));
            plugin.getLogger().log(Level.WARNING, "REPLAY GAP: could not stop segment for " + uuid + "; retained recorder remains tracked for cleanup", unwrap(error));
        }
    }

    private void warning(String text) {
        lastWarning = System.currentTimeMillis();
        plugin.getLogger().warning(text);
    }

    private static Throwable unwrap(Throwable error) {
        return error instanceof InvocationTargetException invocation && invocation.getCause() != null ? invocation.getCause() : error;
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onQuit(PlayerQuitEvent event) {
        Session session = sessions.get(event.getPlayer().getUniqueId());
        if (session != null) finish(session, "DISCONNECTED");
        retryAfter.remove(event.getPlayer().getUniqueId());
        firstSegmentStarted.remove(event.getPlayer().getUniqueId());
    }

    @Override public void close() {
        if (closing) return;
        closing = true;
        if (task != null) task.cancel();
        HandlerList.unregisterAll(this);
        for (Session session : new ArrayList<>(sessions.values())) finish(session, "SHUTDOWN");
        try { CompletableFuture.allOf(writes.toArray(CompletableFuture[]::new)).get(20, TimeUnit.SECONDS); }
        catch (Exception error) { plugin.getLogger().warning("Replay shutdown save incomplete; check private .pending files and server logs"); }
    }
}
