package org.thehill.hill175.ui;

import io.papermc.paper.dialog.Dialog;
import io.papermc.paper.registry.data.dialog.ActionButton;
import io.papermc.paper.registry.data.dialog.DialogBase;
import io.papermc.paper.registry.data.dialog.action.DialogAction;
import io.papermc.paper.registry.data.dialog.body.DialogBody;
import io.papermc.paper.registry.data.dialog.type.DialogType;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickCallback;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryOpenEvent;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.player.PlayerResourcePackStatusEvent;
import org.bukkit.event.player.PlayerTeleportEvent;
import org.bukkit.inventory.ItemStack;
import org.bukkit.plugin.IllegalPluginAccessException;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.world.BuildingCatalog;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import java.util.function.Predicate;

/** Native dialogs show clickable map numbers with named destination buttons as a fallback. */
public final class CampusMapMenu implements Listener, AutoCloseable {
    static final int pageSize = 12;
    static final Duration sessionLifetime = Duration.ofMinutes(5);
    private final JavaPlugin plugin;
    private List<CampusMapLabels.Destination> destinations;
    private CampusMapLabels labels;
    private final CampusMapPack pack;
    private final BedrockForms bedrock;
    private final Predicate<Player> canUse;
    private final BiConsumer<Player, Selection> onSelect;
    private final Map<UUID, Session> sessions = new HashMap<>();
    private final Set<UUID> offeredPack = new HashSet<>();
    private final Set<UUID> loadedPack = new HashSet<>();
    private Consumer<Player> undoAction;
    private volatile boolean isClosed;

    public CampusMapMenu(JavaPlugin plugin, String revision, BuildRegion campusBounds,
                         List<BuildingCatalog.Building> buildings, CampusMapPack pack,
                         Predicate<Player> canUse, BiConsumer<Player, Selection> onSelect,
                         Consumer<Player> onBack) {
        this.plugin = Objects.requireNonNull(plugin);
        Objects.requireNonNull(revision);
        Objects.requireNonNull(campusBounds);
        // Kept for constructor compatibility. Close now returns directly to gameplay.
        Objects.requireNonNull(onBack);
        this.destinations = buildings.stream().sorted(Comparator.comparingInt(BuildingCatalog.Building::mapNumber)
                .thenComparing(BuildingCatalog.Building::name)).map(CampusMapLabels.Destination::fromBuilding).toList();
        this.pack = pack;
        this.bedrock = new BedrockForms(plugin);
        this.canUse = Objects.requireNonNull(canUse);
        this.onSelect = Objects.requireNonNull(onSelect);
    }

    public void undoAction(Consumer<Player> action) { undoAction = Objects.requireNonNull(action); }
    public void labels(CampusMapLabels value) {
        labels = Objects.requireNonNull(value);
        destinations = value.destinations();
    }

    public void open(Player player) {
        if (!isAvailable(player)) return;
        if (undoAction == null) throw new IllegalStateException("Configure the campus undo action before opening the map.");
        player.closeInventory();
        openMap(player, false);
        if (!bedrock.isBedrock(player) && pack != null && offeredPack.add(player.getUniqueId())) pack.offer(player);
    }

    private void openMap(Player player, boolean isZoomed) {
        if (!isAvailable(player)) return;
        Session session = begin(player, isZoomed ? View.core : View.main, 0);
        var choices = new ArrayList<Choice>();
        choices.add(new Choice("Buildings", next -> openBuildings(next, 0)));
        if (!bedrock.isBedrock(player)) {
            choices.add(new Choice(isZoomed ? "Whole Campus" : "Zoom Buildings", next -> openMap(next, !isZoomed)));
        }
        choices.add(new Choice("Undo Last 15 Seconds", next -> undoAction.accept(next)));
        addPackChoice(player, choices, isZoomed);
        show(player, session, isZoomed ? "Campus Buildings" : "Hill Campus Map", mapBody(player, session, isZoomed),
                "Choose Buildings, then a numbered destination. Everyone builds together in the shared campus.", choices);
    }

    private List<DialogBody> mapBody(Player player, Session session, boolean isZoomed) {
        var body = new ArrayList<DialogBody>();
        boolean hasArtwork = loadedPack.contains(player.getUniqueId());
        boolean hasLabels = hasArtwork && labels != null && pack != null && labels.matchesPack(pack.sha1Hex());
        if (hasLabels) body.add(labelArtwork(session, isZoomed));
        else if (hasArtwork) body.add(mapArtwork(isZoomed));
        body.add(message(hasLabels ? "Click a map number to go there." : hasArtwork ? "Choose Buildings to go to a numbered destination."
                : "Choose Buildings to go to a numbered destination. Optional map artwork is not loaded."));
        return body;
    }

