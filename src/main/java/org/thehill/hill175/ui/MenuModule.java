package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryCloseEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.InventoryHolder;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class MenuModule implements Listener {
    private static final int VISIT_PAGE_SIZE = 45;

    private final CompetitionModule competition;
    private final Map<UUID, MenuSession> sessions = new HashMap<>();

    public MenuModule(CompetitionModule competition) {
        this.competition = competition;
    }

    public void openMain(Player player) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 27, Component.text("Hill 175 Competition", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);

        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.NETHER_STAR, "Hill 175 Competition",
                List.of("Your entries are on the left.", "Create entries on the right."), NamedTextColor.GOLD));

        List<Entry> ownEntries = competition.entriesFor(competition.nicknameKey(player.getName()));
        for (int index = 0; index < Math.min(2, ownEntries.size()); index++) {
            Entry entry = ownEntries.get(index);
            int slot = index == 0 ? 10 : 11;
            inventory.setItem(slot, entryItem(entry, true));
            session.actions.put(slot, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        }
        if (ownEntries.isEmpty()) {
            inventory.setItem(10, item(Material.LIGHT_GRAY_DYE, "No entries yet",
                    List.of("Choose a category on the right."), NamedTextColor.GRAY));
        }

        inventory.setItem(13, item(Material.PLAYER_HEAD, "Visit Builds",
                List.of("Browse participant entries."), NamedTextColor.AQUA));
        session.actions.put(13, new MenuAction(ActionType.OPEN_VISITS, null, null, 0));

        int slot = 15;
        for (Category category : Category.values()) {
            boolean alreadyJoined = ownEntries.stream().anyMatch(entry -> entry.category() == category);
            Material material = alreadyJoined ? Material.BARRIER : category.icon();
            String title = alreadyJoined ? category.displayName() + " — already entered" : "Create " + category.displayName();
            List<String> lore = alreadyJoined
                    ? List.of("One entry per person in each category.")
                    : categoryLore(category);
            inventory.setItem(slot, item(material, title, lore, alreadyJoined ? NamedTextColor.RED : NamedTextColor.GREEN));
            if (!alreadyJoined) {
                session.actions.put(slot, new MenuAction(ActionType.CONFIRM_CREATE, null, category, 0));
            }
            slot++;
        }

        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    public void openCategory(Player player, Category category) {
        competition.entriesFor(competition.nicknameKey(player.getName())).stream()
                .filter(entry -> entry.category() == category)
                .findFirst()
                .ifPresentOrElse(
                        entry -> competition.teleportToEntry(player, entry, false),
                        () -> openCreateConfirmation(player, category)
                );
    }

    public void openVisits(Player player, int page) {
        List<Entry> entries = competition.allEntries().stream()
                .sorted(Comparator.comparing((Entry entry) -> entry.category())
                        .thenComparing((Entry entry) -> entry.title()))
                .toList();
        int maxPage = Math.max(0, (entries.size() - 1) / VISIT_PAGE_SIZE);
        int safePage = Math.max(0, Math.min(page, maxPage));
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 54,
                Component.text("Visit Builds — Page " + (safePage + 1), NamedTextColor.AQUA));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);

        int start = safePage * VISIT_PAGE_SIZE;
        int end = Math.min(entries.size(), start + VISIT_PAGE_SIZE);
        for (int index = start; index < end; index++) {
            Entry entry = entries.get(index);
            int slot = index - start;
            inventory.setItem(slot, visitHead(entry));
            session.actions.put(slot, new MenuAction(ActionType.VISIT_ENTRY, entry.id(), null, safePage));
        }
        for (int slot = 45; slot < 54; slot++) {
            inventory.setItem(slot, item(Material.GRAY_STAINED_GLASS_PANE, " ", List.of(), NamedTextColor.GRAY));
        }
        if (safePage > 0) {
            inventory.setItem(45, item(Material.ARROW, "Previous Page", List.of(), NamedTextColor.YELLOW));
            session.actions.put(45, new MenuAction(ActionType.OPEN_VISITS, null, null, safePage - 1));
        }
        inventory.setItem(49, item(Material.COMPASS, "Back to My Entries", List.of(), NamedTextColor.GOLD));
        session.actions.put(49, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));
        if (safePage < maxPage) {
            inventory.setItem(53, item(Material.ARROW, "Next Page", List.of(), NamedTextColor.YELLOW));
            session.actions.put(53, new MenuAction(ActionType.OPEN_VISITS, null, null, safePage + 1));
        }
        if (entries.isEmpty()) {
            inventory.setItem(22, item(Material.PAPER, "No public entries yet", List.of(), NamedTextColor.GRAY));
        }

        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    private void openCreateConfirmation(Player player, Category category) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 9,
                Component.text("Create " + category.displayName() + "?", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(3, item(Material.LIME_CONCRETE, "Create Entry",
                categoryLore(category), NamedTextColor.GREEN));
        session.actions.put(3, new MenuAction(ActionType.CREATE_ENTRY, null, category, 0));
        inventory.setItem(5, item(Material.RED_CONCRETE, "Cancel", List.of(), NamedTextColor.RED));
        session.actions.put(5, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    @EventHandler
    public void onInventoryClick(InventoryClickEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) {
            return;
        }
        MenuSession session = sessions.get(player.getUniqueId());
        if (session == null || !event.getView().getTopInventory().equals(session.inventory)) {
            return;
        }
        event.setCancelled(true);
        if (event.getRawSlot() < 0 || event.getRawSlot() >= session.inventory.getSize()) {
            return;
        }
        MenuAction action = session.actions.get(event.getRawSlot());
        if (action == null) {
            return;
        }
        switch (action.type) {
            case OPEN_MAIN -> openMain(player);
            case OPEN_VISITS -> openVisits(player, action.page);
            case CONFIRM_CREATE -> openCreateConfirmation(player, action.category);
            case CREATE_ENTRY -> {
                player.closeInventory();
                competition.createEntry(player, action.category);
            }
            case OPEN_ENTRY -> competition.allEntries().stream()
                    .filter(entry -> entry.id().equals(action.entryId))
                    .findFirst()
                    .ifPresent(entry -> {
                        player.closeInventory();
                        competition.teleportToEntry(player, entry, false);
                    });
            case VISIT_ENTRY -> competition.allEntries().stream()
                    .filter(entry -> entry.id().equals(action.entryId))
                    .findFirst()
                    .ifPresent(entry -> {
                        player.closeInventory();
                        boolean owner = entry.isMember(competition.nicknameKey(player.getName()));
                        competition.teleportToEntry(player, entry, !owner);
                    });
        }
    }

    @EventHandler
    public void onInventoryClose(InventoryCloseEvent event) {
        if (!(event.getPlayer() instanceof Player player)) {
            return;
        }
        MenuSession session = sessions.get(player.getUniqueId());
        if (session != null && event.getInventory().equals(session.inventory)) {
            sessions.remove(player.getUniqueId());
        }
    }

    private ItemStack entryItem(Entry entry, boolean ownEntry) {
        List<String> lore = new ArrayList<>();
        lore.add(entry.category().displayName());
        lore.add(entry.title().isBlank() ? "Untitled project" : entry.title());
        lore.add(entry.submitted() ? "Submitted and locked" : "Building open");
        lore.add(ownEntry ? "Click to teleport in Owner Mode." : "Click to visit.");
        return item(entry.category().icon(), entry.category().displayName(), lore,
                entry.submitted() ? NamedTextColor.GREEN : NamedTextColor.GOLD);
    }

    private ItemStack visitHead(Entry entry) {
        ItemStack head = new ItemStack(Material.PLAYER_HEAD);
        ItemMeta meta = head.getItemMeta();
        String title = entry.title().isBlank() ? "Untitled " + entry.category().displayName() : entry.title();
        meta.displayName(Component.text(title, NamedTextColor.AQUA).decoration(TextDecoration.ITALIC, false));
        List<Component> lore = new ArrayList<>();
        lore.add(Component.text(entry.category().displayName(), NamedTextColor.GOLD).decoration(TextDecoration.ITALIC, false));
        String memberNames = entry.members().stream().map(competition::displayName).sorted().reduce((a, b) -> a + " & " + b).orElse("Participant");
        lore.add(Component.text("By " + memberNames, NamedTextColor.GRAY).decoration(TextDecoration.ITALIC, false));
        lore.add(Component.text("Click to visit.", NamedTextColor.GREEN).decoration(TextDecoration.ITALIC, false));
        meta.lore(lore);
        head.setItemMeta(meta);
        return head;
    }

    private static ItemStack item(Material material, String title, List<String> loreLines, NamedTextColor color) {
        ItemStack item = new ItemStack(material);
        ItemMeta meta = item.getItemMeta();
        meta.displayName(Component.text(title, color).decoration(TextDecoration.ITALIC, false));
        meta.lore(loreLines.stream()
                .map(line -> Component.text(line, NamedTextColor.GRAY).decoration(TextDecoration.ITALIC, false))
                .toList());
        item.setItemMeta(meta);
        return item;
    }

    private static List<String> categoryLore(Category category) {
        return switch (category) {
            case JOURNEY -> List.of("Recreate a Hill building, landmark, or area.", "64 x 64 protected outdoor plot.");
            case PLACE -> List.of("Design a useful Hill interior.", "32 x 32 protected interior shell.");
            case PEOPLE -> List.of("Imagine Hill's future.", "Private editable campus-template world.");
        };
    }

    private static void fill(Inventory inventory, Material material) {
        ItemStack filler = item(material, " ", List.of(), NamedTextColor.GRAY);
        for (int slot = 0; slot < inventory.getSize(); slot++) {
            inventory.setItem(slot, filler);
        }
    }

    private enum ActionType {
        OPEN_MAIN,
        OPEN_VISITS,
        CONFIRM_CREATE,
        CREATE_ENTRY,
        OPEN_ENTRY,
        VISIT_ENTRY
    }

    private record MenuAction(ActionType type, UUID entryId, Category category, int page) {
    }

    private static final class MenuSession {
        private final Inventory inventory;
        private final Map<Integer, MenuAction> actions = new HashMap<>();

        private MenuSession(Inventory inventory) {
            this.inventory = inventory;
        }
    }

    private static final class HillMenuHolder implements InventoryHolder {
        private Inventory inventory;

        @Override
        public Inventory getInventory() {
            return inventory;
        }
    }
}
