package org.thehill.hill175.blueprint;

import io.papermc.paper.event.packet.PlayerChunkLoadEvent;
import io.papermc.paper.math.Position;
import org.bukkit.Bukkit;
import org.bukkit.Chunk;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.BlockState;
import org.bukkit.block.TileState;
import org.bukkit.block.data.BlockData;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockDamageAbortEvent;
import org.bukkit.event.block.BlockDamageEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.player.PlayerTeleportEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.competition.CompetitionModule;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Shows a request's proposed blocks on the shared blueprint to one reviewer only, with green boxes around
 * its areas and pink boxes where the blueprint changed after the student's snapshot. Real blocks change
 * only when the request is accepted.
 */
public final class BlueprintReview implements Listener, AutoCloseable {
    private static final Duration LIFETIME = Duration.ofMinutes(30);
    private final JavaPlugin plugin;
    private final BlueprintService service;
    private final CompetitionModule competition;
    private final BlueprintOutlines outlines;
    private final Map<UUID, Session> sessions = new HashMap<>();
    private BukkitTask timer;
    private boolean closed;

    /** What the reviewer is looking at, for hotbar and action-bar text. */
    public record Shown(UUID request, String title, String author, int blocks, int areas, long conflicts) { }

    public BlueprintReview(JavaPlugin plugin, BlueprintService service, CompetitionModule competition, BlueprintOutlines outlines) {
        this.plugin = plugin;
        this.service = service;
        this.competition = competition;
        this.outlines = outlines;
    }

