package org.thehill.hill175.ui;

import io.papermc.paper.dialog.Dialog;
import io.papermc.paper.registry.data.dialog.ActionButton;
import io.papermc.paper.registry.data.dialog.DialogBase;
import io.papermc.paper.registry.data.dialog.action.DialogAction;
import io.papermc.paper.registry.data.dialog.body.DialogBody;
import io.papermc.paper.registry.data.dialog.input.DialogInput;
import io.papermc.paper.registry.data.dialog.type.DialogType;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickCallback;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.access.AccessControl;
import org.thehill.hill175.blueprint.BlueprintRepository;
import org.thehill.hill175.blueprint.BlueprintService;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.replay.BuildRecorder;
import org.thehill.hill175.replay.BuildReplayViewer;
import org.thehill.hill175.ui.IconMenu.Icon;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Consumer;

/**
 * The Hill Menu: one central page of item icons (My Campus, Friends, Help and, for staff, Staff). Each of those
 * opens its own page with a Back arrow. Things already in the hotbar (sending builds, the campus map) are not
 * repeated here. Sign in and typed values use native dialogs.
 */
public final class PlayerActions implements Listener, AutoCloseable {
    public record Choice(String label, Runnable run) {}
    private record View(UUID id, String participant, UUID world, long opened) {}
    private final Map<UUID, View> active = new HashMap<>();
    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final MenuModule menus;
    private final BlueprintService blueprint;
    private final AccessControl access;
    private final BedrockForms forms;
    private final IconMenu icons;
    private final BlueprintStaging staging;
    private BuildRecorder recordings;
    private BuildReplayViewer replayViewer;
    private static final Duration LIFETIME = Duration.ofMinutes(5);

    public PlayerActions(JavaPlugin plugin, CompetitionModule competition, MenuModule menus, BlueprintService blueprint, AccessControl access) {
        this.plugin = plugin;
        this.competition = competition;
        this.menus = menus;
        this.blueprint = blueprint;
        this.access = access;
        forms = new BedrockForms(plugin);
        icons = new IconMenu(plugin, forms, p -> competition.isAuthenticated(p) && access.allowed(p),
                p -> competition.isAuthenticated(p) ? competition.participantKey(p) : "");
        staging = blueprint == null ? null : new BlueprintStaging(plugin, blueprint, competition);
        if (staging != null) blueprint.playerScreens(staging);
    }

    public IconMenu icons() { return icons; }

    public void buildReplays(BuildRecorder recordings, BuildReplayViewer viewer) {
        this.recordings = recordings;
        this.replayViewer = viewer;
    }

    private boolean canReviewBuilds(Player player) {
        return replayViewer != null && access.mayReviewReplays(player) && player.hasPermission("hill175.replay");
    }

    private Icon replays(Player player) {
        return new Icon(Material.CLOCK, "Replays", "Watch a player's building sessions, even after they sign out.", () -> recordings(player, 0))
                .withClick("Click to choose a player!");
    }

    private void recordings(Player player, int requested) {
        if (!canReviewBuilds(player)) return;
        var profiles = recordings.profiles();
        int pages = Math.max(1, Math.ceilDiv(profiles.size(), IconMenu.PAGE_SIZE));
        int page = Math.clamp(requested, 0, pages - 1);
        var screen = icons.screen(pages == 1 ? "Replays: Choose a Player" : "Replays (" + (page + 1) + "/" + pages + ")");
        if (profiles.isEmpty()) screen.add(new Icon(Material.PAPER, "No recordings yet", "Players appear here after their first recorded session.", null).withClick(null));
        for (var profile : profiles.subList(page * IconMenu.PAGE_SIZE, Math.min(profiles.size(), (page + 1) * IconMenu.PAGE_SIZE))) {
            screen.add(new Icon(Material.PLAYER_HEAD, profile.name(), "Play recorded time. Offline gaps are skipped.",
                    () -> { if (canReviewBuilds(player)) replayViewer.open(player, profile.id()); }).withClick("Click to watch!"));
        }
        screen.pages(page > 0 ? () -> recordings(player, page - 1) : null, page + 1 < pages ? () -> recordings(player, page + 1) : null);
        back(screen, player);
        screen.show(player);
    }

