package org.thehill.hill175.replay;

import io.papermc.paper.math.Position;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.GameRules;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.WorldCreator;
import org.bukkit.block.data.BlockData;
import org.bukkit.entity.Mannequin;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.world.ChunkLoadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Level;

final class ReplayStage implements Listener, AutoCloseable {
    static final String PREFIX = "hill_replay_";
    private static final String MARKER = ".hill175-build-replay";
    private static final double VIEW_RADIUS_SQUARED = 28 * 28;
    private static final int ACTOR_WAIT_TICKS = 20;
    private final JavaPlugin plugin;
    private final UUID viewerId;
    private final BuildTape tape;
    private final LinkedHashSet<BuildTape.BlockPos> pending = new LinkedHashSet<>();
    private final Map<String, BlockData> palette = new HashMap<>();
    private final Map<World, Path> worlds = new HashMap<>();
    private final BukkitTask render;
    private World world;
    private Mannequin actor;
    private ActorChunk actorChunk;
    private ActorChunk pendingActorChunk;
    private int actorWait;
    private boolean closed;
    private BuildTape.Segment segment;
    private long localTime;
    private int applied;
    private int generatedAt;
    private Location pendingPose;
    private boolean swingAfterRender;

    ReplayStage(JavaPlugin plugin, UUID viewerId, BuildTape tape) {
        this.plugin = plugin;
        this.viewerId = viewerId;
        this.tape = tape;
        Bukkit.getPluginManager().registerEvents(this, plugin);
        render = Bukkit.getScheduler().runTaskTimer(plugin, this::renderBlocks, 1L, 1L);
    }

    boolean owns(World candidate) { return worlds.containsKey(candidate); }
    boolean ready() { return pending.isEmpty() && pendingPose == null; }

    boolean allowsMovement(Location destination) {
        Location anchor = pendingPose;
        if (anchor == null && actor != null) anchor = actor.getLocation();
        return anchor != null && inView(anchor, destination);
    }

    private static boolean inView(Location anchor, Location destination) {
        return anchor.getWorld().equals(destination.getWorld()) && anchor.distanceSquared(destination) <= VIEW_RADIUS_SQUARED;
    }

    void show(Player viewer, long time) throws IOException {
        if (!viewerId.equals(viewer.getUniqueId())) throw new IllegalArgumentException("Wrong replay viewer.");
        if (closed) throw new IOException("This replay stage is closed.");
        var cursor = tape.at(time);
        var pose = cursor.segment().poseAt(cursor.time());
        if (segment != cursor.segment()) {
            switchScene(viewer, cursor, pose);
            return;
        }
        int target = segment.editCountAt(cursor.time());
        localTime = cursor.time();
        boolean swing = false;
        long previousChunk = Long.MIN_VALUE;
        boolean loaded = false;
        for (int index = Math.min(applied, target); index < Math.max(applied, target); index++) {
            var edit = segment.edits().get(index);
            long chunk = BuildTape.chunkKey(edit.x() >> 4, edit.z() >> 4);
            if (chunk != previousChunk) {
                loaded = world.isChunkLoaded(edit.x() >> 4, edit.z() >> 4);
                previousChunk = chunk;
            }
            if (loaded) pending.add(edit.position());
            swing |= edit.subject();
        }
        applied = target;
        Location position = location(pose);
        if (!inView(position, viewer.getLocation())
                && (!viewer.teleport(vantage(position)) || closed || !world.equals(viewer.getWorld()))) {
            throw new IOException("Could not follow the recorded player.");
        }
        holdActorDestination(position);
        pendingPose = position;
        swingAfterRender = swing;
        finishFrame();
    }

    private void holdActorDestination(Location position) {
        ActorChunk target = new ActorChunk(position);
        if (target.equals(pendingActorChunk)) return;
        if (pendingActorChunk != null) pendingActorChunk.release(plugin);
        pendingActorChunk = null;
        if (!target.equals(actorChunk)) {
            pendingActorChunk = target;
            target.retain(plugin);
        }
    }

    void finishFrame() throws IOException {
        if (!pending.isEmpty() || pendingPose == null || closed) return;
        if (actor == null || !actor.isValid()) {
            if (++actorWait >= ACTOR_WAIT_TICKS) throw new IOException("The replay figure is no longer available.");
            return;
        }
        if (!actor.getLocation().equals(pendingPose)) {
            if (!actor.teleport(pendingPose)) throw new IOException("Could not move the replay figure.");
            actor.setBodyYaw(pendingPose.getYaw());
        }
        if (pendingActorChunk != null) {
            actorChunk.release(plugin);
            actorChunk = pendingActorChunk;
            pendingActorChunk = null;
        }
        pendingPose = null;
        actorWait = 0;
        if (swingAfterRender) actor.swingMainHand();
        swingAfterRender = false;
    }

