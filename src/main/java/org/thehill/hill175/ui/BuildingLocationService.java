package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.world.WorldUnloadEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.world.BuildingCatalog.Building;

import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.Function;
import java.util.function.Predicate;

/** Transient location captions using Minecraft's native actionbar. */
public final class BuildingLocationService implements Listener, AutoCloseable {
    private static final double enterDistance = 18.0;
    private static final double exitDistance = 24.0;
    private static final double switchAdvantage = 4.0;
    private final JavaPlugin plugin;
    private final Function<World, List<Building>> catalog;
    private final Predicate<World> campusWorld;
    private final Predicate<Player> captionEligible;
    private final Map<UUID, CaptionState> captions = new HashMap<>();
    private final Map<UUID, List<Building>> catalogs = new HashMap<>();
    private BukkitTask task;

    public BuildingLocationService(JavaPlugin plugin, Function<World, List<Building>> catalog,
                                   Predicate<World> campusWorld, Predicate<Player> captionEligible) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.catalog = Objects.requireNonNull(catalog, "catalog");
        this.campusWorld = Objects.requireNonNull(campusWorld, "campusWorld");
        this.captionEligible = Objects.requireNonNull(captionEligible, "captionEligible");
    }

    public void start() {
        if (task != null) return;
        task = plugin.getServer().getScheduler().runTaskTimer(plugin,
                () -> plugin.getServer().getOnlinePlayers().forEach(this::refresh), 1L, 10L);
    }

    public void refresh(Player player) {
        if (!player.isOnline()) { forget(player.getUniqueId()); return; }
        CaptionState previous = captions.get(player.getUniqueId());
        World world = player.getWorld();
        if (!captionEligible.test(player) || world == null || !campusWorld.test(world)) {
            clear(player, previous);
            return;
        }
        List<Building> buildings = catalogs.computeIfAbsent(world.getUID(), ignored -> List.copyOf(catalog.apply(world)));
        Building current = previous != null && previous.worldId().equals(world.getUID()) ? previous.building() : null;
        Building selected = nearest(buildings, player.getLocation(), current);
        CaptionState next = selected == null ? null : new CaptionState(world.getUID(), selected);
        if (Objects.equals(previous, next)) return;
        if (next == null) { clear(player, previous); return; }
        player.sendActionBar(Component.text(selected.name(), NamedTextColor.GOLD));
        captions.put(player.getUniqueId(), next);
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onJoin(PlayerJoinEvent event) { forget(event.getPlayer().getUniqueId()); }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onQuit(PlayerQuitEvent event) { forget(event.getPlayer().getUniqueId()); }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onWorldChange(PlayerChangedWorldEvent event) { clear(event.getPlayer(), captions.get(event.getPlayer().getUniqueId())); }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onWorldUnload(WorldUnloadEvent event) {
        UUID worldId = event.getWorld().getUID();
        catalogs.remove(worldId);
        captions.values().removeIf(state -> state.worldId().equals(worldId));
    }

    public void forget(UUID playerId) { captions.remove(playerId); }

    /** Refresh metadata after an explicitly selected campus is replaced. */
    public void invalidateCatalog(World world) { if (world != null) catalogs.remove(world.getUID()); }

    private void clear(Player player, CaptionState previous) {
        captions.remove(player.getUniqueId());
        // Auth and camera hints take priority. Do not erase them when eligibility is withdrawn.
        if (previous != null && player.isOnline() && captionEligible.test(player)) player.sendActionBar(Component.empty());
    }

    static Building nearest(List<Building> buildings, Location position, Building current) {
        Building candidate = buildings.stream()
                .filter(building -> distance(building, position) <= enterDistance)
                .min(Comparator.comparingDouble((Building building) -> distance(building, position))
                        .thenComparingInt(Building::mapNumber).thenComparing(Building::id)).orElse(null);
        if (current == null || !buildings.contains(current) || distance(current, position) > exitDistance) return candidate;
        if (candidate == null || candidate.equals(current)) return current;
        return distance(candidate, position) + switchAdvantage < distance(current, position) ? candidate : current;
    }

    static double distance(Building building, Location position) {
        double dx = Math.max(Math.max(building.minX() - position.getX(), 0), position.getX() - (building.maxX() + 1.0));
        double dz = Math.max(Math.max(building.minZ() - position.getZ(), 0), position.getZ() - (building.maxZ() + 1.0));
        return Math.hypot(dx, dz);
    }

    @Override
    public void close() {
        if (task != null) { task.cancel(); task = null; }
        plugin.getServer().getOnlinePlayers().forEach(player -> clear(player, captions.get(player.getUniqueId())));
        captions.clear();
        catalogs.clear();
    }

    private record CaptionState(UUID worldId, Building building) { }
}