    public void open(Player p) {
        if (!competition.isAuthenticated(p)) {
            authentication(p);
            return;
        }
        var screen = icons.screen("Hill Menu").header(profile(p));
        screen.add(command(p, Material.GRASS_BLOCK, "My Campus", "Go to your own copy of the Hill campus.", "campus home").withClick("Click to go!"));
        if (blueprint != null) {
            screen.add(new Icon(Material.BEACON, "Shared Blueprint", "Fly through the shared Hill campus that every campus copies. Look only.",
                    () -> staging.visit(p)).withClick("Click to visit!"));
            screen.add(new Icon(Material.PLAYER_HEAD, "Friends", "Invite friends to build in your campus, or visit theirs.", () -> competition.openParty(p)));
            if (hasCampus(p)) screen.add(new Icon(Material.TNT, "Reset My Campus", "Start over from the newest shared blueprint.", () -> confirmReset(p))
                    .withColor(net.kyori.adventure.text.format.NamedTextColor.RED).withClick("Click to reset!"));
        } else {
            screen.add(command(p, Material.CLOCK, "Undo Recent Build", "Undo your last 15 seconds of building.", "campus undo").withClick("Click to undo!"));
            screen.add(new Icon(Material.NETHER_STAR, "Competition Projects", "Your entries, camera and gallery.", () -> projects(p)));
        }
        screen.add(new Icon(Material.BOOK, "Help", "Rules, how to play and the campus map download.", () -> help(p)));
        if (canReviewBuilds(p)) screen.add(replays(p));
        if (access.mayReviewReplays(p) || p.hasPermission("hill175.campus.rollback")) {
            screen.add(new Icon(Material.SPYGLASS, "Staff", "Review builds and other staff tools.", () -> staff(p)));
        }
        screen.show(p);
    }

    /** The profile card at the top of the Hill Menu: the player's head, name and build status. */
    private Icon profile(Player p) {
        List<String> lines = new ArrayList<>();
        if (blueprint != null) {
            try {
                var overview = blueprint.overview(p);
                if (overview.entry() == null) lines.add("No campus yet. Click My Campus!");
                else if (overview.conflicts() > 0) lines.add("The blueprint changed " + overview.conflicts() + " of your blocks.");
                else if (overview.waiting() != null) lines.add("Build waiting for review: " + overview.waiting().title());
                else if (overview.lastDecision() != null) lines.add("Last build: " + (overview.lastDecision().status() == BlueprintRepository.Status.APPROVED ? "approved" : "sent back"));
                else lines.add("Send builds with the emerald.");
            } catch (IOException | RuntimeException exception) {
                lines.add("Send builds with the emerald.");
            }
        }
        return new Icon(Material.PLAYER_HEAD, p.getName(), "", null).withHead(p).withLore(lines).withClick(null);
    }

    private void back(IconMenu.Screen screen, Player p) { screen.back("Hill Menu", () -> open(p)); }

    private boolean hasCampus(Player p) {
        try { return blueprint.overview(p).entry() != null; }
        catch (IOException | RuntimeException exception) { return false; }
    }

    private void confirmReset(Player p) {
        icons.confirm(p, "Reset your campus?", "Everything you built that is not in the shared blueprint is removed. This cannot be undone.",
                "Reset My Campus", () -> reset(p), () -> open(p));
    }