    private void switchScene(Player viewer, BuildTape.Cursor cursor, BuildTape.Pose pose) throws IOException {
        World previous = world;
        String name = PREFIX + UUID.randomUUID().toString().replace("-", "");
        Path dimensions = root(plugin);
        if (Files.getFileStore(dimensions).getUsableSpace() < ReplayStorage.minimumFreeBytes(plugin) + (8L << 20)) {
            throw new ReplayStorage.Full("There is not enough free disk space to open a replay world safely. Please ask an operator to free space.");
        }
        Path folder = dimensions.resolve(name);
        Files.createDirectory(folder);
        Files.writeString(folder.resolve(MARKER), name);
        var next = cursor.segment();
        World created = WorldCreator.name(name).generateStructures(false)
                .generator(ReplayTerrain.generator(plugin, next.scene(), next.frame(cursor.time())))
                .forcedSpawnPosition(Position.block((int) Math.floor(pose.x()), (int) Math.floor(pose.y()), (int) Math.floor(pose.z())), 0, 0)
                .createWorld();
        if (created == null) throw new IOException("Could not create a private replay world.");
        worlds.put(created, folder);
        if (!created.getWorldFolder().toPath().toAbsolutePath().normalize().equals(folder)) throw new IOException("Unexpected replay world folder.");
        segment = next;
        world = created;
        world.setAutoSave(false);
        world.setPVP(false);
        world.setDifficulty(org.bukkit.Difficulty.PEACEFUL);
        world.setViewDistance(4);
        world.setSimulationDistance(2);
        world.setTime(6000);
        world.setStorm(false);
        world.setGameRule(GameRules.SPAWN_MOBS, false);
        world.setGameRule(GameRules.SPAWNER_BLOCKS_WORK, false);
        world.setGameRule(GameRules.ADVANCE_TIME, false);
        world.setGameRule(GameRules.ADVANCE_WEATHER, false);
        world.setGameRule(GameRules.TNT_EXPLODES, false);
        world.setGameRule(GameRules.RANDOM_TICK_SPEED, 0);
        world.setGameRule(GameRules.FIRE_SPREAD_RADIUS_AROUND_PLAYER, 0);
        localTime = cursor.time();
        applied = segment.editCountAt(localTime);
        generatedAt = applied;
        pending.clear();
        Location position = location(pose);
        Location view = vantage(position);
        withdrawActor();
        if (!viewer.teleport(view) || closed || !created.equals(viewer.getWorld())) throw new IOException("Could not enter the private replay.");
        spawnActor(viewer, position);
        viewer.sendMessage(Component.text(tape.name() + " • " + segment.world(), NamedTextColor.AQUA));
        if (previous != null) release(previous);
    }

    private Location location(BuildTape.Pose pose) {
        return new Location(world, pose.x(), pose.y(), pose.z(), pose.yaw(), pose.pitch());
    }

    private Location vantage(Location position) {
        Location target = position.clone().add(0, 1.5, 0);
        for (double distance : new double[]{4, 2}) {
            for (int offset : new int[]{0, 90, -90, 180}) {
                double angle = Math.toRadians(position.getYaw() + offset);
                Location view = position.clone().add(distance * Math.sin(angle), distance / 2, -distance * Math.cos(angle));
                Location eye = view.clone().add(0, 1.62, 0);
                if (!view.getBlock().isPassable() || !eye.getBlock().isPassable()) continue;
                var direction = target.toVector().subtract(eye.toVector());
                if (world.rayTraceBlocks(eye, direction, direction.length(), org.bukkit.FluidCollisionMode.NEVER, true) == null) {
                    return view.setDirection(direction);
                }
            }
        }
        return position.clone();
    }

    private void spawnActor(Player viewer, Location position) throws IOException {
        if (actor != null) throw new IllegalStateException("The previous replay figure has not been removed.");
        actorChunk = new ActorChunk(position);
        actorChunk.retain(plugin);
        actor = world.spawn(position, Mannequin.class, mannequin -> {
            mannequin.customName(Component.text(tape.name(), NamedTextColor.GOLD));
            mannequin.setCustomNameVisible(true);
            mannequin.setDescription(null);
            mannequin.setGravity(false);
            mannequin.setImmovable(true);
            mannequin.setInvulnerable(true);
            mannequin.setCollidable(false);
            mannequin.setPersistent(false);
            mannequin.setVisibleByDefault(false);
        });
        if (!actor.isValid()) throw new IOException("Could not spawn the replay figure.");
        viewer.showEntity(plugin, actor);
    }

