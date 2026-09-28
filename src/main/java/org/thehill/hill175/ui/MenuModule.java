package org.thehill.hill175.ui;

import io.papermc.paper.connection.PlayerGameConnection;
import io.papermc.paper.dialog.Dialog;
import io.papermc.paper.dialog.DialogResponseView;
import io.papermc.paper.event.player.PlayerCustomClickEvent;
import io.papermc.paper.registry.data.dialog.ActionButton;
import io.papermc.paper.registry.data.dialog.DialogBase;
import io.papermc.paper.registry.data.dialog.action.DialogAction;
import io.papermc.paper.registry.data.dialog.body.DialogBody;
import io.papermc.paper.registry.data.dialog.input.DialogInput;
import io.papermc.paper.registry.data.dialog.input.TextDialogInput;
import io.papermc.paper.registry.data.dialog.type.DialogType;
import net.kyori.adventure.key.Key;
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
import org.bukkit.event.inventory.InventoryDragEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.InventoryHolder;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.plugin.java.JavaPlugin;
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
    private static final int TITLE_MAX_LENGTH = 80;
    private static final int DESCRIPTION_MAX_LENGTH = 750;
    private static final Key SAVE_SUBMISSION_ACTION = Key.key("hill175", "save_submission");
    private static final Key CANCEL_SUBMISSION_ACTION = Key.key("hill175", "cancel_submission");

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final Map<UUID, MenuSession> sessions = new HashMap<>();
    private final Map<UUID, SubmissionDialogPrompt> submissionPrompts = new HashMap<>();

    public MenuModule(CompetitionModule competition) {
        this.plugin = JavaPlugin.getProvidingPlugin(MenuModule.class);
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

        List<Entry> ownEntries = competition.entriesFor(competition.participantKey(player));
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
                .filter(entry -> entry.isMember(competition.participantKey(player)))
                .ifPresentOrElse(
                        entry -> openEntryDetails(player, entry),
                        () -> {
                            List<Entry> entries = competition.entriesFor(competition.participantKey(player));
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
                Component.text("Build Options - " + entry.category().displayName(), NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);

        inventory.setItem(4, item(Material.NETHER_STAR, "Build Options",
                List.of(
                        entry.submitted() ? "This entry is locked." : "Manage this entry without hotbar clutter.",
                        "Camera and navigation tools remain in the hotbar."
                ), NamedTextColor.GOLD));
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

        if (entry.submitted()) {
            inventory.setItem(15, item(Material.GRAY_DYE, "Editing Locked",
                    List.of("Resume editing before changing", "the title or description."), NamedTextColor.GRAY));
        } else {
            inventory.setItem(15, item(Material.WRITABLE_BOOK, "Edit Submission",
                    List.of("Open the editable title and", "description form."), NamedTextColor.AQUA));
            session.actions.put(15, new MenuAction(ActionType.EDIT_SUBMISSION, entry.id(), null, 0));
        }

        inventory.setItem(16, item(Material.ENDER_EYE, "Visit Build",
                List.of("Open this entry in Visitor Mode."), NamedTextColor.YELLOW));
        session.actions.put(16, new MenuAction(ActionType.VISIT_ENTRY, entry.id(), null, 0));

        if (entry.submitted()) {
            inventory.setItem(20, item(Material.GRAY_DYE, "Category Change Locked",
                    List.of("Resume editing before changing", "this entry's category."), NamedTextColor.GRAY));
        } else {
            inventory.setItem(20, item(Material.RECOVERY_COMPASS, "Change Category",
                    List.of("Choose a different competition category.", "This replaces the entire build space."),
                    NamedTextColor.YELLOW));
            session.actions.put(20, new MenuAction(ActionType.OPEN_CATEGORY_SWITCH, entry.id(), null, 0));
        }

        inventory.setItem(21, item(entry.submitted() ? Material.LIME_DYE : Material.TRIPWIRE_HOOK,
                entry.submitted() ? "Resume Editing" : "Lock Submission",
                entry.submitted()
                        ? List.of("Unlock the entry and return to", "Owner Mode before the deadline.")
                        : List.of("Submit the current title, description,", "and saved camera poses."),
                entry.submitted() ? NamedTextColor.YELLOW : NamedTextColor.GREEN));
        session.actions.put(21, new MenuAction(
                entry.submitted() ? ActionType.TOGGLE_SUBMISSION : ActionType.CONFIRM_SUBMISSION,
                entry.id(), null, 0));

        if (entry.submitted()) {
            inventory.setItem(22, item(Material.GRAY_DYE, "Reset Locked",
                    List.of("Resume editing before resetting", "this build space."), NamedTextColor.GRAY));
            inventory.setItem(23, item(Material.GRAY_DYE, "Delete Locked",
                    List.of("Resume editing before deleting", "this entry."), NamedTextColor.GRAY));
        } else {
            inventory.setItem(22, item(Material.BARRIER, "Reset Entry",
                    List.of("Restore this build space and", "clear title, description, and cameras."), NamedTextColor.RED));
            session.actions.put(22, new MenuAction(ActionType.CONFIRM_RESET, entry.id(), null, 0));

            inventory.setItem(23, item(Material.LAVA_BUCKET, "Delete Entry",
                    List.of("Delete this entry and free the category slot."), NamedTextColor.RED));
            session.actions.put(23, new MenuAction(ActionType.CONFIRM_DELETE, entry.id(), null, 0));
        }

        inventory.setItem(26, item(Material.COMPASS, "Back to Main Menu", List.of(), NamedTextColor.GOLD));
        session.actions.put(26, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));

        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    public void openCategory(Player player, Category category) {
        competition.entriesFor(competition.participantKey(player)).stream()
                .filter(entry -> entry.category() == category)
                .findFirst()
                .ifPresentOrElse(
                        entry -> openEntryDetails(player, entry),
                        () -> openCreateConfirmation(player, category)
                );
    }

    public void openSurvival(Player player) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 9,
                Component.text("Enter Survival", NamedTextColor.GREEN));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        inventory.setItem(4, item(Material.GRASS_BLOCK, "Enter Survival",
                List.of("Resume your survival world."), NamedTextColor.GREEN));
        session.actions.put(4, new MenuAction(ActionType.ENTER_SURVIVAL, null, null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    public void openCameraControls(Player player) {
        MenuSession openSession = sessions.get(player.getUniqueId());
        if (openSession != null
                && player.getOpenInventory().getTopInventory().equals(openSession.inventory)) {
            return;
        }
        competition.currentEntry(player).ifPresentOrElse(
                entry -> openCameraControls(player, entry),
                () -> player.sendMessage(Component.text("Open or visit an entry first.", NamedTextColor.RED))
        );
    }

    private void openCameraControls(Player player, Entry entry) {
        boolean editor = competition.canEditCameras(player, entry);
        boolean owner = entry.isMember(competition.participantKey(player));
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 27,
                Component.text(editor ? "Camera Controls" : "Camera Views", NamedTextColor.AQUA));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.ENDER_EYE, editor ? "Submission Cameras" : "Saved Camera Views",
                editor
                        ? List.of("Choose a numbered slot.", "Replacing and removing require confirmation.")
                        : List.of("Choose a saved camera view."),
                NamedTextColor.AQUA));
        for (int cameraSlot = 1; cameraSlot <= Entry.MAX_CAMERA_SLOTS; cameraSlot++) {
            int inventorySlot = 9 + cameraSlot * 2;
            boolean saved = entry.cameraPose(cameraSlot).isPresent();
            if (saved) {
                inventory.setItem(inventorySlot, item(Material.ENDER_EYE, "Camera " + cameraSlot,
                        editor
                                ? List.of("Preview, replace, or remove this slot.")
                                : List.of("Preview this saved view."),
                        NamedTextColor.GREEN));
                session.actions.put(inventorySlot, new MenuAction(
                        editor ? ActionType.OPEN_CAMERA_SLOT : ActionType.PREVIEW_CAMERA,
                        entry.id(), null, cameraSlot));
            } else if (editor) {
                inventory.setItem(inventorySlot, item(Material.LIME_DYE, "Save Camera " + cameraSlot,
                        List.of("Save your current view to this slot."), NamedTextColor.GREEN));
                session.actions.put(inventorySlot, new MenuAction(ActionType.SAVE_CAMERA, entry.id(), null, cameraSlot));
            } else {
                inventory.setItem(inventorySlot, item(Material.GRAY_DYE, "Camera " + cameraSlot + " Empty",
                        List.of("No saved view in this slot."), NamedTextColor.GRAY));
            }
        }
        inventory.setItem(26, item(owner ? Material.NETHER_STAR : Material.COMPASS,
                owner ? "Back to Build Options" : "Back to Main Menu", List.of(), NamedTextColor.GOLD));
        session.actions.put(26, new MenuAction(owner ? ActionType.OPEN_ENTRY : ActionType.OPEN_MAIN, entry.id(), null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    private void openCameraSlotControls(Player player, Entry entry, int cameraSlot) {
        if (!competition.canEditCameras(player, entry) || entry.cameraPose(cameraSlot).isEmpty()) {
            openCameraControls(player, entry);
            return;
        }
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 9,
                Component.text("Camera " + cameraSlot, NamedTextColor.AQUA));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(1, item(Material.ENDER_EYE, "Preview Camera",
                List.of("View this saved angle."), NamedTextColor.AQUA));
        session.actions.put(1, new MenuAction(ActionType.PREVIEW_CAMERA, entry.id(), null, cameraSlot));
        inventory.setItem(3, item(Material.LIME_DYE, "Replace Camera",
                List.of("Replace this slot with your current view."), NamedTextColor.YELLOW));
        session.actions.put(3, new MenuAction(ActionType.CONFIRM_REPLACE_CAMERA, entry.id(), null, cameraSlot));
        inventory.setItem(5, item(Material.RED_DYE, "Remove Camera",
                List.of("Clear this slot after confirmation."), NamedTextColor.RED));
        session.actions.put(5, new MenuAction(ActionType.CONFIRM_REMOVE_CAMERA, entry.id(), null, cameraSlot));
        inventory.setItem(8, item(Material.ARROW, "Back to Cameras", List.of(), NamedTextColor.GOLD));
        session.actions.put(8, new MenuAction(ActionType.OPEN_CAMERA_CONTROLS, entry.id(), null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    private void openCameraReplaceConfirmation(Player player, Entry entry, int cameraSlot) {
        openCameraConfirmation(
                player,
                entry,
                cameraSlot,
                "Replace camera " + cameraSlot + "?",
                Material.LIME_DYE,
                "Replace saved view",
                List.of("This overwrites only camera slot " + cameraSlot + "."),
                "Confirm Replace",
                ActionType.REPLACE_CAMERA
        );
    }

    private void openCameraRemoveConfirmation(Player player, Entry entry, int cameraSlot) {
        openCameraConfirmation(
                player,
                entry,
                cameraSlot,
                "Remove camera " + cameraSlot + "?",
                Material.RED_DYE,
                "Remove saved view",
                List.of("This clears only camera slot " + cameraSlot + "."),
                "Confirm Remove",
                ActionType.REMOVE_CAMERA
        );
    }

    public void openActiveCameraRemovalConfirmation(Player player) {
        competition.activeCameraPreview(player).ifPresentOrElse(context -> {
            if (!competition.canEditCameras(player, context.entry())) {
                player.sendMessage(Component.text("Only an entry owner may remove this camera.", NamedTextColor.RED));
                return;
            }
            openCameraConfirmation(
                    player,
                    context.entry(),
                    context.oneBasedIndex(),
                    "Remove camera " + context.oneBasedIndex() + "?",
                    Material.RED_DYE,
                    "Remove active camera",
                    List.of("The preview will close after removal."),
                    "Confirm Remove",
                    ActionType.REMOVE_ACTIVE_CAMERA
            );
        }, () -> player.sendMessage(Component.text("That camera preview is no longer active.", NamedTextColor.RED)));
    }

    private void openCameraConfirmation(
            Player player,
            Entry entry,
            int cameraSlot,
            String menuTitle,
            Material warningMaterial,
            String warningTitle,
            List<String> warningLore,
            String confirmTitle,
            ActionType confirmAction
    ) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 9, Component.text(menuTitle, NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(2, item(warningMaterial, warningTitle, warningLore, NamedTextColor.RED));
        inventory.setItem(4, item(Material.LIME_CONCRETE, confirmTitle, List.of("Click to continue."), NamedTextColor.GREEN));
        session.actions.put(4, new MenuAction(confirmAction, entry.id(), null, cameraSlot));
        inventory.setItem(6, item(Material.RED_CONCRETE, "Back Without Changes", List.of(), NamedTextColor.RED));
        session.actions.put(6, new MenuAction(ActionType.OPEN_CAMERA_CONTROLS, entry.id(), null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
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
                List.of("Create the build space, then open", "the title and description form."), NamedTextColor.GREEN));
        session.actions.put(3, new MenuAction(ActionType.CREATE_ENTRY, null, category, 0));
        inventory.setItem(5, item(Material.RED_CONCRETE, "Cancel", List.of(), NamedTextColor.RED));
        session.actions.put(5, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    public void openResetConfirmation(Player player, Entry entry) {
        openEntryConfirmation(
                player,
                entry,
                "Reset this entry?",
                Material.BARRIER,
                "Reset removes all build changes",
                List.of("The original build space will be restored.", "Title, description, and cameras will be cleared."),
                "Confirm Reset",
                ActionType.RESET_ENTRY
        );
    }

    public void openSubmitConfirmation(Player player, Entry entry) {
        openEntryConfirmation(
                player,
                entry,
                "Lock this submission?",
                Material.TRIPWIRE_HOOK,
                "Submission checklist",
                List.of(
                        "Title: " + (entry.title().isBlank() ? "MISSING" : "ready"),
                        "Description: " + (entry.description().isBlank() ? "MISSING" : "ready"),
                        "Cameras: " + entry.cameraPoses().size() + "/3",
                        "Locking switches the build to Visitor Mode."
                ),
                "Confirm Lock",
                ActionType.SUBMIT_ENTRY
        );
    }

    public void openDeleteConfirmation(Player player, Entry entry) {
        openEntryConfirmation(
                player,
                entry,
                "Delete this entry?",
                Material.LAVA_BUCKET,
                "Deletion cannot be undone",
                List.of("The entry, metadata, and camera poses", "will be removed and its category slot freed."),
                "Confirm Delete",
                ActionType.DELETE_ENTRY
        );
    }

    private void openCategorySwitch(Player player, Entry entry) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 27,
                Component.text("Change Category", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.RECOVERY_COMPASS, "Choose a New Category",
                List.of("Changing category replaces all blocks,", "submission details, and camera poses."),
                NamedTextColor.RED));
        int slot = 11;
        for (Category category : Category.values()) {
            if (category == entry.category()) {
                inventory.setItem(slot, item(Material.GRAY_DYE, category.displayName() + " — current category",
                        List.of("Choose one of the other categories."), NamedTextColor.GRAY));
            } else {
                inventory.setItem(slot, item(category.icon(), "Switch to " + category.displayName(),
                        categoryLore(category), NamedTextColor.YELLOW));
                session.actions.put(slot,
                        new MenuAction(ActionType.CONFIRM_CATEGORY_SWITCH, entry.id(), category, 0));
            }
            slot += 2;
        }
        inventory.setItem(26, item(Material.ARROW, "Back to Build Options", List.of(), NamedTextColor.GOLD));
        session.actions.put(26, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    private void openCategorySwitchConfirmation(Player player, Entry entry, Category category) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 9,
                Component.text("Replace with " + category.displayName() + "?", NamedTextColor.RED));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(2, item(Material.LAVA_BUCKET, "The current build will be replaced",
                List.of("Blocks, title, description, cameras,", "and submission data will be cleared."),
                NamedTextColor.RED));
        inventory.setItem(4, item(Material.LIME_CONCRETE, "Confirm Category Change",
                List.of("Switch to " + category.displayName() + "."), NamedTextColor.GREEN));
        session.actions.put(4, new MenuAction(ActionType.SWITCH_CATEGORY, entry.id(), category, 0));
        inventory.setItem(6, item(Material.RED_CONCRETE, "Back Without Changes", List.of(), NamedTextColor.RED));
        session.actions.put(6, new MenuAction(ActionType.OPEN_CATEGORY_SWITCH, entry.id(), null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    private void openEntryConfirmation(
            Player player,
            Entry entry,
            String menuTitle,
            Material warningMaterial,
            String warningTitle,
            List<String> warningLore,
            String confirmTitle,
            ActionType confirmAction
    ) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = Bukkit.createInventory(holder, 9, Component.text(menuTitle, NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(2, item(warningMaterial, warningTitle, warningLore, NamedTextColor.RED));
        inventory.setItem(4, item(Material.LIME_CONCRETE, confirmTitle,
                List.of("Click to continue."), NamedTextColor.GREEN));
        session.actions.put(4, new MenuAction(confirmAction, entry.id(), null, 0));
        inventory.setItem(6, item(Material.RED_CONCRETE, "Back Without Changes",
                List.of("Return to entry controls."), NamedTextColor.RED));
        session.actions.put(6, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        sessions.put(player.getUniqueId(), session);
        player.openInventory(inventory);
    }

    private void openSubmissionDialog(Player player, Entry entry, boolean newlyCreated) {
        openSubmissionDialog(player, entry, newlyCreated, entry.title(), entry.description());
    }

    private void openSubmissionDialog(
            Player player,
            Entry entry,
            boolean newlyCreated,
            String initialTitle,
            String initialDescription
    ) {
        player.sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                .append(Component.text("Enter a title and description, then choose Save. Cancel removes a newly created unnamed entry.", NamedTextColor.YELLOW)
                        .decoration(TextDecoration.BOLD, false)));
        DialogBase base = DialogBase.builder(Component.text("Submission Details", NamedTextColor.GOLD))
                .externalTitle(Component.text("Edit Hill 175 Submission"))
                .canCloseWithEscape(false)
                .pause(false)
                .afterAction(DialogBase.DialogAfterAction.CLOSE)
                .body(List.of(DialogBody.plainMessage(Component.text(
                        "Give visitors a clear name and a short description of what your team built.",
                        NamedTextColor.GRAY
                ), 360)))
                .inputs(List.of(
                        DialogInput.text("title", Component.text("Entry title", NamedTextColor.WHITE))
                                .width(360)
                                .initial(initialTitle)
                                .maxLength(TITLE_MAX_LENGTH)
                                .build(),
                        DialogInput.text("description", Component.text("Description", NamedTextColor.WHITE))
                                .width(360)
                                .initial(initialDescription)
                                .maxLength(DESCRIPTION_MAX_LENGTH)
                                .multiline(TextDialogInput.MultilineOptions.create(12, 140))
                                .build()
                ))
                .build();
        ActionButton save = ActionButton.create(
                Component.text("Save Submission", NamedTextColor.GREEN),
                Component.text("Save the title and description."),
                170,
                DialogAction.customClick(SAVE_SUBMISSION_ACTION, null)
        );
        ActionButton cancel = ActionButton.create(
                Component.text(newlyCreated ? "Cancel & Delete Entry" : "Back Without Saving", NamedTextColor.RED),
                Component.text(newlyCreated ? "Delete this newly created entry." : "Return to entry controls."),
                170,
                DialogAction.customClick(CANCEL_SUBMISSION_ACTION, null)
        );
        Dialog dialog = Dialog.create(factory -> factory.empty()
                .base(base)
                .type(DialogType.confirmation(save, cancel)));
        submissionPrompts.put(player.getUniqueId(), new SubmissionDialogPrompt(entry.id(), newlyCreated));
        // Let the inventory-close and any entry teleport packets reach the
        // client before displaying the native form.
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (player.isOnline() && submissionPrompts.containsKey(player.getUniqueId())) {
                player.showDialog(dialog);
            }
        }, 1L);
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
            case CONFIRM_RESET -> competition.entry(action.entryId).ifPresent(entry -> openResetConfirmation(player, entry));
            case CONFIRM_SUBMISSION -> competition.entry(action.entryId).ifPresent(entry -> openSubmitConfirmation(player, entry));
            case CONFIRM_DELETE -> competition.entry(action.entryId).ifPresent(entry -> openDeleteConfirmation(player, entry));
            case OPEN_CATEGORY_SWITCH -> competition.entry(action.entryId)
                    .ifPresent(entry -> openCategorySwitch(player, entry));
            case CONFIRM_CATEGORY_SWITCH -> competition.entry(action.entryId)
                    .ifPresent(entry -> openCategorySwitchConfirmation(player, entry, action.category));
            case CREATE_ENTRY -> {
                player.closeInventory();
                competition.createEntry(player, action.category).ifPresent(entry -> openSubmissionDialog(player, entry, true));
            }
            case ENTER_BUILD -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.teleportToEntry(player, entry, false);
            });
            case VISIT_ENTRY -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.teleportToEntry(player, entry, true);
            });
            case ENTER_SURVIVAL -> {
                player.closeInventory();
                competition.teleportSurvival(player);
            }
            case OPEN_CAMERA_CONTROLS -> competition.entry(action.entryId).ifPresent(entry -> openCameraControls(player, entry));
            case OPEN_CAMERA_SLOT -> competition.entry(action.entryId)
                    .ifPresent(entry -> openCameraSlotControls(player, entry, action.page));
            case PREVIEW_CAMERA -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.previewCamera(player, entry, action.page);
            });
            case SAVE_CAMERA -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.recordCamera(player, action.page);
                Bukkit.getScheduler().runTaskLater(plugin, () -> {
                    if (player.isOnline() && !competition.isCameraPreviewing(player)) {
                        competition.entry(entry.id()).ifPresent(updated -> openCameraControls(player, updated));
                    }
                }, 1L);
            });
            case CONFIRM_REPLACE_CAMERA -> competition.entry(action.entryId)
                    .ifPresent(entry -> openCameraReplaceConfirmation(player, entry, action.page));
            case REPLACE_CAMERA -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.recordCamera(player, action.page);
            });
            case CONFIRM_REMOVE_CAMERA -> competition.entry(action.entryId)
                    .ifPresent(entry -> openCameraRemoveConfirmation(player, entry, action.page));
            case REMOVE_CAMERA -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.removeCamera(player, action.page);
            });
            case REMOVE_ACTIVE_CAMERA -> {
                player.closeInventory();
                competition.removeActiveCameraPreview(player, action.entryId, action.page);
            }
            case CLOSE_MENU -> player.closeInventory();
            case EDIT_SUBMISSION -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                openSubmissionDialog(player, entry, false);
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
                    openSubmitConfirmation(player, entry);
                }
            });
            case SUBMIT_ENTRY -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.submitEntry(player, entry);
            });
            case DELETE_ENTRY -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.deleteEntry(player, entry);
            });
            case SWITCH_CATEGORY -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.switchEntry(player, entry, action.category);
            });
        }
    }

    @EventHandler
    public void onInventoryDrag(InventoryDragEvent event) {
        if (!(event.getWhoClicked() instanceof Player player)) {
            return;
        }
        MenuSession session = sessions.get(player.getUniqueId());
        if (session != null && event.getView().getTopInventory().equals(session.inventory)) {
            event.setCancelled(true);
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
    public void onQuit(PlayerQuitEvent event) {
        UUID playerId = event.getPlayer().getUniqueId();
        sessions.remove(playerId);
        submissionPrompts.remove(playerId);
    }

    @EventHandler
    public void onSubmissionDialogAction(PlayerCustomClickEvent event) {
        if (!event.getIdentifier().equals(SAVE_SUBMISSION_ACTION)
                && !event.getIdentifier().equals(CANCEL_SUBMISSION_ACTION)) {
            return;
        }
        if (!(event.getCommonConnection() instanceof PlayerGameConnection connection)) {
            return;
        }
        Player player = connection.getPlayer();
        SubmissionDialogPrompt prompt = submissionPrompts.remove(player.getUniqueId());
        if (prompt == null) {
            return;
        }
        competition.entry(prompt.entryId()).ifPresent(entry -> {
            if (event.getIdentifier().equals(CANCEL_SUBMISSION_ACTION)) {
                if (prompt.newlyCreated()) {
                    competition.deleteEntry(player, entry);
                } else {
                    Bukkit.getScheduler().runTaskLater(plugin, () -> openEntryDetails(player, entry), 1L);
                }
                return;
            }

            DialogResponseView response = event.getDialogResponseView();
            String title = response == null ? null : response.getText("title");
            String description = response == null ? null : response.getText("description");
            title = title == null ? "" : title.trim();
            description = description == null ? "" : description.trim();
            if (!competition.isAuthenticated(player)
                    || !entry.isMember(competition.participantKey(player))
                    || entry.submitted()) {
                player.sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                        .append(Component.text("This entry is no longer available for editing.", NamedTextColor.RED)
                                .decoration(TextDecoration.BOLD, false)));
                return;
            }
            if (title.isEmpty() || description.isEmpty()
                    || title.length() > TITLE_MAX_LENGTH
                    || description.length() > DESCRIPTION_MAX_LENGTH) {
                player.sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                        .append(Component.text("Both fields are required. Title is limited to " + TITLE_MAX_LENGTH
                                        + " characters and description to " + DESCRIPTION_MAX_LENGTH + ".", NamedTextColor.RED)
                                .decoration(TextDecoration.BOLD, false)));
                openSubmissionDialog(
                        player,
                        entry,
                        prompt.newlyCreated(),
                        title.substring(0, Math.min(title.length(), TITLE_MAX_LENGTH)),
                        description.substring(0, Math.min(description.length(), DESCRIPTION_MAX_LENGTH))
                );
                return;
            }
            competition.setTitle(player, entry, title);
            competition.setDescription(player, entry, description);
            player.sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                    .append(Component.text("Submission details saved. Use Entry Controls to open Build Options and submit when your cameras are ready.", NamedTextColor.GREEN)
                            .decoration(TextDecoration.BOLD, false)));
            Bukkit.getScheduler().runTaskLater(plugin, () -> openEntryDetails(player, entry), 1L);
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
            case PEOPLE -> List.of("Imagine Hill's future.", "Private Hill campus world generated from the VoxelEarth template.");
        };
    }

    private static void fill(Inventory inventory, Material material) {
        ItemStack filler = item(material, " ", List.of(), NamedTextColor.GRAY);
        for (int slot = 0; slot < inventory.getSize(); slot++) {
            inventory.setItem(slot, filler);
        }
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
        CONFIRM_RESET,
        CONFIRM_SUBMISSION,
        CONFIRM_DELETE,
        OPEN_CATEGORY_SWITCH,
        CONFIRM_CATEGORY_SWITCH,
        CREATE_ENTRY,
        ENTER_BUILD,
        VISIT_ENTRY,
        ENTER_SURVIVAL,
        OPEN_CAMERA_CONTROLS,
        OPEN_CAMERA_SLOT,
        PREVIEW_CAMERA,
        SAVE_CAMERA,
        CONFIRM_REPLACE_CAMERA,
        REPLACE_CAMERA,
        CONFIRM_REMOVE_CAMERA,
        REMOVE_CAMERA,
        REMOVE_ACTIVE_CAMERA,
        CLOSE_MENU,
        EDIT_SUBMISSION,
        RESET_ENTRY,
        SUBMIT_ENTRY,
        TOGGLE_SUBMISSION,
        DELETE_ENTRY,
        SWITCH_CATEGORY
    }

    private record MenuAction(ActionType type, UUID entryId, Category category, int page) {
    }

    private record SubmissionDialogPrompt(UUID entryId, boolean newlyCreated) {
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
