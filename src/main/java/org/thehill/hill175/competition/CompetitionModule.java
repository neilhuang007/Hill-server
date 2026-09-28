package org.thehill.hill175.competition;

import net.kyori.adventure.bossbar.BossBar;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.title.Title;
import io.papermc.paper.datacomponent.DataComponentTypes;
import io.papermc.paper.datacomponent.item.Consumable;
import io.papermc.paper.datacomponent.item.MapId;
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
import org.bukkit.entity.Interaction;
import org.bukkit.entity.Player;
import org.bukkit.inventory.EntityEquipment;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.PlayerInventory;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.map.MapRenderer;
import org.bukkit.map.MapView;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.potion.PotionEffect;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.data.SurvivalInventoryStore;
import org.thehill.hill175.model.Account;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.world.CampusChartMapRenderer;
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
    public static final String CAMERA_PREVIEW_REMOVE_ITEM_ID = "camera-preview-remove";
    public static final String RULES_ITEM_ID = "competition-rules";
    public static final String LOBBY_ITEM_ID = "return-lobby";
    public static final String CAMPUS_CHART_ITEM_ID = "campus-chart";
    private static final Pattern NICKNAME_PATTERN = Pattern.compile("^[A-Za-z0-9_]{3,16}$");
    private static final Set<String> RESERVED_NICKNAMES = Set.of("hilljourney", "hillplace", "hillpeople", "hillsurvival");
    private static final int MAX_TITLE_LENGTH = 80;
    private static final int MAX_DESCRIPTION_LENGTH = 750;
    private static final int CAMPUS_CHART_SLOT = 1;
    private static final long CAMERA_CAPTURE_SILENCE_NANOS = 750_000_000L;
    private static final float CAMERA_MARKER_HITBOX_WIDTH = 0.8F;
    private static final float CAMERA_MARKER_HITBOX_HEIGHT = 1.2F;
    private static final String CAMERA_MARKER_TAG = "hill175_camera_marker";
    private static final String CAMERA_MARKER_ENTRY_PREFIX = "hill175_camera_entry_";
    private static final String CAMERA_MARKER_INDEX_PREFIX = "hill175_camera_index_";
    private static final String CAMERA_VIEW_ANCHOR_TAG = "hill175_camera_view_anchor";
    private static final String HUB_KIT = "hub";
    private static final String SURVIVAL_KIT = "survival";
    private static final long AUTHENTICATION_REMINDER_INTERVAL_NANOS = 2_000_000_000L;

    private final JavaPlugin plugin;
    private final CompetitionStore store;
    private final WorldModule worlds;
    private final PasswordHasher passwordHasher;
    private final IdentityLinker identityLinker;
    private final SurvivalInventoryStore survivalInventories;
    private final ClientCameraBridge cameraBridge;
    private final NamespacedKey itemKey;
    private final Set<UUID> authenticatedSessions = ConcurrentHashMap.newKeySet();
    private final Set<UUID> pendingRegistrations = ConcurrentHashMap.newKeySet();
    private final Map<UUID, UUID> currentEntryByPlayer = new HashMap<>();
    private final Map<String, TeamInvite> invitesByTarget = new HashMap<>();
    private final Map<UUID, FailureWindow> loginFailures = new HashMap<>();
    private final Map<UUID, Integer> nextPreviewIndexByPlayer = new HashMap<>();
    private final Map<UUID, Integer> nextCameraWriteIndexByPlayer = new HashMap<>();
    private final Map<UUID, UUID> pendingPeopleEntryByPlayer = new HashMap<>();
    private final Map<UUID, String> activeKitByPlayer = new HashMap<>();
    private final Map<UUID, CampusChartMap> campusChartMapsByEntry = new HashMap<>();
    private final Map<UUID, PreviewState> activePreviewsByPlayer = new HashMap<>();
    private final Map<UUID, BossBar> previewBossBarsByPlayer = new HashMap<>();
    private final Map<UUID, Long> lastPreviewExitAtNanosByPlayer = new HashMap<>();
    private final Map<UUID, Long> lastCameraItemUseAtNanosByPlayer = new HashMap<>();
    private final Map<UUID, Long> lastAuthenticationReminderAtNanosByPlayer = new HashMap<>();

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
        this.survivalInventories = new SurvivalInventoryStore(plugin.getDataFolder(), plugin.getLogger());
        this.cameraBridge = ClientCameraBridge.create(plugin);
        this.itemKey = new NamespacedKey(plugin, "item-id");
    }

    public void handleJoin(Player player) {
        // Paper initially places every connection in the primary Overworld,
        // which is also our survival world. Only an existing persistent intent
        // proves this player was actually in survival before reconnecting.
        if (worlds.isSurvivalWorld(player.getWorld())
                && survivalInventories.isActive(player.getUniqueId())) {
            saveSurvivalState(player);
        }
        store.recordConnection(nicknameKey(player.getName()), connectionAddress(player), "join");
        authenticatedSessions.remove(player.getUniqueId());
        pendingRegistrations.remove(player.getUniqueId());
        currentEntryByPlayer.remove(player.getUniqueId());
        nextPreviewIndexByPlayer.remove(player.getUniqueId());
        nextCameraWriteIndexByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        activeKitByPlayer.remove(player.getUniqueId());
        lastPreviewExitAtNanosByPlayer.remove(player.getUniqueId());
        lastCameraItemUseAtNanosByPlayer.remove(player.getUniqueId());
        lastAuthenticationReminderAtNanosByPlayer.remove(player.getUniqueId());
        clearCameraPreview(player);
        clearSurvivalState(player);
        player.setGameMode(GameMode.ADVENTURE);
        player.setAllowFlight(false);
        player.setFlying(false);
        player.setGravity(false);
        player.teleport(worlds.authenticationSpawn());
        showAuthenticationTitle(player);
        sendAuthenticationInstructions(player);
    }

    public void handleQuit(Player player) {
        if (worlds.isSurvivalWorld(player.getWorld())) {
            saveSurvivalState(player);
            survivalInventories.markActive(player.getUniqueId());
        }
        store.recordConnection(nicknameKey(player.getName()), connectionAddress(player), "quit");
        authenticatedSessions.remove(player.getUniqueId());
        pendingRegistrations.remove(player.getUniqueId());
        currentEntryByPlayer.remove(player.getUniqueId());
        loginFailures.remove(player.getUniqueId());
        nextPreviewIndexByPlayer.remove(player.getUniqueId());
        nextCameraWriteIndexByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        activeKitByPlayer.remove(player.getUniqueId());
        lastPreviewExitAtNanosByPlayer.remove(player.getUniqueId());
        lastCameraItemUseAtNanosByPlayer.remove(player.getUniqueId());
        lastAuthenticationReminderAtNanosByPlayer.remove(player.getUniqueId());
        clearCameraPreview(player);
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
        if (isReservedNpcNickname(nicknameKey)) {
            message(player, NamedTextColor.RED, "That nickname is reserved for a Hill 175 category guide.");
            return;
        }
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

    public void tickSessionLocks() {
        long now = System.nanoTime();
        for (Player online : Bukkit.getOnlinePlayers()) {
            if (!isAuthenticated(online)) {
                enforceAuthenticationLock(online);
                Long previous = lastAuthenticationReminderAtNanosByPlayer.get(online.getUniqueId());
                if (previous == null || now - previous >= AUTHENTICATION_REMINDER_INTERVAL_NANOS) {
                    showAuthenticationTitle(online);
                    online.sendActionBar(Component.text(authenticationHint(online), NamedTextColor.YELLOW));
                    lastAuthenticationReminderAtNanosByPlayer.put(online.getUniqueId(), now);
                }
                continue;
            }
            PreviewState preview = activePreviewsByPlayer.get(online.getUniqueId());
            if (preview != null) {
                enforceCameraPreviewLock(online, preview);
            }
        }
    }

    public Optional<Location> lockedSessionLocation(Player player) {
        PreviewState preview = activePreviewsByPlayer.get(player.getUniqueId());
        if (preview != null) {
            return Optional.of(preview.bodyLocation().clone());
        }
        if (!isAuthenticated(player)) {
            return Optional.of(worlds.authenticationSpawn());
        }
        return Optional.empty();
    }

    private void enforceAuthenticationLock(Player player) {
        player.setGameMode(GameMode.ADVENTURE);
        player.setAllowFlight(false);
        player.setFlying(false);
        player.setGravity(false);
        Location locked = worlds.authenticationSpawn();
        if (!samePose(player.getLocation(), locked, 0.001, 0.01f)) {
            player.teleport(locked);
        }
    }

    private void enforceCameraPreviewLock(Player player, PreviewState preview) {
        player.setGameMode(GameMode.ADVENTURE);
        player.setGravity(false);
        player.setAllowFlight(true);
        player.setFlying(true);
        PreviewState active = ensureCameraAnchor(player, preview);
        if (!samePose(player.getLocation(), active.bodyLocation(), 0.001, 0.01f)) {
            player.teleport(active.bodyLocation());
        }
        focusCamera(player, active);
    }

    private String authenticationHint(Player player) {
        if (store.account(nicknameKey(player.getName())).isPresent()) {
            return "Use /login <password> to enter Hill 175";
        }
        return "Use /register " + player.getName() + " <password> <repeatPassword>";
    }

    public void sendRules(Player player) {
        message(player, NamedTextColor.GOLD, "Hill 175 Competition Rules");
        message(player, NamedTextColor.WHITE, "Create up to two entries in different categories. Teams may have up to two people.");
        message(player, NamedTextColor.WHITE, "Build only in your entry. Visitors can fly and observe but cannot modify blocks.");
        message(player, NamedTextColor.WHITE, "Living mobs, portals, explosions, destructive commands, and bypass attempts are blocked.");
        message(player, NamedTextColor.WHITE, "Right-click Capture Camera View to save up to three submission views; click a camera marker to preview it.");
        message(player, NamedTextColor.WHITE, "Use /help, the Competition Compass, or Entry Controls instead of remembering long command chains.");
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
        message(player, NamedTextColor.WHITE, "/camera - open fixed-view camera controls; /camera list or /camera remove <1-3>");
        message(player, NamedTextColor.WHITE, "/rules - review the competition rules");
        message(player, NamedTextColor.GRAY, "Most actions are also available through the Compass and entry menus.");
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
        boolean fromSurvival = worlds.isSurvivalWorld(player.getWorld());
        if (fromSurvival) {
            saveSurvivalState(player);
        }
        worlds.ensureEntryWorld(entry);
        if (worlds.synchronizePeopleRegion(entry)) {
            store.saveEntry(entry);
        }
        if (entry.category() == Category.PEOPLE && !worlds.isPeopleWorldReady(entry.worldName())) {
            currentEntryByPlayer.put(player.getUniqueId(), entry.id());
            pendingPeopleEntryByPlayer.put(player.getUniqueId(), entry.id());
            if (!teleportEndingCameraPreview(player, worlds.hubSpawn())) {
                currentEntryByPlayer.remove(player.getUniqueId());
                pendingPeopleEntryByPlayer.remove(player.getUniqueId());
                message(player, NamedTextColor.RED, "The lobby teleport was interrupted. Use /hub to try again.");
                return;
            }
            if (fromSurvival) {
                clearSurvivalState(player);
                survivalInventories.markInactive(player.getUniqueId());
            }
            player.setGravity(true);
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
            message(player, NamedTextColor.AQUA, "The People world is still loading from the campus template. You'll be teleported in automatically when it is ready.");
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
        if (!teleportEndingCameraPreview(player, safeSpawn.get())) {
            pendingPeopleEntryByPlayer.remove(player.getUniqueId());
            message(player, NamedTextColor.RED, "The entry teleport was interrupted. Try again from the Competition Compass.");
            return;
        }
        if (fromSurvival) {
            clearSurvivalState(player);
            survivalInventories.markInactive(player.getUniqueId());
        }
        currentEntryByPlayer.put(player.getUniqueId(), entry.id());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        refreshCameraMarkers(entry);
        if (entry.category() == Category.PEOPLE) {
            message(player, NamedTextColor.AQUA,
                    "This People build was spawned from the server's Hill School campus template.");
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
        boolean fromSurvival = worlds.isSurvivalWorld(player.getWorld());
        if (fromSurvival) {
            saveSurvivalState(player);
        }
        if (!teleportEndingCameraPreview(player, worlds.hubSpawn())) {
            message(player, NamedTextColor.RED, "The lobby teleport was interrupted. Use /hub to try again.");
            return;
        }
        if (fromSurvival) {
            clearSurvivalState(player);
            survivalInventories.markInactive(player.getUniqueId());
        }
        currentEntryByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        player.setGravity(true);
        player.setGameMode(GameMode.ADVENTURE);
        player.setAllowFlight(true);
        player.setFlying(false);
        giveHubItems(player);
        sendHubTip(player);
    }

    public void teleportSurvival(Player player) {
        if (!isAuthenticated(player)) {
            return;
        }
        boolean fromSurvival = worlds.isSurvivalWorld(player.getWorld());
        Location target = fromSurvival
                ? player.getLocation()
                : survivalInventories.lastLocation(player)
                        .filter(location -> worlds.isSurvivalWorld(location.getWorld()))
                        .orElseGet(worlds::survivalSpawn);
        if (!teleportEndingCameraPreview(player, target)) {
            message(player, NamedTextColor.RED, "The survival teleport was interrupted. Try again from the Survival guide.");
            return;
        }
        currentEntryByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        restoreSurvivalInventory(player);
        survivalInventories.clearDeathPending(player.getUniqueId());
        setSurvivalMode(player);
        activeKitByPlayer.put(player.getUniqueId(), SURVIVAL_KIT);
        survivalInventories.markActive(player.getUniqueId());
        message(player, NamedTextColor.GREEN, "Survival World: normal survival gameplay is enabled here. Use /hub to return.");
    }

    public void handleSurvivalRespawn(Player player) {
        if (!isAuthenticated(player)) {
            return;
        }
        currentEntryByPlayer.remove(player.getUniqueId());
        pendingPeopleEntryByPlayer.remove(player.getUniqueId());
        setSurvivalMode(player);
        activeKitByPlayer.put(player.getUniqueId(), SURVIVAL_KIT);
        survivalInventories.save(player);
        survivalInventories.clearDeathPending(player.getUniqueId());
        survivalInventories.markActive(player.getUniqueId());
    }

    public void handleSurvivalDeath(Player player) {
        if (!worlds.isSurvivalWorld(player.getWorld())) {
            return;
        }
        survivalInventories.saveAfterDeath(player);
        survivalInventories.markDeathPending(player.getUniqueId());
        survivalInventories.markActive(player.getUniqueId());
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
        if (worlds.isSurvivalWorld(location)) {
            return true;
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
        if (isCameraPreviewing(player)) {
            return;
        }
        if (worlds.isSurvivalWorld(location)) {
            currentEntryByPlayer.remove(player.getUniqueId());
            pendingPeopleEntryByPlayer.remove(player.getUniqueId());
            if (!SURVIVAL_KIT.equals(activeKitByPlayer.get(player.getUniqueId()))) {
                restoreSurvivalInventory(player);
                activeKitByPlayer.put(player.getUniqueId(), SURVIVAL_KIT);
            }
            setSurvivalMode(player);
            return;
        }
        Optional<Entry> entry = entryAt(location);
        if (entry.isPresent()) {
            Entry activeEntry = entry.get();
            currentEntryByPlayer.put(player.getUniqueId(), activeEntry.id());
            pendingPeopleEntryByPlayer.remove(player.getUniqueId());
            boolean ownerMode = activeEntry.isMember(nicknameKey(player.getName()))
                    && !activeEntry.submitted()
                    && !worlds.isResetting(activeEntry.id());
            boolean entryOwner = activeEntry.isMember(nicknameKey(player.getName()));
            String desiredKit = ownerMode
                    ? ownerKit(activeEntry)
                    : visitorKit(activeEntry, entryOwner);
            if (ownerMode) {
                setOwnerMode(player);
            } else {
                setVisitorMode(player);
            }
            if (desiredKit.equals(activeKitByPlayer.get(player.getUniqueId()))) {
                return;
            }
            if (ownerMode) {
                giveEntryOwnerItems(player, activeEntry);
            } else {
                giveEntryVisitorItems(player, activeEntry, entryOwner);
            }
            return;
        }
        if (location.getWorld() != null && location.getWorld().equals(worlds.hubWorld())) {
            if (!pendingPeopleEntryByPlayer.containsKey(player.getUniqueId())) {
                currentEntryByPlayer.remove(player.getUniqueId());
            }
            if (HUB_KIT.equals(activeKitByPlayer.get(player.getUniqueId()))) {
                return;
            }
            player.setGravity(true);
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
        switchEntry(player, current.get(), newCategory);
    }

    public void switchEntry(Player player, Entry entry, Category newCategory) {
        if (!ensureEditableEntryAccess(player, entry)) {
            return;
        }
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
        cancelPendingPeopleEntry(entry.id());
        evacuateEntry(entry);
        clearCameraMarkers(entry);
        Runnable finishSwitch = () -> {
            int allocationIndex = newCategory == Category.PEOPLE ? 0 : store.nextAllocation(newCategory);
            WorldModule.Allocation allocation;
            try {
                allocation = worlds.allocate(newCategory, allocationIndex, entry.id());
            } catch (IllegalStateException exception) {
                message(player, NamedTextColor.RED, exception.getMessage());
                return;
            }
            entry.category(newCategory);
            entry.worldName(allocation.worldName());
            entry.region(allocation.region());
            entry.allocationIndex(allocation.allocationIndex());
            entry.title("");
            entry.description("");
            entry.clearCameraPoses();
            store.saveEntry(entry);
            if (player.isOnline()) {
                teleportToEntry(player, entry, false);
                message(player, NamedTextColor.GREEN, "Entry switched to " + newCategory.displayName() + ".");
            }
        };
        message(player, NamedTextColor.YELLOW,
                "Category change started. Your previous build space is being restored first.");
        if (entry.category() == Category.PEOPLE) {
            if (worlds.deletePrivateWorld(entry)) {
                finishSwitch.run();
            } else {
                refreshCameraMarkers(entry);
                message(player, NamedTextColor.RED,
                        "Category change failed because the private world could not be removed. Staff can retry after checking the server log.");
            }
        } else {
            worlds.reset(entry, finishSwitch, exception -> {
                refreshCameraMarkers(entry);
                if (player.isOnline()) {
                    message(player, NamedTextColor.RED,
                            "Category change failed while restoring the old build. Nothing was reallocated; please retry or contact staff.");
                }
            });
        }
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

    public boolean recordCamera(Player player) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        if (current.isEmpty()) {
            return false;
        }
        int slot = current.get().firstEmptyCameraSlot()
                .orElseGet(() -> normalizedCameraWriteIndex(player, current.get()));
        return recordCamera(player, slot);
    }

    public void useCameraItem(Player player) {
        Optional<Entry> current = currentEntry(player);
        if (current.isPresent() && canEditCameras(player, current.get())) {
            long now = System.nanoTime();
            Long previousUse = lastCameraItemUseAtNanosByPlayer.put(player.getUniqueId(), now);
            if (previousUse == null || now - previousUse >= CAMERA_CAPTURE_SILENCE_NANOS) {
                recordCamera(player);
            }
            return;
        }
        previewNextCamera(player);
    }

    public boolean recordCamera(Player player, int oneBasedSlot) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        if (current.isEmpty()) {
            return false;
        }
        Entry entry = current.get();
        if (oneBasedSlot < 1 || oneBasedSlot > Entry.MAX_CAMERA_SLOTS) {
            message(player, NamedTextColor.RED, "Camera slot must be 1, 2, or 3.");
            return false;
        }
        if (!entry.region().contains(player.getLocation())) {
            message(player, NamedTextColor.RED, "Stand inside your build space to save a camera pose.");
            return false;
        }
        CameraPose pose = CameraPose.from(player.getEyeLocation());
        if (worlds.safeCameraTeleport(entry, pose, player.getEyeHeight()).isEmpty()) {
            message(player, NamedTextColor.RED,
                    "That camera position is obstructed, unsafe, or aimed outside your build. Move to a clear position, aim inward, and try again.");
            return false;
        }
        boolean replacing = entry.cameraPose(oneBasedSlot).isPresent();
        entry.setCameraPose(oneBasedSlot, pose);
        store.saveEntry(entry);
        refreshCameraMarkers(entry);
        nextCameraWriteIndexByPlayer.put(player.getUniqueId(), oneBasedSlot % Entry.MAX_CAMERA_SLOTS + 1);
        player.playSound(player.getLocation(), Sound.ENTITY_ITEM_PICKUP, 1.0f, 1.4f);
        message(player, NamedTextColor.GREEN, "Camera " + oneBasedSlot + "/3 "
                + (replacing ? "updated." : "saved."));
        return true;
    }

    public boolean removeCamera(Player player, int index) {
        Optional<Entry> current = requireCurrentEditableEntry(player);
        if (current.isEmpty()) {
            return false;
        }
        if (!current.get().removeCameraPose(index)) {
            message(player, NamedTextColor.RED, "No camera pose exists at index " + index + ".");
            return false;
        }
        store.saveEntry(current.get());
        refreshCameraMarkers(current.get());
        nextCameraWriteIndexByPlayer.put(player.getUniqueId(), index);
        message(player, NamedTextColor.GREEN, "Camera pose " + index + " removed.");
        return true;
    }

    public Optional<CameraPreviewContext> activeCameraPreview(Player player) {
        PreviewState preview = activePreviewsByPlayer.get(player.getUniqueId());
        if (preview == null) {
            return Optional.empty();
        }
        Optional<Entry> entry = store.entry(preview.entryId());
        return entry.map(value -> new CameraPreviewContext(value, preview.oneBasedIndex()));
    }

    public boolean canEditCameras(Player player, Entry entry) {
        return isAuthenticated(player)
                && entry.isMember(nicknameKey(player.getName()))
                && !entry.submitted()
                && !worlds.isResetting(entry.id());
    }

    public boolean removeActiveCameraPreview(Player player, UUID entryId, int oneBasedIndex) {
        PreviewState preview = activePreviewsByPlayer.get(player.getUniqueId());
        if (preview == null || !preview.entryId().equals(entryId) || preview.oneBasedIndex() != oneBasedIndex) {
            message(player, NamedTextColor.RED, "That camera preview is no longer active.");
            return false;
        }
        Optional<Entry> current = store.entry(entryId);
        if (current.isEmpty() || !canEditCameras(player, current.get())) {
            message(player, NamedTextColor.RED, "Only an entry owner may remove an unlocked camera pose.");
            return false;
        }
        Entry entry = current.get();
        if (!entry.removeCameraPose(oneBasedIndex)) {
            message(player, NamedTextColor.RED, "No camera pose exists at index " + oneBasedIndex + ".");
            return false;
        }
        store.saveEntry(entry);
        PreviewState cleared = clearCameraPreview(player);
        refreshCameraMarkers(entry);
        if (cleared != null && player.teleport(cleared.returnLocation())) {
            restoreEntryKitAfterPreview(player, cleared);
        } else if (cleared != null) {
            refreshMovementMode(player, player.getLocation());
        }
        nextCameraWriteIndexByPlayer.put(player.getUniqueId(), oneBasedIndex);
        lastPreviewExitAtNanosByPlayer.put(player.getUniqueId(), System.nanoTime());
        message(player, NamedTextColor.GREEN, "Camera pose " + oneBasedIndex + " removed.");
        return true;
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
        for (int slot : current.get().savedCameraSlots()) {
            CameraPose pose = current.get().cameraPose(slot).orElseThrow();
            message(player, NamedTextColor.AQUA, slot + ". " + pose.worldName() + " @ "
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
        int nextIndex = nextSavedCameraIndex(entry, nextPreviewIndexByPlayer.getOrDefault(player.getUniqueId(), 0));
        if (nextIndex < 0) {
            message(player, NamedTextColor.YELLOW, "Save a camera pose first.");
            return;
        }
        CameraPose pose = entry.cameraPose(nextIndex + 1).orElseThrow();
        Optional<Location> target = worlds.safeCameraTeleport(entry, pose, player.getEyeHeight(true));
        if (target.isEmpty()) {
            message(player, NamedTextColor.RED,
                    "That camera pose is now obstructed or unsafe. Clear the viewpoint or save a replacement pose.");
            return;
        }
        if (!beginCameraPreview(player, entry, nextIndex + 1, target.get())) {
            message(player, NamedTextColor.RED, "The camera teleport was interrupted. Try the preview again.");
            return;
        }
        nextPreviewIndexByPlayer.put(player.getUniqueId(), (nextIndex + 1) % Entry.MAX_CAMERA_SLOTS);
        announceCameraPreview(player, nextIndex + 1, entry.cameraPoses().size());
    }

    public void previewCamera(Player player, Entry entry, int oneBasedIndex) {
        if (!mayPreviewEntry(player, entry)) {
            return;
        }
        int index = oneBasedIndex - 1;
        if (index < 0 || index >= Entry.MAX_CAMERA_SLOTS || entry.cameraPose(oneBasedIndex).isEmpty()) {
            message(player, NamedTextColor.RED, "No camera pose exists at index " + oneBasedIndex + ".");
            return;
        }
        CameraPose pose = entry.cameraPose(oneBasedIndex).orElseThrow();
        Optional<Location> target = worlds.safeCameraTeleport(entry, pose, player.getEyeHeight(true));
        if (target.isEmpty()) {
            message(player, NamedTextColor.RED,
                    "That camera pose is now obstructed or unsafe. Clear the viewpoint or save a replacement pose.");
            return;
        }
        if (!beginCameraPreview(player, entry, oneBasedIndex, target.get())) {
            message(player, NamedTextColor.RED, "The camera teleport was interrupted. Try the preview again.");
            return;
        }
        nextPreviewIndexByPlayer.put(player.getUniqueId(), (index + 1) % Entry.MAX_CAMERA_SLOTS);
        announceCameraPreview(player, oneBasedIndex, entry.cameraPoses().size());
    }

    public boolean previewCameraMarker(Player player, Entity entity) {
        if (!entity.getScoreboardTags().contains(CAMERA_MARKER_TAG)) {
            return false;
        }
        UUID entryId = null;
        Integer oneBasedIndex = null;
        for (String tag : entity.getScoreboardTags()) {
            if (tag.startsWith(CAMERA_MARKER_ENTRY_PREFIX)) {
                try {
                    entryId = UUID.fromString(tag.substring(CAMERA_MARKER_ENTRY_PREFIX.length()));
                } catch (IllegalArgumentException ignored) {
                    return false;
                }
            }
            if (tag.startsWith(CAMERA_MARKER_INDEX_PREFIX)) {
                try {
                    oneBasedIndex = Integer.parseInt(tag.substring(CAMERA_MARKER_INDEX_PREFIX.length()));
                } catch (NumberFormatException ignored) {
                    return false;
                }
            }
        }
        if (entryId == null || oneBasedIndex == null) {
            return false;
        }
        Optional<Entry> current = currentEntry(player);
        if (current.isEmpty() || !current.get().id().equals(entryId)) {
            return false;
        }
        Optional<Entry> entry = store.entry(entryId);
        if (entry.isEmpty()
                || !entry.get().worldName().equals(entity.getWorld().getName())) {
            return false;
        }
        previewCamera(player, entry.get(), oneBasedIndex);
        return true;
    }

    public boolean isCameraPreviewing(Player player) {
        return activePreviewsByPlayer.containsKey(player.getUniqueId());
    }

    public boolean acceptsCameraPreviewLeftClick(Player player) {
        PreviewState preview = activePreviewsByPlayer.get(player.getUniqueId());
        return preview != null && System.nanoTime() - preview.startedAtNanos() >= 150_000_000L;
    }

    public boolean acceptsCameraItemLeftClick(Player player) {
        Long lastExit = lastPreviewExitAtNanosByPlayer.get(player.getUniqueId());
        return lastExit == null || System.nanoTime() - lastExit >= 150_000_000L;
    }

    public Optional<Location> cameraPreviewLocation(Player player) {
        PreviewState preview = activePreviewsByPlayer.get(player.getUniqueId());
        return preview == null
                ? Optional.empty()
                : Optional.of(preview.bodyLocation().clone());
    }

    public boolean exitCameraPreview(Player player) {
        PreviewState preview = clearCameraPreview(player);
        if (preview == null) {
            return false;
        }
        if (!player.teleport(preview.returnLocation())) {
            activePreviewsByPlayer.put(player.getUniqueId(), preview);
            restoreActiveCameraPreview(player, preview);
            message(player, NamedTextColor.RED, "The camera preview could not return you to your previous position.");
            return false;
        }
        restoreEntryKitAfterPreview(player, preview);
        lastPreviewExitAtNanosByPlayer.put(player.getUniqueId(), System.nanoTime());
        message(player, NamedTextColor.AQUA, "Camera preview closed.");
        return true;
    }

    public void shutdown() {
        for (Player player : Bukkit.getOnlinePlayers()) {
            if (worlds.isSurvivalWorld(player.getWorld())) {
                saveSurvivalState(player);
                survivalInventories.markActive(player.getUniqueId());
            }
            PreviewState preview = clearCameraPreview(player);
            if (preview == null) {
                continue;
            }
            player.teleport(preview.returnLocation());
            restoreEntryKitAfterPreview(player, preview);
        }
        activePreviewsByPlayer.clear();
        previewBossBarsByPlayer.clear();
        lastPreviewExitAtNanosByPlayer.clear();
        lastCameraItemUseAtNanosByPlayer.clear();
    }

    private boolean teleportEndingCameraPreview(Player player, Location target) {
        PreviewState preview = clearCameraPreview(player);
        if (player.teleport(target)) {
            return true;
        }
        if (preview != null) {
            activePreviewsByPlayer.put(player.getUniqueId(), preview);
            restoreActiveCameraPreview(player, preview);
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

    private boolean isReservedNpcNickname(String nicknameKey) {
        if (RESERVED_NICKNAMES.contains(nicknameKey)) {
            return true;
        }
        for (Category category : Category.values()) {
            String path = "worlds.hub-npcs." + category.name().toLowerCase(Locale.ROOT) + ".profile-name";
            String profileName = plugin.getConfig().getString(path, "");
            if (nicknameKey.equals(nicknameKey(profileName))) {
                return true;
            }
        }
        String survivalProfileName = plugin.getConfig()
                .getString("worlds.hub-npcs.survival.profile-name", "HillSurvival");
        return nicknameKey.equals(nicknameKey(survivalProfileName));
    }

    private void authenticate(Player player, Account account, String successMessage) {
        authenticatedSessions.add(player.getUniqueId());
        lastAuthenticationReminderAtNanosByPlayer.remove(player.getUniqueId());
        store.recordConnection(account.nicknameKey(), connectionAddress(player), "authenticated");
        player.displayName(Component.text(account.displayName()));
        player.playerListName(Component.text(account.displayName(), NamedTextColor.GOLD));
        if (survivalInventories.isActive(player.getUniqueId())) {
            teleportSurvival(player);
        } else {
            teleportHub(player);
        }
        showWelcomeTitle(player, account.displayName());
        message(player, NamedTextColor.GREEN, successMessage);
        sendRules(player);
    }

    public void resetEntry(Player player, Entry entry) {
        if (!ensureEditableEntryAccess(player, entry)) {
            return;
        }
        boolean playerWasInEntry = isInEntryBuild(player, entry);
        message(player, NamedTextColor.YELLOW, "Reset started. All blocks in this entry will be restored.");
        cancelPendingPeopleEntry(entry.id());
        clearCameraMarkers(entry);
        evacuateEntry(entry);
        worlds.reset(entry, () -> {
            entry.clearCameraPoses();
            entry.title("");
            entry.description("");
            store.saveEntry(entry);
            refreshCameraMarkers(entry);
            if (player.isOnline()) {
                if (playerWasInEntry) {
                    teleportToEntry(player, entry, false);
                }
                message(player, NamedTextColor.GREEN, "Entry reset complete.");
            }
        }, exception -> {
            refreshCameraMarkers(entry);
            if (player.isOnline()) {
                message(player, NamedTextColor.RED,
                        "Entry reset failed and editing has been re-enabled. Please retry or contact staff.");
            }
        });
    }

    public void deleteEntry(Player player, Entry entry) {
        if (!ensureEditableEntryAccess(player, entry)) {
            return;
        }
        boolean playerWasInEntry = isInEntryBuild(player, entry);
        cancelPendingPeopleEntry(entry.id());
        clearCameraMarkers(entry);
        evacuateEntry(entry);
        Runnable finishDelete = () -> {
            store.deleteEntry(entry.id());
            currentEntryByPlayer.values().removeIf(id -> id.equals(entry.id()));
            if (player.isOnline()) {
                if (playerWasInEntry) {
                    teleportHub(player);
                }
                message(player, NamedTextColor.GREEN, "Entry deleted. You may create a replacement.");
            }
        };
        if (entry.category() == Category.PEOPLE) {
            if (worlds.deletePrivateWorld(entry)) {
                finishDelete.run();
            } else {
                refreshCameraMarkers(entry);
                message(player, NamedTextColor.RED,
                        "Entry deletion failed because the private world could not be removed. The entry was kept.");
            }
        } else {
            message(player, NamedTextColor.YELLOW,
                    "Deletion started. The build space is being restored before its slot is released.");
            worlds.reset(entry, finishDelete, exception -> {
                refreshCameraMarkers(entry);
                if (player.isOnline()) {
                    message(player, NamedTextColor.RED,
                            "Entry deletion failed while restoring the build space. The entry was kept.");
                }
            });
        }
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
        activeKitByPlayer.put(player.getUniqueId(), HUB_KIT);
    }

    private void giveEntryOwnerItems(Player player, Entry entry) {
        clearCompetitionItems(player);
        player.getInventory().setItem(0, competitionItem(Material.ENDER_PEARL, LOBBY_ITEM_ID, "Return to Lobby",
                "Right-click to return to the exhibition lobby."));
        givePeopleCampusChart(player, entry);
        player.getInventory().setItem(3, competitionItem(Material.ENDER_EYE, CAMERA_ITEM_ID, "Capture Camera View",
                "Right-click once to save your exact position and view."));
        player.getInventory().setItem(7, competitionItem(Material.WRITTEN_BOOK, RULES_ITEM_ID, "Hill 175 Rules",
                "Right-click to review competition rules."));
        player.getInventory().setItem(8, competitionItem(Material.NETHER_STAR, ENTRY_MENU_ITEM_ID, "Entry Controls",
                "Open the menu for this entry."));
        activeKitByPlayer.put(player.getUniqueId(), ownerKit(entry));
    }

    private void giveEntryVisitorItems(Player player, Entry entry, boolean owner) {
        clearCompetitionItems(player);
        player.getInventory().setItem(0, competitionItem(Material.ENDER_PEARL, LOBBY_ITEM_ID, "Return to Lobby",
                "Right-click to return to the exhibition lobby."));
        givePeopleCampusChart(player, entry);
        player.getInventory().setItem(3, competitionItem(Material.ENDER_EYE, CAMERA_ITEM_ID, "Next Camera View",
                "Right-click to view the next saved camera, or click a marker."));
        player.getInventory().setItem(7, competitionItem(Material.WRITTEN_BOOK, RULES_ITEM_ID, "Hill 175 Rules",
                "Right-click to review competition rules."));
        player.getInventory().setItem(8, competitionItem(owner ? Material.NETHER_STAR : Material.COMPASS,
                owner ? ENTRY_MENU_ITEM_ID : COMPASS_ITEM_ID,
                owner ? "Entry Controls" : "Competition Compass",
                owner ? "Open the menu for this entry." : "Open entries, visit builds, or create a project."));
        activeKitByPlayer.put(player.getUniqueId(), visitorKit(entry, owner));
    }

    private void giveCameraPreviewItems(Player player, Entry entry) {
        clearCompetitionItems(player);
        player.getInventory().setItem(0, competitionItem(Material.ENDER_PEARL, LOBBY_ITEM_ID, "Return to Lobby",
                "Right-click to return to the exhibition lobby."));
        givePeopleCampusChart(player, entry);
        player.getInventory().setItem(3, competitionItem(Material.BARRIER, CAMERA_PREVIEW_ITEM_ID, "Exit Camera Preview",
                "Left-click or right-click to return to your previous position."));
        // Marker/menu entry can start from any held slot. Put the exit control
        // directly in the player's hand on every entry and recovery path.
        player.getInventory().setHeldItemSlot(3);
        player.getInventory().setItem(7, competitionItem(Material.WRITTEN_BOOK, RULES_ITEM_ID, "Hill 175 Rules",
                "Right-click to review competition rules."));
        boolean owner = entry.isMember(nicknameKey(player.getName()));
        if (canEditCameras(player, entry)) {
            player.getInventory().setItem(4, competitionItem(Material.RED_DYE, CAMERA_PREVIEW_REMOVE_ITEM_ID,
                    "Remove This Camera", "Right-click to remove this exact camera pose after confirmation."));
        }
        player.getInventory().setItem(8, competitionItem(owner ? Material.NETHER_STAR : Material.COMPASS,
                owner ? ENTRY_MENU_ITEM_ID : COMPASS_ITEM_ID,
                owner ? "Entry Controls" : "Competition Compass",
                owner ? "Open the menu for this entry." : "Open entries, visit builds, or create a project."));
        activeKitByPlayer.put(player.getUniqueId(), previewKit(entry));
    }

    private void givePeopleCampusChart(Player player, Entry entry) {
        if (!shouldGiveCampusChart(entry, player.getWorld())) {
            return;
        }
        player.getInventory().setItem(CAMPUS_CHART_SLOT, campusChartItem(player, entry));
    }

    private ItemStack campusChartItem(Player player, Entry entry) {
        ItemStack item = competitionItem(Material.FILLED_MAP, CAMPUS_CHART_ITEM_ID, "People Campus Chart",
                "North is up. The red marker shows your position in this campus world.");
        MapView mapView = campusChartMapView(player, entry);
        if (mapView != null) {
            item.setData(DataComponentTypes.MAP_ID, MapId.mapId(mapView.getId()));
        }
        return item;
    }

    private MapView campusChartMapView(Player player, Entry entry) {
        World world = player.getWorld();
        if (world == null) {
            return null;
        }
        BuildRegion chartRegion = worlds.campusChartRegion(world).orElseGet(() -> campusChartBounds(entry));
        CampusChartMap cached = campusChartMapsByEntry.get(entry.id());
        if (cached != null
                && cached.world() == world
                && cached.region().equals(chartRegion)) {
            return cached.view();
        }

        MapView mapView = Bukkit.createMap(world);
        mapView.setCenterX(chartRegion.centerX());
        mapView.setCenterZ(chartRegion.centerZ());
        mapView.setScale(MapView.Scale.FARTHEST);
        mapView.setTrackingPosition(false);
        mapView.setUnlimitedTracking(false);
        mapView.setLocked(true);
        for (MapRenderer renderer : List.copyOf(mapView.getRenderers())) {
            mapView.removeRenderer(renderer);
        }
        mapView.addRenderer(new CampusChartMapRenderer(chartRegion));
        campusChartMapsByEntry.put(entry.id(), new CampusChartMap(chartRegion, world, mapView));
        return mapView;
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
        if (worlds.isResetting(entry.id())) {
            message(player, NamedTextColor.YELLOW,
                    "This entry is already being reset or changed. Please wait for it to finish.");
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
        for (World world : Bukkit.getWorlds()) {
            for (Entity entity : world.getEntities()) {
                if (entity.getScoreboardTags().contains(CAMERA_VIEW_ANCHOR_TAG)) {
                    entity.remove();
                }
            }
        }
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
        player.setGravity(true);
        player.setGameMode(GameMode.CREATIVE);
        player.setAllowFlight(true);
    }

    private void setVisitorMode(Player player) {
        player.setGravity(true);
        player.setGameMode(GameMode.SPECTATOR);
        player.setAllowFlight(true);
    }

    private void setSurvivalMode(Player player) {
        player.setGravity(true);
        player.setGameMode(GameMode.SURVIVAL);
        player.setAllowFlight(false);
        player.setFlying(false);
    }

    private void clearSurvivalState(Player player) {
        player.closeInventory();
        player.setItemOnCursor(null);
        player.getInventory().clear();
        player.getEnderChest().clear();
        for (PotionEffect effect : player.getActivePotionEffects()) {
            player.removePotionEffect(effect.getType());
        }
        player.setLevel(0);
        player.setExp(0.0f);
        player.setTotalExperience(0);
        player.setFoodLevel(20);
        player.setSaturation(5.0f);
        player.setExhaustion(0.0f);
        if (player.getHealth() > 0.0) {
            player.setHealth(player.getMaxHealth());
        }
        player.setRemainingAir(player.getMaximumAir());
        player.setFireTicks(0);
    }

    private void restoreSurvivalInventory(Player player) {
        survivalInventories.restore(player);
    }

    private void saveSurvivalState(Player player) {
        if (survivalInventories.isDeathPending(player.getUniqueId())) {
            return;
        }
        settleSurvivalCursor(player);
        survivalInventories.save(player);
    }

    private void settleSurvivalCursor(Player player) {
        player.closeInventory();
        ItemStack cursor = player.getItemOnCursor();
        if (cursor == null || cursor.getType().isAir()) {
            return;
        }
        player.setItemOnCursor(null);
        player.getInventory().addItem(cursor.clone()).values().forEach(leftover ->
                player.getWorld().dropItemNaturally(player.getLocation(), leftover));
    }

    private boolean beginCameraPreview(Player player, Entry entry, int oneBasedIndex, Location target) {
        PreviewState previous = activePreviewsByPlayer.get(player.getUniqueId());
        Location returnLocation = previous == null
                ? player.getLocation().clone()
                : previous.returnLocation().clone();
        Location cameraLocation = target.clone().add(0.0, player.getEyeHeight(true), 0.0);
        Entity cameraAnchor = spawnCameraAnchor(cameraLocation);
        PreviewState preview = new PreviewState(
                entry.id(),
                oneBasedIndex,
                returnLocation,
                target.clone(),
                cameraLocation,
                cameraAnchor.getUniqueId(),
                System.nanoTime()
        );
        activePreviewsByPlayer.put(player.getUniqueId(), preview);
        player.setSneaking(false);
        player.setSwimming(false);
        player.setGliding(false);
        player.setGameMode(GameMode.ADVENTURE);
        player.setGravity(false);
        player.setAllowFlight(true);
        player.setFlying(true);
        if (player.teleport(target)) {
            if (previous != null) {
                destroyCameraAnchor(previous);
            }
            giveCameraPreviewItems(player, entry);
            setCameraMarkersVisible(player, entry, false);
            focusCamera(player, preview);
            Bukkit.getScheduler().runTaskLater(plugin, () -> {
                PreviewState active = activePreviewsByPlayer.get(player.getUniqueId());
                if (active != null && active.cameraAnchorId().equals(preview.cameraAnchorId())) {
                    focusCamera(player, active);
                }
            }, 1L);
            return true;
        }
        destroyCameraAnchor(preview);
        if (previous == null) {
            activePreviewsByPlayer.remove(player.getUniqueId());
            restoreEntryKitAfterPreview(player, preview);
        } else {
            activePreviewsByPlayer.put(player.getUniqueId(), previous);
            restoreActiveCameraPreview(player, previous);
        }
        return false;
    }

    private Entity spawnCameraAnchor(Location cameraLocation) {
        if (cameraLocation.getWorld() == null) {
            throw new IllegalArgumentException("Camera anchor requires a world");
        }
        cameraLocation.getChunk().load();
        return cameraLocation.getWorld().spawn(cameraLocation, Interaction.class, interaction -> {
            interaction.setInteractionWidth(0.01f);
            interaction.setInteractionHeight(0.01f);
            interaction.setResponsive(false);
            interaction.setGravity(false);
            interaction.setInvulnerable(true);
            interaction.setSilent(true);
            interaction.setPersistent(false);
            interaction.setRotation(cameraLocation.getYaw(), cameraLocation.getPitch());
            interaction.addScoreboardTag(CAMERA_VIEW_ANCHOR_TAG);
        });
    }

    private PreviewState ensureCameraAnchor(Player player, PreviewState preview) {
        Entity anchor = Bukkit.getEntity(preview.cameraAnchorId());
        if (anchor == null || !anchor.isValid()) {
            anchor = spawnCameraAnchor(preview.cameraLocation());
            PreviewState updated = preview.withCameraAnchor(anchor.getUniqueId());
            activePreviewsByPlayer.put(player.getUniqueId(), updated);
            return updated;
        }
        if (!samePose(anchor.getLocation(), preview.cameraLocation(), 0.001, 0.01f)) {
            anchor.teleport(preview.cameraLocation());
        }
        anchor.setRotation(preview.cameraLocation().getYaw(), preview.cameraLocation().getPitch());
        return preview;
    }

    private void focusCamera(Player player, PreviewState preview) {
        PreviewState active = ensureCameraAnchor(player, preview);
        Entity anchor = Bukkit.getEntity(active.cameraAnchorId());
        if (anchor != null && cameraBridge.focus(player, anchor)) {
            return;
        }
        if (!samePose(player.getLocation(), active.bodyLocation(), 0.001, 0.01f)) {
            player.teleport(active.bodyLocation());
        }
    }

    private void destroyCameraAnchor(PreviewState preview) {
        Entity anchor = Bukkit.getEntity(preview.cameraAnchorId());
        if (anchor != null && anchor.getScoreboardTags().contains(CAMERA_VIEW_ANCHOR_TAG)) {
            anchor.remove();
        }
    }

    private void announceCameraPreview(Player player, int oneBasedIndex, int cameraCount) {
        player.playSound(player.getLocation(), Sound.ENTITY_ENDERMAN_TELEPORT, 0.7f, 1.2f);
        showCameraPreviewDisplay(player, oneBasedIndex, cameraCount);
        message(player, NamedTextColor.AQUA, "Previewing camera slot " + oneBasedIndex
                + " (" + cameraCount + "/3 saved). Use Exit Camera Preview to return.");
    }

    private void showCameraPreviewDisplay(Player player, int oneBasedIndex, int cameraCount) {
        hideCameraPreviewDisplay(player);
        BossBar bossBar = BossBar.bossBar(
                Component.text("Previewing camera slot " + oneBasedIndex + " (" + cameraCount + "/3 saved)"
                        + "  -  Use Exit Camera Preview to return", NamedTextColor.AQUA),
                1.0f,
                BossBar.Color.BLUE,
                BossBar.Overlay.PROGRESS
        );
        previewBossBarsByPlayer.put(player.getUniqueId(), bossBar);
        player.showBossBar(bossBar);
        player.clearTitle();
        player.showTitle(Title.title(
                Component.text("Previewing camera slot " + oneBasedIndex, NamedTextColor.AQUA, TextDecoration.BOLD),
                Component.text("Use Exit Camera Preview to return", NamedTextColor.WHITE),
                Title.Times.times(Duration.ZERO, Duration.ofSeconds(3), Duration.ofMillis(500))
        ));
    }

    private void hideCameraPreviewDisplay(Player player) {
        BossBar bossBar = previewBossBarsByPlayer.remove(player.getUniqueId());
        if (bossBar != null) {
            player.hideBossBar(bossBar);
        }
    }

    private PreviewState clearCameraPreview(Player player) {
        PreviewState preview = activePreviewsByPlayer.remove(player.getUniqueId());
        if (preview != null) {
            cameraBridge.reset(player);
            destroyCameraAnchor(preview);
            player.setGravity(true);
            player.clearTitle();
            hideCameraPreviewDisplay(player);
            store.entry(preview.entryId()).ifPresent(entry ->
                    setCameraMarkersVisible(player, entry, shouldShowCameraMarkers(player, entry)));
        }
        return preview;
    }

    private void restoreEntryKitAfterPreview(Player player, PreviewState preview) {
        Optional<Entry> entry = store.entry(preview.entryId());
        if (entry.isEmpty() || player.getLocation().getWorld() == null
                || !entry.get().worldName().equals(player.getLocation().getWorld().getName())) {
            refreshMovementMode(player, player.getLocation());
            return;
        }
        Entry restoredEntry = entry.get();
        boolean owner = restoredEntry.isMember(nicknameKey(player.getName()));
        if (owner && !restoredEntry.submitted() && !worlds.isResetting(restoredEntry.id())) {
            setOwnerMode(player);
            giveEntryOwnerItems(player, restoredEntry);
        } else {
            setVisitorMode(player);
            giveEntryVisitorItems(player, restoredEntry, owner);
        }
    }

    private void restoreActiveCameraPreview(Player player, PreviewState preview) {
        player.setGameMode(GameMode.ADVENTURE);
        player.setGravity(false);
        player.setAllowFlight(true);
        player.setFlying(true);
        ensureCameraAnchor(player, preview);
        store.entry(preview.entryId()).ifPresent(entry -> {
            giveCameraPreviewItems(player, entry);
            setCameraMarkersVisible(player, entry, false);
            showCameraPreviewDisplay(player, preview.oneBasedIndex(), entry.cameraPoses().size());
        });
    }

    private void synchronizeEntryModes(Entry entry) {
        for (Player online : Bukkit.getOnlinePlayers()) {
            String nicknameKey = nicknameKey(online.getName());
            if (isCameraPreviewing(online)) {
                continue;
            }
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
            if (isInEntryBuild(online, entry)) {
                teleportHub(online);
            }
        }
    }

    private boolean isInEntryBuild(Player player, Entry entry) {
        boolean insideOwnedRegion = entry.region().contains(player.getLocation());
        boolean insidePrivatePeopleWorld = entry.category() == Category.PEOPLE
                && player.getWorld().getName().equals(entry.worldName());
        return insideOwnedRegion || insidePrivatePeopleWorld;
    }

    private void cancelPendingPeopleEntry(UUID entryId) {
        pendingPeopleEntryByPlayer.values().removeIf(entryId::equals);
    }

    private void showAuthenticationTitle(Player player) {
        player.showTitle(net.kyori.adventure.title.Title.title(
                Component.text("Hill 175", NamedTextColor.GOLD, TextDecoration.BOLD),
                Component.text("Please sign in using your Hill credentials", NamedTextColor.WHITE),
                Title.Times.times(Duration.ZERO, Duration.ofSeconds(3), Duration.ZERO)
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
                "Tip: right-click the Compass, a category guide, or the Survival guide; /entry home returns to your build.");
    }

    private void sendOwnerEntryTip(Player player) {
        message(player, NamedTextColor.GRAY,
                "Tip: stand where you want the view, aim, then right-click Capture Camera View. Click its marker to preview it.");
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
        for (int markerNumber : entry.savedCameraSlots()) {
            CameraPose pose = entry.cameraPose(markerNumber).orElseThrow();
            Location markerLocation = new Location(world, pose.x(), pose.y() - 1.6, pose.z(), pose.yaw(), pose.pitch());
            world.spawn(markerLocation, ArmorStand.class, stand -> {
                stand.customName(Component.text("Camera " + markerNumber + " - Click to view", NamedTextColor.AQUA));
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
                stand.setSmall(false);
                EntityEquipment equipment = stand.getEquipment();
                if (equipment != null) {
                    equipment.setHelmet(new ItemStack(Material.ENDER_EYE));
                }
                configureCameraMarker(stand, entry, markerNumber);
            });
            Location hitboxLocation = new Location(
                    world,
                    pose.x(),
                    pose.y() - CAMERA_MARKER_HITBOX_HEIGHT / 2.0,
                    pose.z(),
                    pose.yaw(),
                    pose.pitch()
            );
            world.spawn(hitboxLocation, Interaction.class, hitbox -> {
                hitbox.setInteractionWidth(CAMERA_MARKER_HITBOX_WIDTH);
                hitbox.setInteractionHeight(CAMERA_MARKER_HITBOX_HEIGHT);
                hitbox.setResponsive(true);
                hitbox.setGravity(false);
                hitbox.setInvulnerable(true);
                hitbox.setSilent(true);
                hitbox.setPersistent(true);
                configureCameraMarker(hitbox, entry, markerNumber);
            });
        }
    }

    private void configureCameraMarker(Entity marker, Entry entry, int markerNumber) {
        marker.addScoreboardTag(CAMERA_MARKER_TAG);
        marker.addScoreboardTag(cameraMarkerEntryTag(entry.id()));
        marker.addScoreboardTag(CAMERA_MARKER_INDEX_PREFIX + markerNumber);
        for (Player viewer : marker.getWorld().getPlayers()) {
            if (shouldShowCameraMarkers(viewer, entry)) {
                viewer.showEntity(plugin, marker);
            } else {
                viewer.hideEntity(plugin, marker);
            }
        }
    }

    private void setCameraMarkersVisible(Player viewer, Entry entry, boolean visible) {
        World world = Bukkit.getWorld(entry.worldName());
        if (world == null) {
            return;
        }
        String entryTag = cameraMarkerEntryTag(entry.id());
        for (Entity entity : world.getEntities()) {
            if (!entity.getScoreboardTags().contains(CAMERA_MARKER_TAG)
                    || !entity.getScoreboardTags().contains(entryTag)) {
                continue;
            }
            if (visible) {
                viewer.showEntity(plugin, entity);
            } else {
                viewer.hideEntity(plugin, entity);
            }
        }
    }

    private boolean shouldShowCameraMarkers(Player viewer, Entry entry) {
        boolean viewingEntry = currentEntry(viewer)
                .map(current -> current.id().equals(entry.id()))
                .orElse(false);
        if (!viewingEntry && !viewer.hasPermission("hill175.staff")) {
            return false;
        }
        PreviewState preview = activePreviewsByPlayer.get(viewer.getUniqueId());
        return preview == null || !preview.entryId().equals(entry.id());
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

    private static boolean samePose(Location current, Location expected, double distanceTolerance, float angleTolerance) {
        if (current == null || expected == null || current.getWorld() == null || expected.getWorld() == null
                || !current.getWorld().getName().equals(expected.getWorld().getName())) {
            return false;
        }
        return current.distanceSquared(expected) <= distanceTolerance * distanceTolerance
                && Math.abs(angleDelta(current.getYaw(), expected.getYaw())) <= angleTolerance
                && Math.abs(angleDelta(current.getPitch(), expected.getPitch())) <= angleTolerance;
    }

    private static float angleDelta(float left, float right) {
        float delta = (left - right) % 360.0f;
        if (delta > 180.0f) {
            delta -= 360.0f;
        } else if (delta < -180.0f) {
            delta += 360.0f;
        }
        return delta;
    }

    private static String ownerKit(Entry entry) {
        return "owner:" + entry.id();
    }

    private static String visitorKit(Entry entry, boolean owner) {
        return "visitor:" + entry.id() + ":" + owner;
    }

    private static String previewKit(Entry entry) {
        return "preview:" + entry.id();
    }

    static boolean shouldGiveCampusChart(Entry entry, World world) {
        return entry.category() == Category.PEOPLE
                && world != null
                && entry.worldName().equals(world.getName());
    }

    private BuildRegion campusChartBounds(Entry entry) {
        return campusChartBounds(entry, plugin.getConfig().getIntegerList("people.campus-chart.block-bounds"));
    }

    static BuildRegion campusChartBounds(Entry entry, List<Integer> configuredBounds) {
        if (configuredBounds.size() != 6) {
            return entry.region();
        }
        try {
            return new BuildRegion(
                    entry.worldName(),
                    configuredBounds.get(0),
                    configuredBounds.get(1),
                    configuredBounds.get(2),
                    configuredBounds.get(3),
                    configuredBounds.get(4),
                    configuredBounds.get(5)
            );
        } catch (IllegalArgumentException ignored) {
            return entry.region();
        }
    }

    private int normalizedCameraWriteIndex(Player player, Entry entry) {
        int next = nextCameraWriteIndexByPlayer.getOrDefault(player.getUniqueId(), 1);
        if (next < 1 || next > Entry.MAX_CAMERA_SLOTS) {
            return 1;
        }
        return next;
    }

    private static int nextSavedCameraIndex(Entry entry, int startIndex) {
        int start = Math.floorMod(startIndex, Entry.MAX_CAMERA_SLOTS);
        for (int offset = 0; offset < Entry.MAX_CAMERA_SLOTS; offset++) {
            int index = (start + offset) % Entry.MAX_CAMERA_SLOTS;
            if (entry.cameraPose(index + 1).isPresent()) {
                return index;
            }
        }
        return -1;
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

    private record CampusChartMap(BuildRegion region, World world, MapView view) {
    }

    private record PreviewState(
            UUID entryId,
            int oneBasedIndex,
            Location returnLocation,
            Location bodyLocation,
            Location cameraLocation,
            UUID cameraAnchorId,
            long startedAtNanos
    ) {
        PreviewState withCameraAnchor(UUID newCameraAnchorId) {
            return new PreviewState(
                    entryId,
                    oneBasedIndex,
                    returnLocation.clone(),
                    bodyLocation.clone(),
                    cameraLocation.clone(),
                    newCameraAnchorId,
                    startedAtNanos
            );
        }
    }

    public record CameraPreviewContext(Entry entry, int oneBasedIndex) {
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