    void withdrawActor() {
        Mannequin previous = actor;
        ActorChunk previousChunk = actorChunk;
        ActorChunk destinationChunk = pendingActorChunk;
        actor = null;
        actorChunk = null;
        pendingActorChunk = null;
        pendingPose = null;
        actorWait = 0;
        swingAfterRender = false;
        try {
            if (previous != null) {
                try {
                    Player viewer = Bukkit.getPlayer(viewerId);
                    if (plugin.isEnabled() && viewer != null && viewer.getWorld().equals(previous.getWorld())) {
                        viewer.hideEntity(plugin, previous);
                    }
                } finally {
                    previous.remove();
                }
            }
        } finally {
            try {
                if (destinationChunk != null) destinationChunk.release(plugin);
            } finally {
                if (previousChunk != null) previousChunk.release(plugin);
            }
        }
    }

    @EventHandler public void chunkLoaded(ChunkLoadEvent event) {
        if (world != null && world.equals(event.getWorld()) && (!event.isNewChunk() || applied != generatedAt)) {
            queueChunk(event.getChunk().getX(), event.getChunk().getZ());
        }
    }

    private void queueChunk(int chunkX, int chunkZ) {
        segment.positions(BuildTape.chunkKey(chunkX, chunkZ)).forEach(pending::add);
    }

    private void renderBlocks() {
        for (int budget = 512; budget > 0 && !pending.isEmpty(); budget--) {
            var pos = pending.removeFirst();
            if (!world.isChunkLoaded(pos.x() >> 4, pos.z() >> 4) || pos.y() < world.getMinHeight() || pos.y() >= world.getMaxHeight()) continue;
            var state = palette.computeIfAbsent(segment.stateAt(pos, localTime), Bukkit::createBlockData);
            var block = world.getBlockAt(pos.x(), pos.y(), pos.z());
            if (!block.getBlockData().equals(state)) block.setBlockData(state, false);
        }
    }

    private static Path root(JavaPlugin plugin) {
        return plugin.getServer().getWorldContainer().toPath().toAbsolutePath().normalize()
                .resolve(Bukkit.getWorlds().getFirst().getName()).resolve("dimensions/minecraft");
    }

    static void cleanup(JavaPlugin plugin) {
        Path root = root(plugin);
        try {
            Files.createDirectories(root);
            try (var folders = Files.newDirectoryStream(root, PREFIX + "*")) {
                for (Path folder : folders) if (Bukkit.getWorld(folder.getFileName().toString()) == null) deleteOwned(folder);
            }
        } catch (IOException error) { plugin.getLogger().log(Level.WARNING, "Could not clean abandoned build replay worlds.", error); }
    }

    private static void deleteOwned(Path folder) throws IOException {
        String name = folder.getFileName().toString();
        Path marker = folder.resolve(MARKER);
        if (!name.matches(PREFIX + "[a-f0-9]{32}") || !Files.isDirectory(folder, LinkOption.NOFOLLOW_LINKS)
                || !Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS) || !name.equals(Files.readString(marker))) return;
        try (var files = Files.walk(folder)) {
            for (Path file : files.sorted(Comparator.reverseOrder()).toList()) Files.delete(file);
        }
    }

    private void release(World disposable) {
        Path folder = worlds.get(disposable);
        if (folder == null || Bukkit.isTickingWorlds() || !disposable.getPlayers().isEmpty() || !Bukkit.unloadWorld(disposable, false)) return;
        worlds.remove(disposable);
        Runnable remove = () -> {
            try { deleteOwned(folder); }
            catch (IOException error) { plugin.getLogger().log(Level.WARNING, "Could not remove temporary replay world " + folder, error); }
        };
        if (plugin.isEnabled()) Bukkit.getScheduler().runTaskAsynchronously(plugin, remove); else remove.run();
    }

    @Override public void close() {
        if (closed) return;
        closed = true;
        render.cancel();
        HandlerList.unregisterAll(this);
        try {
            withdrawActor();
        } finally {
            Set.copyOf(worlds.keySet()).forEach(this::release);
            if (!worlds.isEmpty() && plugin.isEnabled()) {
                Bukkit.getScheduler().runTask(plugin, () -> Set.copyOf(worlds.keySet()).forEach(this::release));
            }
        }
    }

    private record ActorChunk(World world, int x, int z) {
        ActorChunk(Location position) { this(position.getWorld(), position.getBlockX() >> 4, position.getBlockZ() >> 4); }
        void retain(JavaPlugin plugin) { world.addPluginChunkTicket(x, z, plugin); }
        void release(JavaPlugin plugin) { world.removePluginChunkTicket(x, z, plugin); }
    }
}
