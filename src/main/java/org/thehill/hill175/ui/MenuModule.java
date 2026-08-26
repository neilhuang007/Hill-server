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
import org.bukkit.event.player.PlayerEditBookEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.InventoryHolder;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.inventory.meta.WritableBookMeta;
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
    private static final int BOOK_PAGE_LENGTH = 220;

    private final CompetitionModule competition;
    private final Map<UUID, MenuSession> sessions = new HashMap<>();
    private final Map<UUID, SubmissionBookPrompt> submissionPrompts = new HashMap<>();

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
                List.of("Your entries are on the left.", "Create or visit on the right."), NamedTextColor.GOLD));

        List<Entry> ownEntries = competition.entriesFor(competition.nicknameKey(player.getName()));
        for (int index = 0; index < Math.min(2, ownEntries.size()); index++) {
            Entry entry = ownEntries.get(index);
            int slot = index == 0 ? 10 : 11;
            inventory.setItem(slot, entryCard(entry, true));
            session.actions.put(slot, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        }
        if (ownEntries.isEmpty()) {
            inventory.setItem(10, item(Material.LIGHT_GRAY_DYE, "No entries yet",
                    List.of("Choose a category on the right."), NamedTextColor.GRAY));
        }

        inventory.setItem(13, item(Material.PLAYER_HEAD, "Visit Builds",
                List.of("Browse submitted and active entries."), NamedTextColor.AQUA));
        session.actions.put(13, new MenuAction(ActionType.OPEN_VISITS, null, null, 0));

        int slot = 15;
        for (Category category : Category.values()) {
            boolean alreadyJoined = ownEntries.stream().anyMatch(entry -> entry.category() == category);
            Material material = alreadyJoined ? Material.BARRIER : category.icon();
            String title = alreadyJoined ? category.displayName() + " — already entered" : "Create " + category.displayName();
            List<String> lore = alreadyJoined
                    ? List.of("Open the existing entry on the left.")
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

    public void openCurrentEntry(Player player) {
        competition.currentEntry(player)
                .filter(entry -> entry.isMember(competition.nicknameKey(player.getName())))
                .ifPresentOrElse(
                        entry -> openEntryDetails(player, entry),
                        () -> {
                            List<Entry> entries = competition.entriesFor(competition.nicknameKey(player.getName()));
                            if (entries.size() == 1) {
                                openEntryDetails(player, entries.getFirst());
                            } else {
                                openMain(player);
                            }
                        }
                );
    }

    public void openEntry(Player player, Entry entry) {
        openEntryDetails(player, entry);
    }

    public void openEntryDetails(Player player, Entry entry) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 27,
                Component.text(entry.category().displayName() + " Entry", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);

        inventory.setItem(10, entrySummary(entry));
        inventory.setItem(11, item(entry.submitted() ? Material.LIME_DYE : Material.CLOCK,
                entry.submitted() ? "Submission Locked" : "Build Open",
                entry.submitted()
                        ? List.of("The entry is currently submitted.", "Unlock it before editing again.")
                        : List.of("The entry is ready for building.", "Use the controls on the right to manage it."),
                entry.submitted() ? NamedTextColor.GREEN : NamedTextColor.YELLOW));
        inventory.setItem(12, item(Material.PLAYER_HEAD, "Team",
                List.of(entry.members().stream()
                        .map(competition::displayName)
                        .sorted()
                        .reduce((left, right) -> left + " & " + right)
                        .orElse("Participant")),
                NamedTextColor.AQUA));

        inventory.setItem(14, item(Material.ENDER_PEARL, "Enter Build",
                List.of(entry.submitted() ? "Open this entry in Visitor Mode." : "Teleport into this build."), NamedTextColor.GREEN));
        session.actions.put(14, new MenuAction(ActionType.ENTER_BUILD, entry.id(), null, 0));

        inventory.setItem(15, item(Material.WRITABLE_BOOK, "Edit Submission",
                List.of("Open a book-and-quill prompt for", "the title and description."), NamedTextColor.AQUA));
        session.actions.put(15, new MenuAction(ActionType.EDIT_SUBMISSION, entry.id(), null, 0));

        inventory.setItem(16, item(Material.ENDER_EYE, "Visit Build",
                List.of("Open this entry in Visitor Mode."), NamedTextColor.YELLOW));
        session.actions.put(16, new MenuAction(ActionType.VISIT_ENTRY, entry.id(), null, 0));

        inventory.setItem(21, item(entry.submitted() ? Material.LIME_DYE : Material.TRIPWIRE_HOOK,
                entry.submitted() ? "Resume Editing" : "Lock Submission",
                entry.submitted()
                        ? List.of("Unlock the entry and return to", "Owner Mode before the deadline.")
                        : List.of("Submit the current title, description,", "and saved camera poses."),
                entry.submitted() ? NamedTextColor.YELLOW : NamedTextColor.GREEN));
        session.actions.put(21, new MenuAction(ActionType.TOGGLE_SUBMISSION, entry.id(), null, 0));

        inventory.setItem(22, item(Material.BARRIER, "Reset Entry",
                List.of("Restore this build space and", "clear title, description, and cameras."), NamedTextColor.RED));
        session.actions.put(22, new MenuAction(ActionType.RESET_ENTRY, entry.id(), null, 0));

        inventory.setItem(23, item(Material.LAVA_BUCKET, "Delete Entry",
                List.of("Delete this entry and free the category slot."), NamedTextColor.RED));
        session.actions.put(23, new MenuAction(ActionType.DELETE_ENTRY, entry.id(), null, 0));

        inventory.setItem(26, item(Material.COMPASS, "Back to Main Menu", List.of(), NamedTextColor.GOLD));
        session.actions.put(26, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));

        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    public void openCategory(Player player, Category category) {
        competition.entriesFor(competition.nicknameKey(player.getName())).stream()
                .filter(entry -> entry.category() == category)
                .findFirst()
                .ifPresentOrElse(
                        entry -> openEntryDetails(player, entry),
                        () -> openCreateConfirmation(player, category)
                );
    }

    public void openVisits(Player player, int page) {
        List<Entry> entries = competition.allEntries().stream()
                .sorted(Comparator.comparing((Entry entry) -> entry.category().displayName())
                        .thenComparing(entry -> entry.title().toLowerCase()))
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
                List.of("Create the build space, then open", "a book prompt for its submission details."), NamedTextColor.GREEN));
        session.actions.put(3, new MenuAction(ActionType.CREATE_ENTRY, null, category, 0));
        inventory.setItem(5, item(Material.RED_CONCRETE, "Cancel", List.of(), NamedTextColor.RED));
        session.actions.put(5, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    private void openSubmissionBook(Player player, Entry entry, boolean newlyCreated) {
        player.sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                .append(Component.text("Write the title on the first line, then add the description below it.", NamedTextColor.YELLOW)
                        .decoration(TextDecoration.BOLD, false)));
        ItemStack book = new ItemStack(Material.WRITABLE_BOOK);
        WritableBookMeta meta = (WritableBookMeta) book.getItemMeta();
        meta.setPages(buildSubmissionPages(entry));
        book.setItemMeta(meta);
        submissionPrompts.put(player.getUniqueId(), new SubmissionBookPrompt(entry.id(), newlyCreated));
        player.openBook(book);
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
            case OPEN_ENTRY -> competition.entry(action.entryId).ifPresent(entry -> openEntryDetails(player, entry));
            case CONFIRM_CREATE -> openCreateConfirmation(player, action.category);
            case CREATE_ENTRY -> {
                player.closeInventory();
                competition.createEntry(player, action.category).ifPresent(entry -> openSubmissionBook(player, entry, true));
            }
            case ENTER_BUILD -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.teleportToEntry(player, entry, false);
            });
            case VISIT_ENTRY -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.teleportToEntry(player, entry, true);
            });
            case EDIT_SUBMISSION -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                openSubmissionBook(player, entry, false);
            });
            case RESET_ENTRY -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.resetEntry(player, entry);
            });
            case TOGGLE_SUBMISSION -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                if (entry.submitted()) {
                    competition.unlockEntry(player, entry);
                } else {
                    competition.submitEntry(player, entry);
                }
            });
            case DELETE_ENTRY -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.deleteEntry(player, entry);
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

    @EventHandler
    public void onBookEdit(PlayerEditBookEvent event) {
        SubmissionBookPrompt prompt = submissionPrompts.remove(event.getPlayer().getUniqueId());
        if (prompt == null) {
            return;
        }
        competition.entry(prompt.entryId()).ifPresent(entry -> {
            SubmissionDraft draft = parseSubmissionDraft(event.getNewBookMeta().getPages());
            if (draft == null) {
                event.getPlayer().sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                        .append(Component.text("Write the title on the first line, then add a description below it.", NamedTextColor.RED)
                                .decoration(TextDecoration.BOLD, false)));
                return;
            }
            competition.setTitle(event.getPlayer(), entry, draft.title());
            competition.setDescription(event.getPlayer(), entry, draft.description());
            event.getPlayer().sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                    .append(Component.text("Submission details saved. Use the hotbar or entry menu to submit when your cameras are ready.", NamedTextColor.GREEN)
                            .decoration(TextDecoration.BOLD, false)));
            Bukkit.getScheduler().runTaskLater(Bukkit.getPluginManager().getPlugin("Hill175"),
                    () -> openEntryDetails(event.getPlayer(), entry), 1L);
        });
    }

    private ItemStack entryCard(Entry entry, boolean ownEntry) {
        List<String> lore = new ArrayList<>();
        lore.add(entry.category().displayName());
        lore.add(entry.title().isBlank() ? "Untitled project" : entry.title());
        lore.add(entry.submitted() ? "Submitted and locked" : "Building open");
        lore.add(ownEntry ? "Click to open entry controls." : "Click to visit.");
        return item(entry.category().icon(), entry.category().displayName(), lore,
                entry.submitted() ? NamedTextColor.GREEN : NamedTextColor.GOLD);
    }

    private ItemStack entrySummary(Entry entry) {
        List<String> lore = new ArrayList<>();
        lore.add(entry.title().isBlank() ? "Untitled project" : entry.title());
        lore.add(entry.submitted() ? "Submitted and locked" : "Building open");
        lore.add("Cameras: " + entry.cameraPoses().size() + "/3");
        lore.add("Members: " + entry.members().stream().map(competition::displayName).sorted().reduce((a, b) -> a + " & " + b).orElse("Participant"));
        if (!entry.description().isBlank()) {
            lore.add(trimLore(entry.description(), 64));
        }
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
        lore.add(Component.text(entry.submitted() ? "Submitted project" : "Build in progress", NamedTextColor.YELLOW).decoration(TextDecoration.ITALIC, false));
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
            case PEOPLE -> List.of("Imagine Hill's future.", "Private Hill campus world imported from structure.nbt.");
        };
    }

    private static void fill(Inventory inventory, Material material) {
        ItemStack filler = item(material, " ", List.of(), NamedTextColor.GRAY);
        for (int slot = 0; slot < inventory.getSize(); slot++) {
            inventory.setItem(slot, filler);
        }
    }

    private static List<String> buildSubmissionPages(Entry entry) {
        if (entry.title().isBlank() && entry.description().isBlank()) {
            return List.of("");
        }
        String title = entry.title().isBlank() ? "" : entry.title();
        String body = title + "\n" + entry.description();
        List<String> pages = new ArrayList<>();
        for (int start = 0; start < body.length(); start += BOOK_PAGE_LENGTH) {
            pages.add(body.substring(start, Math.min(body.length(), start + BOOK_PAGE_LENGTH)));
        }
        if (pages.isEmpty()) {
            pages.add("");
        }
        return pages;
    }

    private static SubmissionDraft parseSubmissionDraft(List<String> pages) {
        String joined = String.join("\n", pages).replace('\r', '\n').trim();
        if (joined.isBlank()) {
            return null;
        }
        String[] lines = joined.split("\n");
        int titleLineIndex = -1;
        for (int index = 0; index < lines.length; index++) {
            if (!lines[index].isBlank()) {
                titleLineIndex = index;
                break;
            }
        }
        if (titleLineIndex < 0) {
            return null;
        }
        String title = lines[titleLineIndex].trim();
        StringBuilder description = new StringBuilder();
        for (int index = titleLineIndex + 1; index < lines.length; index++) {
            if (description.length() > 0) {
                description.append('\n');
            }
            description.append(lines[index]);
        }
        String descriptionText = description.toString().trim();
        if (title.isBlank() || descriptionText.isBlank()) {
            return null;
        }
        return new SubmissionDraft(title, descriptionText);
    }

    private static String trimLore(String text, int maxLength) {
        if (text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength - 3) + "...";
    }

    private enum ActionType {
        OPEN_MAIN,
        OPEN_VISITS,
        OPEN_ENTRY,
        CONFIRM_CREATE,
        CREATE_ENTRY,
        ENTER_BUILD,
        VISIT_ENTRY,
        EDIT_SUBMISSION,
        RESET_ENTRY,
        TOGGLE_SUBMISSION,
        DELETE_ENTRY
    }

    private record MenuAction(ActionType type, UUID entryId, Category category, int page) {
    }

    private record SubmissionBookPrompt(UUID entryId, boolean newlyCreated) {
    }

    private record SubmissionDraft(String title, String description) {
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