    private DialogBody labelArtwork(Session session, boolean isZoomed) {
        Component image = labels.render(isZoomed ? "core" : "full", destination -> {
            var action = callback(session, player -> selectDestination(player, destination));
            return ClickEvent.custom(action.id(), action.additions());
        });
        return DialogBody.plainMessage(image, CampusMapLabels.dialogBodyWidth);
    }

    private DialogBody mapArtwork(boolean isZoomed) {
        ItemStack image = new ItemStack(Material.PAPER);
        var meta = image.getItemMeta();
        meta.displayName(Component.empty().decoration(TextDecoration.ITALIC, false));
        meta.setItemModel(new NamespacedKey("hill175", "campus/official_" + (isZoomed ? "core" : "full")));
        image.setItemMeta(meta);
        return DialogBody.item(image).width(256).height(256).showDecorations(false).showTooltip(false).build();
    }

    private void addPackChoice(Player player, List<Choice> choices, boolean isZoomed) {
        if (pack == null || bedrock.isBedrock(player) || loadedPack.contains(player.getUniqueId())) return;
        choices.add(new Choice("Load School Map", next -> {
            openMap(next, isZoomed);
            offeredPack.add(next.getUniqueId());
            pack.offer(next);
        }));
    }

    private void openBuildings(Player player, int page) {
        if (!isAvailable(player)) return;
        int lastPage = Math.max(0, (destinations.size() - 1) / pageSize);
        int currentPage = Math.clamp(page, 0, lastPage);
        Session session = begin(player, View.buildings, currentPage);
        var choices = new ArrayList<Choice>();
        for (var destination : destinations.subList(currentPage * pageSize, Math.min((currentPage + 1) * pageSize, destinations.size()))) {
            choices.add(new Choice(destination.menuLabel(), destination.tooltip(), next -> selectDestination(next, destination)));
        }
        if (currentPage > 0) choices.add(new Choice("Previous Buildings", next -> openBuildings(next, currentPage - 1)));
        if (currentPage < lastPage) choices.add(new Choice("More Buildings", next -> openBuildings(next, currentPage + 1)));
        choices.add(new Choice("Back to Map", next -> openMap(next, false)));
        String instructions = "Choose a building number from the school map. Page " + (currentPage + 1) + " of " + (lastPage + 1) + ".";
        show(player, session, "Choose a Building", List.of(message(instructions)), instructions, choices);
    }

    private void selectDestination(Player player, CampusMapLabels.Destination destination) {
        if (!destination.available()) {
            player.sendMessage(text(destination.unavailableReason()));
            return;
        }
        onSelect.accept(player, destination.selection());
    }

