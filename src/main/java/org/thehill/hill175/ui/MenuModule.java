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
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
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
import org.thehill.hill175.world.BuildingCatalog;
import org.thehill.hill175.world.CampusAreaCatalog;
import org.thehill.hill175.world.WorldModule;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.HashSet;
import java.util.Set;

public final class MenuModule implements Listener {
    private static final int VISIT_PAGE_SIZE = 45;
    private static final Key SAVE_SUBMISSION_ACTION = Key.key("hill175", "save_submission");
    private static final Key CANCEL_SUBMISSION_ACTION = Key.key("hill175", "cancel_submission");

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final WorldModule worlds;
    private final BedrockForms bedrockForms;
    private final Map<UUID, MenuSession> sessions = new HashMap<>();
    private final Map<UUID, SubmissionDialogPrompt> submissionPrompts = new HashMap<>();
    private final Set<UUID> choosingBuilding = new HashSet<>();
    private final Set<UUID> choosingSingleBuilding = new HashSet<>();
    private final Map<UUID, UUID> buildingSwitches = new HashMap<>();
    private java.util.function.Consumer<Player> campusWorkshop;

    public void campusWorkshop(java.util.function.Consumer<Player> opener) {
        this.campusWorkshop = java.util.Objects.requireNonNull(opener);
    }

    public MenuModule(CompetitionModule competition, WorldModule worlds) {
        this.plugin = JavaPlugin.getProvidingPlugin(MenuModule.class);
        this.competition = competition;
        this.worlds = worlds;
        this.bedrockForms = new BedrockForms(plugin);
    }