    private void reset(Player p) {
        try {
            p.sendMessage(Component.text("Resetting your campus... Building pauses until it is done.", net.kyori.adventure.text.format.NamedTextColor.YELLOW));
            blueprint.reset(p).whenComplete((count, error) -> {
                if (!p.isOnline()) return;
                if (error != null) p.sendMessage(Component.text("The reset stopped: " + error.getMessage(), net.kyori.adventure.text.format.NamedTextColor.RED));
                else p.sendMessage(Component.text("Your campus now matches the shared blueprint" + (count == 0 ? "." : " (" + count + " blocks changed)."),
                        net.kyori.adventure.text.format.NamedTextColor.GREEN));
            });
        } catch (RuntimeException exception) {
            p.sendMessage(Component.text(exception.getMessage(), net.kyori.adventure.text.format.NamedTextColor.RED));
        }
    }

    /** Every saved blueprint version, newest first. Clicking one opens it with Roll Back and Cancel in the hotbar. */
    private void history(Player p, int requested) {
        List<BlueprintService.Revision> revisions;
        try { revisions = blueprint.revisions(); }
        catch (IOException | RuntimeException exception) { p.sendMessage("Blueprint: " + exception.getMessage()); return; }
        int pages = Math.max(1, (revisions.size() + IconMenu.PAGE_SIZE - 1) / IconMenu.PAGE_SIZE);
        int page = Math.clamp(requested, 0, pages - 1);
        var date = java.time.format.DateTimeFormatter.ofPattern("MMM d, h:mm a").withZone(java.time.ZoneId.systemDefault());
        var screen = icons.screen(pages > 1 ? "Blueprint History (" + (page + 1) + "/" + pages + ")" : "Blueprint History");
        for (var revision : revisions.subList(page * IconMenu.PAGE_SIZE, Math.min(revisions.size(), (page + 1) * IconMenu.PAGE_SIZE))) {
            boolean current = revision.number() == blueprint.latestUpdate();
            Material material = revision.number() == 0 ? Material.GRASS_BLOCK : revision.title().startsWith("Rolled back") ? Material.ECHO_SHARD
                    : revision.staff() ? Material.BRICKS : Material.PAPER;
            List<String> lines = new ArrayList<>();
            lines.add(revision.title());
            if (!revision.author().isBlank()) lines.add("By " + revision.author());
            if (revision.when() != null) lines.add(date.format(revision.when()));
            if (current) lines.add("This is the shared blueprint now.");
            Icon icon = new Icon(material, revision.number() == 0 ? "Original Campus" : "Update #" + revision.number(), "",
                    current ? null : () -> staging.preview(p, revision.number())).withLore(lines).withClick(current ? null : "Click to look and roll back!");
            screen.add(current ? icon.withColor(net.kyori.adventure.text.format.NamedTextColor.AQUA) : icon);
        }
        screen.pages(page > 0 ? () -> history(p, page - 1) : null, page + 1 < pages ? () -> history(p, page + 1) : null);
        screen.back("Staff", () -> staff(p));
        screen.show(p);
    }

    private void help(Player p) {
        var screen = icons.screen("Help")
                .add(command(p, Material.BOOK, "Rules", "Show the server rules in chat.", "rules").withClick("Click to read!"))
                .add(command(p, Material.KNOWLEDGE_BOOK, "How to Play", "Show how everything works in chat.", "help").withClick("Click to read!"))
                .add(command(p, Material.MAP, "Download Campus Map", "Get a private link to download the campus.", "download").withClick("Click to get the link!"));
        back(screen, p);
        screen.show(p);
    }

    private void authentication(Player p) {
        if (competition.usesMicrosoftAuthentication()) {
            show(p, "School Sign In", "Open your school sign in link in chat, then enter the code from your browser.", List.of(
                    new Choice("Get Sign In Link", () -> competition.verify(p, null)),
                    new Choice("Enter Browser Code", () -> fields(p, "Confirm School Account", "Use the code from your own browser.",
                            List.of(field("Code", "", 32)), v -> competition.verify(p, v.getFirst())))));
        } else {
            show(p, "Competition Sign In", "Use your competition password.", List.of(
                    new Choice("Sign In", () -> fields(p, "Sign In", "Enter your competition password.",
                            List.of(field("Password", "", 128)), v -> competition.login(p, v.getFirst()))),
                    new Choice("Register", () -> fields(p, "Register", "Choose a competition password.",
                            List.of(field("Password", "", 128), field("Repeat password", "", 128)),
                            v -> competition.register(p, v.get(0), v.get(1))))));
        }
    }

