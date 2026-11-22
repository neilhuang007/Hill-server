package org.thehill.hill175.replay;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Particle;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.PluginCommand;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.entity.Projectile;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockExplodeEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.entity.EntityDamageByEntityEvent;
import org.bukkit.event.entity.EntityDamageEvent;
import org.bukkit.event.entity.EntityDeathEvent;
import org.bukkit.event.entity.EntityExplodeEvent;
import org.bukkit.event.entity.PlayerDeathEvent;
import org.bukkit.event.player.PlayerBucketEmptyEvent;
import org.bukkit.event.player.PlayerBucketFillEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.projectiles.ProjectileSource;
import org.bukkit.scheduler.BukkitRunnable;
import org.bukkit.scheduler.BukkitTask;

import java.io.IOException;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Predicate;
import java.util.logging.Level;

public final class IncidentReplayService implements Listener, CommandExecutor, TabCompleter, AutoCloseable {
    private static final String PERMISSION = "hill175.replay";
    private static final DateTimeFormatter CLOCK = DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss 'UTC'").withZone(ZoneOffset.UTC);
    private static final UUID ENVIRONMENT = new UUID(0, 0);
    private final JavaPlugin plugin;
    private final Predicate<Player> authenticated;
    private final IncidentStore store;
    private final Map<UUID, Location> lastPositions = new ConcurrentHashMap<>();
    private final List<BukkitTask> playback = new ArrayList<>();
    private BukkitTask sampler;
    private boolean registered;

    public IncidentReplayService(JavaPlugin plugin, Predicate<Player> authenticated) {
        this.plugin = plugin;
        this.authenticated = authenticated;
        this.store = new IncidentStore(plugin.getDataFolder().toPath().resolve("incident-replay"), plugin.getLogger());
    }

    public void register(PluginCommand command) {
        if (registered) throw new IllegalStateException("Incident replay already registered");
        registered = true;
        command.setExecutor(this);
        command.setTabCompleter(this);
        Bukkit.getPluginManager().registerEvents(this, plugin);
        sampler = Bukkit.getScheduler().runTaskTimer(plugin, this::samplePositions, 200L, 200L);
    }

    private void samplePositions() {
        for (Player player : Bukkit.getOnlinePlayers()) {
            Location location = player.getLocation();
            Location previous = lastPositions.put(player.getUniqueId(), location.clone());
            if (previous == null || previous.getWorld() != location.getWorld() || previous.distanceSquared(location) >= 4) {
                record(player, IncidentRecord.Kind.POSITION, location, "sample");
            }
        }
    }