    public void openMain(Player player) {
        if (campusWorkshop != null && worlds.sharedCampusEntry().isPresent()) {
            campusWorkshop.accept(player);
            return;
        }
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 27, Component.text("Hill 175 Competition", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);

        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.GRASS_BLOCK, "Open Shared Campus",
                List.of("Choose a location on the campus image.", "Build together in the shared campus.",
                        "Automatic backups protect your work."), NamedTextColor.GOLD));
        session.actions.put(4, new MenuAction(ActionType.OPEN_WORKSHOP, null, null, 0));

        List<Entry> ownEntries = competition.entriesFor(competition.participantKey(player));
        for (int index = 0; index < Math.min(2, ownEntries.size()); index++) {
            Entry entry = ownEntries.get(index);
            int slot = index == 0 ? 10 : 11;
            inventory.setItem(slot, entryCard(entry, true));
            session.actions.put(slot, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        }
        if (ownEntries.isEmpty()) {
            inventory.setItem(10, item(Material.LIGHT_GRAY_DYE, "No entries yet",
                    List.of("Start with Journey, Place, or People."), NamedTextColor.GRAY));
        }

        inventory.setItem(13, item(Material.PLAYER_HEAD, "Visit Builds",
                List.of("Browse submitted and active entries."), NamedTextColor.AQUA));
        session.actions.put(13, new MenuAction(ActionType.OPEN_VISITS, null, null, 0));

        int slot = 15;
        for (Category category : Category.values()) {
            boolean alreadyJoined = ownEntries.stream().anyMatch(entry -> entry.category() == category);
            Material material = alreadyJoined ? Material.BARRIER : category.icon();
            String title = alreadyJoined ? category.displayName() + " — already entered" : "Start " + category.displayName();
            List<String> lore = alreadyJoined
                    ? List.of("Continue your existing project.")
                    : categoryLore(category);
            inventory.setItem(slot, item(material, title, lore, alreadyJoined ? NamedTextColor.RED : NamedTextColor.GREEN));
            if (!alreadyJoined) {
                session.actions.put(slot, new MenuAction(ActionType.CONFIRM_CREATE, null, category, 0));
            }
            slot++;
        }

        competition.pendingInviter(player).ifPresent(name -> {
            inventory.setItem(22, item(Material.PLAYER_HEAD, "Accept Team Invite",
                    List.of("Join " + name + " in their project."), NamedTextColor.GREEN));
            session.actions.put(22, new MenuAction(ActionType.ACCEPT_INVITE, null, null, 0, name));
        });
        presentMenu(player, session);
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

    public void openEntryDetails(Player player, Entry entry) {
        boolean preparing = competition.isPreparingSubmission(entry);
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 27,
                Component.text("Build Options - " + entry.category().displayName(), NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);

        inventory.setItem(4, item(Material.NETHER_STAR, "Build Options",
                List.of(
                        preparing ? "Preparing images; your build is paused." : entry.submitted() ? "This entry is locked." : "Build, capture, then submit.",
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
        session.actions.put(12, new MenuAction(ActionType.OPEN_TEAM, entry.id(), null, 0));

        inventory.setItem(14, item(Material.ENDER_PEARL, "Enter Build",
                List.of(entry.submitted() ? "Open this entry in Visitor Mode." : "Teleport into this build."), NamedTextColor.GREEN));
        session.actions.put(14, new MenuAction(ActionType.ENTER_BUILD, entry.id(), null, 0));

        if (entry.submitted()) {
            inventory.setItem(15, item(Material.GRAY_DYE, "Editing Locked",
                    List.of("Resume editing before changing", "the title or description."), NamedTextColor.GRAY));
        } else {
            inventory.setItem(15, item(Material.WRITABLE_BOOK, "Edit Details",
                    List.of("Open the editable title and", "description form."), NamedTextColor.AQUA));
            session.actions.put(15, new MenuAction(ActionType.EDIT_SUBMISSION, entry.id(), null, 0));
        }

        inventory.setItem(16, item(Material.ENDER_EYE, "Visit Build",
                List.of("Open this entry in Visitor Mode."), NamedTextColor.YELLOW));
        session.actions.put(16, new MenuAction(ActionType.VISIT_ENTRY, entry.id(), null, 0));

        inventory.setItem(18, item(Material.PAINTING, "Website Preview",
                List.of("See your camera images on the website.", "Draft previews use a private link."), NamedTextColor.AQUA));
        session.actions.put(18, new MenuAction(ActionType.OPEN_WEBSITE, entry.id(), null, 0));

        inventory.setItem(19, item(Material.ENDER_EYE, "Camera Views",
                List.of("Save, preview, replace or remove a view.", "Save at least one view before submitting."), NamedTextColor.AQUA));
        session.actions.put(19, new MenuAction(ActionType.OPEN_CAMERA_CONTROLS, entry.id(), null, 0));
        inventory.setItem(20, item(Material.FILLED_MAP, "Build Boundary",
                List.of("See exactly where you can build.", "Your selected area is saved with this entry."), NamedTextColor.AQUA));
        session.actions.put(20, new MenuAction(ActionType.SHOW_BOUNDARY, entry.id(), null, 0));

        inventory.setItem(21, item(entry.submitted() ? Material.LIME_DYE : Material.TRIPWIRE_HOOK,
                preparing ? "Cancel Submission Preparation" : entry.submitted() ? "Resume Editing" : "Submit Entry",
                entry.submitted()
                        ? List.of("Unlock the entry and return to", "Owner Mode before the deadline.")
                        : List.of("Generate fresh images and publish automatically.", "Your build becomes read-only."),
                entry.submitted() ? NamedTextColor.YELLOW : NamedTextColor.GREEN));
        session.actions.put(21, new MenuAction(
                entry.submitted() || preparing ? ActionType.TOGGLE_SUBMISSION : ActionType.CONFIRM_SUBMISSION,
                entry.id(), null, 0));

        inventory.setItem(22, item(Material.COMPARATOR, "Project Settings",
                List.of("Change category, reset, or delete this project."), NamedTextColor.GRAY));
        session.actions.put(22, new MenuAction(ActionType.OPEN_SETTINGS, entry.id(), null, 0));

        inventory.setItem(26, item(Material.COMPASS, "Back to Main Menu", List.of(), NamedTextColor.GOLD));
        session.actions.put(26, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));

        presentMenu(player, session);
    }

    private void openProjectSettings(Player player, Entry entry) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 27, Component.text("Project Settings", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.COMPARATOR, "Manage this project",
                List.of("These actions change or remove your build.", "You will confirm before anything is replaced."), NamedTextColor.YELLOW));
        if (entry.submitted()) {
            inventory.setItem(20, item(Material.GRAY_DYE, "Category Change Locked",
                    List.of("Resume editing before changing", "this entry's category."), NamedTextColor.GRAY));
        } else {
            inventory.setItem(20, item(Material.RECOVERY_COMPASS, "Change Category",
                    List.of("Choose a different competition category.", "This replaces the entire build space."),
                    NamedTextColor.YELLOW));
            session.actions.put(20, new MenuAction(ActionType.OPEN_CATEGORY_SWITCH, entry.id(), null, 0));
        }

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

        inventory.setItem(26, item(Material.ARROW, "Back to Build Options", List.of(), NamedTextColor.GOLD));
        session.actions.put(26, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        presentMenu(player, session);
    }

    private void openTeam(Player player, Entry entry, int page) {
        if (!entry.isMember(competition.participantKey(player))) return;
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 54, Component.text("Project Team", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.PLAYER_HEAD, "Build together",
                List.of("Up to two students per project.", "Choose an online student to invite.", "Invites last five minutes."), NamedTextColor.GOLD));
        List<Player> candidates = Bukkit.getOnlinePlayers().stream().filter(competition::isAuthenticated)
                .filter(other -> !entry.isMember(competition.participantKey(other)))
                .filter(other -> competition.entriesFor(competition.participantKey(other)).size() < 2)
                .filter(other -> competition.entriesFor(competition.participantKey(other)).stream()
                        .noneMatch(existing -> existing.category() == entry.category()))
                .sorted(Comparator.comparing(Player::getName)).map(other -> (Player) other).toList();
        page = Math.clamp(page, 0, Math.max(0, (candidates.size() - 1) / 28));
        boolean editable = !entry.submitted() && !competition.isPreparingSubmission(entry);
        if (editable && entry.members().size() < 2) {
            for (int offset = 0; offset < 28 && page * 28 + offset < candidates.size(); offset++) {
                Player other = candidates.get(page * 28 + offset);
                int slot = 10 + offset / 7 * 9 + offset % 7;
                inventory.setItem(slot, item(Material.PLAYER_HEAD, "Invite " + other.getName(),
                        List.of("They can accept from the Competition Compass."), NamedTextColor.GREEN));
                session.actions.put(slot, new MenuAction(ActionType.INVITE_MEMBER, entry.id(), null, page, other.getName()));
            }
        } else {
            inventory.setItem(13, item(Material.GRAY_DYE, editable ? "Team is full" : "Resume editing to change the team", List.of(), NamedTextColor.GRAY));
        }
        if (editable && candidates.isEmpty() && entry.members().size() < 2) {
            inventory.setItem(13, item(Material.GRAY_DYE, "No available students online",
                    List.of("Ask a friend to sign in, then reopen Team."), NamedTextColor.GRAY));
        }
        if (page > 0) {
            inventory.setItem(45, item(Material.ARROW, "Previous", List.of(), NamedTextColor.GOLD));
            session.actions.put(45, new MenuAction(ActionType.OPEN_TEAM, entry.id(), null, page - 1));
        }
        if ((page + 1) * 28 < candidates.size()) {
            inventory.setItem(53, item(Material.ARROW, "Next", List.of(), NamedTextColor.GOLD));
            session.actions.put(53, new MenuAction(ActionType.OPEN_TEAM, entry.id(), null, page + 1));
        }
        if (editable) {
            inventory.setItem(50, item(Material.OAK_DOOR, "Leave Team",
                    List.of(entry.members().size() == 1 ? "Leaving alone deletes this project. Confirmation required." : "Your teammate keeps the project. Confirmation required."), NamedTextColor.YELLOW));
            session.actions.put(50, new MenuAction(ActionType.CONFIRM_LEAVE_TEAM, entry.id(), null, 0));
        }
        inventory.setItem(49, item(Material.ARROW, "Back to Build Options", List.of(), NamedTextColor.GOLD));
        session.actions.put(49, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        presentMenu(player, session);
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
        Inventory inventory = createInventory(holder, 9,
                Component.text("Enter Survival", NamedTextColor.GREEN));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        inventory.setItem(4, item(Material.GRASS_BLOCK, "Enter Survival",
                List.of("Resume your survival world."), NamedTextColor.GREEN));
        session.actions.put(4, new MenuAction(ActionType.ENTER_SURVIVAL, null, null, 0));
        presentMenu(player, session);
    }

    public void showBuildingMap(Player player) {
        choosingSingleBuilding.remove(player.getUniqueId());
        if (worlds.isSurvivalWorld(player.getWorld())) competition.teleportHub(player);
        choosingBuilding.add(player.getUniqueId());
        openAreaList(player);
    }

    private void openAreaList(Player player) {
        List<CampusAreaCatalog.Area> areas;
        try {
            areas = worlds.areas();
        } catch (IllegalStateException exception) {
            player.sendMessage(Component.text(exception.getMessage(), NamedTextColor.RED));
            openMain(player);
            return;
        }
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 27, Component.text("Choose a Campus Area", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.FILLED_MAP, "Your campus area",
                List.of("Choose an area, build, capture, then submit.", "Each project gets a private copy of the campus."), NamedTextColor.GOLD));
        UUID switchId = buildingSwitches.get(player.getUniqueId());
        for (int index = 0; index < areas.size() && index < 7; index++) {
            CampusAreaCatalog.Area area = areas.get(index);
            int slot = 10 + index;
            inventory.setItem(slot, item(Material.GRASS_BLOCK, area.name(),
                    List.of(area.description(), area.blocks() + " ground blocks", "Review this area before starting."), NamedTextColor.GREEN));
            session.actions.put(slot, new MenuAction(ActionType.PREVIEW_AREA, switchId, Category.PLACE, 0, area.id()));
        }
        inventory.setItem(22, item(Material.BRICKS, "Choose a Single Building",
                List.of("Prefer a smaller project? Open the building map."), NamedTextColor.AQUA));
        session.actions.put(22, new MenuAction(ActionType.SINGLE_BUILDING, switchId, Category.PLACE, 0));
        inventory.setItem(26, item(Material.COMPASS, "Back to Main Menu", List.of(), NamedTextColor.GOLD));
        session.actions.put(26, new MenuAction(ActionType.CANCEL_BUILDING, null, null, 0));
        presentMenu(player, session);
    }

    private void previewArea(Player player, MenuAction action) {
        worlds.area(action.buildingId).ifPresent(area -> {
            HillMenuHolder holder = new HillMenuHolder();
            Inventory inventory = createInventory(holder, 27, Component.text(area.name(), NamedTextColor.GOLD));
            holder.inventory = inventory;
            MenuSession session = new MenuSession(inventory);
            fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
            List<String> description = new ArrayList<>(List.of(area.description(), "Editable rectangles (X, Z):"));
            for (var part : area.parts()) description.add(part.minX() + ", " + part.minZ() + " to " + part.maxX() + ", " + part.maxZ());
            description.add("Only these rectangles can be changed.");
            description.add("Capture a view and submit from Build Options.");
            inventory.setItem(4, item(Material.FILLED_MAP, area.name(), description, NamedTextColor.GOLD));
            inventory.setItem(11, item(Material.LIME_CONCRETE, action.entryId == null ? "Build Here" : "Replace Entry with This Area",
                    action.entryId == null ? List.of("Create your private campus area.")
                            : List.of("Replaces the current build, details and cameras."), NamedTextColor.GREEN));
            session.actions.put(11, new MenuAction(ActionType.CREATE_BUILDING, action.entryId, Category.PLACE, 0, area.id()));
            inventory.setItem(15, item(Material.ARROW, "Choose Another Area", List.of(), NamedTextColor.YELLOW));
            session.actions.put(15, new MenuAction(ActionType.AREA_LIST, action.entryId, Category.PLACE, 0));
            presentMenu(player, session);
        });
    }

    private void showBoundary(Player player, Entry entry) {
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 27, Component.text("Your Build Boundary", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        List<String> lines = new ArrayList<>(List.of("Editable rectangles (inclusive X, Z):"));
        for (var part : entry.editableRegions()) lines.add(part.minX() + ", " + part.minZ() + " to " + part.maxX() + ", " + part.maxZ());
        lines.add("Your map outlines these rectangles in green.");
        lines.add("Outside them you can explore and take photos.");
        inventory.setItem(4, item(Material.FILLED_MAP, "Where you can build", lines, NamedTextColor.GOLD));
        inventory.setItem(11, item(Material.ENDER_PEARL, "Return to My Build", List.of(), NamedTextColor.GREEN));
        session.actions.put(11, new MenuAction(ActionType.ENTER_BUILD, entry.id(), null, 0));
        inventory.setItem(15, item(Material.ARROW, "Back to Build Options", List.of(), NamedTextColor.YELLOW));
        session.actions.put(15, new MenuAction(ActionType.OPEN_ENTRY, entry.id(), null, 0));
        presentMenu(player, session);
    }

    private void showSingleBuildingMap(Player player) {
        choosingSingleBuilding.add(player.getUniqueId());
        try {
            if (worlds.buildings().isEmpty()) throw new IllegalStateException("No buildings are available yet.");
        } catch (IllegalStateException exception) {
            player.sendMessage(Component.text(exception.getMessage(), NamedTextColor.RED));
            return;
        }
        if (worlds.isSurvivalWorld(player.getWorld())) {
            competition.teleportHub(player);
        }
        choosingBuilding.add(player.getUniqueId());
        player.closeInventory();
        if (showNativeCampusMap(player, true)) return;
        competition.giveCampusSelectionMap(player);
        player.getInventory().setHeldItemSlot(1);
        openBuildingList(player, true, 0);
        player.sendMessage(Component.text("Choose your building", NamedTextColor.GOLD));
        player.sendMessage(Component.text("Hold the map to see numbered buildings. Right-click to choose one. You can edit inside and outside.", NamedTextColor.GRAY));
    }

    public void openCampusMap(Player player) {
        if (campusWorkshop != null && worlds.sharedCampusEntry().isPresent()) {
            campusWorkshop.accept(player);
            return;
        }
        Entry current = competition.currentEntry(player).orElse(null);
        boolean selecting = choosingBuilding.contains(player.getUniqueId())
                || current == null || (!WorldModule.isPrivatePlace(current) && current.category() != Category.PEOPLE);
        if (selecting && !choosingSingleBuilding.contains(player.getUniqueId())) openAreaList(player);
        else if (!showNativeCampusMap(player, selecting)) openBuildingList(player, selecting, 0);
    }

    private boolean showNativeCampusMap(Player player, boolean selecting) {
        if (!bedrockForms.isBedrock(player)) return false;
        List<BuildingCatalog.Building> buildings = worlds.buildings();
        List<String> buttons = new ArrayList<>(buildings.stream().map(BuildingCatalog.Building::name).toList());
        buttons.add("Back to projects");
        UUID switchId = buildingSwitches.get(player.getUniqueId());
        sessions.remove(player.getUniqueId());
        return bedrockForms.show(player, "Hill Campus Map",
                selecting ? "Choose a building to make your own. Tap a building on the map to see more."
                        : "Tap a building to explore it. Editing remains limited to your project's saved boundary.",
                buttons, index -> {
                    if (!competition.isAuthenticated(player)) return;
                    if (index == buildings.size()) {
                        choosingBuilding.remove(player.getUniqueId());
                        buildingSwitches.remove(player.getUniqueId());
                        openMain(player);
                    } else if (index >= 0 && index < buildings.size()) {
                        BuildingCatalog.Building building = buildings.get(index);
                        if (selecting) previewBuilding(player, new MenuAction(ActionType.PREVIEW_BUILDING,
                                switchId, Category.PLACE, 0, building.id()));
                        else showBuildingDirections(player, building.id());
                    }
                }, () -> {});
    }

    public void showWebsite(Player player, Entry entry) {
        if (!entry.isMember(competition.participantKey(player)) && !entry.submitted()) {
            player.sendMessage(Component.text("Only this entry's team can open its draft preview.", NamedTextColor.RED));
            return;
        }
        String link = competition.galleryLink(entry);
        player.closeInventory();
        if (link == null || link.isBlank()) {
            player.sendMessage(Component.text("The website preview is not configured yet.", NamedTextColor.YELLOW));
            return;
        }
        player.sendMessage(Component.text("Open Website Preview", NamedTextColor.AQUA)
                .clickEvent(ClickEvent.openUrl(link)));
        player.sendMessage(Component.text("Camera images appear automatically after capture.", NamedTextColor.GRAY));
    }

    public void requestCameraSave(Player player, int slot) {
        competition.currentEntry(player).ifPresentOrElse(entry -> {
            if (!competition.canEditEntry(player, entry)) {
                player.sendMessage(Component.text("Open an editable entry that you own first.", NamedTextColor.RED));
            } else if (entry.cameraPose(slot).isPresent()) {
                openCameraReplaceConfirmation(player, entry, slot);
            } else {
                competition.recordCamera(player, slot);
            }
        }, () -> player.sendMessage("Open your build before saving a camera."));
    }

    public void requestCameraRemove(Player player, int slot) {
        competition.currentEntry(player).ifPresentOrElse(entry -> {
            if (!competition.canEditEntry(player, entry) || entry.cameraPose(slot).isEmpty()) {
                player.sendMessage(Component.text("Choose a saved camera in your editable entry.", NamedTextColor.RED));
            } else {
                openCameraRemoveConfirmation(player, entry, slot);
            }
        }, () -> player.sendMessage("Open your build before removing a camera."));
    }

    private void openBuildingList(Player player, boolean selecting, int page) {
        List<BuildingCatalog.Building> buildings;
        try {
            buildings = worlds.buildings();
        } catch (IllegalStateException exception) {
            player.sendMessage(Component.text(exception.getMessage(), NamedTextColor.RED));
            return;
        }
        int pageSize = 28;
        int lastPage = Math.max(0, (buildings.size() - 1) / pageSize);
        page = Math.max(0, Math.min(page, lastPage));
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 54,
                Component.text(selecting ? "Choose a Hill Building" : "Campus Navigation", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(4, item(Material.FILLED_MAP, selecting ? "Your building, inside and out" : "Find your way",
                List.of("Numbers match the map in your hand.", selecting
                        ? "Select a building to review its build area." : "Select a building for its location."), NamedTextColor.GOLD));
        UUID switchId = buildingSwitches.get(player.getUniqueId());
        for (int offset = 0; offset < pageSize && page * pageSize + offset < buildings.size(); offset++) {
            BuildingCatalog.Building building = buildings.get(page * pageSize + offset);
            int slot = 10 + (offset / 7) * 9 + offset % 7;
            inventory.setItem(slot, item(Material.BRICKS, "#" + building.mapNumber() + " " + building.name(),
                    List.of(building.width() + " x " + building.depth() + " blocks, plus outdoor space",
                            selecting ? "Click to preview your choice." : "Click to show location and direction."), NamedTextColor.WHITE));
            session.actions.put(slot, new MenuAction(selecting ? ActionType.PREVIEW_BUILDING : ActionType.BUILDING_DIRECTIONS,
                    switchId, Category.PLACE, page, building.id()));
        }
        if (page > 0) {
            inventory.setItem(45, item(Material.ARROW, "Previous", List.of(), NamedTextColor.GOLD));
            session.actions.put(45, new MenuAction(selecting ? ActionType.BUILDING_PAGE : ActionType.NAVIGATION_PAGE, switchId, null, page - 1));
        }
        if (page < lastPage) {
            inventory.setItem(53, item(Material.ARROW, "Next", List.of(), NamedTextColor.GOLD));
            session.actions.put(53, new MenuAction(selecting ? ActionType.BUILDING_PAGE : ActionType.NAVIGATION_PAGE, switchId, null, page + 1));
        }
        inventory.setItem(49, item(Material.FILLED_MAP, "View Map", List.of("Close this menu and hold your map.", "Right-click the map to return."), NamedTextColor.AQUA));
        session.actions.put(49, new MenuAction(ActionType.CLOSE_MENU, null, null, 0));
        inventory.setItem(48, item(Material.COMPASS, "Main Menu", List.of(), NamedTextColor.GOLD));
        session.actions.put(48, new MenuAction(ActionType.CANCEL_BUILDING, null, null, 0));
        presentMenu(player, session);
    }

    private void previewBuilding(Player player, MenuAction action) {
        worlds.building(action.buildingId).ifPresent(building -> {
            HillMenuHolder holder = new HillMenuHolder();
            Inventory inventory = createInventory(holder, 27, Component.text(building.name(), NamedTextColor.GOLD));
            holder.inventory = inventory;
            MenuSession session = new MenuSession(inventory);
            fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
            inventory.setItem(4, item(Material.BRICKS, "#" + building.mapNumber() + " " + building.name(),
                    List.of("Original building: " + building.width() + " x " + building.depth() + " blocks",
                            "Private campus copy with outdoor space.", "Change walls, roof, rooms and furnishings."), NamedTextColor.GOLD));
            inventory.setItem(11, item(Material.LIME_CONCRETE, action.entryId == null ? "Build Here" : "Replace Entry with This Building",
                    action.entryId == null ? List.of("Create your private building area.")
                            : List.of("Replaces your current entry's blocks,", "title, description and camera views."), NamedTextColor.GREEN));
            session.actions.put(11, new MenuAction(ActionType.CREATE_BUILDING, action.entryId, Category.PLACE, 0, building.id()));
            inventory.setItem(15, item(Material.ARROW, "Choose Another Building", List.of(), NamedTextColor.YELLOW));
            session.actions.put(15, new MenuAction(ActionType.BUILDING_PAGE, action.entryId, Category.PLACE, action.page));
            presentMenu(player, session);
        });
    }

    private void showBuildingDirections(Player player, String buildingId) {
        worlds.building(buildingId).ifPresent(building -> {
            HillMenuHolder holder = new HillMenuHolder();
            Inventory inventory = createInventory(holder, 27, Component.text(building.name(), NamedTextColor.GOLD));
            holder.inventory = inventory;
            MenuSession session = new MenuSession(inventory);
            fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
            inventory.setItem(4, item(Material.FILLED_MAP, building.name(),
                    List.of("X " + building.centerX() + ", Z " + building.centerZ(),
                            "Visiting does not change your editable area."), NamedTextColor.GOLD));
            inventory.setItem(11, item(Material.ENDER_PEARL, "Go here",
                    List.of("Travel if this destination is inside your visiting area."), NamedTextColor.GREEN));
            session.actions.put(11, new MenuAction(ActionType.TRAVEL_BUILDING, null, null, 0, buildingId));
            inventory.setItem(15, item(Material.ARROW, "Back to campus map", List.of(), NamedTextColor.YELLOW));
            session.actions.put(15, new MenuAction(ActionType.NAVIGATION_PAGE, null, null, 0));
            presentMenu(player, session);
        });
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
        boolean editor = competition.canEditEntry(player, entry);
        boolean owner = entry.isMember(competition.participantKey(player));
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 27,
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
        presentMenu(player, session);
    }

    private void openCameraSlotControls(Player player, Entry entry, int cameraSlot) {
        if (!competition.canEditEntry(player, entry) || entry.cameraPose(cameraSlot).isEmpty()) {
            openCameraControls(player, entry);
            return;
        }
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 9,
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
        presentMenu(player, session);
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
            if (!competition.canEditEntry(player, context.entry())) {
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
        Inventory inventory = createInventory(holder, 9, Component.text(menuTitle, NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(2, item(warningMaterial, warningTitle, warningLore, NamedTextColor.RED));
        inventory.setItem(4, item(Material.LIME_CONCRETE, confirmTitle, List.of("Click to continue."), NamedTextColor.GREEN));
        session.actions.put(4, new MenuAction(confirmAction, entry.id(), null, cameraSlot));
        inventory.setItem(6, item(Material.RED_CONCRETE, "Back Without Changes", List.of(), NamedTextColor.RED));
        session.actions.put(6, new MenuAction(ActionType.OPEN_CAMERA_CONTROLS, entry.id(), null, 0));
        presentMenu(player, session);
    }

    public void openVisits(Player player, int page) {
        List<Entry> entries = competition.allEntries().stream()
                .sorted(Comparator.comparing((Entry entry) -> entry.category().displayName())
                        .thenComparing(entry -> entry.title().toLowerCase()))
                .toList();
        int maxPage = Math.max(0, (entries.size() - 1) / VISIT_PAGE_SIZE);
        int safePage = Math.max(0, Math.min(page, maxPage));
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 54,
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

        presentMenu(player, session);
    }

    private void openCreateConfirmation(Player player, Category category) {
        if (category == Category.PLACE) {
            showBuildingMap(player);
            return;
        }
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 9,
                Component.text("Create " + category.displayName() + "?", NamedTextColor.GOLD));
        holder.inventory = inventory;
        MenuSession session = new MenuSession(inventory);
        fill(inventory, Material.GRAY_STAINED_GLASS_PANE);
        inventory.setItem(3, item(Material.LIME_CONCRETE, "Create Entry",
                List.of("Go straight to your new build.", "Add a title and description whenever you're ready."), NamedTextColor.GREEN));
        session.actions.put(3, new MenuAction(ActionType.CREATE_ENTRY, null, category, 0));
        inventory.setItem(5, item(Material.RED_CONCRETE, "Cancel", List.of(), NamedTextColor.RED));
        session.actions.put(5, new MenuAction(ActionType.OPEN_MAIN, null, null, 0));
        presentMenu(player, session);
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
        if (entry.cameraPoses().isEmpty()) {
            player.sendMessage(Component.text("Save a camera view, then choose Submit Entry in Build Options.", NamedTextColor.YELLOW));
            openCameraControls(player, entry);
            return;
        }
        openEntryConfirmation(
                player,
                entry,
                "Submit this entry?",
                Material.TRIPWIRE_HOOK,
                "Ready to share your build?",
                List.of(
                        "Title: " + (entry.title().isBlank() ? "use category name" : "ready"),
                        "Description: " + (entry.description().isBlank() ? "optional" : "ready"),
                        "Cameras: " + entry.cameraPoses().size() + "/3",
                        "Images are captured and published automatically.",
                        "Your build locks after the images are ready."
                ),
                "Confirm Submission",
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
        Inventory inventory = createInventory(holder, 27,
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
        presentMenu(player, session);
    }

    public void openCategorySwitchConfirmation(Player player, Entry entry, Category category) {
        if (category == Category.PLACE) {
            buildingSwitches.put(player.getUniqueId(), entry.id());
            showBuildingMap(player);
            return;
        }
        HillMenuHolder holder = new HillMenuHolder();
        Inventory inventory = createInventory(holder, 9,
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
        presentMenu(player, session);
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
        Inventory inventory = createInventory(holder, 9, Component.text(menuTitle, NamedTextColor.GOLD));
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
        presentMenu(player, session);
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
        if (bedrockForms.showFields(player, "About your build", "Add a title and a short description. Choose Submit to save.",
                List.of(new BedrockForms.Field("title", "Build title", initialTitle, Entry.MAX_TITLE_LENGTH),
                        new BedrockForms.Field("description", "Description", initialDescription, Entry.MAX_DESCRIPTION_LENGTH)),
                values -> {
                    CompetitionModule.DetailsUpdateResult result = competition.saveSubmissionDetails(
                            player, entry, values.get(0).trim(), values.get(1).trim());
                    if (result == CompetitionModule.DetailsUpdateResult.SAVED) openEntryDetails(player, entry);
                    else if (result == CompetitionModule.DetailsUpdateResult.INVALID_DETAILS)
                        openSubmissionDialog(player, entry, false, values.get(0), values.get(1));
                }, () -> {})) return;
        player.sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                .append(Component.text("Add a title and description whenever you're ready.", NamedTextColor.YELLOW)
                        .decoration(TextDecoration.BOLD, false)));
        DialogBase base = DialogBase.builder(Component.text("Submission Details", NamedTextColor.GOLD))
                .externalTitle(Component.text("Edit Hill 175 Submission"))
                .canCloseWithEscape(true)
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
                                .maxLength(Entry.MAX_TITLE_LENGTH)
                                .build(),
                        DialogInput.text("description", Component.text("Description", NamedTextColor.WHITE))
                                .width(360)
                                .initial(initialDescription)
                                .maxLength(Entry.MAX_DESCRIPTION_LENGTH)
                                .multiline(TextDialogInput.MultilineOptions.create(12, 140))
                                .build()
                ))
                .build();
        ActionButton save = ActionButton.create(
                Component.text("Save Details", NamedTextColor.GREEN),
                Component.text("Save the title and description."),
                170,
                DialogAction.customClick(SAVE_SUBMISSION_ACTION, null)
        );
        ActionButton cancel = ActionButton.create(
                Component.text(newlyCreated ? "Start Building" : "Back Without Saving", NamedTextColor.YELLOW),
                Component.text(newlyCreated ? "Keep the entry and add details later." : "Return to entry controls."),
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
        executeAction(player, action);
    }

    private void executeAction(Player player, MenuAction action) {
        if (!competition.isAuthenticated(player)) {
            competition.sendAuthenticationInstructions(player);
            return;
        }
        switch (action.type) {
            case OPEN_TEAM -> competition.entry(action.entryId).ifPresent(entry -> openTeam(player, entry, action.page));
            case INVITE_MEMBER -> competition.entry(action.entryId).ifPresent(entry -> {
                competition.invite(player, entry, action.buildingId);
                openTeam(player, entry, action.page);
            });
            case ACCEPT_INVITE -> {
                player.closeInventory();
                competition.acceptInvite(player, action.buildingId);
            }
            case CONFIRM_LEAVE_TEAM -> competition.entry(action.entryId).ifPresent(entry -> openEntryConfirmation(
                    player, entry, "Leave this team?", Material.OAK_DOOR, "Leave Team",
                    List.of(entry.members().size() == 1 ? "You are the only member. This deletes the project." : "Your teammate keeps the project."),
                    "Confirm Leave", ActionType.LEAVE_TEAM));
            case LEAVE_TEAM -> competition.entry(action.entryId).ifPresent(entry -> {
                player.closeInventory();
                competition.leaveTeam(player, entry);
            });
            case AREA_LIST -> openAreaList(player);
            case PREVIEW_AREA -> previewArea(player, action);
            case SINGLE_BUILDING -> showSingleBuildingMap(player);
            case SHOW_BOUNDARY -> competition.entry(action.entryId).ifPresent(entry -> showBoundary(player, entry));
            case OPEN_WEBSITE -> competition.entry(action.entryId).ifPresent(entry -> showWebsite(player, entry));
            case CANCEL_BUILDING -> {
                choosingSingleBuilding.remove(player.getUniqueId());
                choosingBuilding.remove(player.getUniqueId());
                buildingSwitches.remove(player.getUniqueId());
                openMain(player);
            }
            case BUILDING_PAGE -> { if (!showNativeCampusMap(player, true)) openBuildingList(player, true, action.page); }
            case NAVIGATION_PAGE -> { if (!showNativeCampusMap(player, false)) openBuildingList(player, false, action.page); }
            case PREVIEW_BUILDING -> previewBuilding(player, action);
            case BUILDING_DIRECTIONS -> showBuildingDirections(player, action.buildingId);
            case TRAVEL_BUILDING -> {
                player.closeInventory();
                competition.travelToBuilding(player, action.buildingId);
            }
            case CREATE_BUILDING -> {
                choosingSingleBuilding.remove(player.getUniqueId());
                player.closeInventory();
                choosingBuilding.remove(player.getUniqueId());
                buildingSwitches.remove(player.getUniqueId());
                if (action.entryId == null) {
                    competition.createEntry(player, Category.PLACE, action.buildingId);
                } else {
                    competition.entry(action.entryId).ifPresent(entry ->
                            competition.switchEntry(player, entry, Category.PLACE, action.buildingId));
                }
            }
            case OPEN_SETTINGS -> competition.entry(action.entryId).ifPresent(entry -> openProjectSettings(player, entry));
            case OPEN_MAIN -> openMain(player);
            case OPEN_WORKSHOP -> {
                if (campusWorkshop != null) campusWorkshop.accept(player);
                else openCategory(player, Category.PEOPLE);
            }
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
                competition.createEntry(player, action.category);
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
                if (entry.submitted() || competition.isPreparingSubmission(entry)) {
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
        choosingBuilding.remove(playerId);
        choosingSingleBuilding.remove(playerId);
        buildingSwitches.remove(playerId);
        bedrockForms.clear(event.getPlayer());
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
                    player.sendMessage(Component.text("Your building is ready. Add a title later in Entry Controls.", NamedTextColor.GREEN));
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
            CompetitionModule.DetailsUpdateResult result = competition.saveSubmissionDetails(player, entry, title, description);
            if (result == CompetitionModule.DetailsUpdateResult.INVALID_DETAILS) {
                openSubmissionDialog(
                        player,
                        entry,
                        prompt.newlyCreated(),
                        title.substring(0, Math.min(title.length(), Entry.MAX_TITLE_LENGTH)),
                        description.substring(0, Math.min(description.length(), Entry.MAX_DESCRIPTION_LENGTH))
                );
                return;
            }
            if (result == CompetitionModule.DetailsUpdateResult.SAVED) {
                Bukkit.getScheduler().runTaskLater(plugin, () -> openEntryDetails(player, entry), 1L);
            }
        });
    }

    private ItemStack entryCard(Entry entry, boolean ownEntry) {
        List<String> lore = new ArrayList<>();
        lore.add(entry.category().displayName());
        lore.add(entry.title().isBlank() ? "Untitled project" : entry.title());
        lore.add(entry.submitted() ? "Submitted and locked" : "Building open");
        lore.add(ownEntry ? "Click to open entry controls." : "Click to visit.");
        return item(entry.category().icon(), (ownEntry ? "Continue " : "") + (entry.title().isBlank() ? entry.category().displayName() : entry.title()), lore,
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
            case JOURNEY -> List.of("Build a Hill spot or landmark.", "64 x 64 outdoor plot.");
            case PLACE -> List.of("Choose your own campus area.", "Build, capture a view, then submit.");
            case PEOPLE -> List.of("Recreate a Hill scene.", "Your own copy of the campus.");
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

    private static Inventory createInventory(HillMenuHolder holder, int size, Component title) {
        holder.title = title;
        return Bukkit.createInventory(holder, size, title);
    }

    /** Use touch-friendly native actions on Bedrock and inventory controls on Java. */
    private void presentMenu(Player player, MenuSession session) {
        sessions.put(player.getUniqueId(), session);
        if (bedrockForms.isBedrock(player)) {
            player.closeInventory();
            List<Integer> slots = session.actions.keySet().stream().sorted().toList();
            List<String> labels = slots.stream().map(slot -> {
                ItemMeta meta = session.inventory.getItem(slot).getItemMeta();
                String label = plain(meta.displayName());
                List<Component> lore = meta.lore();
                if (lore != null && !lore.isEmpty()) label += "\n" + plain(lore.getFirst());
                return label;
            }).toList();
            List<String> descriptions = new ArrayList<>();
            for (int slot = 0; slot < session.inventory.getSize(); slot++) {
                if (session.actions.containsKey(slot)) continue;
                ItemStack card = session.inventory.getItem(slot);
                if (card == null || !card.hasItemMeta()) continue;
                ItemMeta meta = card.getItemMeta();
                if (plain(meta.displayName()).isBlank()) continue;
                descriptions.add(plain(meta.displayName()));
                if (meta.hasLore()) descriptions.addAll(meta.lore().stream().map(MenuModule::plain).toList());
            }
            String content = String.join("\n", descriptions);
            String title = plain(((HillMenuHolder) session.inventory.getHolder()).title);
            if (bedrockForms.show(player, title, content, labels, index -> {
                if (sessions.get(player.getUniqueId()) != session || index < 0 || index >= slots.size()) return;
                sessions.remove(player.getUniqueId(), session);
                executeAction(player, session.actions.get(slots.get(index)));
            }, () -> sessions.remove(player.getUniqueId(), session))) return;
        }
        player.openInventory(session.inventory);
    }

    private static String plain(Component text) {
        return text == null ? "" : PlainTextComponentSerializer.plainText().serialize(text);
    }

    public void shutdown() {
        bedrockForms.close();
        sessions.clear();
        submissionPrompts.clear();
    }

    private enum ActionType {
        OPEN_WORKSHOP,
        OPEN_TEAM,
        INVITE_MEMBER,
        ACCEPT_INVITE,
        CONFIRM_LEAVE_TEAM,
        LEAVE_TEAM,
        AREA_LIST,
        PREVIEW_AREA,
        SINGLE_BUILDING,
        SHOW_BOUNDARY,
        TRAVEL_BUILDING,
        OPEN_WEBSITE,
        CANCEL_BUILDING,
        BUILDING_PAGE,
        NAVIGATION_PAGE,
        PREVIEW_BUILDING,
        BUILDING_DIRECTIONS,
        CREATE_BUILDING,
        OPEN_SETTINGS,
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

    private record MenuAction(ActionType type, UUID entryId, Category category, int page, String buildingId) {
        MenuAction(ActionType type, UUID entryId, Category category, int page) {
            this(type, entryId, category, page, null);
        }
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
        private Component title;

        @Override
        public Inventory getInventory() {
            return inventory;
        }
    }
}
