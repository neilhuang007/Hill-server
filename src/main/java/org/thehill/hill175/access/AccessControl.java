package org.thehill.hill175.access;

import io.papermc.paper.event.player.AsyncChatEvent;
import net.kyori.adventure.text.Component;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.AsyncPlayerPreLoginEvent;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.permissions.PermissionAttachment;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.auth.sso.SsoException;
import org.thehill.hill175.auth.sso.VerifiedSession;

import java.io.IOException;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;

/** Canonical account moderation shared by Java, Bedrock, school admission, chat and recovery. */
public final class AccessControl implements Listener, CommandExecutor, TabCompleter, AutoCloseable {
    private record Session(String subject, ServerRole microsoft) { }
    private static final Set<String> MUTED_COMMANDS = Set.of("hillmenu", "verify", "login", "register", "help", "rules",
            "campus", "campusbackup", "hill175", "h175", "competition", "hub", "lobby", "camera", "entry", "hillstaff",
            "download", "hillreplay", "party", "invite", "blueprint", "review");
    private final JavaPlugin plugin;
    private final AccessStore store;
    private final Predicate<Player> authenticated;
    private final boolean microsoft;
    private final Clock clock;
    private final String unlockHash;
    private final Map<String, Attempts> unlockAttempts = new HashMap<>();
    private Instant globalUnlockReset = Instant.MIN;
    private int globalUnlockFailures;
    private final ThreadPoolExecutor writes = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(256), Thread.ofPlatform().daemon().name("hill175-moderation-", 0).factory());
    private final Map<UUID, Session> sessions = new ConcurrentHashMap<>();
    private final Map<UUID, PermissionAttachment> permissions = new HashMap<>();
    private volatile boolean closing;

    public AccessControl(JavaPlugin plugin, Path file, Predicate<Player> authenticated, boolean microsoft) throws IOException {
        this(plugin, file, authenticated, microsoft, Clock.systemUTC(), configuredHash(plugin, file));
    }
    AccessControl(JavaPlugin plugin, Path file, Predicate<Player> authenticated, boolean microsoft, Clock clock, String unlockHash) throws IOException {
        this.plugin = plugin; this.authenticated = authenticated; this.microsoft = microsoft; this.clock = clock;
        this.unlockHash = unlockHash;
        store = new AccessStore(file);
    }
    private static String configuredHash(JavaPlugin plugin, Path file) throws IOException {
        if (plugin.getServer().spigot().getSpigotConfig().getBoolean("commands.log", true)) {
            throw new IOException("Sensitive authentication requires commands.log=false in spigot.yml.");
        }
        return AdminUnlockKey.load(file.toAbsolutePath().getParent(), System.getenv("HILL175_ADMIN_UNLOCK_SHA256"));
    }

    /** Also called by SSO before any new game alias is linked. */
    public void requireSchoolAdmission(String subject) {
        AccessStore.Sanction ban = store.account(subject).ban();
        if (active(ban)) throw new SsoException("This Hill account is banned from this server. Reason: " + ban.reason());
    }

    public boolean allowed(Player player) {
        try { return !active(ban(player.getUniqueId(), subject(player))); }
        catch (RuntimeException unavailable) { return false; }
    }

    /** Main thread admission, before gameplay unlocks. Writes are serialized away from the game thread. */
    public void authenticated(Player player, VerifiedSession identity) {
        String subject = microsoft ? identity.participantKey() : gameSubject(player.getUniqueId());
        AccessStore.Sanction ban = ban(player.getUniqueId(), subject);
        if (active(ban)) throw new SecurityException("You are banned from this server. Reason: " + ban.reason());
        sessions.put(player.getUniqueId(), new Session(subject, identity.role()));
        applyPermissions(player);
        UUID id = player.getUniqueId();
        String gameName = player.getName();
        submit(() -> store.remember(id, gameName, identity.displayName(), subject, identity.role()), () -> { });
    }

    private boolean active(AccessStore.Sanction sanction) { return sanction != null && sanction.active(clock.instant()); }
    private static String gameSubject(UUID id) { return "game:" + id; }
    private String subject(Player player) {
        Session session = sessions.get(player.getUniqueId());
        return session != null ? session.subject : store.profile(player.getUniqueId()).map(AccessStore.Profile::subject)
                .orElse(gameSubject(player.getUniqueId()));
    }
    private ServerRole role(Player player) {
        Session session = sessions.get(player.getUniqueId());
        if (session == null || !authenticated.test(player)) return ServerRole.PLAYER;
        ServerRole assigned = store.account(session.subject).assigned();
        return assigned.ordinal() > session.microsoft.ordinal() ? assigned : session.microsoft;
    }
    private AccessStore.Sanction ban(UUID id, String subject) {
        AccessStore.Sanction game = store.account(gameSubject(id)).ban();
        return active(game) ? game : store.account(subject).ban();
    }
    private boolean muted(Player player) {
        return active(store.account(subject(player)).mute()) || active(store.account(gameSubject(player.getUniqueId())).mute());
    }

    public boolean mayReviewReplays(Player player) {
        return authenticated.test(player) && role(player).atLeast(ServerRole.STAFF);
    }

    private void applyPermissions(Player player) {
        PermissionAttachment previous = permissions.remove(player.getUniqueId());
        if (previous != null) player.removeAttachment(previous);
        ServerRole role = role(player);
        if (role == ServerRole.PLAYER) return;
        PermissionAttachment attachment = player.addAttachment(plugin);
        attachment.setPermission("hill175.staff", true);
        attachment.setPermission("hill175.campus.rollback", true);
        attachment.setPermission("hill175.replay", true);
        attachment.setPermission("hill175.blueprint.review", true);
        if (role.atLeast(ServerRole.MODERATOR)) attachment.setPermission("hill175.moderation", true);
        if (role == ServerRole.ADMINISTRATOR) {
            attachment.setPermission("hill175.roles.manage", true);
            attachment.setPermission("hill175.blueprint.backup", true);
        }
        permissions.put(player.getUniqueId(), attachment);
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onPreLogin(AsyncPlayerPreLoginEvent event) {
        try {
            String subject = store.profile(event.getUniqueId()).map(AccessStore.Profile::subject).orElse(gameSubject(event.getUniqueId()));
            var ban = ban(event.getUniqueId(), subject);
            if (active(ban)) event.disallow(AsyncPlayerPreLoginEvent.Result.KICK_BANNED,
                    Component.text("You are banned from this server. Reason: " + ban.reason()));
        } catch (RuntimeException unavailable) {
            event.disallow(AsyncPlayerPreLoginEvent.Result.KICK_OTHER, Component.text("Admission is unavailable. Contact server staff."));
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onChat(AsyncChatEvent event) {
        boolean blocked;
        try { blocked = !allowed(event.getPlayer()) || muted(event.getPlayer()); }
        catch (RuntimeException unavailable) { blocked = true; }
        if (blocked) {
            event.setCancelled(true);
            event.getPlayer().sendMessage(Component.text("You are muted. Contact server staff if you need help."));
        }
    }

    @EventHandler(priority = EventPriority.LOWEST, ignoreCancelled = true)
    public void onCommand(PlayerCommandPreprocessEvent event) {
        if (event.getMessage().split("\\s+", 2)[0].equalsIgnoreCase("/admin")) {
            String request = event.getMessage();
            event.setCancelled(true);
            event.setMessage("/admin");
            unlock(event.getPlayer(), request);
            return;
        }
        String command = event.getMessage().split("\\s+", 2)[0].replaceFirst("^/", "").toLowerCase(Locale.ROOT);
        boolean blocked;
        try { blocked = !allowed(event.getPlayer()) || (muted(event.getPlayer()) && !MUTED_COMMANDS.contains(command)); }
        catch (RuntimeException unavailable) { blocked = true; }
        if (blocked) {
            event.setCancelled(true);
            event.getPlayer().sendMessage(Component.text("Messaging commands are unavailable while you are muted."));
        }
    }

    private void unlock(Player player, String request) {
        String[] args = request.strip().split("\\s+");
        if (!authenticated.test(player) || !sessions.containsKey(player.getUniqueId()) || !allowed(player)) {
            player.sendMessage("Unknown command."); return;
        }
        Instant now = clock.instant();
        if (!globalUnlockReset.isAfter(now)) { globalUnlockFailures = 0; globalUnlockReset = now.plusSeconds(900); }
        String subject = subject(player);
        Attempts attempts = unlockAttempts.get(subject);
        if (globalUnlockFailures >= 20 || (attempts != null && attempts.until.isAfter(now) && attempts.failures >= 5)) {
            player.sendMessage("Unknown command."); return;
        }
        if (args.length != 3 || !args[1].equals("unlock") || !AdminUnlockKey.matches(args[2], unlockHash)) {
            if (attempts == null || !attempts.until.isAfter(now)) attempts = new Attempts(now.plusSeconds(900));
            attempts.failures++; unlockAttempts.put(subject, attempts); globalUnlockFailures++;
            // Keep failed guesses bounded even during large sign-in events.
            unlockAttempts.entrySet().removeIf(entry -> !entry.getValue().until.isAfter(now));
            player.sendMessage("Unknown command."); return;
        }
        try {
            UUID playerId = player.getUniqueId();
            submit(() -> {
                var ban = ban(playerId, subject);
                if (active(ban)) throw new SecurityException("Unknown command.");
                store.claimAdministrator(subject, unlockHash, clock.instant());
            }, () -> {
                if (player.isOnline() && authenticated.test(player) && subject(player).equals(subject)) {
                    applyPermissions(player);
                    player.sendMessage("Administrator role enabled.");
                }
            }, player);
        } catch (SecurityException unavailable) { player.sendMessage("Unknown command."); }
    }
    private static final class Attempts {
        private final Instant until;
        private int failures;
        private Attempts(Instant until) { this.until = until; }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onQuit(PlayerQuitEvent event) {
        sessions.remove(event.getPlayer().getUniqueId());
        var attachment = permissions.remove(event.getPlayer().getUniqueId());
        if (attachment != null) event.getPlayer().removeAttachment(attachment);
    }

    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        try {
            requireSignedIn(sender);
            if (args.length == 0) {
                sender.sendMessage("Staff controls: /hillstaff whoami, info <target>, role <target> <player|staff|moderator|administrator>, "
                        + "mute <target> <duration|permanent> <reason>, unmute <target>, ban <target> <duration|permanent> <reason>, unban <target>, kick <target> <reason>.");
                return true;
            }
            String action = args[0].toLowerCase(Locale.ROOT);
            if (action.equals("whoami") && sender instanceof Player player) {
                player.sendMessage("Your server role: " + role(player).label() + ".");
                return true;
            }
            if (!Set.of("info", "role", "ban", "unban", "mute", "unmute", "kick").contains(action)) {
                throw new IllegalArgumentException("Unknown staff control. Use /hillstaff for commands.");
            }
            requireRole(sender, action.equals("info") ? ServerRole.STAFF : action.equals("role") ? ServerRole.ADMINISTRATOR : ServerRole.MODERATOR);
            if (args.length < 2) throw new IllegalArgumentException("Specify a known game name, game UUID, or exact school account identifier.");
            String target = resolve(args[1]);
            if (action.equals("info")) {
                var account = store.account(target);
                sender.sendMessage("Account: " + target + ". Role: " + account.role().label() + ". Banned: " + active(account.ban()) + ". Muted: " + active(account.mute()) + ".");
                store.profiles().forEach((id, profile) -> {
                    if (profile.subject().equals(target)) sender.sendMessage(profile.gameName() + " (" + id + "): " + profile.displayName());
                });
                return true;
            }
            ServerRole assigned = action.equals("role") && args.length == 3 ? ServerRole.parse(args[2]) : null;
            validateHierarchy(sender, target, assigned);
            Instant until = Instant.MAX;
            String value = "";
            if (action.equals("role")) {
                if (assigned == null) throw new IllegalArgumentException("Usage: /hillstaff role <target> <player|staff|moderator|administrator>");
                value = assigned.name();
            } else if (action.equals("ban") || action.equals("mute")) {
                if (args.length < 4) throw new IllegalArgumentException("Usage: /hillstaff " + action + " <target> <10m|2h|7d|permanent> <reason>");
                until = expires(args[2], clock.instant());
                value = plainReason(args, 3);
            } else if (action.equals("kick")) {
                if (args.length < 3) throw new IllegalArgumentException("Usage: /hillstaff kick <target> <reason>");
                value = plainReason(args, 2);
            } else if (args.length != 2) throw new IllegalArgumentException("Usage: /hillstaff " + action + " <target>");
            String actor = sender instanceof Player player ? subject(player) : "console";
            String detail = value;
            Instant expiration = until;
            // The worker rechecks authority before persisting, so queued demotions cannot retain privileges.
            ServerRole actorRole = sender instanceof Player player ? role(player) : ServerRole.ADMINISTRATOR;
            submit(() -> {
                if (sender instanceof Player) {
                    ServerRole current = store.account(actor).role();
                    if (current.ordinal() < actorRole.ordinal()) throw new SecurityException("Your role changed before this request was saved.");
                    if (targetRole(target).ordinal() >= current.ordinal()) throw new SecurityException("You cannot manage a peer or a higher role.");
                }
                store.change(target, action, detail, actor, clock.instant(), expiration);
            }, () -> {
                for (Player player : plugin.getServer().getOnlinePlayers()) {
                    if (!subject(player).equals(target) && !gameSubject(player.getUniqueId()).equals(target)) continue;
                    if (action.equals("ban") || action.equals("kick")) player.kick(Component.text((action.equals("ban") ? "Banned: " : "Removed: ") + detail));
                    else {
                        if (action.equals("role")) applyPermissions(player);
                        player.sendMessage(Component.text("Staff updated your account: " + action + "."));
                    }
                }
                sender.sendMessage("Saved " + action + " for " + target + ".");
            }, sender);
        } catch (IllegalArgumentException | SecurityException exception) {
            sender.sendMessage(exception.getMessage() == null ? "Invalid staff command." : exception.getMessage());
        }
        return true;
    }

    private void requireSignedIn(CommandSender sender) {
        if (sender instanceof ConsoleCommandSender) return;
        if (!(sender instanceof Player player) || !authenticated.test(player) || !sessions.containsKey(player.getUniqueId())) {
            throw new SecurityException("Sign in before using staff controls.");
        }
    }
    private void requireRole(CommandSender sender, ServerRole minimum) {
        if (!(sender instanceof ConsoleCommandSender) && (!(sender instanceof Player player) || !role(player).atLeast(minimum))) {
            throw new SecurityException("This control requires the " + minimum.label() + " role.");
        }
    }
    private void validateHierarchy(CommandSender sender, String target, ServerRole assigned) {
        if (sender instanceof ConsoleCommandSender) return;
        Player player = (Player) sender;
        ServerRole ownRole = role(player);
        if (subject(player).equals(target) || gameSubject(player.getUniqueId()).equals(target)
                || targetRole(target).ordinal() >= ownRole.ordinal()
                || (assigned != null && assigned.ordinal() >= ownRole.ordinal())) {
            throw new SecurityException("You can manage only lower roles. Use the server console to appoint or change administrators.");
        }
    }
    private ServerRole targetRole(String target) {
        ServerRole role = store.account(target).role();
        if (target.startsWith("game:")) {
            var profile = store.profile(UUID.fromString(target.substring(5)));
            if (profile.isPresent()) {
                ServerRole schoolRole = store.account(profile.orElseThrow().subject()).role();
                if (schoolRole.ordinal() > role.ordinal()) role = schoolRole;
            }
        }
        return role;
    }
    private String resolve(String text) {
        if (text.startsWith("entra:") || text.startsWith("game:")) { AccessStore.validateSubject(text); return text; }
        try {
            UUID id = UUID.fromString(text);
            if (!id.toString().equalsIgnoreCase(text)) throw new IllegalArgumentException();
            return store.profile(id).map(AccessStore.Profile::subject).orElseThrow(() -> new IllegalArgumentException("That game UUID has not signed in yet."));
        } catch (IllegalArgumentException ignored) { }
        var matches = store.profiles().values().stream().filter(profile -> profile.gameName().equalsIgnoreCase(text))
                .map(AccessStore.Profile::subject).distinct().toList();
        if (matches.size() != 1) throw new IllegalArgumentException("Unknown or ambiguous game name. Use the exact account identifier from /hillstaff info.");
        return matches.getFirst();
    }
    static Instant expires(String duration, Instant now) {
        if (duration.equalsIgnoreCase("permanent")) return Instant.MAX;
        if (!duration.matches("[1-9][0-9]{0,4}[mhd]")) throw new IllegalArgumentException("Use a duration such as 10m, 2h, 7d, or permanent.");
        long number = Long.parseLong(duration.substring(0, duration.length() - 1));
        Duration value = switch (duration.charAt(duration.length() - 1)) {
            case 'm' -> Duration.ofMinutes(number); case 'h' -> Duration.ofHours(number); default -> Duration.ofDays(number);
        };
        if (value.compareTo(Duration.ofDays(365)) > 0) throw new IllegalArgumentException("Timed sanctions are limited to 365 days. Use permanent for longer sanctions.");
        return now.plus(value);
    }
    private static String plainReason(String[] args, int from) {
        String reason = String.join(" ", Arrays.copyOfRange(args, from, args.length));
        if (reason.isBlank() || reason.length() > 240 || reason.codePoints().anyMatch(c -> Character.isISOControl(c)
                || Character.getType(c) == Character.FORMAT || c == 0x00a7)) throw new IllegalArgumentException("Use a plain reason of 1 to 240 characters.");
        return reason;
    }

    @FunctionalInterface private interface Write { void run() throws IOException; }
    private void submit(Write write, Runnable completed) { submit(write, completed, null); }
    private void submit(Write write, Runnable completed, CommandSender sender) {
        if (closing) throw new SecurityException("Moderation is stopping. Try again after restart.");
        try {
            writes.execute(() -> {
                try {
                    write.run();
                    if (!closing) plugin.getServer().getScheduler().runTask(plugin, completed);
                } catch (SecurityException denied) {
                    if (!closing && sender != null) plugin.getServer().getScheduler().runTask(plugin, () -> sender.sendMessage(denied.getMessage()));
                } catch (IOException | RuntimeException exception) {
                    plugin.getLogger().severe("Stopping Paper because moderation records could not be saved safely.");
                    if (!closing) plugin.getServer().getScheduler().runTask(plugin, () -> plugin.getServer().shutdown());
                }
            });
        } catch (RejectedExecutionException busy) { throw new SecurityException("Staff controls are busy. Try again shortly."); }
    }

    @Override public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        try {
            requireSignedIn(sender);
            if (args.length == 1) {
                List<String> commands = sender instanceof ConsoleCommandSender || role((Player) sender).atLeast(ServerRole.ADMINISTRATOR)
                        ? List.of("whoami", "info", "role", "ban", "unban", "mute", "unmute", "kick")
                        : role((Player) sender).atLeast(ServerRole.MODERATOR) ? List.of("whoami", "info", "ban", "unban", "mute", "unmute", "kick")
                        : role((Player) sender).atLeast(ServerRole.STAFF) ? List.of("whoami", "info") : List.of("whoami");
                return commands.stream().filter(value -> value.startsWith(args[0].toLowerCase(Locale.ROOT))).toList();
            }
            if (args.length == 3 && args[0].equalsIgnoreCase("role")) {
                requireRole(sender, ServerRole.ADMINISTRATOR);
                return Arrays.stream(ServerRole.values()).map(role -> role.name().toLowerCase(Locale.ROOT)).filter(value -> value.startsWith(args[2].toLowerCase(Locale.ROOT))).toList();
            }
        } catch (SecurityException ignored) { }
        return List.of();
    }
    @Override public void close() throws IOException {
        closing = true;
        writes.shutdown();
        try {
            if (!writes.awaitTermination(10, TimeUnit.SECONDS)) throw new IOException("Moderation writes have not finished. Keep the process stopped before restarting.");
        } catch (InterruptedException exception) { Thread.currentThread().interrupt(); throw new IOException(exception); }
        for (Player player : plugin.getServer().getOnlinePlayers()) {
            var attachment = permissions.remove(player.getUniqueId());
            if (attachment != null) player.removeAttachment(attachment);
        }
        store.close();
    }
}
