package org.thehill.hill175.competition;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.text.event.ClickEvent;
import io.papermc.paper.datacomponent.DataComponentTypes;
import io.papermc.paper.datacomponent.item.Consumable;
import io.papermc.paper.datacomponent.item.consumable.ItemUseAnimation;
import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.Sound;
import org.bukkit.World;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.inventory.EntityEquipment;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.PlayerInventory;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.model.Account;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.world.WorldModule;

import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

public final class CompetitionModule {
    public static final String COMPASS_ITEM_ID = "competition-compass";
    public static final String CAMERA_ITEM_ID = "submission-camera";
    public static final String ENTRY_MENU_ITEM_ID = "entry-controls";
    public static final String ENTRY_RESET_ITEM_ID = "entry-reset";
    public static final String ENTRY_SUBMIT_ITEM_ID = "entry-submit-toggle";
    public static final String CAMERA_PREVIEW_ITEM_ID = "camera-preview";
    public static final String RULES_ITEM_ID = "competition-rules";
    public static final String LOBBY_ITEM_ID = "return-lobby";
    private static final Pattern NICKNAME_PATTERN = Pattern.compile("^[A-Za-z0-9_]{3,16}$");
    private static final int MAX_TITLE_LENGTH = 80;
    private static final int MAX_DESCRIPTION_LENGTH = 750;
    private static final String CAMERA_MARKER_TAG = "hill175_camera_marker";
    private static final String CAMERA_MARKER_ENTRY_PREFIX = "hill175_camera_entry_";
    private static final String CAMERA_MARKER_INDEX_PREFIX = "hill175_camera_index_";

    private final JavaPlugin plugin;
    private final CompetitionStore store;
    private final WorldModule worlds;
    private final PasswordHasher passwordHasher;
    private final IdentityLinker identityLinker;
    private final NamespacedKey itemKey;
    private final Set<UUID> authenticatedSessions = ConcurrentHashMap.newKeySet();
    private final Set<UUID> pendingRegistrations = ConcurrentHashMap.newKeySet();
    private final Map<UUID, UUID> currentEntryByPlayer = new HashMap<>();
    private final Map<String, TeamInvite> invitesByTarget = new HashMap<>();
    private final Map<UUID, FailureWindow> loginFailures = new HashMap<>();
    private final Map<UUID, Integer> nextPreviewIndexByPlayer = new HashMap<>();
    private final Map<UUID, Integer> nextCameraWriteIndexByPlayer = new HashMap<>();
    private final Map<UUID, UUID> pendingPeopleEntryByPlayer = new HashMap<>();

    public CompetitionModule(
            JavaPlugin plugin,
            CompetitionStore store,
            WorldModule worlds,
            PasswordHasher passwordHasher,
            IdentityLinker identityLinker
    ) {
        this.plugin = plugin;
        this.store = store;
        this.worlds = worlds;
        this.passwordHasher = passwordHasher;
        this.identityLinker = identityLinker;
        this.itemKey = new NamespacedKey(plugin, "item-id");
    }

    public void handleJoin(Player player) {
        store.recordConnection(nicknameKey(player.getName()), connectionAddress(player), "join");
        authenticatedSessions.remove(player.getUniqueId());
        pendingRegistrations.remove(player.getUniqueId());
        currentEntryByPlayer.remove(player.getUniqueId());
        nextPreviewIndexByPlayer.remove(player.getUniqueId());
        nextCameraWriteIndexByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        player.getInventory().clear();
        player.setGameMode(GameMode.ADVENTURE);
        player.setAllowFlight(false);
        player.setFlying(false);
        player.teleport(worlds.authenticationSpawn());
        showAuthenticationTitle(player);
        sendAuthenticationInstructions(player);
    }

    public void handleQuit(Player player) {
        store.recordConnection(nicknameKey(player.getName()), connectionAddress(player), "quit");
        authenticatedSessions.remove(player.getUniqueId());
        pendingRegistrations.remove(player.getUniqueId());
        currentEntryByPlayer.remove(player.getUniqueId());
        loginFailures.remove(player.getUniqueId());
        nextPreviewIndexByPlayer.remove(player.getUniqueId());
        nextCameraWriteIndexByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
    }

    public boolean isAuthenticated(Player player) {
        return authenticatedSessions.contains(player.getUniqueId());
    }

    public Optional<Account> account(Player player) {
        return store.account(nicknameKey(player.getName()));
    }

    public Optional<Account> account(String nicknameKey) {
        return store.account(nicknameKey);
    }

    public String displayName(String nicknameKey) {
        return store.account(nicknameKey)
                .map(Account::displayName)
                .orElse(nicknameKey);
    }