    private void record(Player actor, IncidentRecord.Kind kind, Location location, String detail) {
        World world = location.getWorld();
        if (world == null) return;
        store.append(new IncidentRecord(System.currentTimeMillis(), actor == null ? ENVIRONMENT : actor.getUniqueId(),
                actor == null ? "environment" : actor.getName(), kind, world.getUID(), world.getName(),
                location.getBlockX(), location.getBlockY(), location.getBlockZ(), detail));
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent event) {
        record(event.getPlayer(), IncidentRecord.Kind.BREAK, event.getBlock().getLocation(), event.getBlock().getType().name());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlace(BlockPlaceEvent event) {
        record(event.getPlayer(), IncidentRecord.Kind.PLACE, event.getBlockPlaced().getLocation(), event.getBlockPlaced().getType().name());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBucketEmpty(PlayerBucketEmptyEvent event) {
        record(event.getPlayer(), IncidentRecord.Kind.BUCKET_EMPTY, event.getBlock().getLocation(), event.getBucket().name());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBucketFill(PlayerBucketFillEvent event) {
        record(event.getPlayer(), IncidentRecord.Kind.BUCKET_FILL, event.getBlock().getLocation(), event.getBucket().name());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onDamage(EntityDamageByEntityEvent event) {
        Player attacker = attacker(event.getDamager());
        if (attacker != null) record(attacker, IncidentRecord.Kind.DAMAGE, event.getEntity().getLocation(),
                "target=" + event.getEntity().getType() + ",damage=" + Math.round(event.getFinalDamage() * 10) / 10.0);
        if (event.getEntity() instanceof Player victim && victim != attacker) record(victim, IncidentRecord.Kind.DAMAGE,
                victim.getLocation(), "cause=" + event.getCause() + ",source=" + event.getDamager().getType());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onEnvironmentalDamage(EntityDamageEvent event) {
        if (event instanceof EntityDamageByEntityEvent) return;
        if (event.getEntity() instanceof Player victim) record(victim, IncidentRecord.Kind.DAMAGE,
                victim.getLocation(), "cause=" + event.getCause());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlayerDeath(PlayerDeathEvent event) {
        record(event.getEntity(), IncidentRecord.Kind.DEATH, event.getEntity().getLocation(), "player");
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onEntityDeath(EntityDeathEvent event) {
        if (event.getEntity() instanceof Player) return;
        Player killer = event.getEntity().getKiller();
        if (killer != null) record(killer, IncidentRecord.Kind.DEATH, event.getEntity().getLocation(),
                "target=" + event.getEntityType());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onEntityExplosion(EntityExplodeEvent event) {
        Player source = attacker(event.getEntity());
        record(source, IncidentRecord.Kind.EXPLOSION, event.getLocation(),
                "entity=" + event.getEntityType() + ",blocks=" + event.blockList().size());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBlockExplosion(BlockExplodeEvent event) {
        record(null, IncidentRecord.Kind.EXPLOSION, event.getBlock().getLocation(),
                "block=" + event.getBlock().getType() + ",blocks=" + event.blockList().size());
    }

    @EventHandler public void onQuit(PlayerQuitEvent event) {
        lastPositions.remove(event.getPlayer().getUniqueId());
    }

    private static Player attacker(Entity entity) {
        if (entity instanceof Player player) return player;
        if (entity instanceof Projectile projectile) {
            ProjectileSource shooter = projectile.getShooter();
            if (shooter instanceof Player player) return player;
        }
        return null;
    }

    private boolean allowed(CommandSender sender) {
        if (!sender.hasPermission(PERMISSION)) { sender.sendMessage("You do not have access to incident replay."); return false; }
        if (sender instanceof Player player && !authenticated.test(player)) {
            sender.sendMessage("Only signed-in staff may review incidents."); return false;
        }
        return true;
    }

    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!allowed(sender)) return true;
        if (args.length < 1 || args.length > 3 || (!args[0].equalsIgnoreCase("recent") && !args[0].equalsIgnoreCase("play"))) {
            sender.sendMessage("Usage: /hillreplay recent|play [minutes: 1-120] [exact player name or UUID]"); return true;
        }
        boolean play = args[0].equalsIgnoreCase("play");
        if (play && !(sender instanceof Player)) { sender.sendMessage("Playback requires an in-game staff viewer."); return true; }
        int minutes = 15;
        if (args.length >= 2) {
            try { minutes = Integer.parseInt(args[1]); }
            catch (NumberFormatException ignored) { sender.sendMessage("Minutes must be 1-120."); return true; }
        }
        if (minutes < 1 || minutes > 120) { sender.sendMessage("Minutes must be 1-120."); return true; }
        String filter = args.length == 3 ? args[2] : null;
        if (filter != null && !filter.matches("[A-Za-z0-9_.-]{1,36}")) {
            sender.sendMessage("Use an exact player name or UUID."); return true;
        }
        long since = System.currentTimeMillis() - minutes * 60_000L;
        UUID viewer = sender instanceof Player player ? player.getUniqueId() : null;
        sender.sendMessage("Searching incident logs asynchronously...");
        try {
            Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
                IncidentStore.Result result;
                try { result = store.query(since, filter, play ? 40 : 30); }
                catch (IOException error) {
                    plugin.getLogger().log(Level.WARNING, "Incident replay query failed", error);
                    Bukkit.getScheduler().runTask(plugin, () -> sender.sendMessage("Incident logs unavailable; see server log."));
                    return;
                }
                Bukkit.getScheduler().runTask(plugin, () -> {
                    CommandSender target = viewer == null ? sender : Bukkit.getPlayer(viewer);
                    if (target == null || !allowed(target)) return;
                    if (result.partial()) target.sendMessage("Warning: query scanned only the newest 16 MiB; older events may be omitted.");
                    if (result.records().isEmpty()) { target.sendMessage("No matching recorded events in that window."); return; }
                    if (play) startPlayback((Player) target, result.records());
                    else {
                        target.sendMessage("Recent incidents (" + result.records().size() + " newest matching records):");
                        for (IncidentRecord record : result.records()) target.sendMessage(format(record));
                    }
                });
            });
        } catch (IllegalStateException error) { sender.sendMessage("Incident replay is stopping."); }
        return true;
    }

    private static String format(IncidentRecord record) {
        return CLOCK.format(Instant.ofEpochMilli(record.time())) + " " + record.name() + " [" + record.actor() + "] "
                + record.kind() + " " + record.worldName() + " " + record.x() + "," + record.y() + "," + record.z()
                + " " + record.detail();
    }

    private void startPlayback(Player viewer, List<IncidentRecord> records) {
        viewer.sendMessage("Incident timeline: " + records.size() + " events, 4 ticks apart. Particles only within 48 blocks in your current world; no teleport/world changes.");
        BukkitRunnable sequence = new BukkitRunnable() {
            int index;
            @Override public void run() {
                if (!viewer.isOnline() || !viewer.hasPermission(PERMISSION) || !authenticated.test(viewer)) { stop(); return; }
                if (index >= records.size()) { stop(); return; }
                IncidentRecord record = records.get(index++);
                viewer.sendMessage(format(record));
                World world = viewer.getWorld();
                if (!world.getUID().equals(record.world())) return;
                Location location = new Location(world, record.x() + 0.5, record.y() + 0.5, record.z() + 0.5);
                if (viewer.getLocation().distanceSquared(location) > 48 * 48) return;
                viewer.spawnParticle(Particle.END_ROD, location, 8, .35, .35, .35, .01);
            }
            private void stop() { cancel(); }
        };
        playback.removeIf(BukkitTask::isCancelled);
        playback.add(sequence.runTaskTimer(plugin, 1L, 4L));
    }

    @Override public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        if (!sender.hasPermission(PERMISSION)) return List.of();
        if (args.length == 1) return List.of("recent", "play").stream().filter(value -> value.startsWith(args[0].toLowerCase())).toList();
        if (args.length == 2) return List.of("15", "30", "60", "120").stream().filter(value -> value.startsWith(args[1])).toList();
        return List.of();
    }

    @Override public void close() {
        if (sampler != null) sampler.cancel();
        for (BukkitTask task : playback) task.cancel();
        playback.clear();
        HandlerList.unregisterAll(this);
        store.close();
    }
}