    /** The hub's Blueprint guide sends a build, like the emerald in the campus hotbar. */
    public void blueprint(Player p) {
        if (staging != null && competition.isAuthenticated(p)) staging.box(p);
    }

    public void sync(Player p) {
        if (staging != null && competition.isAuthenticated(p)) staging.fix(p);
    }

    private void projects(Player p) {
        var screen = icons.screen("Competition Projects").addAll(List.of(
                new Icon(Material.CHEST, "My Entries", "Your entries and categories.", () -> menus.openCompetition(p)),
                new Icon(Material.CRAFTING_TABLE, "Current Build", "Options for the build you are in.", () -> menus.openCurrentEntry(p)),
                command(p, Material.OAK_DOOR, "Visit Builds", "Visit other entries.", "entry visit"),
                command(p, Material.PAINTING, "Gallery Preview", "See your gallery page.", "entry website"),
                input(p, Material.NAME_TAG, "Edit Title", "entry title", field("Title", "", Entry.MAX_TITLE_LENGTH)),
                input(p, Material.WRITABLE_BOOK, "Edit Description", "entry description", field("Description", "", Entry.MAX_DESCRIPTION_LENGTH)),
                command(p, Material.ENDER_EYE, "Camera Controls", "Save camera views.", "camera"),
                command(p, Material.BARRIER, "Exit Camera Preview", "Leave the camera view.", "camera exit")));
        back(screen, p);
        screen.show(p);
    }

    private void staff(Player p) {
        List<Icon> page = new ArrayList<>();
        if (canReviewBuilds(p)) page.add(replays(p));
        var target = field("Player name or account ID", "", 100);
        var reason = field("Reason", "", 300);
        if (blueprint != null && blueprint.allowedActions(p).contains("review")) {
            long waiting;
            try { waiting = blueprint.repository().summaries().stream().filter(summary -> summary.status() == BlueprintRepository.Status.PENDING).count(); }
            catch (IOException | RuntimeException exception) { waiting = 0; }
            page.add(new Icon(Material.SPYGLASS, "Review Builds", waiting + (waiting == 1 ? " build is" : " builds are")
                    + " waiting. Fly to each one and choose Accept or Reject.", () -> staging.review(p)).withClick("Click to start reviewing!"));
            page.add(new Icon(Material.BRICKS, "Edit Blueprint", "Build directly in the shared blueprint. Your changes reach every campus when you leave.",
                    () -> { staging.leave(p); safely(p, () -> blueprint.startEditing(p)); }).withClick("Click to start building!"));
            if (blueprint.drafting()) page.add(new Icon(Material.WRITABLE_BOOK, "Save Blueprint Changes", "Send the staff edits to every campus now.",
                    () -> safely(p, () -> blueprint.saveEdits(p))).withClick("Click to save!"));
            page.add(new Icon(Material.ECHO_SHARD, "Roll Back Blueprint", "Look at saved versions of the shared blueprint and go back to one.",
                    () -> history(p, 0)));
        }
        if (access.mayReviewReplays(p)) {
            if (p.hasPermission("hill175.replay")) {
                page.add(input(p, Material.CLOCK, "Recent Incidents", "hillreplay recent",
                        field("Minutes (1 to 120)", "15", 3), field("Player name or UUID (optional)", "", 36)));
                page.add(input(p, Material.RECOVERY_COMPASS, "Play Incident Timeline", "hillreplay play",
                        field("Minutes (1 to 120)", "15", 3), field("Player name or UUID (optional)", "", 36)));
            }
            page.add(input(p, Material.NAME_TAG, "Account Details", "hillstaff info", target));
        }
        page.add(command(p, Material.PLAYER_HEAD, "My Role", "Show your staff role in chat.", "hillstaff whoami").withHead(p).withClick("Click to show!"));
        if (blueprint != null && blueprint.allowedActions(p).contains("backup")) {
            page.add(command(p, Material.CHEST, "Save Blueprint Snapshot", "Back up the shared blueprint now.", "blueprint backup"));
            page.add(command(p, Material.BOOKSHELF, "List Blueprint Snapshots", "Show saved blueprint backups.", "blueprint backups"));
        }
        if (blueprint == null && p.hasPermission("hill175.campus.rollback")) {
            page.add(command(p, Material.ENDER_CHEST, "Campus Recovery", "Restore part of the shared campus.", "campusbackup menu"));
            page.add(command(p, Material.CHEST, "Save Campus Snapshot", "Back up the shared campus now.", "campusbackup save"));
        }
        if (p.hasPermission("hill175.moderation")) {
            var duration = field("Duration (10m, 2h, 7d or permanent)", "10m", 16);
            page.add(input(p, Material.WHITE_WOOL, "Mute Player", "hillstaff mute", target, duration, reason));
            page.add(input(p, Material.LIME_WOOL, "Remove Mute", "hillstaff unmute", target));
            page.add(input(p, Material.IRON_BARS, "Ban Player", "hillstaff ban", target, duration, reason));
            page.add(input(p, Material.OAK_DOOR, "Remove Ban", "hillstaff unban", target));
            page.add(input(p, Material.FEATHER, "Kick Player", "hillstaff kick", target, reason));
        }
        if (p.hasPermission("hill175.roles.manage")) page.add(input(p, Material.GOLD_INGOT, "Assign Role", "hillstaff role", target,
                field("Role (player, staff, moderator or administrator)", "", 16)));
        var screen = icons.screen("Staff").addAll(page);
        back(screen, p);
        screen.show(p);
    }