    public void start() {
        timer = Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 10L, 10L);
    }

    /** Moves the reviewer next to the request on the blueprint and shows its proposed blocks. */
    public Shown show(Player player, UUID proposalId) throws IOException {
        requireAccess(player);
        if (sessions.size() >= 8 && !sessions.containsKey(player.getUniqueId())) {
            throw new IllegalStateException("Eight reviews are already open. Try again in a moment.");
        }
        BlueprintRepository.Submission submission = service.repository().read(proposalId);
        if (submission.status() != BlueprintRepository.Status.PENDING) throw new IllegalStateException("That request was already decided.");
        World world = service.acceptedWorld();
        BlueprintMerge.Plan plan = BlueprintMerge.plan(submission.changes(), new BukkitBlueprintBlocks(world));
        Set<BlockPosition> conflicts = new HashSet<>();
        for (BlueprintMerge.Conflict conflict : plan.conflicts()) conflicts.add(conflict.position());
        List<PreviewBlock> blocks = new ArrayList<>();
        for (BlockChange change : submission.changes()) blocks.add(new PreviewBlock(change, conflicts.contains(change.position())));
        Session session = new Session(player, competition.participantKey(player), submission, world, blocks);
        end(player);
        sessions.put(player.getUniqueId(), session);
        if (!focus(player, session)) {
            end(player);
            throw new IllegalStateException("The review could not open. Try again.");
        }
        return new Shown(submission.id(), submission.title(), competition.displayName(submission.author()), blocks.size(), session.areas.size(), session.conflicts);
    }

    private boolean focus(Player player, Session session) {
        ChangeAreas.Area area = session.areas.getFirst();
        double centerX = (area.minX() + area.maxX() + 1) / 2.0;
        double centerY = (area.minY() + area.maxY() + 1) / 2.0;
        double centerZ = (area.minZ() + area.maxZ() + 1) / 2.0;
        double reach = Math.max(area.maxX() - area.minX(), Math.max(area.maxY() - area.minY(), area.maxZ() - area.minZ())) / 2.0;
        Location destination = new Location(session.world, centerX + 6 + reach * 0.6, Math.min(session.world.getMaxHeight() - 2, centerY + 6 + reach * 0.6),
                centerZ + 8 + reach * 0.8);
        destination.setDirection(new org.bukkit.util.Vector(centerX, centerY, centerZ).subtract(destination.toVector()));
        if (!competition.teleportReadOnly(player, session.world, destination)
                || !player.getWorld().equals(session.world) || sessions.get(player.getUniqueId()) != session) return false;
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (!valid(player, session)) return;
            render(player, session, block -> true);
            drawBoxes(player, session);
        }, 2L);
        return true;
    }

    private void drawBoxes(Player player, Session session) {
        List<BlueprintOutlines.Box> boxes = new ArrayList<>();
        session.blocks.stream().filter(block -> block.conflict).limit(24)
                .forEach(block -> boxes.add(BlueprintOutlines.Box.block(block.change.position(), BlueprintOutlines.Tone.CONFLICT)));
        for (ChangeAreas.Area area : session.areas) {
            boolean conflict = area.positions().stream().anyMatch(session.conflictPositions::contains);
            boxes.add(BlueprintOutlines.Box.around(area, conflict ? BlueprintOutlines.Tone.CONFLICT : BlueprintOutlines.Tone.CHANGE));
        }
        outlines.show(player, session.world, boxes, LIFETIME);
    }

    private void render(Player player, Session session, java.util.function.Predicate<PreviewBlock> selected) {
        if (!valid(player, session)) return;
        try {
            Map<Position, BlockData> changes = new HashMap<>();
            List<PreviewBlock> visible = session.blocks.stream().filter(selected).filter(block -> player.isChunkSent(block.chunk)
                    && session.world.isChunkLoaded(block.change.position().blockX() >> 4, block.change.position().blockZ() >> 4)).toList();
            for (PreviewBlock block : visible) {
                BlockPosition position = block.change.position();
                changes.put(Position.block(position.blockX(), position.blockY(), position.blockZ()), block.after);
            }
            if (!changes.isEmpty()) player.sendMultiBlockChange(changes);
            for (PreviewBlock block : visible) {
                Location position = location(session.world, block.change.position());
                if (block.proposedState() instanceof TileState tile) player.sendBlockUpdate(position, (TileState) tile.copy(position));
            }
        } catch (Exception exception) {
            plugin.getLogger().log(java.util.logging.Level.WARNING, "Could not display a private blueprint preview.", exception);
            end(player);
            player.sendMessage("The preview could not be displayed. No blueprint blocks were changed.");
        }
    }

    private void tick() {
        for (Session session : List.copyOf(sessions.values())) {
            Player player = session.player;
            if (!valid(player, session)) { end(player); continue; }
            if (!outlines.showing(player)) drawBoxes(player, session);
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onChunk(PlayerChunkLoadEvent event) {
        Session session = sessions.get(event.getPlayer().getUniqueId());
        if (session == null || !event.getWorld().equals(session.world)) return;
        long chunk = event.getChunk().getChunkKey();
        Bukkit.getScheduler().runTask(plugin, () -> render(event.getPlayer(), session, block -> block.chunk == chunk));
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onInteract(PlayerInteractEvent event) {
        if (event.getClickedBlock() != null) repairAfterInteraction(event.getPlayer(), event.getClickedBlock());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onDamage(BlockDamageEvent event) { repairAfterInteraction(event.getPlayer(), event.getBlock()); }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onAbortDamage(BlockDamageAbortEvent event) { repairAfterInteraction(event.getPlayer(), event.getBlock()); }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onBreak(BlockBreakEvent event) { repairAfterInteraction(event.getPlayer(), event.getBlock()); }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPlace(BlockPlaceEvent event) { repairAfterInteraction(event.getPlayer(), event.getBlock()); }

    /** Vanilla resends real blocks after a click; put the preview back on the next tick. */
    private void repairAfterInteraction(Player player, org.bukkit.block.Block block) {
        Session session = sessions.get(player.getUniqueId());
        if (session == null || !block.getWorld().equals(session.world) || !valid(player, session)) return;
        session.corrections.add(new BlockPosition(block.getX(), block.getY(), block.getZ()));
        for (org.bukkit.block.BlockFace face : List.of(org.bukkit.block.BlockFace.NORTH, org.bukkit.block.BlockFace.SOUTH,
                org.bukkit.block.BlockFace.EAST, org.bukkit.block.BlockFace.WEST, org.bukkit.block.BlockFace.UP, org.bukkit.block.BlockFace.DOWN)) {
            var adjacent = block.getRelative(face);
            session.corrections.add(new BlockPosition(adjacent.getX(), adjacent.getY(), adjacent.getZ()));
        }
        if (session.repairQueued) return;
        session.repairQueued = true;
        Bukkit.getScheduler().runTask(plugin, () -> {
            session.repairQueued = false;
            Set<BlockPosition> affected = Set.copyOf(session.corrections);
            session.corrections.clear();
            render(player, session, changed -> affected.contains(changed.change.position()));
        });
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onTeleport(PlayerTeleportEvent event) {
        Session session = sessions.get(event.getPlayer().getUniqueId());
        if (session != null && event.getTo() != null && !event.getTo().getWorld().equals(session.world)) end(event.getPlayer());
    }

    @EventHandler public void onQuit(PlayerQuitEvent event) { end(event.getPlayer()); }

    public boolean reviewing(Player player, UUID proposalId) {
        Session session = sessions.get(player.getUniqueId());
        return session != null && session.submission.id().equals(proposalId) && valid(player, session);
    }

    public void proposalDecided(UUID proposalId) {
        for (Session session : List.copyOf(sessions.values())) if (session.submission.id().equals(proposalId)) end(session.player);
    }

    public void clearAll() {
        for (Session session : List.copyOf(sessions.values())) end(session.player);
    }

    /** Removes the preview and sends the real blocks back to the reviewer. */
    public void end(Player player) {
        Session session = sessions.remove(player.getUniqueId());
        if (session == null) return;
        outlines.clear(player);
        if (!player.isOnline() || !player.getWorld().equals(session.world)) return;
        try {
            Map<Position, BlockData> restored = new HashMap<>();
            List<TileState> tiles = new ArrayList<>();
            for (PreviewBlock block : session.blocks) {
                BlockPosition position = block.change.position();
                if (!player.isChunkSent(block.chunk) || !session.world.isChunkLoaded(position.blockX() >> 4, position.blockZ() >> 4)) continue;
                BlockState actual = location(session.world, position).getBlock().getState();
                restored.put(Position.block(position.blockX(), position.blockY(), position.blockZ()), actual.getBlockData());
                if (actual instanceof TileState tile) tiles.add(tile);
            }
            if (!restored.isEmpty()) player.sendMultiBlockChange(restored);
            for (TileState tile : tiles) player.sendBlockUpdate(tile.getLocation(), tile);
        } catch (RuntimeException exception) {
            plugin.getLogger().log(java.util.logging.Level.WARNING, "Could not clear a blueprint preview; reconnecting refreshes the view.", exception);
            player.sendMessage("Please reconnect to refresh your blueprint view.");
        }
    }

    private void requireAccess(Player player) {
        if (closed) throw new IllegalStateException("Review is closed.");
        service.requireReviewer(player);
        service.acceptedWorld();
    }

    private boolean valid(Player player, Session session) {
        try {
            requireAccess(player);
            return player.isOnline() && Bukkit.getPlayer(player.getUniqueId()) == player && sessions.get(player.getUniqueId()) == session
                    && competition.participantKey(player).equals(session.identity) && session.expires.isAfter(Instant.now())
                    && player.getWorld().equals(session.world)
                    && service.repository().summaries().stream().anyMatch(summary -> summary.id().equals(session.submission.id())
                    && summary.status() == BlueprintRepository.Status.PENDING);
        } catch (IOException | RuntimeException exception) { return false; }
    }

    private static Location location(World world, BlockPosition position) { return new Location(world, position.blockX(), position.blockY(), position.blockZ()); }

    @Override public void close() {
        if (timer != null) timer.cancel();
        clearAll();
        closed = true;
        HandlerList.unregisterAll(this);
    }

    private static final class Session {
        final Player player;
        final String identity;
        final BlueprintRepository.Submission submission;
        final World world;
        final List<PreviewBlock> blocks;
        final List<ChangeAreas.Area> areas;
        final Set<BlockPosition> conflictPositions = new HashSet<>();
        final Instant expires = Instant.now().plus(LIFETIME);
        final long conflicts;
        final Set<BlockPosition> corrections = new HashSet<>();
        boolean repairQueued;

        Session(Player player, String identity, BlueprintRepository.Submission submission, World world, List<PreviewBlock> blocks) {
            this.player = player;
            this.identity = identity;
            this.submission = submission;
            this.world = world;
            this.blocks = List.copyOf(blocks);
            for (PreviewBlock block : blocks) if (block.conflict) conflictPositions.add(block.change.position());
            conflicts = conflictPositions.size();
            areas = ChangeAreas.of(blocks.stream().map(block -> block.change.position()).toList());
        }
    }

    private static final class PreviewBlock {
        final BlockChange change;
        final boolean conflict;
        final BlockData after;
        final long chunk;
        private BlockState afterState;
        private boolean loaded;

        PreviewBlock(BlockChange change, boolean conflict) {
            this.change = change;
            this.conflict = conflict;
            after = Bukkit.createBlockData(change.after().blockData());
            chunk = Chunk.getChunkKey(change.position().blockX() >> 4, change.position().blockZ() >> 4);
        }

        BlockState proposedState() throws IOException {
            if (loaded) return afterState;
            loaded = true;
            byte[] bytes = change.after().structure();
            if (bytes.length == 0) return null;
            var structure = Bukkit.getStructureManager().loadStructure(new ByteArrayInputStream(bytes));
            if (structure.getEntityCount() != 0 || structure.getPaletteCount() != 1 || structure.getPalettes().getFirst().getBlockCount() != 1) {
                throw new IOException("Invalid one-block review snapshot.");
            }
            afterState = structure.getPalettes().getFirst().getBlocks().getFirst();
            return afterState;
        }
    }
}