    public void register(Player player, String nicknameArgument, String password, String repeatedPassword) {
        if (isAuthenticated(player)) {
            message(player, NamedTextColor.YELLOW, "You are already authenticated.");
            return;
        }
        if (pendingRegistrations.contains(player.getUniqueId())) {
            message(player, NamedTextColor.YELLOW, "Your identity link is already being processed.");
            return;
        }
        if (!NICKNAME_PATTERN.matcher(nicknameArgument).matches()
                || !nicknameArgument.equalsIgnoreCase(player.getName())) {
            message(player, NamedTextColor.RED, "The registration username must match your current Minecraft nickname: " + player.getName());
            return;
        }
        String nicknameKey = nicknameKey(player.getName());
        if (store.account(nicknameKey).isPresent()) {
            message(player, NamedTextColor.YELLOW, "This nickname is already registered. Use /login <password>.");
            return;
        }
        int minimumLength = plugin.getConfig().getInt("authentication.password-min-length", 8);
        if (password.length() < minimumLength || password.length() > 128) {
            message(player, NamedTextColor.RED, "Competition password must be " + minimumLength + "-128 characters.");
            return;
        }
        if (!password.equals(repeatedPassword)) {
            message(player, NamedTextColor.RED, "The two passwords do not match.");
            return;
        }

        char[] passwordCharacters = password.toCharArray();
        PasswordHasher.PasswordRecord passwordRecord;
        try {
            passwordRecord = passwordHasher.hash(passwordCharacters);
        } finally {
            Arrays.fill(passwordCharacters, '\0');
        }

        IdentityLinker.LinkTicket ticket = identityLinker.begin(player.getName(), player.getUniqueId());
        pendingRegistrations.add(player.getUniqueId());
        player.sendMessage(Component.text("Open this temporary Hill account link: ", NamedTextColor.YELLOW)
                .append(Component.text(ticket.url(), NamedTextColor.AQUA)
                        .clickEvent(ClickEvent.openUrl(ticket.url()))));
        message(player, NamedTextColor.GRAY, "Development mode: the school-account link will approve automatically.");

        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            IdentityLinker.LinkResult result = identityLinker.complete(ticket);
            pendingRegistrations.remove(player.getUniqueId());
            if (!result.approved()) {
                message(player, NamedTextColor.RED, result.message());
                return;
            }
            Account account = new Account(
                    nicknameKey,
                    player.getName(),
                    result.schoolIdentity(),
                    result.displayName(),
                    passwordRecord.saltBase64(),
                    passwordRecord.hashBase64(),
                    passwordRecord.iterations(),
                    Instant.now()
            );
            store.saveAccount(account);
            if (player.isOnline()) {
                authenticate(player, account, "Registration complete. School link approved.");
            }
        }, plugin.getConfig().getLong("authentication.stub-link-delay-ticks", 20L));
    }

    public void login(Player player, String password) {
        if (isAuthenticated(player)) {
            message(player, NamedTextColor.YELLOW, "You are already authenticated.");
            return;
        }
        FailureWindow failureWindow = loginFailures.computeIfAbsent(player.getUniqueId(), ignored -> new FailureWindow());
        if (failureWindow.isLocked()) {
            message(player, NamedTextColor.RED, "Too many failed attempts. Wait before trying again.");
            return;
        }
        Optional<Account> existing = store.account(nicknameKey(player.getName()));
        if (existing.isEmpty()) {
            message(player, NamedTextColor.YELLOW, "This nickname is not registered. Use /register "
                    + player.getName() + " <password> <repeatPassword>.");
            return;
        }
        Account account = existing.get();
        char[] passwordCharacters = password.toCharArray();
        boolean valid;
        try {
            valid = passwordHasher.verify(
                    passwordCharacters,
                    account.passwordSalt(),
                    account.passwordHash(),
                    account.passwordIterations()
            );
        } finally {
            Arrays.fill(passwordCharacters, '\0');
        }
        if (!valid) {
            failureWindow.recordFailure();
            message(player, NamedTextColor.RED, "Incorrect password.");
            return;
        }
        loginFailures.remove(player.getUniqueId());
        authenticate(player, account, "Login successful.");
    }

    public void sendAuthenticationInstructions(Player player) {
        if (store.account(nicknameKey(player.getName())).isPresent()) {
            message(player, NamedTextColor.GOLD, "Please sign in using your Hill competition password.");
            message(player, NamedTextColor.WHITE, "/login <password>");
        } else {
            message(player, NamedTextColor.GOLD, "Please register and link your Hill identity.");
            message(player, NamedTextColor.WHITE, "/register " + player.getName() + " <password> <repeatPassword>");
        }
        message(player, NamedTextColor.GRAY, "Authentication commands are private and never sent to public chat.");
    }

    public void sendRules(Player player) {
        message(player, NamedTextColor.GOLD, "Hill 175 Competition Rules");
        message(player, NamedTextColor.WHITE, "Create up to two entries in different categories. Teams may have up to two people.");
        message(player, NamedTextColor.WHITE, "Build only in your entry. Visitors can fly and observe but cannot modify blocks.");
        message(player, NamedTextColor.WHITE, "Living mobs, portals, explosions, destructive commands, and bypass attempts are blocked.");
        message(player, NamedTextColor.WHITE, "Use the camera item to save or replace up to three submission views. Left-click previews them; right-click saves one.");
        message(player, NamedTextColor.WHITE, "Use /help, the Competition Compass, or the entry hotbar tools instead of remembering long command chains.");
        message(player, NamedTextColor.GRAY, "Main exhibition hub: the Hill 175 project world.");
    }

    public void sendHelp(Player player) {
        message(player, NamedTextColor.GOLD, "Hill 175 Commands");
        if (!isAuthenticated(player)) {
            message(player, NamedTextColor.WHITE, "/register <nickname> <password> <repeatPassword>");
            message(player, NamedTextColor.WHITE, "/login <password>");
            message(player, NamedTextColor.WHITE, "/help and /rules");
            return;
        }
        message(player, NamedTextColor.WHITE, "/competition or /hill175 - open the main competition menu");
        message(player, NamedTextColor.WHITE, "/help - show these competition commands again");
        message(player, NamedTextColor.WHITE, "/hub or /lobby - return to the exhibition lobby");
        message(player, NamedTextColor.WHITE, "/entry create <journey|place|people>, /entry list, /entry home, /entry visit");
        message(player, NamedTextColor.WHITE, "/entry title <text>, /entry description <text>");
        message(player, NamedTextColor.WHITE, "/entry reset, /entry delete, /entry switch <journey|place|people>");
        message(player, NamedTextColor.WHITE, "/entry submit, /entry unlock");
        message(player, NamedTextColor.WHITE, "/team invite <nickname>, /team accept <nickname>, /team leave");
        message(player, NamedTextColor.WHITE, "/camera or /camera save, /camera list, /camera preview, /camera remove <1-3>");
        message(player, NamedTextColor.WHITE, "/rules - review the competition rules");
        message(player, NamedTextColor.GRAY, "Most actions are also available through the compass, entry menus, and hotbar tools.");
    }

    public Optional<Entry> createEntry(Player player, Category category) {
        String memberKey = requireMemberKey(player);
        if (memberKey == null) {
            return Optional.empty();
        }
        List<Entry> memberships = entriesFor(memberKey);
        if (memberships.size() >= 2) {
            message(player, NamedTextColor.RED, "You already participate in two entries.");
            return Optional.empty();
        }
        if (memberships.stream().anyMatch(entry -> entry.category() == category)) {
            message(player, NamedTextColor.RED, "You already participate in " + category.displayName() + ".");
            return Optional.empty();
        }

        UUID entryId = UUID.randomUUID();
        int allocationIndex = category == Category.PEOPLE ? 0 : store.nextAllocation(category);
        WorldModule.Allocation allocation;
        try {
            allocation = worlds.allocate(category, allocationIndex, entryId);
        } catch (IllegalStateException exception) {
            message(player, NamedTextColor.RED, exception.getMessage());
            return Optional.empty();
        }
        Entry entry = new Entry(
                entryId,
                category,
                Set.of(memberKey),
                allocation.worldName(),
                allocation.region(),
                allocation.allocationIndex()
        );
        store.saveEntry(entry);
        teleportToEntry(player, entry, false);
        message(player, NamedTextColor.GREEN, category.displayName() + " entry created.");
        return Optional.of(entry);
    }

    public void teleportToEntry(Player player, Entry entry, boolean visiting) {
        if (!isAuthenticated(player)) {
            return;
        }
        worlds.ensureEntryWorld(entry);
        if (entry.category() == Category.PEOPLE && !worlds.isPeopleWorldReady(entry.worldName())) {
            currentEntryByPlayer.put(player.getUniqueId(), entry.id());
            pendingPeopleEntryByPlayer.put(player.getUniqueId(), entry.id());
            if (!player.teleport(worlds.hubSpawn())) {
                currentEntryByPlayer.remove(player.getUniqueId());
                pendingPeopleEntryByPlayer.remove(player.getUniqueId());
                message(player, NamedTextColor.RED, "The lobby teleport was interrupted. Use /hub to try again.");
                return;
            }
            player.setGameMode(GameMode.ADVENTURE);
            player.setAllowFlight(true);
            player.setFlying(false);
            giveHubItems(player);
            worlds.whenPeopleWorldReady(entry.worldName(), () -> {
                UUID playerId = player.getUniqueId();
                if (shouldCompletePendingPeopleTeleport(
                        entry.id(),
                        currentEntryByPlayer.get(playerId),
                        pendingPeopleEntryByPlayer.get(playerId),
                        player.isOnline(),
                        isAuthenticated(player)
                )) {
                    pendingPeopleEntryByPlayer.remove(playerId);
                    teleportToEntry(player, entry, visiting);
                }
            });
            message(player, NamedTextColor.AQUA, "The People world is still loading from structure.nbt. You'll be teleported in automatically when it is ready.");
            sendHubTip(player);
            return;
        }
        Optional<Location> safeSpawn = worlds.safeEntrySpawn(entry);
        if (safeSpawn.isEmpty()) {
            currentEntryByPlayer.remove(player.getUniqueId());
            pendingPeopleEntryByPlayer.remove(player.getUniqueId());
            message(player, NamedTextColor.RED, "No safe two-block-tall spawn is available inside this entry.");
            message(player, NamedTextColor.YELLOW, "Open Entry Controls from the lobby to reset the build, or ask staff to clear its spawn area.");
            return;
        }
        if (!player.teleport(safeSpawn.get())) {
            pendingPeopleEntryByPlayer.remove(player.getUniqueId());
            message(player, NamedTextColor.RED, "The entry teleport was interrupted. Try again from the Competition Compass.");
            return;
        }
        currentEntryByPlayer.put(player.getUniqueId(), entry.id());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        refreshCameraMarkers(entry);
        if (entry.category() == Category.PEOPLE) {
            message(player, NamedTextColor.AQUA,
                    "This People build was spawned from the server's structure.nbt school template.");
        }
        boolean owner = entry.isMember(nicknameKey(player.getName()));
        if (owner && !visiting && !entry.submitted() && !worlds.isResetting(entry.id())) {
            setOwnerMode(player);
            giveEntryOwnerItems(player, entry);
            message(player, NamedTextColor.GREEN, "Owner Mode: you may build inside this entry.");
            sendOwnerEntryTip(player);
        } else {
            setVisitorMode(player);
            giveEntryVisitorItems(player, entry, owner);
            message(player, NamedTextColor.AQUA, "Visitor Mode: fly and observe; editing is disabled.");
            sendVisitorEntryTip(player);
        }
    }

    public void teleportHub(Player player) {
        if (!isAuthenticated(player)) {
            return;
        }
        if (!player.teleport(worlds.hubSpawn())) {
            message(player, NamedTextColor.RED, "The lobby teleport was interrupted. Use /hub to try again.");
            return;
        }
        currentEntryByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        player.setGameMode(GameMode.ADVENTURE);
        player.setAllowFlight(true);
        player.setFlying(false);
        giveHubItems(player);
        sendHubTip(player);
    }

    public boolean home(Player player) {
        List<Entry> ownedEntries = entriesFor(nicknameKey(player.getName()));
        Optional<Entry> currentOwned = currentEntry(player)
                .filter(entry -> entry.isMember(nicknameKey(player.getName())));
        if (currentOwned.isPresent()) {
            teleportToEntry(player, currentOwned.get(), false);
            return true;
        } else if (ownedEntries.size() == 1) {
            teleportToEntry(player, ownedEntries.getFirst(), false);
            return true;
        }
        return false;
    }

    public Optional<Entry> currentEntry(Player player) {
        UUID current = currentEntryByPlayer.get(player.getUniqueId());
        if (current != null) {
            Optional<Entry> entry = store.entry(current);
            if (entry.isPresent()) {
                return entry;
            }
        }
        return entryAt(player.getLocation());
    }

    public Optional<Entry> entryAt(Location location) {
        return store.entries().stream()
                .filter(entry -> entry.region().contains(location))
                .findFirst();
    }

    public boolean mayBuild(Player player, Location location) {
        if (!isAuthenticated(player)) {
            return false;
        }
        String key = nicknameKey(player.getName());
        return entryAt(location)
                .filter(entry -> entry.isMember(key))
                .filter(entry -> !entry.submitted())
                .filter(entry -> !worlds.isResetting(entry.id()))
                .isPresent();
    }

    public void refreshMovementMode(Player player, Location location) {
        if (!isAuthenticated(player)) {
            return;
        }
        Optional<Entry> entry = entryAt(location);
        if (entry.isPresent()) {
            currentEntryByPlayer.put(player.getUniqueId(), entry.get().id());
            pendingPeopleEntryByPlayer.remove(player.getUniqueId());
            if (entry.get().isMember(nicknameKey(player.getName()))
                    && !entry.get().submitted()
                    && !worlds.isResetting(entry.get().id())) {
                setOwnerMode(player);
                giveEntryOwnerItems(player, entry.get());
            } else {
                setVisitorMode(player);
                giveEntryVisitorItems(player, entry.get(), entry.get().isMember(nicknameKey(player.getName())));
            }
            return;
        }
        if (location.getWorld() != null && location.getWorld().equals(worlds.hubWorld())) {
            currentEntryByPlayer.remove(player.getUniqueId());
            pendingPeopleEntryByPlayer.remove(player.getUniqueId());
            player.setGameMode(GameMode.ADVENTURE);
            player.setAllowFlight(true);
            giveHubItems(player);
            return;
        }
        if (isCompetitionBuildWorld(location)) {
            setVisitorMode(player);
        }
    }

    public void resetCurrentEntry(Player player) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        current.ifPresent(entry -> resetEntry(player, entry));
    }

    public void deleteCurrentEntry(Player player) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        current.ifPresent(entry -> deleteEntry(player, entry));
    }

    public void switchCurrentEntry(Player player, Category newCategory) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        if (current.isEmpty()) {
            return;
        }
        Entry entry = current.get();
        if (entry.category() == newCategory) {
            message(player, NamedTextColor.YELLOW, "This entry is already in " + newCategory.displayName() + ".");
            return;
        }
        for (String member : entry.members()) {
            boolean duplicate = entriesFor(member).stream()
                    .anyMatch(other -> !other.id().equals(entry.id()) && other.category() == newCategory);
            if (duplicate) {
                message(player, NamedTextColor.RED, "A team member already participates in " + newCategory.displayName() + ".");
                return;
            }
        }
        evacuateEntry(entry);
        clearCameraMarkers(entry);
        if (entry.category() == Category.PEOPLE) {
            worlds.deletePrivateWorld(entry);
        } else {
            worlds.reset(entry, () -> {
            });
        }
        int allocationIndex = newCategory == Category.PEOPLE ? 0 : store.nextAllocation(newCategory);
        WorldModule.Allocation allocation = worlds.allocate(newCategory, allocationIndex, entry.id());
        entry.category(newCategory);
        entry.worldName(allocation.worldName());
        entry.region(allocation.region());
        entry.allocationIndex(allocation.allocationIndex());
        entry.title("");
        entry.description("");
        entry.clearCameraPoses();
        store.saveEntry(entry);
        teleportToEntry(player, entry, false);
        message(player, NamedTextColor.GREEN, "Entry switched to " + newCategory.displayName() + ".");
    }

    public void setTitle(Player player, String title) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        current.ifPresent(entry -> setTitle(player, entry, title));
    }

    public void setDescription(Player player, String description) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        current.ifPresent(entry -> setDescription(player, entry, description));
    }

    public void submit(Player player) {
        Optional<Entry> current = requireCurrentOwnedEntry(player);
        current.ifPresent(entry -> submitEntry(player, entry));
    }

    public void unlock(Player player) {
        Optional<Entry> current = requireCurrentOwnedEntry(player);
        current.ifPresent(entry -> unlockEntry(player, entry));
    }

    public void recordCamera(Player player) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        if (current.isEmpty()) {
            return;
        }
        Entry entry = current.get();
        if (!entry.region().contains(player.getLocation())) {
            message(player, NamedTextColor.RED, "Stand inside your build space to save a camera pose.");
            return;
        }
        CameraPose pose = CameraPose.from(player.getEyeLocation());
        if (worlds.safeCameraTeleport(entry, pose, player.getEyeHeight()).isEmpty()) {
            message(player, NamedTextColor.RED,
                    "That camera position is obstructed, unsafe, or aimed outside your build. Move to a clear position, aim inward, and try again.");
            return;
        }
        int slotNumber;
        if (entry.cameraPoses().size() < 3) {
            entry.addCameraPose(pose);
            slotNumber = entry.cameraPoses().size();
        } else {
            slotNumber = normalizedCameraWriteIndex(player, entry);
            entry.setCameraPose(slotNumber, pose);
        }
        store.saveEntry(entry);
        refreshCameraMarkers(entry);
        nextCameraWriteIndexByPlayer.put(player.getUniqueId(), slotNumber % 3 + 1);
        player.playSound(player.getLocation(), Sound.ENTITY_ITEM_PICKUP, 1.0f, 1.4f);
        message(player, NamedTextColor.GREEN, (entry.cameraPoses().size() < 3 || slotNumber == entry.cameraPoses().size())
                ? "Camera pose " + slotNumber + "/3 saved."
                : "Camera pose " + slotNumber + "/3 updated.");
    }

    public void removeCamera(Player player, int index) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        if (current.isEmpty()) {
            return;
        }
        if (!current.get().removeCameraPose(index)) {
            message(player, NamedTextColor.RED, "No camera pose exists at index " + index + ".");
            return;
        }
        store.saveEntry(current.get());
        refreshCameraMarkers(current.get());
        nextCameraWriteIndexByPlayer.put(player.getUniqueId(), Math.min(index, Math.max(1, current.get().cameraPoses().size() + 1)));
        message(player, NamedTextColor.GREEN, "Camera pose removed.");
    }

    public void listCameras(Player player) {
        Optional<Entry> current = requireCurrentOwnedEntry(player);
        if (current.isEmpty()) {
            return;
        }
        if (current.get().cameraPoses().isEmpty()) {
            message(player, NamedTextColor.YELLOW, "No camera poses saved.");
            return;
        }
        for (int index = 0; index < current.get().cameraPoses().size(); index++) {
            CameraPose pose = current.get().cameraPoses().get(index);
            message(player, NamedTextColor.AQUA, (index + 1) + ". " + pose.worldName() + " @ "
                    + Math.round(pose.x()) + ", " + Math.round(pose.y()) + ", " + Math.round(pose.z()));
        }
    }

    public void previewNextCamera(Player player) {
        if (!isAuthenticated(player)) {
            return;
        }
        Optional<Entry> current = currentEntry(player);
        if (current.isEmpty()) {
            message(player, NamedTextColor.RED, "Open or visit an entry first.");
            return;
        }
        Entry entry = current.get();
        if (entry.cameraPoses().isEmpty()) {
            message(player, NamedTextColor.YELLOW, "Save a camera pose first.");
            return;
        }
        int nextIndex = nextPreviewIndexByPlayer.getOrDefault(player.getUniqueId(), 0);
        if (nextIndex >= entry.cameraPoses().size()) {
            nextIndex = 0;
        }
        CameraPose pose = entry.cameraPoses().get(nextIndex);
        Optional<Location> target = worlds.safeCameraTeleport(entry, pose, player.getEyeHeight());
        if (target.isEmpty()) {
            message(player, NamedTextColor.RED,
                    "That camera pose is now obstructed or unsafe. Clear the viewpoint or save a replacement pose.");
            return;
        }
        if (!player.teleport(target.get())) {
            message(player, NamedTextColor.RED, "The camera teleport was interrupted. Try the preview again.");
            return;
        }
        nextPreviewIndexByPlayer.put(player.getUniqueId(), (nextIndex + 1) % entry.cameraPoses().size());
        player.playSound(player.getLocation(), Sound.ENTITY_ENDERMAN_TELEPORT, 0.7f, 1.2f);
        message(player, NamedTextColor.AQUA, "Previewing camera " + (nextIndex + 1) + "/" + entry.cameraPoses().size()
                + ". Tip: /entry home returns to the build; /hub returns to the lobby.");
    }

    public void previewCamera(Player player, Entry entry, int oneBasedIndex) {
        if (!mayPreviewEntry(player, entry)) {
            return;
        }
        int index = oneBasedIndex - 1;
        if (index < 0 || index >= entry.cameraPoses().size()) {
            message(player, NamedTextColor.RED, "No camera pose exists at index " + oneBasedIndex + ".");
            return;
        }
        CameraPose pose = entry.cameraPoses().get(index);
        Optional<Location> target = worlds.safeCameraTeleport(entry, pose, player.getEyeHeight());
        if (target.isEmpty()) {
            message(player, NamedTextColor.RED,
                    "That camera pose is now obstructed or unsafe. Clear the viewpoint or save a replacement pose.");
            return;
        }
        if (!player.teleport(target.get())) {
            message(player, NamedTextColor.RED, "The camera teleport was interrupted. Try the preview again.");
            return;
        }
        nextPreviewIndexByPlayer.put(player.getUniqueId(), (index + 1) % entry.cameraPoses().size());
        player.playSound(player.getLocation(), Sound.ENTITY_ENDERMAN_TELEPORT, 0.7f, 1.2f);
        message(player, NamedTextColor.AQUA, "Previewing camera " + oneBasedIndex + "/" + entry.cameraPoses().size()
                + ". Tip: /entry home returns to the build; /hub returns to the lobby.");
    }

    public boolean previewCameraMarker(Player player, Entity entity) {
        if (!entity.getScoreboardTags().contains(CAMERA_MARKER_TAG)) {
            return false;
        }
        Optional<Entry> current = currentEntry(player);
        if (current.isEmpty()) {
            return false;
        }
        Entry entry = current.get();
        if (!entry.isMember(nicknameKey(player.getName())) && !player.hasPermission("hill175.staff")) {
            return false;
        }
        if (!entity.getScoreboardTags().contains(cameraMarkerEntryTag(entry.id()))) {
            return false;
        }
        for (String tag : entity.getScoreboardTags()) {
            if (tag.startsWith(CAMERA_MARKER_INDEX_PREFIX)) {
                try {
                    previewCamera(player, entry, Integer.parseInt(tag.substring(CAMERA_MARKER_INDEX_PREFIX.length())));
                    return true;
                } catch (NumberFormatException ignored) {
                    return false;
                }
            }
        }
        return false;
    }

    public void invite(Player inviter, String targetNickname) {
        Optional<Entry> current = requireCurrentEditableEntry(inviter);
        if (current.isEmpty()) {
            return;
        }
        Entry entry = current.get();
        if (entry.members().size() >= 2) {
            message(inviter, NamedTextColor.RED, "This entry already has two team members.");
            return;
        }
        String targetKey = nicknameKey(targetNickname);
        if (targetKey.equals(nicknameKey(inviter.getName()))) {
            message(inviter, NamedTextColor.RED, "You cannot invite yourself.");
            return;
        }
        Player target = Bukkit.getPlayerExact(targetNickname);
        if (target == null || !isAuthenticated(target)) {
            message(inviter, NamedTextColor.RED, "That authenticated participant is not online.");
            return;
        }
        if (entriesFor(targetKey).size() >= 2) {
            message(inviter, NamedTextColor.RED, "That participant already has two entries.");
            return;
        }
        if (entriesFor(targetKey).stream().anyMatch(existing -> existing.category() == entry.category())) {
            message(inviter, NamedTextColor.RED, "That participant already has an entry in this category.");
            return;
        }
        invitesByTarget.put(targetKey, new TeamInvite(entry.id(), nicknameKey(inviter.getName()), Instant.now().plus(Duration.ofMinutes(5))));
        message(inviter, NamedTextColor.GREEN, "Invite sent to " + target.getName() + ".");
        message(target, NamedTextColor.GOLD, inviter.getName() + " invited you to their " + entry.category().displayName()
                + " entry. Use /team accept " + inviter.getName() + ".");
    }

    public void acceptInvite(Player target, String inviterNickname) {
        String targetKey = requireMemberKey(target);
        if (targetKey == null) {
            return;
        }
        TeamInvite invite = invitesByTarget.get(targetKey);
        if (invite == null || invite.expiresAt().isBefore(Instant.now())
                || !invite.inviterKey().equals(nicknameKey(inviterNickname))) {
            message(target, NamedTextColor.RED, "No valid invite from that participant.");
            return;
        }
        Optional<Entry> entryOptional = store.entry(invite.entryId());
        if (entryOptional.isEmpty()) {
            invitesByTarget.remove(targetKey);
            message(target, NamedTextColor.RED, "That entry no longer exists.");
            return;
        }
        Entry entry = entryOptional.get();
        if (entry.submitted()) {
            message(target, NamedTextColor.RED, "That entry is submitted. A member must unlock it before changing the team.");
            return;
        }
        if (entriesFor(targetKey).size() >= 2
                || entriesFor(targetKey).stream().anyMatch(existing -> existing.category() == entry.category())
                || !entry.addMember(targetKey)) {
            message(target, NamedTextColor.RED, "You cannot join this entry.");
            return;
        }
        invitesByTarget.remove(targetKey);
        store.saveEntry(entry);
        teleportToEntry(target, entry, false);
        message(target, NamedTextColor.GREEN, "Team invite accepted.");
        notifyEntry(entry, target.getName() + " joined the team.");
    }

    public void leaveTeam(Player player) {
        Optional<Entry> current = requireCurrentOwnedEntry(player);
        if (current.isEmpty()) {
            return;
        }
        Entry entry = current.get();
        String key = nicknameKey(player.getName());
        if (entry.members().size() == 1) {
            deleteCurrentEntry(player);
            return;
        }
        entry.removeMember(key);
        store.saveEntry(entry);
        currentEntryByPlayer.remove(player.getUniqueId());
        teleportHub(player);
        notifyEntry(entry, player.getName() + " left the team.");
    }

    public List<Entry> entriesFor(String nicknameKey) {
        return store.entries().stream()
                .filter(entry -> entry.isMember(nicknameKey))
                .sorted(Comparator.comparing(Entry::category))
                .toList();
    }

    public Collection<Entry> allEntries() {
        return store.entries();
    }

    public Optional<Entry> entry(UUID id) {
        return store.entry(id);
    }

    public boolean isCompetitionItem(ItemStack item, String expectedId) {
        if (item == null || item.getType().isAir() || !item.hasItemMeta()) {
            return false;
        }
        return expectedId.equals(item.getItemMeta().getPersistentDataContainer().get(itemKey, PersistentDataType.STRING));
    }

    public String nicknameKey(String nickname) {
        return nickname.toLowerCase(Locale.ROOT);
    }

    private void authenticate(Player player, Account account, String successMessage) {
        authenticatedSessions.add(player.getUniqueId());
        store.recordConnection(account.nicknameKey(), connectionAddress(player), "authenticated");
        player.displayName(Component.text(account.displayName()));
        player.playerListName(Component.text(account.displayName(), NamedTextColor.GOLD));
        teleportHub(player);
        showWelcomeTitle(player, account.displayName());
        message(player, NamedTextColor.GREEN, successMessage);
        sendRules(player);
    }

    public void resetEntry(Player player, Entry entry) {
        if (!ensureEditableEntryAccess(player, entry)) {
            return;
        }
        message(player, NamedTextColor.YELLOW, "Reset started. All blocks in this entry will be restored.");
        clearCameraMarkers(entry);
        evacuateEntry(entry);
        worlds.reset(entry, () -> {
            entry.clearCameraPoses();
            entry.title("");
            entry.description("");
            store.saveEntry(entry);
            refreshCameraMarkers(entry);
            if (player.isOnline()) {
                teleportToEntry(player, entry, false);
                message(player, NamedTextColor.GREEN, "Entry reset complete.");
            }
        });
    }

    public void deleteEntry(Player player, Entry entry) {
        if (!ensureEditableEntryAccess(player, entry)) {
            return;
        }
        clearCameraMarkers(entry);
        evacuateEntry(entry);
        if (entry.category() == Category.PEOPLE) {
            worlds.deletePrivateWorld(entry);
        } else {
            worlds.reset(entry, () -> {
            });
        }
        store.deleteEntry(entry.id());
        currentEntryByPlayer.values().removeIf(id -> id.equals(entry.id()));
        teleportHub(player);
        message(player, NamedTextColor.GREEN, "Entry deleted. You may create a replacement.");
    }

    public void setTitle(Player player, Entry entry, String title) {
        if (!ensureEditableEntryAccess(player, entry)) {
            return;
        }
        String normalized = title.trim();
        if (normalized.isEmpty() || normalized.length() > MAX_TITLE_LENGTH) {
            message(player, NamedTextColor.RED, "Title must contain 1-" + MAX_TITLE_LENGTH + " characters.");
            return;
        }
        entry.title(normalized);
        store.saveEntry(entry);
        message(player, NamedTextColor.GREEN, "Project title saved.");
    }

    public void setDescription(Player player, Entry entry, String description) {
        if (!ensureEditableEntryAccess(player, entry)) {
            return;
        }
        String normalized = description.trim();
        if (normalized.isEmpty() || normalized.length() > MAX_DESCRIPTION_LENGTH) {
            message(player, NamedTextColor.RED, "Description must contain 1-" + MAX_DESCRIPTION_LENGTH + " characters.");
            return;
        }
        entry.description(normalized);
        store.saveEntry(entry);
        message(player, NamedTextColor.GREEN, "Project description saved.");
    }

    public void submitEntry(Player player, Entry entry) {
        if (!ensureOwnedEntryAccess(player, entry)) {
            return;
        }
        if (entry.submitted()) {
            message(player, NamedTextColor.YELLOW, "This entry is already submitted.");
            return;
        }
        if (entry.title().isBlank() || entry.description().isBlank()) {
            message(player, NamedTextColor.RED, "Set both title and description before submitting.");
            return;
        }
        if (entry.cameraPoses().isEmpty()) {
            message(player, NamedTextColor.RED, "Save at least one camera pose before submitting.");
            return;
        }
        entry.submit(Instant.now());
        store.saveEntry(entry);
        synchronizeEntryModes(entry);
        message(player, NamedTextColor.GREEN, "Entry submitted and locked. Use /entry unlock to continue editing before the deadline.");
    }

    public void unlockEntry(Player player, Entry entry) {
        if (!ensureOwnedEntryAccess(player, entry)) {
            return;
        }
        entry.clearSubmission();
        store.saveEntry(entry);
        synchronizeEntryModes(entry);
        message(player, NamedTextColor.YELLOW, "Submission unlocked. Re-submit after changes.");
    }

    private void giveHubItems(Player player) {
        clearCompetitionItems(player);
        player.getInventory().setItem(0, competitionItem(Material.COMPASS, COMPASS_ITEM_ID, "Competition Compass",
                "Open entries, visit builds, or create a project."));
        player.getInventory().setItem(7, competitionItem(Material.WRITTEN_BOOK, RULES_ITEM_ID, "Hill 175 Rules",
                "Right-click to review competition rules."));
    }

    private void giveEntryOwnerItems(Player player, Entry entry) {
        clearCompetitionItems(player);
        player.getInventory().setItem(0, competitionItem(Material.ENDER_PEARL, LOBBY_ITEM_ID, "Return to Lobby",
                "Right-click to return to the exhibition lobby."));
        player.getInventory().setItem(1, competitionItem(Material.BARRIER, ENTRY_RESET_ITEM_ID, "Reset Entry",
                "Right-click to restore this build space."));
        player.getInventory().setItem(2, competitionItem(entry.submitted() ? Material.LIME_DYE : Material.TRIPWIRE_HOOK,
                ENTRY_SUBMIT_ITEM_ID,
                entry.submitted() ? "Resume Editing" : "Lock Submission",
                entry.submitted()
                        ? "Right-click to unlock this submission and continue editing."
                        : "Right-click to submit and lock this entry."));
        player.getInventory().setItem(3, competitionItem(Material.BLAZE_ROD, CAMERA_ITEM_ID, "Submission Camera",
                "Right-click to save or replace a camera pose. Left-click to preview the next saved pose."));
        player.getInventory().setItem(7, competitionItem(Material.WRITTEN_BOOK, RULES_ITEM_ID, "Hill 175 Rules",
                "Right-click to review competition rules."));
        player.getInventory().setItem(8, competitionItem(Material.NETHER_STAR, ENTRY_MENU_ITEM_ID, "Entry Controls",
                "Open the menu for this entry."));
    }

    private void giveEntryVisitorItems(Player player, Entry entry, boolean owner) {
        clearCompetitionItems(player);
        player.getInventory().setItem(0, competitionItem(Material.ENDER_PEARL, LOBBY_ITEM_ID, "Return to Lobby",
                "Right-click to return to the exhibition lobby."));
        player.getInventory().setItem(3, competitionItem(Material.BLAZE_ROD, CAMERA_ITEM_ID, "Submission Camera",
                "Left-click or right-click to preview the next saved camera pose."));
        player.getInventory().setItem(7, competitionItem(Material.WRITTEN_BOOK, RULES_ITEM_ID, "Hill 175 Rules",
                "Right-click to review competition rules."));
        player.getInventory().setItem(8, competitionItem(owner ? Material.NETHER_STAR : Material.COMPASS,
                owner ? ENTRY_MENU_ITEM_ID : COMPASS_ITEM_ID,
                owner ? "Entry Controls" : "Competition Compass",
                owner ? "Open the menu for this entry." : "Open entries, visit builds, or create a project."));
    }

    private ItemStack competitionItem(Material material, String id, String name, String lore) {
        ItemStack item = new ItemStack(material);
        ItemMeta meta = item.getItemMeta();
        meta.displayName(Component.text(name, NamedTextColor.GOLD).decoration(TextDecoration.ITALIC, false));
        meta.lore(List.of(Component.text(lore, NamedTextColor.GRAY).decoration(TextDecoration.ITALIC, false)));
        meta.getPersistentDataContainer().set(itemKey, PersistentDataType.STRING, id);
        item.setItemMeta(meta);
        // Minecraft 26.2 only sends an air-use packet for items with a use
        // behavior. A no-animation, long-running consumable makes every Hill
        // tool right-clickable in empty air; ServerListener cancels the use
        // immediately, before consumption can complete.
        item.setData(DataComponentTypes.CONSUMABLE, Consumable.consumable()
                .consumeSeconds(60.0F)
                .animation(ItemUseAnimation.NONE)
                .hasConsumeParticles(false));
        return item;
    }

    private void clearCompetitionItems(Player player) {
        PlayerInventory inventory = player.getInventory();
        for (int slot = 0; slot < inventory.getSize(); slot++) {
            ItemStack item = inventory.getItem(slot);
            if (item != null && item.hasItemMeta()
                    && item.getItemMeta().getPersistentDataContainer().has(itemKey, PersistentDataType.STRING)) {
                inventory.setItem(slot, null);
            }
        }
    }

    private Optional<Entry> requireCurrentOwnedEntry(Player player) {
        if (!isAuthenticated(player)) {
            message(player, NamedTextColor.RED, "Authenticate first.");
            return Optional.empty();
        }
        Optional<Entry> current = currentEntry(player);
        if (current.isEmpty() || !current.get().isMember(nicknameKey(player.getName()))) {
            message(player, NamedTextColor.RED, "Open one of your entries first.");
            return Optional.empty();
        }
        return current;
    }

    private Optional<Entry> requireCurrentEditableEntry(Player player) {
        Optional<Entry> current = requireCurrentOwnedEntry(player);
        if (current.isPresent() && current.get().submitted()) {
            message(player, NamedTextColor.RED, "This entry is submitted and locked. Use /entry unlock first.");
            return Optional.empty();
        }
        return current;
    }

    private String requireMemberKey(Player player) {
        if (!isAuthenticated(player)) {
            message(player, NamedTextColor.RED, "Authenticate first.");
            return null;
        }
        return nicknameKey(player.getName());
    }

    private boolean ensureOwnedEntryAccess(Player player, Entry entry) {
        if (!isAuthenticated(player)) {
            message(player, NamedTextColor.RED, "Authenticate first.");
            return false;
        }
        if (!entry.isMember(nicknameKey(player.getName()))) {
            message(player, NamedTextColor.RED, "That is not one of your entries.");
            return false;
        }
        return true;
    }

    private boolean ensureEditableEntryAccess(Player player, Entry entry) {
        if (!ensureOwnedEntryAccess(player, entry)) {
            return false;
        }
        if (entry.submitted()) {
            message(player, NamedTextColor.RED, "This entry is submitted and locked. Use /entry unlock first.");
            return false;
        }
        return true;
    }

    private boolean mayPreviewEntry(Player player, Entry entry) {
        if (!isAuthenticated(player)) {
            message(player, NamedTextColor.RED, "Authenticate first.");
            return false;
        }
        if (entry.isMember(nicknameKey(player.getName()))) {
            return true;
        }
        Optional<Entry> current = currentEntry(player);
        if (current.isPresent() && current.get().id().equals(entry.id())) {
            return true;
        }
        message(player, NamedTextColor.RED, "Open or visit that entry first.");
        return false;
    }

    public void rebuildAllCameraMarkers() {
        for (Entry entry : store.entries()) {
            refreshCameraMarkers(entry);
        }
    }

    private boolean isCompetitionBuildWorld(Location location) {
        if (location.getWorld() == null) {
            return false;
        }
        String name = location.getWorld().getName();
        return name.equals(plugin.getConfig().getString("worlds.journey", "hill_journey"))
                || name.equals(plugin.getConfig().getString("worlds.place", "hill_place"))
                || name.startsWith("hill_people_");
    }

    private void setOwnerMode(Player player) {
        player.setGameMode(GameMode.CREATIVE);
        player.setAllowFlight(true);
    }

    private void setVisitorMode(Player player) {
        player.setGameMode(GameMode.SPECTATOR);
        player.setAllowFlight(true);
    }

    private void synchronizeEntryModes(Entry entry) {
        for (Player online : Bukkit.getOnlinePlayers()) {
            String nicknameKey = nicknameKey(online.getName());
            if (!entry.isMember(nicknameKey) && !entry.region().contains(online.getLocation())) {
                continue;
            }
            if (entry.isMember(nicknameKey)
                    && !entry.submitted()
                    && !worlds.isResetting(entry.id())
                    && entry.region().contains(online.getLocation())) {
                setOwnerMode(online);
                giveEntryOwnerItems(online, entry);
            } else if (online.getLocation().getWorld() != null
                    && entry.worldName().equals(online.getLocation().getWorld().getName())) {
                setVisitorMode(online);
                giveEntryVisitorItems(online, entry, entry.isMember(nicknameKey));
            }
        }
    }

    private void notifyEntry(Entry entry, String text) {
        for (Player online : Bukkit.getOnlinePlayers()) {
            if (entry.isMember(nicknameKey(online.getName()))) {
                message(online, NamedTextColor.AQUA, text);
            }
        }
    }

    private void evacuateEntry(Entry entry) {
        for (Player online : Bukkit.getOnlinePlayers()) {
            boolean insideOwnedRegion = entry.region().contains(online.getLocation());
            boolean insidePrivatePeopleWorld = entry.category() == Category.PEOPLE
                    && online.getWorld().getName().equals(entry.worldName());
            if (insideOwnedRegion || insidePrivatePeopleWorld) {
                teleportHub(online);
            }
        }
    }

    private void showAuthenticationTitle(Player player) {
        player.clearTitle();
        player.showTitle(net.kyori.adventure.title.Title.title(
                Component.text("Hill 175", NamedTextColor.GOLD, TextDecoration.BOLD),
                Component.text("Please sign in using your Hill credentials", NamedTextColor.WHITE)
        ));
    }

    private void showWelcomeTitle(Player player, String displayName) {
        // Clearing first guarantees clients replay the welcome even when the same account reconnects.
        player.clearTitle();
        player.showTitle(net.kyori.adventure.title.Title.title(
                Component.text("Welcome, " + displayName, NamedTextColor.GOLD),
                Component.text("Hill 175 Minecraft Competition", NamedTextColor.WHITE)
        ));
    }

    private void sendHubTip(Player player) {
        message(player, NamedTextColor.GRAY,
                "Tip: right-click the Compass or a category guide to choose an entry; /entry home returns to your build.");
    }

    private void sendOwnerEntryTip(Player player) {
        message(player, NamedTextColor.GRAY,
                "Tip: /hub returns to the lobby. Your hotbar has Reset, Lock, Camera, and Entry Controls; commands include /entry reset and /camera.");
    }

    private void sendVisitorEntryTip(Player player) {
        message(player, NamedTextColor.GRAY,
                "Tip: /hub returns to the lobby; use the Compass or Entry Controls to choose another build.");
    }

    private void refreshCameraMarkers(Entry entry) {
        clearCameraMarkers(entry);
        if (entry.cameraPoses().isEmpty()) {
            return;
        }
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) {
            return;
        }
        for (int index = 0; index < entry.cameraPoses().size(); index++) {
            CameraPose pose = entry.cameraPoses().get(index);
            int markerNumber = index + 1;
            Location markerLocation = new Location(world, pose.x(), pose.y() - 1.6, pose.z(), pose.yaw(), pose.pitch());
            world.spawn(markerLocation, ArmorStand.class, stand -> {
                stand.customName(Component.text("Camera " + markerNumber, NamedTextColor.AQUA));
                stand.setCustomNameVisible(true);
                stand.setVisible(false);
                stand.setBasePlate(false);
                stand.setArms(false);
                stand.setGravity(false);
                stand.setInvulnerable(true);
                stand.setPersistent(true);
                stand.setRemoveWhenFarAway(false);
                stand.setCanPickupItems(false);
                stand.setMarker(false);
                stand.setSmall(true);
                stand.addScoreboardTag(CAMERA_MARKER_TAG);
                stand.addScoreboardTag(cameraMarkerEntryTag(entry.id()));
                stand.addScoreboardTag(CAMERA_MARKER_INDEX_PREFIX + markerNumber);
                EntityEquipment equipment = stand.getEquipment();
                if (equipment != null) {
                    equipment.setHelmet(new ItemStack(Material.BLAZE_ROD));
                }
                for (Player viewer : world.getPlayers()) {
                    if (entry.isMember(nicknameKey(viewer.getName())) || viewer.hasPermission("hill175.staff")) {
                        viewer.showEntity(plugin, stand);
                    } else {
                        viewer.hideEntity(plugin, stand);
                    }
                }
            });
        }
    }

    private void clearCameraMarkers(Entry entry) {
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) {
            return;
        }
        String entryTag = cameraMarkerEntryTag(entry.id());
        for (var entity : world.getEntities()) {
            if (entity.getScoreboardTags().contains(CAMERA_MARKER_TAG)
                    && entity.getScoreboardTags().contains(entryTag)) {
                entity.remove();
            }
        }
    }

    private static String cameraMarkerEntryTag(UUID entryId) {
        return CAMERA_MARKER_ENTRY_PREFIX + entryId;
    }

    private int normalizedCameraWriteIndex(Player player, Entry entry) {
        int next = nextCameraWriteIndexByPlayer.getOrDefault(player.getUniqueId(), 1);
        if (next < 1 || next > Math.max(1, entry.cameraPoses().size())) {
            return 1;
        }
        return next;
    }

    static boolean shouldCompletePendingPeopleTeleport(
            UUID expectedEntry,
            UUID currentEntry,
            UUID pendingEntry,
            boolean online,
            boolean authenticated
    ) {
        return online
                && authenticated
                && Objects.equals(expectedEntry, currentEntry)
                && Objects.equals(expectedEntry, pendingEntry);
    }

    private static void message(Player player, NamedTextColor color, String text) {
        player.sendMessage(Component.text("[Hill 175] ", NamedTextColor.GOLD, TextDecoration.BOLD)
                .append(Component.text(text, color).decoration(TextDecoration.BOLD, false)));
    }

    private static String connectionAddress(Player player) {
        if (player.getAddress() == null || player.getAddress().getAddress() == null) {
            return "unknown";
        }
        return player.getAddress().getAddress().getHostAddress();
    }

    private record TeamInvite(UUID entryId, String inviterKey, Instant expiresAt) {
    }

    private static final class FailureWindow {
        private int failures;
        private Instant startedAt = Instant.now();

        void recordFailure() {
            if (Duration.between(startedAt, Instant.now()).toMinutes() >= 15) {
                failures = 0;
                startedAt = Instant.now();
            }
            failures++;
        }

        boolean isLocked() {
            if (Duration.between(startedAt, Instant.now()).toMinutes() >= 15) {
                failures = 0;
                startedAt = Instant.now();
            }
            return failures >= 5;
        }
    }
}