    private static void safely(Player p, Runnable action) {
        try { action.run(); }
        catch (RuntimeException exception) {
            p.sendMessage(Component.text("Blueprint: " + exception.getMessage(), net.kyori.adventure.text.format.NamedTextColor.RED));
        }
    }

    private static BedrockForms.Field field(String label, String initial, int limit) {
        String key = label.split("[ (]", 2)[0].toLowerCase(java.util.Locale.ROOT);
        return new BedrockForms.Field(key, label, initial, limit);
    }

    private Icon command(Player p, Material material, String label, String lore, String fixed) {
        return new Icon(material, label, lore, () -> run(p, fixed, List.of())).withClick("Click to use!");
    }

    private Icon input(Player p, Material material, String label, String fixed, BedrockForms.Field... inputs) {
        return new Icon(material, label, "Opens a short form to fill in.", () -> fields(p, label, "Fill in the fields and choose Submit.", List.of(inputs),
                values -> run(p, fixed, values))).withClick("Click to fill in!");
    }

    private void run(Player p, String fixed, List<String> fields) {
        String[] tokens = fixed.split(" ");
        List<String> args = new ArrayList<>(Arrays.asList(tokens).subList(1, tokens.length));
        for (String value : fields) args.add(value.strip());
        if (tokens[0].equals("hillreplay") && args.getLast().isEmpty()) args.removeLast();
        execute(p, tokens[0], args.toArray(String[]::new));
    }

    private void execute(Player p, String name, String... args) {
        if (!competition.isAuthenticated(p) || !access.allowed(p)) return;
        var command = plugin.getCommand(name);
        if (command != null && command.testPermission(p)) command.execute(p, name, args);
    }

    private String identity(Player p) { return competition.isAuthenticated(p) ? competition.participantKey(p) : null; }

    private View begin(Player p) {
        View view = new View(UUID.randomUUID(), identity(p), p.getWorld().getUID(), System.nanoTime());
        active.put(p.getUniqueId(), view);
        return view;
    }

