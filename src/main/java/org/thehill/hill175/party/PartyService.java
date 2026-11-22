package org.thehill.hill175.party;

import com.destroystokyo.paper.event.player.PlayerStartSpectatingEntityEvent;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.event.HoverEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerPortalEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.event.player.PlayerRespawnEvent;
import org.bukkit.event.player.PlayerTeleportEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.party.PartyStore.Campus;
import org.thehill.hill175.party.PartyStore.Invitation;
import org.thehill.hill175.party.PartyStore.Phase;
import org.thehill.hill175.ui.IconMenu;
import org.thehill.hill175.world.WorldModule;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.function.Predicate;
import java.util.logging.Level;

public final class PartyService implements Listener, CommandExecutor, TabCompleter, AutoCloseable {
    public static final String PERSONAL_CAMPUS_MARKER = "personal-campus";
    private static final int PAGE_SIZE = 20;
    private static final List<String> COMMAND_ACTIONS = List.of("home", "invite", "accept", "decline", "join", "visit", "leave", "remove", "revoke");
    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final CompetitionStore store;
    private final WorldModule worlds;
    private final Runnable beforeCreate;
    private final Consumer<Entry> registerNewBranch;
    private final Predicate<Entry> frozen;
    private final PartyStore partyStore;
    private org.thehill.hill175.ui.PlayerActions playerActions;

    public void playerMenus(org.thehill.hill175.ui.PlayerActions playerActions) {
        this.playerActions = playerActions;
    }

    private final int maxGuests;
    private final Duration inviteExpiry;
    private final Duration inviteCooldown;
    private final Map<UUID, Campus> campusesByEntry = new HashMap<>();
    private final Set<UUID> newlyAllocated = new HashSet<>();
    private final Map<UUID, PendingVisit> pendingVisits = new HashMap<>();
    private Map<String, Campus> campuses = Map.of();
    private final BukkitTask expiryTask;
    private boolean unavailable;
    private boolean closed;