    private Session begin(Player player, View view, int page) {
        Session session = new Session(player.getUniqueId(), view, page, System.nanoTime());
        sessions.put(player.getUniqueId(), session);
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (sessions.get(player.getUniqueId()) == session) invalidate(player);
        }, sessionLifetime.toSeconds() * 20);
        return session;
    }

    private void show(Player player, Session session, String title, List<DialogBody> body,
                      String bedrockText, List<Choice> choices) {
        if (bedrock.isBedrock(player)) {
            showBedrock(player, session, title, bedrockText, choices);
            return;
        }
        DialogBase base = DialogBase.builder(text(title)).canCloseWithEscape(true).pause(false)
                .afterAction(DialogBase.DialogAfterAction.WAIT_FOR_RESPONSE).body(body).build();
        List<ActionButton> buttons = choices.stream().map(choice -> button(session, choice)).toList();
        var type = DialogType.multiAction(buttons).columns(2).exitAction(button(session, closeChoice())).build();
        player.showDialog(Dialog.create(builder -> builder.empty().base(base).type(type)));
    }

    private void showBedrock(Player player, Session session, String title, String content, List<Choice> choices) {
        var options = new ArrayList<>(choices);
        options.add(closeChoice());
        boolean sent = bedrock.show(player, title, content, options.stream().map(Choice::label).toList(),
                index -> dispatch(player, session, options.get(index).action()),
                () -> dispatch(player, session, closeChoice().action()));
        if (!sent) sessions.remove(player.getUniqueId(), session);
    }

    private ActionButton button(Session session, Choice choice) {
        return ActionButton.builder(text(choice.label())).tooltip(text(choice.tooltip())).width(180)
                .action(callback(session, choice.action())).build();
    }

    private DialogAction.CustomClickAction callback(Session session, Consumer<Player> action) {
        var options = ClickCallback.Options.builder().uses(1).lifetime(sessionLifetime).build();
        return DialogAction.customClick((response, audience) -> {
            if (audience instanceof Player player) dispatch(player, session, action);
        }, options);
    }

    private Choice closeChoice() { return new Choice("Close", player -> { }); }

    private void dispatch(Player player, Session session, Consumer<Player> action) {
        if (isClosed || !plugin.isEnabled()) return;
        // A pack status can arrive before this task runs. It must not replace a dialog with a queued response.
        session.markPending(player.getUniqueId());
        try {
            Bukkit.getScheduler().runTask(plugin, () -> execute(player, session, action));
        } catch (IllegalPluginAccessException exception) {
            if (!isClosed && plugin.isEnabled()) throw exception;
        }
    }

    private void execute(Player player, Session session, Consumer<Player> action) {
        if (isClosed || !player.isOnline() || plugin.getServer().getPlayer(player.getUniqueId()) != player) return;
        if (!canUse.test(player)) {
            if (sessions.get(player.getUniqueId()) == session) invalidate(player);
            return;
        }
        if (!session.claim(player.getUniqueId(), sessions.get(player.getUniqueId()), System.nanoTime(), true)) return;
        sessions.remove(player.getUniqueId(), session);
        if (!bedrock.isBedrock(player)) player.closeDialog();
        action.accept(player);
    }

    private boolean isAvailable(Player player) { return !isClosed && player != null && player.isOnline() && canUse.test(player); }
    private static Component text(String value) { return Component.text(value, NamedTextColor.WHITE).decoration(TextDecoration.ITALIC, false); }
    private static DialogBody message(String value) { return DialogBody.plainMessage(text(value), 380); }

    @EventHandler public void onQuit(PlayerQuitEvent event) {
        UUID id = event.getPlayer().getUniqueId();
        sessions.remove(id);
        offeredPack.remove(id);
        loadedPack.remove(id);
        bedrock.clear(event.getPlayer());
    }

    private void invalidate(Player player) {
        if (sessions.remove(player.getUniqueId()) == null) return;
        if (bedrock.isBedrock(player)) bedrock.clear(player);
        else player.closeDialog();
    }

    @EventHandler public void onInventoryOpen(InventoryOpenEvent event) {
        if (event.getPlayer() instanceof Player player) invalidate(player);
    }
    @EventHandler public void onCommand(PlayerCommandPreprocessEvent event) { invalidate(event.getPlayer()); }
    @EventHandler public void onTeleport(PlayerTeleportEvent event) { invalidate(event.getPlayer()); }

    @EventHandler public void onPackStatus(PlayerResourcePackStatusEvent event) {
        Player player = event.getPlayer();
        if (pack == null || !pack.id().equals(event.getID()) || !offeredPack.contains(player.getUniqueId())) return;
        var status = event.getStatus();
        if (status == PlayerResourcePackStatusEvent.Status.ACCEPTED || status == PlayerResourcePackStatusEvent.Status.DOWNLOADED) return;
        if (status == PlayerResourcePackStatusEvent.Status.SUCCESSFULLY_LOADED) loadedPack.add(player.getUniqueId());
        else loadedPack.remove(player.getUniqueId());
        Session current = sessions.get(player.getUniqueId());
        if (current == null || !current.canRefresh(System.nanoTime()) || !isAvailable(player)) return;
        openMap(player, current.view == View.core);
    }

    @Override public void close() {
        isClosed = true;
        for (UUID owner : sessions.keySet()) {
            Player player = plugin.getServer().getPlayer(owner);
            if (player != null && !bedrock.isBedrock(player)) player.closeDialog();
        }
        sessions.clear();
        offeredPack.clear();
        loadedPack.clear();
        bedrock.close();
    }

    public record Selection(BuildingCatalog.Building building, int x, int z, boolean entireCampus) { }
    private record Choice(String label, String tooltip, Consumer<Player> action) {
        private Choice(String label, Consumer<Player> action) { this(label, label, action); }
    }
    enum View { main, core, buildings }

    static final class Session {
        final UUID owner;
        final View view;
        final int page;
        final long openedNanos;
        private boolean isConsumed;
        private volatile boolean hasPendingResponse;
        Session(UUID owner, View view, int page, long openedNanos) {
            this.owner = Objects.requireNonNull(owner);
            this.view = Objects.requireNonNull(view);
            this.page = page;
            this.openedNanos = openedNanos;
        }
        boolean isMap() { return view == View.main || view == View.core; }
        boolean canRefresh(long now) { return isMap() && !hasPendingResponse && isActive(now); }
        void markPending(UUID player) { if (owner.equals(player)) hasPendingResponse = true; }
        boolean isActive(long now) { return !isConsumed && now - openedNanos >= 0 && now - openedNanos < sessionLifetime.toNanos(); }
        boolean claim(UUID player, Session current, long now, boolean isAuthenticated) {
            if (!isAuthenticated || !owner.equals(player) || current != this || !isActive(now)) return false;
            isConsumed = true;
            return true;
        }
    }
}