    private void respond(Player p, View view, Runnable action) {
        if (!plugin.isEnabled()) return;
        plugin.getServer().getScheduler().runTask(plugin, () -> {
            if (!active.remove(p.getUniqueId(), view) || !p.isOnline() || plugin.getServer().getPlayer(p.getUniqueId()) != p
                    || !java.util.Objects.equals(view.participant, identity(p)) || !view.world.equals(p.getWorld().getUID())
                    || System.nanoTime() - view.opened > LIFETIME.toNanos() || !access.allowed(p)) return;
            if (!forms.isBedrock(p)) p.closeDialog();
            action.run();
        });
    }

    private void show(Player p, String title, String body, List<Choice> choices) {
        View view = begin(p);
        if (forms.show(p, title, body, choices.stream().map(Choice::label).toList(),
                i -> respond(p, view, choices.get(i).run), () -> active.remove(p.getUniqueId(), view))) return;
        var buttons = choices.stream().map(c -> ActionButton.builder(Component.text(c.label)).width(175)
                .action(DialogAction.customClick((reply, audience) -> {
                    if (audience == p) respond(p, view, c.run);
                }, ClickCallback.Options.builder().uses(1).lifetime(LIFETIME).build())).build()).toList();
        var base = base(title, body).build();
        p.showDialog(Dialog.create(b -> b.empty().base(base).type(DialogType.multiAction(buttons).build())));
    }

    private static DialogBase.Builder base(String title, String body) {
        return DialogBase.builder(Component.text(title)).canCloseWithEscape(true).pause(false)
                .body(List.of(DialogBody.plainMessage(Component.text(body), 360)));
    }

    private void fields(Player p, String title, String body, List<BedrockForms.Field> fields, Consumer<List<String>> action) {
        View view = begin(p);
        Consumer<List<String>> finish = values -> respond(p, view, () -> {
            for (int i = 0; i < fields.size(); i++) {
                String value = values.get(i);
                if (value == null || value.length() > fields.get(i).maxLength() || value.chars().anyMatch(Character::isISOControl)) {
                    p.sendMessage("Check the value for " + fields.get(i).label() + ".");
                    return;
                }
            }
            action.accept(values);
        });
        if (forms.showFields(p, title, body, fields, finish, () -> active.remove(p.getUniqueId(), view))) return;
        var base = base(title, body).inputs(fields.stream().<DialogInput>map(f -> DialogInput.text(f.name(), Component.text(f.label()))
                .initial(f.initial()).maxLength(f.maxLength()).width(340).build()).toList()).build();
        var button = ActionButton.builder(Component.text("Submit")).action(DialogAction.customClick((response, audience) -> {
            if (audience == p) finish.accept(fields.stream().map(f -> response.getText(f.name())).toList());
        }, ClickCallback.Options.builder().uses(1).lifetime(LIFETIME).build())).build();
        p.showDialog(Dialog.create(b -> b.empty().base(base).type(DialogType.multiAction(List.of(button)).build())));
    }

    @EventHandler(priority = org.bukkit.event.EventPriority.HIGHEST)
    public void interact(org.bukkit.event.player.PlayerInteractEvent event) {
        Player p = event.getPlayer();
        if (event.getHand() != org.bukkit.inventory.EquipmentSlot.HAND || !event.getAction().isRightClick()
                || event.getItem() != null && !event.getItem().getType().isAir()) return;
        if (competition.isAuthenticated(p) && !p.isSneaking()) return;
        event.setCancelled(true);
        if (access.allowed(p)) open(p);
    }

    @EventHandler public void quit(PlayerQuitEvent event) {
        active.remove(event.getPlayer().getUniqueId());
        forms.clear(event.getPlayer());
    }

    @Override public void close() {
        if (staging != null) staging.close();
        icons.close();
        active.clear();
        forms.close();
    }
}
