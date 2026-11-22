package org.thehill.hill175.blueprint;

import org.bukkit.Bukkit;
import org.bukkit.Color;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.Particle;
import org.bukkit.World;
import org.bukkit.entity.BlockDisplay;
import org.bukkit.entity.Display;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.bukkit.util.Transformation;
import org.joml.AxisAngle4f;
import org.joml.Vector3f;
import org.thehill.hill175.ui.BedrockForms;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Private box outlines. Java clients see glowing frames that remain visible through walls; Bedrock
 * clients, which do not render display entities, see particle edges instead. Only the viewer sees them.
 */
public final class BlueprintOutlines implements Listener, AutoCloseable {
    public static final String TAG = "hill175_blueprint_outline";
    private static final int MAXIMUM_BOXES = 64;
    private static final float THICKNESS = 0.08f;
    private static final int PARTICLE_BUDGET = 900;

    public enum Tone {
        CHANGE(Material.LIME_CONCRETE, Color.LIME),
        CONFLICT(Material.MAGENTA_CONCRETE, Color.FUCHSIA),
        UPDATE(Material.LIGHT_BLUE_CONCRETE, Color.AQUA),
        MUTED(Material.LIGHT_GRAY_CONCRETE, Color.SILVER);

        final Material material;
        final Color color;
        Tone(Material material, Color color) { this.material = material; this.color = color; }
    }

    public record Box(int minX, int minY, int minZ, int maxX, int maxY, int maxZ, Tone tone) {
        public static Box around(ChangeAreas.Area area, Tone tone) {
            return new Box(area.minX(), area.minY(), area.minZ(), area.maxX(), area.maxY(), area.maxZ(), tone);
        }
        public static Box block(BlockPosition position, Tone tone) {
            return new Box(position.blockX(), position.blockY(), position.blockZ(), position.blockX(), position.blockY(), position.blockZ(), tone);
        }
    }

    private static final class View {
        final World world;
        final List<Box> boxes;
        final List<List<BlockDisplay>> rods = new ArrayList<>();
        final long expiresAt;
        final boolean bedrock;

        View(World world, List<Box> boxes, long expiresAt, boolean bedrock) {
            this.world = world;
            this.boxes = boxes;
            this.expiresAt = expiresAt;
            this.bedrock = bedrock;
        }
    }

    private final JavaPlugin plugin;
    private final BedrockForms bedrock;
    private final Map<UUID, View> views = new HashMap<>();
    private BukkitTask task;
    private int ticks;

    public BlueprintOutlines(JavaPlugin plugin) {
        this.plugin = plugin;
        this.bedrock = new BedrockForms(plugin);
    }

    public void start() {
        Bukkit.getPluginManager().registerEvents(this, plugin);
        task = Bukkit.getScheduler().runTaskTimer(plugin, this::tick, 10L, 10L);
    }

    /** Replaces the viewer's outlines. Boxes beyond the first {@value #MAXIMUM_BOXES} are not drawn. */
    public void show(Player viewer, World world, List<Box> boxes, Duration lifetime) {
        clear(viewer);
        if (boxes.isEmpty() || !viewer.getWorld().equals(world)) return;
        View view = new View(world, List.copyOf(boxes.subList(0, Math.min(MAXIMUM_BOXES, boxes.size()))),
                System.nanoTime() + lifetime.toNanos(), bedrock.isBedrock(viewer));
        for (int index = 0; index < view.boxes.size(); index++) view.rods.add(new ArrayList<>());
        views.put(viewer.getUniqueId(), view);
        if (!view.bedrock) for (int index = 0; index < view.boxes.size(); index++) spawn(viewer, view, index);
    }

    public void clear(Player viewer) {
        View view = views.remove(viewer.getUniqueId());
        if (view != null) view.rods.forEach(rods -> rods.forEach(BlockDisplay::remove));
    }

    public boolean showing(Player viewer) { return views.containsKey(viewer.getUniqueId()); }

    private void spawn(Player viewer, View view, int index) {
        Box box = view.boxes.get(index);
        List<BlockDisplay> rods = view.rods.get(index);
        rods.forEach(BlockDisplay::remove);
        rods.clear();
        for (int cornerX : new int[]{box.minX(), box.maxX() + 1}) for (int cornerZ : new int[]{box.minZ(), box.maxZ() + 1}) {
            if (!view.world.isChunkLoaded(cornerX >> 4, cornerZ >> 4)) return;
        }
        double x0 = box.minX(), y0 = box.minY(), z0 = box.minZ();
        double x1 = box.maxX() + 1.0, y1 = box.maxY() + 1.0, z1 = box.maxZ() + 1.0;
        for (double y : new double[]{y0, y1}) for (double z : new double[]{z0, z1}) rods.add(rod(viewer, view.world, box.tone(), x0, y, z, x1 - x0, 0, 0));
        for (double x : new double[]{x0, x1}) for (double z : new double[]{z0, z1}) rods.add(rod(viewer, view.world, box.tone(), x, y0, z, 0, y1 - y0, 0));
        for (double x : new double[]{x0, x1}) for (double y : new double[]{y0, y1}) rods.add(rod(viewer, view.world, box.tone(), x, y, z0, 0, 0, z1 - z0));
    }

