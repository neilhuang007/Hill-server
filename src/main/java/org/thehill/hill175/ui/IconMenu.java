package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Material;
import org.bukkit.OfflinePlayer;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.ClickType;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.InventoryHolder;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.inventory.meta.SkullMeta;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.function.Predicate;

/**
 * Hypixel-style chest menus: a six-row chest filled with black glass, green item names with short gray
 * descriptions and a yellow "Click to ...!" line, Go Back and Close in the bottom row, and a small
 * "Are you sure?" chest for confirmations. Bedrock players get the same choices as a form.
 */
public final class IconMenu implements Listener, AutoCloseable {
    private static final int SIZE = 54;
    private static final int HEADER = 4;
    private static final int PREVIOUS = 45;
    private static final int BACK = 48;
    private static final int CLOSE = 49;
    private static final int NEXT = 53;
    private static final int[][] SPACED = {{}, {22}, {21, 23}, {20, 22, 24}, {19, 21, 23, 25}};
    private static final int[] GRID = {10, 11, 12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 24, 25, 28, 29, 30, 31, 32, 33, 34, 37, 38, 39, 40, 41, 42, 43};
    public static final int PAGE_SIZE = GRID.length;
    private static final int WRAP = 30;

    /** One menu item. Use the {@code with...} methods to change its colour, click line or player head. */
    public record Icon(Material material, String label, NamedTextColor color, List<String> lore, String click, Runnable action, OfflinePlayer head) {
        public Icon(Material material, String label, String description, Runnable action) {
            this(material, label, NamedTextColor.GREEN, wrap(description), "Click to open!", action, null);
        }
        public Icon withClick(String text) { return new Icon(material, label, color, lore, text, action, head); }
        public Icon withColor(NamedTextColor value) { return new Icon(material, label, value, lore, click, action, head); }
        public Icon withHead(OfflinePlayer player) { return new Icon(material, label, color, lore, click, action, player); }
        public Icon withLore(List<String> lines) { return new Icon(material, label, color, List.copyOf(lines), click, action, head); }
    }

    /** A page being built: an optional header, its icons, and optional Go Back and page arrows. */
    public final class Screen {
        private final String title;
        private final List<Icon> icons = new ArrayList<>();
        private Icon header;
        private String backTo;
        private Runnable back;
        private Runnable previous;
        private Runnable next;

        private Screen(String title) { this.title = title; }
        public Screen header(Icon icon) { header = icon; return this; }
        public Screen add(Icon icon) { icons.add(icon); return this; }
        public Screen addAll(List<Icon> values) { icons.addAll(values); return this; }
        public Screen back(String to, Runnable action) { backTo = to; back = action; return this; }
        public Screen pages(Runnable previousPage, Runnable nextPage) { previous = previousPage; next = nextPage; return this; }
        public void show(Player player) { render(player, this); }
    }

    private final JavaPlugin plugin;
    private final BedrockForms forms;
    private final Predicate<Player> allowed;
    private final Function<Player, String> identity;
    private final Map<UUID, Page> open = new HashMap<>();

    IconMenu(JavaPlugin plugin, BedrockForms forms, Predicate<Player> allowed, Function<Player, String> identity) {
        this.plugin = plugin;
        this.forms = forms;
        this.allowed = allowed;
        this.identity = identity;
        plugin.getServer().getPluginManager().registerEvents(this, plugin);
    }

    public Screen screen(String title) { return new Screen(title); }

    /** A three-row "Are you sure?" chest with green Confirm and red Cancel. */
    public void confirm(Player player, String title, String question, String confirmLabel, Runnable yes, Runnable no) {
        Icon confirm = new Icon(Material.GREEN_TERRACOTTA, confirmLabel, question, yes).withClick("Click to confirm!");
        Icon cancel = new Icon(Material.RED_TERRACOTTA, "Cancel", "Go back without changing anything.", no)
                .withColor(NamedTextColor.RED).withClick("Click to cancel!");
        Page page = new Page(identity.apply(player));
        if (bedrock(player, page, title, question, List.of(confirm, cancel))) return;
        Inventory inventory = open(player, page, 27, title);
        place(page, 11, confirm);
        place(page, 15, cancel);
        player.openInventory(inventory);
        open.put(player.getUniqueId(), page);
    }

    private void render(Player player, Screen screen) {
        if (screen.icons.size() > PAGE_SIZE) throw new IllegalArgumentException("A page holds at most " + PAGE_SIZE + " items.");
        Icon previous = screen.previous == null ? null : new Icon(Material.ARROW, "Previous Page", "", screen.previous).withClick("Click to turn the page!");
        Icon next = screen.next == null ? null : new Icon(Material.ARROW, "Next Page", "", screen.next).withClick("Click to turn the page!");
        Icon back = screen.back == null ? null : new Icon(Material.ARROW, "Go Back", "To " + screen.backTo, screen.back).withClick("Click to go back!");
        Page page = new Page(identity.apply(player));
        List<Icon> choices = new ArrayList<>(screen.icons);
        for (Icon extra : new Icon[]{previous, next, back}) if (extra != null) choices.add(extra);
        if (bedrock(player, page, screen.title, screen.header == null ? "Choose an option." : String.join("\n", screen.header.lore()), choices)) return;
        Inventory inventory = open(player, page, SIZE, screen.title);
        int count = screen.icons.size();
        int[] slots = count <= 4 ? SPACED[count] : count <= 7 ? centred(count) : GRID;
        for (int index = 0; index < count; index++) place(page, slots[index], screen.icons.get(index));
        if (screen.header != null) place(page, HEADER, screen.header);
        if (previous != null) place(page, PREVIOUS, previous);
        if (back != null) place(page, BACK, back);
        if (next != null) place(page, NEXT, next);
        place(page, CLOSE, new Icon(Material.BARRIER, "Close", "", player::closeInventory).withColor(NamedTextColor.RED).withClick(null));
        player.openInventory(inventory);
        open.put(player.getUniqueId(), page);
    }