    public PartyService(JavaPlugin plugin, CompetitionModule competition, CompetitionStore store, WorldModule worlds,
                        Runnable beforeCreate, Consumer<Entry> registerNewBranch, Predicate<Entry> frozen) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.competition = Objects.requireNonNull(competition, "competition");
        this.store = Objects.requireNonNull(store, "store");
        this.worlds = Objects.requireNonNull(worlds, "worlds");
        this.beforeCreate = Objects.requireNonNull(beforeCreate, "beforeCreate");
        this.registerNewBranch = Objects.requireNonNull(registerNewBranch, "registerNewBranch");
        this.frozen = Objects.requireNonNull(frozen, "frozen");
        maxGuests = Math.clamp(plugin.getConfig().getInt("parties.max-guests", 12), 1, 100);
        inviteExpiry = Duration.ofSeconds(Math.clamp(plugin.getConfig().getLong("parties.invite-expiry-seconds", 600L), 30L, 86_400L));
        inviteCooldown = Duration.ofSeconds(Math.clamp(plugin.getConfig().getLong("parties.invite-cooldown-seconds", 10L), 1L, 3_600L));
        partyStore = new PartyStore(plugin.getDataFolder().toPath());
        try {
            campuses = partyStore.load();
            reindex();
            long interrupted = campuses.values().stream().filter(campus -> campus.phase() != Phase.READY).count();
            if (interrupted > 0) plugin.getLogger().warning(interrupted + " personal campus allocation(s) remain locked; no provenance was re-created.");
        } catch (Exception exception) {
            unavailable = true;
            plugin.getLogger().log(Level.SEVERE, "Personal campuses are locked because parties.yml could not be loaded. Preserve the file for recovery.", exception);
        }
        expiryTask = plugin.getServer().getScheduler().runTaskTimer(plugin, this::expireInvitations, 600L, 600L);
    }

    public boolean owns(Entry entry) {
        return entry != null && (campusesByEntry.containsKey(entry.id()) || PERSONAL_CAMPUS_MARKER.equals(entry.selectedBuildingId()));
    }

    public boolean isOwner(Player player, Entry entry) {
        if (!authenticated(player) || entry == null) return false;
        Campus campus = campusesByEntry.get(entry.id());
        return campus != null && campus.ownerKey().equals(competition.participantKey(player)) && validEntry(campus, entry);
    }

    public boolean canVisit(Player player, Entry entry) {
        if (closed || unavailable || !authenticated(player) || entry == null) return false;
        Campus campus = campusesByEntry.get(entry.id());
        if (campus == null || campus.phase() != Phase.READY || !validEntry(campus, entry)) return false;
        String identity = competition.participantKey(player);
        return campus.ownerKey().equals(identity) || campus.guests().containsKey(identity);
    }

    public boolean canBuild(Player player, Entry entry) {
        if (!canVisit(player, entry) || !worlds.isPeopleWorldReady(entry.worldName())) return false;
        try {
            return !frozen.test(entry);
        } catch (RuntimeException exception) {
            plugin.getLogger().log(Level.SEVERE, "Could not verify personal campus freeze/provenance for " + entry.id(), exception);
            return false;
        }
    }

    public Optional<Entry> personalEntry(Player player) {
        if (!authenticated(player)) return Optional.empty();
        Campus campus = campuses.get(competition.participantKey(player));
        return campus == null ? Optional.empty() : entry(campus);
    }

    public boolean home(Player player) {
        if (!available(player)) return false;
        try {
            Campus campus = ensurePersonalCampus(player);
            return travel(player, campus.ownerKey());
        } catch (PartyFailure failure) {
            if (failure.getMessage() != null) error(player, failure.getMessage());
        } catch (RuntimeException exception) {
            internalFailure(player, "Could not open a personal campus.", exception);
        }
        return false;
    }

    public void open(Player player) {
        safely(player, () -> openPage(player, Section.OVERVIEW, 0));
    }

    public void refreshEntry(Entry entry) {
        if (entry == null) return;
        for (Player online : plugin.getServer().getOnlinePlayers()) {
            if (online.getWorld().getName().equals(entry.worldName())) refreshMode(online);
        }
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] arguments) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Personal campus parties are available in game.");
            return true;
        }
        safely(player, () -> {
            if (!available(player)) return;
            if (command.getName().equalsIgnoreCase("invite") || label.equalsIgnoreCase("invite")) {
                if (arguments.length != 1) throw new PartyFailure("Use /invite <online player>.");
                invite(player, arguments[0]);
                return;
            }
            if (arguments.length == 0) {
                openPage(player, Section.OVERVIEW, 0);
                return;
            }
            String action = arguments[0].toLowerCase(Locale.ROOT);
            if (arguments.length == 1) {
                switch (action) {
                    case "home" -> home(player);
                    case "invite" -> openPage(player, Section.INVITE, 0);
                    case "accept" -> chooseInvitation(player, false);
                    case "decline" -> chooseInvitation(player, true);
                    case "join" -> join(player, null);
                    case "visit", "leave" -> openPage(player, Section.CAMPUSES, 0);
                    case "remove", "revoke" -> openPage(player, Section.MANAGE, 0);
                    default -> invite(player, arguments[0]);
                }
                return;
            }
            String target = String.join(" ", List.of(arguments).subList(1, arguments.length));
            switch (action) {
                case "invite" -> {
                    if (arguments.length != 2) throw new PartyFailure("Use /party invite <online player>.");
                    invite(player, target);
                }
                case "accept" -> accept(player, resolveInvitation(player, target));
                case "decline" -> decline(player, resolveInvitation(player, target));
                case "join" -> join(player, target);
                case "visit" -> visit(player, resolveVisitOwner(player, target));
                case "leave" -> leave(player, resolveOwner(player, target, Section.CAMPUSES));
                case "remove" -> remove(player, resolveRoster(player, target, false));
                case "revoke" -> revoke(player, resolveRoster(player, target, true));
                default -> throw new PartyFailure(usage());
            }
        });
        return true;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] arguments) {
        if (!(sender instanceof Player player) || unavailable || closed || !authenticated(player)) return List.of();
        String action = command.getName().equalsIgnoreCase("invite") || alias.equalsIgnoreCase("invite")
                ? "invite" : arguments.length > 0 ? arguments[0].toLowerCase(Locale.ROOT) : "";
        boolean inviteAlias = command.getName().equalsIgnoreCase("invite") || alias.equalsIgnoreCase("invite");
        if (!inviteAlias && arguments.length == 1) {
            List<String> choices = new ArrayList<>(COMMAND_ACTIONS);
            String identity = competition.participantKey(player);
            plugin.getServer().getOnlinePlayers().stream().filter(this::authenticated)
                    .filter(target -> !competition.participantKey(target).equals(identity))
                    .map(Player::getName).filter(name -> !COMMAND_ACTIONS.contains(name.toLowerCase(Locale.ROOT)))
                    .forEach(choices::add);
            return matching(choices, arguments[0]);
        }
        if (arguments.length != (inviteAlias ? 1 : 2)) return List.of();
        List<String> choices = new ArrayList<>();
        if (action.equals("invite")) {
            String identity = competition.participantKey(player);
            plugin.getServer().getOnlinePlayers().stream().filter(this::authenticated)
                    .filter(target -> !competition.participantKey(target).equals(identity))
                    .map(Player::getName).forEach(choices::add);
        } else if (action.equals("remove") || action.equals("revoke")) {
            Campus campus = campuses.get(competition.participantKey(player));
            if (campus != null) {
                if (action.equals("remove")) choices.addAll(campus.guests().values());
                else campus.invitations().values().stream().filter(invite -> invite.active(Instant.now()))
                        .map(Invitation::label).forEach(choices::add);
            }
        } else if (List.of("accept", "decline", "join", "visit", "leave").contains(action)) {
            Section section = action.equals("accept") || action.equals("decline") ? Section.INCOMING : Section.CAMPUSES;
            eligibleCampuses(player, section).stream().map(Campus::ownerLabel).forEach(choices::add);
            if (action.equals("join")) eligibleCampuses(player, Section.INCOMING).stream().map(Campus::ownerLabel).forEach(choices::add);
        }
        return matching(choices, arguments[arguments.length - 1]);
    }

    private Campus ensurePersonalCampus(Player player) {
        String ownerKey = competition.participantKey(player);
        Campus existing = campuses.get(ownerKey);
        if (existing != null) return existing;
        if (store.entries().stream().anyMatch(entry -> PERSONAL_CAMPUS_MARKER.equals(entry.selectedBuildingId()) && entry.isMember(ownerKey))) {
            throw new PartyFailure("Your personal campus index is missing. Ask staff to recover it; no replacement was created.");
        }
        beforeCreate.run();
        UUID entryId = UUID.randomUUID();
        Campus campus = new Campus(ownerKey, label(ownerKey, player.getName()), entryId, "", Phase.PROVISIONING,
                Map.of(), Map.of(), Instant.EPOCH);
        replace(campus);
        try {
            WorldModule.Allocation allocation = worlds.allocate(Category.PEOPLE, 0, entryId);
            campus = campus.allocation(allocation.worldName());
            replace(campus);
            Entry created = new Entry(entryId, Category.PEOPLE, Set.of(ownerKey), allocation.worldName(),
                    allocation.region(), allocation.allocationIndex());
            created.selectedBuildingId(PERSONAL_CAMPUS_MARKER);
            created.editableRegions(allocation.editableRegions());
            store.saveEntry(created);
            store.flush();
            newlyAllocated.add(entryId);
            if (worlds.isPeopleWorldReady(created.worldName())) completeNewCampus(entryId);
            else worlds.whenPeopleWorldReady(created.worldName(), () -> completeNewCampus(entryId));
            return campuses.get(ownerKey);
        } catch (RuntimeException exception) {
            lock(campus, exception);
            throw new PartyFailure("Your new campus could not be prepared safely. It is preserved and locked; ask staff for help.");
        }
    }

    private void completeNewCampus(UUID entryId) {
        if (closed || unavailable || !newlyAllocated.remove(entryId)) return;
        Campus campus = campusesByEntry.get(entryId);
        if (campus == null || campus.phase() != Phase.PROVISIONING) return;
        try {
            Entry created = entry(campus).orElseThrow(() -> new IllegalStateException("New personal entry is missing or changed."));
            if (!worlds.isPeopleWorldReady(created.worldName())) throw new IllegalStateException("New personal world is not ready.");
            registerNewBranch.accept(created);
            replace(campus.phase(Phase.READY));
            refreshEntry(created);
        } catch (RuntimeException exception) {
            lock(campus, exception);
        }
    }

    private void lock(Campus campus, RuntimeException cause) {
        newlyAllocated.remove(campus.entryId());
        plugin.getLogger().log(Level.SEVERE, "Personal campus " + campus.entryId() + " is locked; no existing world will be adopted as a new baseline.", cause);
        if (!unavailable) {
            try {
                replace(campus.phase(Phase.LOCKED));
            } catch (RuntimeException persistenceFailure) {
                plugin.getLogger().log(Level.SEVERE, "Could not persist the locked personal campus state.", persistenceFailure);
            }
        }
        entry(campus).ifPresent(this::refreshEntry);
    }

    private boolean travel(Player player, String ownerKey) {
        requireAvailable(player);
        Campus campus = requireCampus(ownerKey);
        String identity = competition.participantKey(player);
        if (!campus.ownerKey().equals(identity) && !campus.guests().containsKey(identity)) {
            throw new PartyFailure("You are not a guest of that campus. Ask its owner for an invitation.");
        }
        if (campus.phase() == Phase.LOCKED || campus.phase() == Phase.PROVISIONING && !newlyAllocated.contains(campus.entryId())) {
            throw new PartyFailure("That campus is preserved but locked after an interrupted setup. Ask staff for help.");
        }
        Entry destination = entry(campus).orElseThrow(() -> new PartyFailure("That personal campus record is unavailable or changed. Ask staff; no replacement was created."));
        ensureSavedWorld(destination);
        worlds.ensureEntryWorld(destination);
        if (!worlds.isPeopleWorldReady(destination.worldName()) || campus.phase() != Phase.READY) {
            PendingVisit pending = new PendingVisit(player, identity, ownerKey, campus.entryId());
            pendingVisits.put(player.getUniqueId(), pending);
            worlds.whenPeopleWorldReady(destination.worldName(), () -> completeVisit(pending));
            info(player, campus.ownerLabel() + "'s campus is preparing. You will join when it is ready.");
            return true;
        }
        pendingVisits.remove(player.getUniqueId());
        competition.teleportToEntry(player, destination, false);
        competition.refreshMovementMode(player, player.getLocation());
        boolean arrived = player.getWorld().getName().equals(destination.worldName()) && canVisit(player, destination);
        if (!arrived) error(player, "Travel was blocked. Your campus access has not changed.");
        return arrived;
    }

    private boolean visit(Player player, String ownerKey) {
        boolean requested = false;
        try {
            pendingVisits.remove(player.getUniqueId());
            closeControls(player);
            requested = travel(player, ownerKey);
            return requested;
        } finally {
            if (!requested) offerVisitRetry(player, ownerKey);
        }
    }

    private void offerVisitRetry(Player player, String ownerKey) {
        if (!authenticated(player) || closed || unavailable) return;
        Campus campus = campuses.get(ownerKey);
        if (campus == null || !campus.guests().containsKey(competition.participantKey(player))) return;
        player.sendMessage(Component.text("Guest access to " + campus.ownerLabel() + "'s campus is saved. ", NamedTextColor.YELLOW)
                .append(Component.text("[Try Join Again]", NamedTextColor.GREEN)
                        .clickEvent(ClickEvent.runCommand("/party visit " + campus.entryId()))
                        .hoverEvent(HoverEvent.showText(Component.text("Join the owner's campus.")))));
    }

    private void completeVisit(PendingVisit pending) {
        if (closed || unavailable || !pendingVisits.remove(pending.player().getUniqueId(), pending)) return;
        Player player = pending.player();
        if (!authenticated(player) || plugin.getServer().getPlayer(player.getUniqueId()) != player
                || !competition.participantKey(player).equals(pending.identity())) return;
        Campus campus = campuses.get(pending.ownerKey());
        if (campus == null || !campus.entryId().equals(pending.entryId())) return;
        safely(player, () -> {
            boolean requested = false;
            try {
                requested = visit(player, pending.ownerKey());
            } finally {
                if (!requested && authenticated(player)) competition.teleportHub(player);
            }
        });
    }

    private void ensureSavedWorld(Entry entry) {
        if (Bukkit.getWorld(entry.worldName()) != null) return;
        Path container = Bukkit.getWorldContainer().toPath();
        Path direct = container.resolve(entry.worldName());
        boolean saved = Files.isDirectory(direct) || !Bukkit.getWorlds().isEmpty() && Files.isDirectory(container
                .resolve(Bukkit.getWorlds().getFirst().getName()).resolve("dimensions/minecraft").resolve(entry.worldName()));
        for (World loaded : Bukkit.getWorlds()) {
            Path dimensions = loaded.getWorldFolder().toPath().resolve("dimensions/minecraft").resolve(entry.worldName());
            saved |= Files.isDirectory(dimensions);
        }
        if (!saved) throw new PartyFailure("That campus world is missing. Ask staff to restore it; no replacement was created.");
    }

    private void invite(Player owner, String targetName) {
        requireAvailable(owner);
        Player target = plugin.getServer().getPlayerExact(targetName);
        if (target == null || !authenticated(target)) throw new PartyFailure("Choose an online, signed-in player.");
        String ownerKey = competition.participantKey(owner);
        String targetKey = competition.participantKey(target);
        if (ownerKey.equals(targetKey)) throw new PartyFailure("You cannot invite yourself or another account linked to you.");
        Campus campus = ensurePersonalCampus(owner);
        requireReady(campus);
        expireInvitations();
        requireAvailable(owner);
        campus = requireCampus(ownerKey);
        if (campus.guests().containsKey(targetKey)) throw new PartyFailure("That student is already a guest of your campus.");
        Instant now = Instant.now();
        Invitation previous = campus.invitations().get(targetKey);
        if (previous != null && previous.active(now)) throw new PartyFailure("That student already has an invitation. Revoke it first if needed.");
        if (campus.guests().size() + campus.invitations().size() >= maxGuests) {
            throw new PartyFailure("Your campus has no guest spaces left (maximum " + maxGuests + ", including pending invitations).");
        }
        Instant nextInvite = campus.lastInviteAt().plus(inviteCooldown);
        if (nextInvite.isAfter(now)) {
            throw new PartyFailure("Wait " + Math.max(1L, Duration.between(now, nextInvite).toSeconds() + 1L) + " seconds before inviting again.");
        }
        Map<String, Invitation> invitations = new LinkedHashMap<>(campus.invitations());
        Invitation invitation = new Invitation(label(targetKey, target.getName()), now, now.plus(inviteExpiry));
        invitations.put(targetKey, invitation);
        replace(campus.roster(campus.guests(), invitations, now));
        info(owner, "Invited " + label(targetKey, target.getName()) + " to your campus.");
        notifyIdentity(targetKey, Component.text(campus.ownerLabel() + " invited you to their campus. ", NamedTextColor.AQUA)
                .append(Component.text("[Accept & Join]", NamedTextColor.GREEN)
                        .clickEvent(ClickEvent.runCommand("/party accept " + invitation.token()))
                        .hoverEvent(HoverEvent.showText(Component.text("Join " + campus.ownerLabel() + "'s campus."))))
                .append(Component.text(" "))
                .append(Component.text("[Decline]", NamedTextColor.GRAY)
                        .clickEvent(ClickEvent.runCommand("/party decline " + invitation.token()))
                        .hoverEvent(HoverEvent.showText(Component.text("Decline this invitation.", NamedTextColor.RED)))));
    }

    private void accept(Player player, InviteReference reference) {
        requireInvitationCampus(player, reference);
        closeControls(player);
        Campus campus = requireInvitationCampus(player, reference);
        String identity = reference.targetKey();
        Invitation invitation = campus.invitations().get(identity);
        if (campus.guests().size() >= maxGuests) throw new PartyFailure("That campus is full. Ask its owner to make room.");
        Map<String, String> guests = new LinkedHashMap<>(campus.guests());
        Map<String, Invitation> invitations = new LinkedHashMap<>(campus.invitations());
        guests.put(identity, label(identity, invitation.label()));
        invitations.remove(identity);
        replace(campus.roster(guests, invitations, campus.lastInviteAt()));
        info(player, "Invitation accepted. Joining " + campus.ownerLabel() + "'s campus.");
        notifyIdentity(campus.ownerKey(), label(identity, invitation.label()) + " accepted your campus invitation.");
        entry(campus).ifPresent(this::refreshEntry);
        visit(player, campus.ownerKey());
    }

    private void decline(Player player, InviteReference reference) {
        requireInvitationCampus(player, reference);
        closeControls(player);
        Campus campus = requireInvitationCampus(player, reference);
        Map<String, Invitation> invitations = new LinkedHashMap<>(campus.invitations());
        invitations.remove(reference.targetKey());
        replace(campus.roster(campus.guests(), invitations, campus.lastInviteAt()));
        info(player, "Declined " + campus.ownerLabel() + "'s campus invitation.");
        notifyIdentity(campus.ownerKey(), label(reference.targetKey(), player.getName()) + " declined your campus invitation.");
    }

    private Campus requireInvitationCampus(Player player, InviteReference reference) {
        requireAvailable(player);
        Campus campus = requireCampus(reference.ownerKey());
        String identity = competition.participantKey(player);
        Invitation invitation = campus.invitations().get(identity);
        if (!identity.equals(reference.targetKey()) || campus.ownerKey().equals(identity) || invitation == null
                || !invitation.token().equals(reference.token()) || !invitation.active(Instant.now())) {
            throw new PartyFailure("That invitation expired, was declined, or was revoked. Open /party for current invitations.");
        }
        requireReady(campus);
        return campus;
    }

    private void remove(Player owner, String targetKey) {
        requireAvailable(owner);
        Campus campus = requireOwnedCampus(owner);
        if (campus.ownerKey().equals(targetKey)) throw new PartyFailure("The owner cannot be removed.");
        String targetLabel = campus.guests().get(targetKey);
        if (targetLabel == null) throw new PartyFailure("That student is no longer a guest of your campus.");
        Map<String, String> guests = new LinkedHashMap<>(campus.guests());
        guests.remove(targetKey);
        replace(campus.roster(guests, campus.invitations(), campus.lastInviteAt()));
        evict(targetKey, campus);
        info(owner, targetLabel + " was removed from your campus.");
        notifyIdentity(targetKey, "Your guest access to " + campus.ownerLabel() + "'s campus was removed. Your own campus is unchanged.");
    }

    private void revoke(Player owner, String targetKey) {
        requireAvailable(owner);
        Campus campus = requireOwnedCampus(owner);
        Invitation invitation = campus.invitations().get(targetKey);
        if (invitation == null) throw new PartyFailure("That invitation is no longer pending.");
        revoke(owner, targetKey, invitation.token());
    }

    private void revoke(Player owner, String targetKey, UUID token) {
        requireAvailable(owner);
        Campus campus = requireOwnedCampus(owner);
        Invitation invitation = campus.invitations().get(targetKey);
        if (invitation == null || !invitation.token().equals(token) || !invitation.active(Instant.now())) {
            throw new PartyFailure("That invitation has expired or is no longer pending.");
        }
        Map<String, Invitation> invitations = new LinkedHashMap<>(campus.invitations());
        invitations.remove(targetKey);
        replace(campus.roster(campus.guests(), invitations, campus.lastInviteAt()));
        info(owner, "Invitation for " + invitation.label() + " revoked.");
        notifyIdentity(targetKey, "The invitation to " + campus.ownerLabel() + "'s campus was revoked.");
    }

    private void leave(Player player, String ownerKey) {
        requireAvailable(player);
        Campus campus = requireCampus(ownerKey);
        String identity = competition.participantKey(player);
        if (ownerKey.equals(identity)) throw new PartyFailure("You own this campus and cannot leave or transfer it.");
        if (!campus.guests().containsKey(identity)) throw new PartyFailure("You are not a guest of that campus.");
        Map<String, String> guests = new LinkedHashMap<>(campus.guests());
        guests.remove(identity);
        replace(campus.roster(guests, campus.invitations(), campus.lastInviteAt()));
        evict(identity, campus);
        info(player, "You left " + campus.ownerLabel() + "'s campus. Your own campus is unchanged.");
        notifyIdentity(ownerKey, label(identity, player.getName()) + " left your campus.");
    }

    private void evict(String identity, Campus campus) {
        pendingVisits.entrySet().removeIf(visit -> visit.getValue().identity().equals(identity) && visit.getValue().entryId().equals(campus.entryId()));
        for (Player online : plugin.getServer().getOnlinePlayers()) {
            if (!competition.participantKey(online).equals(identity) || !online.getWorld().getName().equals(campus.worldName())) continue;
            try {
                online.closeInventory();
                online.closeDialog();
                if (online.getGameMode() == GameMode.SPECTATOR && online.getSpectatorTarget() != null) online.setSpectatorTarget(null);
            } catch (RuntimeException exception) {
                plugin.getLogger().log(Level.WARNING, "Could not fully clear a removed personal campus guest's controls.", exception);
            }
            try {
                competition.teleportHub(online);
            } catch (RuntimeException exception) {
                plugin.getLogger().log(Level.WARNING, "Could not teleport a removed personal campus guest to the hub.", exception);
            }
            if (online.getWorld().getName().equals(campus.worldName())) {
                try {
                    online.teleport(worlds.hubSpawn(), PlayerTeleportEvent.TeleportCause.PLUGIN);
                } catch (RuntimeException exception) {
                    plugin.getLogger().log(Level.WARNING, "The fallback hub teleport failed for a removed personal campus guest.", exception);
                }
            }
            refreshMode(online);
            if (online.isOnline() && online.getWorld().getName().equals(campus.worldName())) {
                plugin.getLogger().warning("Disconnecting a removed personal campus guest because both hub teleports were interrupted.");
                online.kick(Component.text("Your campus guest access was removed. Reconnect to return to your own campus.", NamedTextColor.RED));
            }
        }
    }

    private void chooseInvitation(Player player, boolean declining) {
        List<Campus> incoming = eligibleCampuses(player, Section.INCOMING);
        if (incoming.isEmpty()) throw new PartyFailure("No active invitations. Open /party to invite a friend.");
        if (incoming.size() > 1) {
            openPage(player, Section.INCOMING, 0);
            return;
        }
        InviteReference reference = invitationReference(player, incoming.getFirst());
        if (declining) decline(player, reference);
        else accept(player, reference);
    }

    private void join(Player player, String input) {
        if (input == null) {
            if (!eligibleCampuses(player, Section.INCOMING).isEmpty()) {
                chooseInvitation(player, false);
                return;
            }
            String identity = competition.participantKey(player);
            List<Campus> friends = eligibleCampuses(player, Section.CAMPUSES).stream()
                    .filter(campus -> !campus.ownerKey().equals(identity)).toList();
            if (friends.isEmpty()) throw new PartyFailure("No invitations or friend campuses yet. Open /party to invite a friend.");
            if (friends.size() == 1) visit(player, friends.getFirst().ownerKey());
            else openPage(player, Section.CAMPUSES, 0);
            return;
        }
        if (invitationToken(input).isPresent()) {
            accept(player, resolveInvitation(player, input));
            return;
        }
        Map<String, String> choices = new LinkedHashMap<>();
        eligibleCampuses(player, Section.INCOMING).forEach(campus -> choices.put(campus.ownerKey(), campus.ownerLabel()));
        eligibleCampuses(player, Section.CAMPUSES).forEach(campus -> choices.put(campus.ownerKey(), campus.ownerLabel()));
        String ownerKey = resolveIdentity(input, choices);
        Campus campus = requireCampus(ownerKey);
        Invitation invitation = campus.invitations().get(competition.participantKey(player));
        if (invitation != null && invitation.active(Instant.now())) accept(player, invitationReference(player, campus));
        else visit(player, ownerKey);
    }

    private InviteReference resolveInvitation(Player player, String input) {
        Optional<UUID> token = invitationToken(input);
        if (token.isPresent()) {
            for (Campus campus : eligibleCampuses(player, Section.INCOMING)) {
                InviteReference reference = invitationReference(player, campus);
                if (reference.token().equals(token.get())) return reference;
            }
            throw new PartyFailure("That invitation expired, was declined, or was revoked. Open /party for current invitations.");
        }
        return invitationReference(player, requireCampus(resolveOwner(player, input, Section.INCOMING)));
    }

    private InviteReference invitationReference(Player player, Campus campus) {
        String identity = competition.participantKey(player);
        Invitation invitation = campus.invitations().get(identity);
        if (invitation == null || !invitation.active(Instant.now())) throw new PartyFailure("That invitation is no longer active.");
        return new InviteReference(campus.ownerKey(), identity, invitation.token());
    }

    private static Optional<UUID> invitationToken(String input) {
        try {
            UUID token = UUID.fromString(input);
            return token.toString().equalsIgnoreCase(input) ? Optional.of(token) : Optional.empty();
        } catch (IllegalArgumentException exception) {
            return Optional.empty();
        }
    }

    private String resolveVisitOwner(Player player, String input) {
        for (Campus campus : eligibleCampuses(player, Section.CAMPUSES)) {
            if (campus.entryId().toString().equalsIgnoreCase(input)) return campus.ownerKey();
        }
        return resolveOwner(player, input, Section.CAMPUSES);
    }

    private String resolveOwner(Player player, String input, Section section) {
        return resolveIdentity(input, eligibleCampuses(player, section).stream()
                .collect(java.util.stream.Collectors.toMap(Campus::ownerKey, Campus::ownerLabel, (first, second) -> first, LinkedHashMap::new)));
    }

    private String resolveRoster(Player player, String input, boolean invitations) {
        Campus campus = requireOwnedCampus(player);
        Map<String, String> choices = new LinkedHashMap<>();
        if (invitations) campus.invitations().forEach((identity, invitation) -> {
            if (invitation.active(Instant.now())) choices.put(identity, invitation.label());
        });
        else choices.putAll(campus.guests());
        return resolveIdentity(input, choices);
    }

    private String resolveIdentity(String input, Map<String, String> choices) {
        if (choices.containsKey(input)) return input;
        Set<String> matches = new HashSet<>();
        choices.forEach((identity, label) -> {
            if (label.equalsIgnoreCase(input)) matches.add(identity);
        });
        for (Player online : plugin.getServer().getOnlinePlayers()) {
            if (authenticated(online) && online.getName().equalsIgnoreCase(input)
                    && choices.containsKey(competition.participantKey(online))) matches.add(competition.participantKey(online));
        }
        if (matches.size() == 1) return matches.iterator().next();
        if (matches.size() > 1) throw new PartyFailure("That name is shared by more than one student. Use /party to select the correct campus or guest.");
        throw new PartyFailure("No matching campus, guest or pending invitation. Open /party to see your current choices.");
    }

    private List<Campus> eligibleCampuses(Player player, Section section) {
        String identity = competition.participantKey(player);
        Instant now = Instant.now();
        return campuses.values().stream().filter(campus -> {
            if (section == Section.INCOMING) {
                Invitation invitation = campus.invitations().get(identity);
                return invitation != null && invitation.active(now);
            }
            return campus.ownerKey().equals(identity) || campus.guests().containsKey(identity);
        }).sorted(Comparator.comparing(Campus::ownerLabel, String.CASE_INSENSITIVE_ORDER).thenComparing(Campus::ownerKey)).toList();
    }

    private void expireInvitations() {
        if (closed || unavailable) return;
        Instant now = Instant.now();
        Map<String, Campus> updated = new LinkedHashMap<>(campuses);
        boolean changed = false;
        for (Campus campus : campuses.values()) {
            Map<String, Invitation> invitations = new LinkedHashMap<>(campus.invitations());
            if (invitations.values().removeIf(invitation -> !invitation.active(now))) {
                updated.put(campus.ownerKey(), campus.roster(campus.guests(), invitations, campus.lastInviteAt()));
                changed = true;
            }
        }
        if (changed) {
            try {
                persist(updated);
            } catch (RuntimeException exception) {
                plugin.getLogger().log(Level.SEVERE, "Could not expire campus invitations; party editing remains locked.", exception);
            }
        }
    }

    private void replace(Campus campus) {
        Map<String, Campus> updated = new LinkedHashMap<>(campuses);
        updated.put(campus.ownerKey(), campus);
        persist(updated);
    }

    private void persist(Map<String, Campus> updated) {
        if (closed || unavailable) throw new PartyFailure("Personal campuses are temporarily locked. Ask staff for help.");
        try {
            partyStore.save(updated);
            campuses = Map.copyOf(updated);
            reindex();
        } catch (Exception exception) {
            unavailable = true;
            pendingVisits.clear();
            plugin.getLogger().log(Level.SEVERE, "Could not atomically persist parties.yml; all personal campus editing is locked until recovery/restart.", exception);
            for (Player online : plugin.getServer().getOnlinePlayers()) {
                if (campusesByEntry.values().stream().anyMatch(campus -> campus.worldName().equals(online.getWorld().getName()))) refreshMode(online);
            }
            throw new PartyFailure("The campus change could not be saved. Personal campuses are locked; ask staff for help.");
        }
    }

    private void reindex() {
        campusesByEntry.clear();
        campuses.values().forEach(campus -> campusesByEntry.put(campus.entryId(), campus));
    }

    private Optional<Entry> entry(Campus campus) {
        return store.entry(campus.entryId()).filter(entry -> validEntry(campus, entry));
    }

    private boolean validEntry(Campus campus, Entry entry) {
        return entry.id().equals(campus.entryId()) && store.entry(entry.id()).orElse(null) == entry
                && entry.category() == Category.PEOPLE && entry.members().equals(Set.of(campus.ownerKey()))
                && entry.worldName().equals(campus.worldName());
    }

    private Campus requireCampus(String ownerKey) {
        Campus campus = campuses.get(ownerKey);
        if (campus == null) throw new PartyFailure("That personal campus is not available. No older competition entry was adopted.");
        return campus;
    }

    private Campus requireOwnedCampus(Player player) {
        Campus campus = requireCampus(competition.participantKey(player));
        if (entry(campus).isEmpty()) throw new PartyFailure("Your personal campus record is unavailable or changed. Ask staff for help.");
        return campus;
    }

    private void requireReady(Campus campus) {
        if (campus.phase() != Phase.READY || entry(campus).isEmpty()) {
            throw new PartyFailure("That campus is still preparing or locked. Open /party home or ask staff for help.");
        }
    }

    private boolean authenticated(Player player) {
        return player != null && player.isOnline() && competition.isAuthenticated(player);
    }

    private boolean available(Player player) {
        if (!authenticated(player)) {
            if (player != null) error(player, "Sign in before opening or sharing a personal campus.");
            return false;
        }
        if (closed || unavailable) {
            error(player, "Personal campuses are temporarily locked. Ask staff for help.");
            return false;
        }
        return true;
    }

    private void requireAvailable(Player player) {
        if (!available(player)) throw new PartyFailure(null);
    }

    private String label(String identity, String fallback) {
        String display = competition.displayName(identity);
        if (display == null || display.isBlank() || display.equals("Unverified legacy participant")) display = fallback;
        String clean = display.replaceAll("[\\p{Cntrl}§]", "").strip();
        if (clean.isBlank()) clean = "Student";
        return clean.substring(0, Math.min(clean.length(), 120));
    }

    private void notifyIdentity(String identity, String message) {
        notifyIdentity(identity, Component.text(message, NamedTextColor.AQUA));
    }

    private void notifyIdentity(String identity, Component message) {
        for (Player online : plugin.getServer().getOnlinePlayers()) {
            if (authenticated(online) && competition.participantKey(online).equals(identity)) online.sendMessage(message);
        }
    }

    private void closeControls(Player player) {
        player.closeInventory();
        player.closeDialog();
    }

    private void refreshMode(Player player) {
        try {
            competition.refreshMovementMode(player, player.getLocation());
        } catch (RuntimeException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not refresh personal campus movement mode.", exception);
        }
    }

    private void safely(Player player, Runnable operation) {
        try {
            operation.run();
        } catch (PartyFailure failure) {
            if (failure.getMessage() != null) error(player, failure.getMessage());
        } catch (RuntimeException exception) {
            internalFailure(player, "A campus action failed.", exception);
        }
    }

    private void internalFailure(Player player, String context, RuntimeException exception) {
        plugin.getLogger().log(Level.SEVERE, context, exception);
        error(player, "That campus action could not be completed safely. Please try again later or ask staff.");
    }

    private static String usage() {
        return "Use /party for the menu, /invite <player> to invite, or /party join to accept and join. Owner names still work with /party accept, decline, visit or leave.";
    }

    private static List<String> matching(List<String> choices, String prefix) {
        return choices.stream().filter(choice -> choice.toLowerCase(Locale.ROOT).startsWith(prefix.toLowerCase(Locale.ROOT)))
                .distinct().sorted(String.CASE_INSENSITIVE_ORDER).toList();
    }

    private static void info(Player player, String message) {
        player.sendMessage(Component.text(message, NamedTextColor.AQUA));
    }

    private static void error(Player player, String message) {
        player.sendMessage(Component.text(message, NamedTextColor.RED));
    }

    /** The Friends page of the Hill Menu and its sub-pages, as Hypixel-style chest menus. */
    private void openPage(Player player, Section section, int requestedPage) {
        if (!available(player)) return;
        expireInvitations();
        requireAvailable(player);
        String identity = competition.participantKey(player);
        Campus own = campuses.get(identity);
        if (section == Section.OVERVIEW) {
            int incoming = eligibleCampuses(player, Section.INCOMING).size();
            int guests = own == null ? 0 : own.guests().size();
            long outgoing = own == null ? 0 : own.invitations().values().stream().filter(invitation -> invitation.active(Instant.now())).count();
            long friendCampuses = eligibleCampuses(player, Section.CAMPUSES).stream().filter(campus -> !campus.ownerKey().equals(identity)).count();
            var screen = screen("Friends");
            screen.add(icon(player, Material.NAME_TAG, "Invite a Friend", "Choose someone online to build in your campus with you.",
                    "Click to choose!", viewer -> openPage(viewer, Section.INVITE, 0)));
            if (incoming > 0) screen.add(icon(player, Material.PAPER, "Invitations", incoming + (incoming == 1 ? " friend has" : " friends have")
                    + " invited you to their campus.", "Click to view!", viewer -> openPage(viewer, Section.INCOMING, 0)));
            if (guests + outgoing > 0) screen.add(icon(player, Material.PLAYER_HEAD, "My Guests", guests + " of " + maxGuests + " guest spaces used."
                    + (outgoing > 0 ? " " + outgoing + " invitations not answered yet." : ""), "Click to manage!", viewer -> openPage(viewer, Section.MANAGE, 0)));
            if (friendCampuses > 0) screen.add(icon(player, Material.OAK_DOOR, "Friends' Campuses", "You can build in " + friendCampuses
                    + (friendCampuses == 1 ? " friend's campus." : " friends' campuses."), "Click to view!", viewer -> openPage(viewer, Section.CAMPUSES, 0)));
            screen.back("Hill Menu", () -> playerActions.open(player));
            screen.show(player);
            return;
        }
        List<IconMenu.Icon> items = icons(player, section, identity, own);
        int pageCount = Math.max(1, (items.size() + IconMenu.PAGE_SIZE - 1) / IconMenu.PAGE_SIZE);
        int page = Math.clamp(requestedPage, 0, pageCount - 1);
        var screen = screen(pageCount > 1 ? section.title + " (" + (page + 1) + "/" + pageCount + ")" : section.title);
        if (items.isEmpty()) {
            screen.add(new IconMenu.Icon(Material.GRAY_DYE, "Nothing Here", section.empty, null).withColor(NamedTextColor.GRAY).withClick(null));
        } else {
            screen.addAll(items.subList(page * IconMenu.PAGE_SIZE, Math.min(items.size(), (page + 1) * IconMenu.PAGE_SIZE)));
        }
        screen.pages(page > 0 ? () -> openPage(player, section, page - 1) : null,
                page + 1 < pageCount ? () -> openPage(player, section, page + 1) : null);
        screen.back("Friends", () -> openPage(player, Section.OVERVIEW, 0));
        screen.show(player);
    }

    private List<IconMenu.Icon> icons(Player player, Section section, String identity, Campus own) {
        List<IconMenu.Icon> choices = new ArrayList<>();
        switch (section) {
            case OVERVIEW -> { }
            case CAMPUSES -> eligibleCampuses(player, section).stream().filter(campus -> !campus.ownerKey().equals(identity))
                    .forEach(campus -> choices.add(icon(player, Material.OAK_DOOR, campus.ownerLabel() + "'s Campus",
                            "Visit, or leave their guest list.", "Click to choose!", viewer -> openCampus(viewer, campus.ownerKey()))));
            case INCOMING -> eligibleCampuses(player, section).forEach(campus -> {
                InviteReference reference = invitationReference(player, campus);
                choices.add(icon(player, Material.PAPER, "From " + campus.ownerLabel(), "Join their campus to build with them.",
                        "Click to answer!", viewer -> openInvitation(viewer, reference)));
            });
            case MANAGE -> {
                if (own != null) {
                    own.guests().forEach((targetKey, guestLabel) -> choices.add(icon(player, Material.PLAYER_HEAD, guestLabel,
                            "A guest in your campus.", "Click to remove!", viewer -> confirm(viewer, "Remove " + guestLabel + "?",
                                    "They can no longer build in your campus.", "Remove", Section.MANAGE, actor -> remove(actor, targetKey)))));
                    own.invitations().forEach((targetKey, invitation) -> {
                        if (invitation.active(Instant.now())) choices.add(icon(player, Material.WRITABLE_BOOK, invitation.label(),
                                "Invited, not answered yet.", "Click to cancel the invite!", viewer -> confirm(viewer, "Cancel invite?",
                                        invitation.label() + " will no longer be able to join.", "Cancel Invite", Section.MANAGE,
                                        actor -> revoke(actor, targetKey, invitation.token()))));
                    });
                }
            }
            case INVITE -> {
                Set<String> identities = new HashSet<>();
                if (own != null) {
                    identities.addAll(own.guests().keySet());
                    own.invitations().forEach((targetKey, invitation) -> { if (invitation.active(Instant.now())) identities.add(targetKey); });
                }
                identities.add(identity);
                plugin.getServer().getOnlinePlayers().stream().filter(this::authenticated).sorted(Comparator.comparing(Player::getName))
                        .forEach(target -> {
                            String targetKey = competition.participantKey(target);
                            if (identities.add(targetKey)) choices.add(icon(player, Material.PLAYER_HEAD, label(targetKey, target.getName()),
                                    "Invite them to build in your campus.", "Click to invite!", viewer -> {
                                        Player current = plugin.getServer().getPlayer(target.getUniqueId());
                                        if (current != target || !authenticated(target) || !competition.participantKey(target).equals(targetKey)) {
                                            throw new PartyFailure("That student is no longer online and signed in.");
                                        }
                                        invite(viewer, target.getName());
                                    }).withHead(target));
                        });
            }
        }
        return choices;
    }

    private void openInvitation(Player player, InviteReference reference) {
        Campus campus = requireInvitationCampus(player, reference);
        var screen = screen(campus.ownerLabel() + "'s Invitation");
        screen.add(icon(player, Material.GREEN_TERRACOTTA, "Accept & Join", "Go to " + campus.ownerLabel() + "'s campus and build with them.",
                "Click to join!", viewer -> accept(viewer, reference)));
        screen.add(icon(player, Material.RED_TERRACOTTA, "Decline", "Say no to this invitation.", "Click to decline!",
                viewer -> decline(viewer, reference)).withColor(NamedTextColor.RED));
        screen.back("Invitations", () -> openPage(player, Section.INCOMING, 0));
        screen.show(player);
    }

    private void openCampus(Player player, String ownerKey) {
        requireAvailable(player);
        Campus campus = requireCampus(ownerKey);
        String identity = competition.participantKey(player);
        if (!ownerKey.equals(identity) && !campus.guests().containsKey(identity)) throw new PartyFailure("You are no longer a guest of that campus.");
        var screen = screen(campus.ownerLabel() + "'s Campus");
        screen.add(icon(player, Material.OAK_DOOR, "Visit", "Go to " + campus.ownerLabel() + "'s campus.", "Click to go!", viewer -> visit(viewer, ownerKey)));
        if (!ownerKey.equals(identity)) screen.add(icon(player, Material.BARRIER, "Leave Their Campus", "Give up your guest spot.", "Click to leave!",
                viewer -> confirm(viewer, "Leave " + campus.ownerLabel() + "'s campus?", "You can only come back if they invite you again.", "Leave",
                        Section.CAMPUSES, actor -> leave(actor, ownerKey))).withColor(NamedTextColor.RED));
        screen.back("Friends' Campuses", () -> openPage(player, Section.CAMPUSES, 0));
        screen.show(player);
    }

    private void confirm(Player player, String title, String question, String confirmLabel, Section returnSection, Consumer<Player> operation) {
        requireAvailable(player);
        String identity = competition.participantKey(player);
        playerActions.icons().confirm(player, title, question, confirmLabel,
                guarded(player, identity, viewer -> { operation.accept(viewer); openPage(viewer, returnSection, 0); }),
                guarded(player, identity, viewer -> openPage(viewer, returnSection, 0)));
    }

    private IconMenu.Screen screen(String title) {
        if (playerActions == null) throw new PartyFailure("Menus are still starting. Try again in a moment.");
        return playerActions.icons().screen(title);
    }

    /** Menu actions recheck access and that the same student is still signed in. */
    private IconMenu.Icon icon(Player player, Material material, String label, String description, String click, Consumer<Player> handler) {
        return new IconMenu.Icon(material, label, description, guarded(player, competition.participantKey(player), handler)).withClick(click);
    }

    private Runnable guarded(Player player, String identity, Consumer<Player> handler) {
        return () -> safely(player, () -> {
            requireAvailable(player);
            if (!identity.equals(competition.participantKey(player))) throw new PartyFailure("Your sign-in changed. Open the menu again.");
            handler.accept(player);
        });
    }

    private boolean mayEnterWorld(Player player, World destination) {
        if (destination == null) return true;
        try {
            List<Campus> mapped = campuses.values().stream().filter(campus -> campus.worldName().equals(destination.getName())).toList();
            List<Entry> marked = store.entries().stream().filter(entry -> PERSONAL_CAMPUS_MARKER.equals(entry.selectedBuildingId())
                    && entry.worldName().equals(destination.getName())).toList();
            if (mapped.isEmpty() && marked.isEmpty()) return true;
            if (mapped.size() != 1) return false;
            Campus campus = mapped.getFirst();
            if (marked.stream().anyMatch(entry -> !entry.id().equals(campus.entryId()))) return false;
            return entry(campus).filter(entry -> canVisit(player, entry)).isPresent();
        } catch (RuntimeException exception) {
            plugin.getLogger().log(Level.SEVERE, "Could not verify personal campus admission to " + destination.getName(), exception);
            return false;
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onTeleportAdmission(PlayerTeleportEvent event) {
        if (event.getTo() != null && !mayEnterWorld(event.getPlayer(), event.getTo().getWorld())) {
            event.setCancelled(true);
            error(event.getPlayer(), "That personal campus is private or unavailable. Open /party to see your campus access.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onPortalAdmission(PlayerPortalEvent event) {
        onTeleportAdmission(event);
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onSpectateAdmission(PlayerStartSpectatingEntityEvent event) {
        if (!mayEnterWorld(event.getPlayer(), event.getNewSpectatorTarget().getWorld())) {
            event.setCancelled(true);
            error(event.getPlayer(), "You cannot spectate inside a private campus without guest access.");
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onRespawnAdmission(PlayerRespawnEvent event) {
        if (!mayEnterWorld(event.getPlayer(), event.getRespawnLocation().getWorld())) event.setRespawnLocation(worlds.hubSpawn());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onTeleport(PlayerTeleportEvent event) {
        pendingVisits.remove(event.getPlayer().getUniqueId());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPortal(PlayerPortalEvent event) {
        pendingVisits.remove(event.getPlayer().getUniqueId());
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        pendingVisits.remove(event.getPlayer().getUniqueId());
    }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        expiryTask.cancel();
        pendingVisits.clear();
        newlyAllocated.clear();
        HandlerList.unregisterAll(this);
    }

    private enum Section {
        OVERVIEW("Friends", ""),
        CAMPUSES("Friends' Campuses", "You are not a guest in a friend's campus yet."),
        INCOMING("Invitations", "No invitations right now."),
        MANAGE("My Guests", "You have no guests yet."),
        INVITE("Invite a Friend", "No one else is online right now.");
        private final String title;
        private final String empty;
        Section(String title, String empty) {
            this.title = title;
            this.empty = empty;
        }
    }

    private record PendingVisit(Player player, String identity, String ownerKey, UUID entryId) { }
    private record InviteReference(String ownerKey, String targetKey, UUID token) { }
    private static final class PartyFailure extends RuntimeException {
        private PartyFailure(String message) { super(message); }
    }
}