    private BlockDisplay rod(Player viewer, World world, Tone tone, double x, double y, double z, double lengthX, double lengthY, double lengthZ) {
        float half = THICKNESS / 2;
        Location origin = new Location(world, x - half, y - half, z - half);
        BlockDisplay display = world.spawn(origin, BlockDisplay.class, created -> {
            created.setVisibleByDefault(false);
            created.setPersistent(false);
            created.addScoreboardTag(TAG);
            created.setBlock(tone.material.createBlockData());
            created.setTransformation(new Transformation(new Vector3f(), new AxisAngle4f(),
                    new Vector3f((float) lengthX + THICKNESS, (float) lengthY + THICKNESS, (float) lengthZ + THICKNESS), new AxisAngle4f()));
            created.setGlowing(true);
            created.setGlowColorOverride(tone.color);
            created.setBrightness(new Display.Brightness(15, 15));
            created.setViewRange(4.0f);
        });
        viewer.showEntity(plugin, display);
        return display;
    }

    private void tick() {
        ticks++;
        long now = System.nanoTime();
        for (Map.Entry<UUID, View> entry : List.copyOf(views.entrySet())) {
            Player viewer = Bukkit.getPlayer(entry.getKey());
            View view = entry.getValue();
            if (viewer == null || !viewer.isOnline() || !viewer.getWorld().equals(view.world) || now - view.expiresAt > 0) {
                if (viewer != null) clear(viewer);
                else { views.remove(entry.getKey()); view.rods.forEach(rods -> rods.forEach(BlockDisplay::remove)); }
                continue;
            }
            if (view.bedrock) particles(viewer, view);
            else if (ticks % 4 == 0) {
                for (int index = 0; index < view.boxes.size(); index++) {
                    if (view.rods.get(index).isEmpty() || view.rods.get(index).stream().anyMatch(rod -> !rod.isValid())) spawn(viewer, view, index);
                }
            }
        }
    }

    private void particles(Player viewer, View view) {
        Location eye = viewer.getEyeLocation();
        int budget = PARTICLE_BUDGET;
        for (Box box : view.boxes) {
            double centerX = (box.minX() + box.maxX() + 1) / 2.0, centerY = (box.minY() + box.maxY() + 1) / 2.0, centerZ = (box.minZ() + box.maxZ() + 1) / 2.0;
            double radius = Math.max(box.maxX() - box.minX(), Math.max(box.maxY() - box.minY(), box.maxZ() - box.minZ())) + 48;
            if (eye.distanceSquared(new Location(view.world, centerX, centerY, centerZ)) > radius * radius) continue;
            budget = edges(viewer, box, budget);
            if (budget <= 0) return;
        }
    }

    /** Draws a box once with particles, visible only to the viewer; used for boxes that follow the player. */
    public void sketch(Player viewer, Box box) { edges(viewer, box, PARTICLE_BUDGET); }

    private static int edges(Player viewer, Box box, int budget) {
        Particle.DustOptions dust = new Particle.DustOptions(box.tone().color, 1.0f);
        double x0 = box.minX(), y0 = box.minY(), z0 = box.minZ(), x1 = box.maxX() + 1.0, y1 = box.maxY() + 1.0, z1 = box.maxZ() + 1.0;
        double[][] edges = {
                {x0, y0, z0, x1, y0, z0}, {x0, y1, z0, x1, y1, z0}, {x0, y0, z1, x1, y0, z1}, {x0, y1, z1, x1, y1, z1},
                {x0, y0, z0, x0, y1, z0}, {x1, y0, z0, x1, y1, z0}, {x0, y0, z1, x0, y1, z1}, {x1, y0, z1, x1, y1, z1},
                {x0, y0, z0, x0, y0, z1}, {x1, y0, z0, x1, y0, z1}, {x0, y1, z0, x0, y1, z1}, {x1, y1, z0, x1, y1, z1}};
        for (double[] edge : edges) {
            double length = Math.max(Math.abs(edge[3] - edge[0]), Math.max(Math.abs(edge[4] - edge[1]), Math.abs(edge[5] - edge[2])));
            int steps = (int) Math.min(48, Math.max(1, Math.ceil(length / 0.75)));
            for (int step = 0; step <= steps && budget > 0; step++, budget--) {
                double fraction = (double) step / steps;
                viewer.spawnParticle(Particle.DUST, edge[0] + (edge[3] - edge[0]) * fraction, edge[1] + (edge[4] - edge[1]) * fraction,
                        edge[2] + (edge[5] - edge[2]) * fraction, 1, 0, 0, 0, 0, dust);
            }
        }
        return budget;
    }

    @EventHandler public void onQuit(PlayerQuitEvent event) { clear(event.getPlayer()); }
    @EventHandler public void onWorldChange(PlayerChangedWorldEvent event) { clear(event.getPlayer()); }

    @Override
    public void close() {
        if (task != null) task.cancel();
        for (View view : views.values()) view.rods.forEach(rods -> rods.forEach(BlockDisplay::remove));
        views.clear();
        bedrock.close();
        HandlerList.unregisterAll(this);
    }
}