    private boolean bedrock(Player player, Page page, String title, String content, List<Icon> choices) {
        if (!forms.isBedrock(player)) return false;
        player.closeInventory();
        open.put(player.getUniqueId(), page);
        if (forms.show(player, title, content, choices.stream().map(Icon::label).toList(),
                index -> run(player, page, choices.get(index).action()), () -> open.remove(player.getUniqueId(), page))) return true;
        open.remove(player.getUniqueId(), page);
        return false;
    }

    private Inventory open(Player player, Page page, int size, String title) {
        Inventory inventory = plugin.getServer().createInventory(page, size, Component.text(title));
        page.inventory = inventory;
        ItemStack filler = item(new Icon(Material.BLACK_STAINED_GLASS_PANE, " ", "", null).withClick(null));
        for (int slot = 0; slot < size; slot++) inventory.setItem(slot, filler);
        return inventory;
    }

    private void place(Page page, int slot, Icon icon) {
        page.inventory.setItem(slot, item(icon));
        if (icon.action() != null) page.actions.put(slot, icon.action());
    }

    private static int[] centred(int count) {
        int[] slots = new int[count];
        int first = 18 + (9 - count) / 2;
        for (int index = 0; index < count; index++) slots[index] = first + index;
        return slots;
    }

    private static ItemStack item(Icon icon) {
        ItemStack item = new ItemStack(icon.head() != null ? Material.PLAYER_HEAD : icon.material());
        ItemMeta meta = item.getItemMeta();
        meta.displayName(Component.text(icon.label(), icon.color()).decoration(TextDecoration.ITALIC, false));
        List<Component> lore = new ArrayList<>();
        for (String line : icon.lore()) lore.add(Component.text(line, NamedTextColor.GRAY).decoration(TextDecoration.ITALIC, false));
        if (icon.click() != null && icon.action() != null) {
            if (!lore.isEmpty()) lore.add(Component.empty());
            lore.add(Component.text(icon.click(), NamedTextColor.YELLOW).decoration(TextDecoration.ITALIC, false));
        }
        meta.lore(lore);
        if (icon.head() != null && meta instanceof SkullMeta skull) skull.setOwningPlayer(icon.head());
        item.setItemMeta(meta);
        return item;
    }

    /** Splits a description into short lore lines, the way Hypixel menus do. */
    static List<String> wrap(String text) {
        if (text == null || text.isBlank()) return List.of();
        List<String> lines = new ArrayList<>();
        for (String paragraph : text.split("\n")) {
            StringBuilder line = new StringBuilder();
            for (String word : paragraph.split(" ")) {
                if (!line.isEmpty() && line.length() + 1 + word.length() > WRAP) {
                    lines.add(line.toString());
                    line.setLength(0);
                }
                if (!line.isEmpty()) line.append(' ');
                line.append(word);
            }
            if (!line.isEmpty()) lines.add(line.toString());
        }
        return List.copyOf(lines);
    }

    private void run(Player player, Page page, Runnable action) {
        if (!open.remove(player.getUniqueId(), page)) return;
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            if (!player.isOnline() || plugin.getServer().getPlayer(player.getUniqueId()) != player || !allowed.test(player)
                    || !page.identity.equals(identity.apply(player))) return;
            player.playSound(player.getLocation(), Sound.UI_BUTTON_CLICK, 0.4f, 1.0f);
            if (page.inventory != null && player.getOpenInventory().getTopInventory() == page.inventory) player.closeInventory();
            action.run();
        });
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onClick(InventoryClickEvent event) {
        if (!(event.getView().getTopInventory().getHolder() instanceof Page page)) return;
        event.setCancelled(true);
        if (!(event.getWhoClicked() instanceof Player player) || open.get(player.getUniqueId()) != page
                || event.getClick() != ClickType.LEFT && event.getClick() != ClickType.RIGHT) return;
        Runnable action = page.actions.get(event.getRawSlot());
        if (action != null) run(player, page, action);
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onDrag(InventoryDragEvent event) {
        if (event.getView().getTopInventory().getHolder() instanceof Page) event.setCancelled(true);
    }

    @EventHandler public void onQuit(PlayerQuitEvent event) { open.remove(event.getPlayer().getUniqueId()); }

    @Override
    public void close() {
        for (Player online : plugin.getServer().getOnlinePlayers()) {
            if (online.getOpenInventory().getTopInventory().getHolder() instanceof Page) online.closeInventory();
        }
        open.clear();
        HandlerList.unregisterAll(this);
    }

    private static final class Page implements InventoryHolder {
        final String identity;
        final Map<Integer, Runnable> actions = new HashMap<>();
        Inventory inventory;

        Page(String identity) { this.identity = identity; }

        @Override public Inventory getInventory() { return inventory; }
    }
}
