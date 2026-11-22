package org.thehill.hill175.access;

import io.papermc.paper.event.player.AsyncChatEvent;
import org.bukkit.Server;
import org.bukkit.command.Command;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.player.AsyncPlayerPreLoginEvent;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.permissions.PermissionAttachment;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitScheduler;
import org.bukkit.scheduler.BukkitTask;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.auth.sso.SsoException;
import org.thehill.hill175.auth.sso.VerifiedSession;

import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class AccessControlTest {
    @TempDir Path directory;
    private static final Instant NOW = Instant.parse("2026-11-09T12:00:00Z");
    private static final String SCHOOL = "entra:76b02f9e-4050-43db-807c-e05e683be3de:8ef143d9-8b69-43b8-b1fb-5ddc68f8b4e4";
    private static final String TOKEN = "unit-test-bootstrap-credential-random-string-12345";
    private JavaPlugin plugin;
    private Server server;
    private ConsoleCommandSender console;

    @BeforeEach void setup() {
        plugin = mock(JavaPlugin.class);
        server = mock(Server.class);
        when(plugin.getServer()).thenReturn(server);
        when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
        when(server.getOnlinePlayers()).thenReturn(List.of());
        BukkitScheduler scheduler = mock(BukkitScheduler.class);
        when(server.getScheduler()).thenReturn(scheduler);
        when(scheduler.runTask(eq(plugin), any(Runnable.class))).thenAnswer(call -> {
            call.getArgument(1, Runnable.class).run(); return mock(BukkitTask.class);
        });
        console = mock(ConsoleCommandSender.class);
    }
    private AccessControl access(boolean microsoft) throws Exception {
        return new AccessControl(plugin, directory.resolve("moderation.json"), player -> true, microsoft,
                Clock.fixed(NOW, ZoneOffset.UTC), AdminUnlockKey.hash(TOKEN));
    }
    private Player player(String name) {
        Player player = mock(Player.class);
        when(player.getUniqueId()).thenReturn(UUID.randomUUID());
        when(player.getName()).thenReturn(name);
        when(player.isOnline()).thenReturn(true);
        when(player.addAttachment(plugin)).thenReturn(mock(PermissionAttachment.class));
        return player;
    }
    private void command(AccessControl access, org.bukkit.command.CommandSender sender, String... args) {
        access.onCommand(sender, mock(Command.class), "hillstaff", args);
    }
    private PlayerCommandPreprocessEvent event(Player player, String command) {
        var event = mock(PlayerCommandPreprocessEvent.class);
        when(event.getPlayer()).thenReturn(player); when(event.getMessage()).thenReturn(command);
        return event;
    }

    @Test void staffGetsRecoveryAndModeratorsGetModerationWithoutOperatorPrivileges() throws Exception {
        try (var access = access(true)) {
            Player staff = player("Staff");
            access.authenticated(staff, new VerifiedSession(SCHOOL, "Hill Staff", NOW.plusSeconds(1800), ServerRole.STAFF));
            PermissionAttachment attachment = staff.addAttachment(plugin);
            verify(attachment).setPermission("hill175.campus.rollback", true);
            verify(attachment).setPermission("hill175.replay", true);
            assertTrue(access.mayReviewReplays(staff));
            verify(attachment, never()).setPermission("hill175.moderation", true);
            verify(staff, never()).setOp(anyBoolean());
            Player moderator = player("Moderator");
            access.authenticated(moderator, new VerifiedSession(SCHOOL, "Hill Staff", NOW.plusSeconds(1800), ServerRole.MODERATOR));
            verify(moderator.addAttachment(plugin)).setPermission("hill175.moderation", true);
            verify(moderator, never()).setOp(anyBoolean());
        }
    }

    @Test void operatorStatusAndPermissionAloneDoNotGrantReplayAccess() throws Exception {
        Player student = player("StudentOperator");
        when(student.isOp()).thenReturn(true);
        when(student.hasPermission("hill175.replay")).thenReturn(true);
        try (var access = access(true)) {
            assertFalse(access.mayReviewReplays(student));
            access.authenticated(student, new VerifiedSession(SCHOOL, "Hill Student", NOW.plusSeconds(1800)));
            assertFalse(access.mayReviewReplays(student));
        }
    }

    @Test void playersCannotGrantRolesAndModeratorsCannotManagePeersOrPromoteThemselves() throws Exception {
        Player player = player("Player");
        try (var access = access(true)) {
            access.authenticated(player, new VerifiedSession(SCHOOL, "Hill Player", NOW.plusSeconds(1800)));
            command(access, player, "role", SCHOOL, "administrator");
            command(access, player, "ban", SCHOOL, "permanent", "Reason");
            verify(player).sendMessage("This control requires the Administrator role.");
            verify(player).sendMessage("This control requires the Moderator role.");
        }
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            store.change(SCHOOL, "role", "MODERATOR", "console", NOW, Instant.MAX);
        }
        try (var access = access(true)) {
            access.authenticated(player, new VerifiedSession(SCHOOL, "Hill Player", NOW.plusSeconds(1800)));
            command(access, player, "ban", SCHOOL, "permanent", "Reason");
            verify(player).sendMessage("You can manage only lower roles. Use the server console to appoint or change administrators.");
            command(access, player, "role", SCHOOL, "administrator");
        }
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            assertEquals(ServerRole.MODERATOR, store.account(SCHOOL).role());
            assertNull(store.account(SCHOOL).ban());
        }
    }

    @Test void microsoftBanRejectsBothKnownTransportsAndFreshAliasAdmission() throws Exception {
        Player java = player("JavaName"), bedrock = player(".BedrockName");
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            store.remember(java.getUniqueId(), java.getName(), "Hill Person", SCHOOL, ServerRole.PLAYER);
            store.remember(bedrock.getUniqueId(), bedrock.getName(), "Hill Person", SCHOOL, ServerRole.PLAYER);
            store.change(SCHOOL, "ban", "Griefing", "console", NOW, Instant.MAX);
        }
        try (var access = access(true)) {
            for (Player player : List.of(java, bedrock)) {
                var preLogin = mock(AsyncPlayerPreLoginEvent.class);
                UUID id = player.getUniqueId();
                when(preLogin.getUniqueId()).thenReturn(id);
                access.onPreLogin(preLogin);
                verify(preLogin).disallow(eq(AsyncPlayerPreLoginEvent.Result.KICK_BANNED), any(net.kyori.adventure.text.Component.class));
                assertFalse(access.allowed(player));
            }
            assertThrows(SsoException.class, () -> access.requireSchoolAdmission(SCHOOL));
            assertThrows(SecurityException.class, () -> access.authenticated(player("FreshAlias"), new VerifiedSession(SCHOOL, "New Name", NOW.plusSeconds(1800))));
        }
    }

    @Test void mutedAccountsCannotChatOrUsePrivateMessageOrNamespacedBypasses() throws Exception {
        Player java = player("JavaName"), bedrock = player(".BedrockName");
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            store.remember(java.getUniqueId(), java.getName(), "Hill Person", SCHOOL, ServerRole.PLAYER);
            store.remember(bedrock.getUniqueId(), bedrock.getName(), "Hill Person", SCHOOL, ServerRole.PLAYER);
            store.change(SCHOOL, "mute", "Chat abuse", "console", NOW, NOW.plusSeconds(600));
        }
        try (var access = access(true)) {
            for (Player player : List.of(java, bedrock)) {
                AsyncChatEvent chat = mock(AsyncChatEvent.class); when(chat.getPlayer()).thenReturn(player);
                access.onChat(chat); verify(chat).setCancelled(true);
                for (String text : List.of("/msg Other hi", "/minecraft:tell Other hi", "/me hello", "/team invite Other")) {
                    var command = event(player, text); access.onCommand(command); verify(command).setCancelled(true);
                }
                var campus = event(player, "/campus home"); access.onCommand(campus); verify(campus, never()).setCancelled(true);
            }
        }
    }

    @Test void consoleCanAssignAnOfflineAdministratorAndBanWithDurableAudit() throws Exception {
        try (var access = access(true)) {
            command(access, console, "role", SCHOOL, "administrator");
            command(access, console, "ban", SCHOOL, "7d", "Reason");
        }
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            assertEquals(ServerRole.ADMINISTRATOR, store.account(SCHOOL).role());
            assertEquals(NOW.plusSeconds(7 * 86400), store.account(SCHOOL).ban().until());
        }
    }

    @Test void explicitTransportTargetsCannotBypassSchoolRoleHierarchy() throws Exception {
        Player moderator = player("Moderator"), administrator = player("Administrator");
        String mod = "entra:76b02f9e-4050-43db-807c-e05e683be3de:" + UUID.randomUUID();
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            store.remember(moderator.getUniqueId(), moderator.getName(), "Hill Moderator", mod, ServerRole.MODERATOR);
            store.remember(administrator.getUniqueId(), administrator.getName(), "Hill Administrator", SCHOOL, ServerRole.ADMINISTRATOR);
        }
        try (var access = access(true)) {
            access.authenticated(moderator, new VerifiedSession(mod, "Hill Moderator", NOW.plusSeconds(1800), ServerRole.MODERATOR));
            command(access, moderator, "ban", "game:" + administrator.getUniqueId(), "permanent", "Reason");
            verify(moderator).sendMessage("You can manage only lower roles. Use the server console to appoint or change administrators.");
        }
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            assertNull(store.account("game:" + administrator.getUniqueId()).ban());
        }
    }

    @Test void hiddenUnlockIsRedactedAbsentFromMetadataAndConsumedAcrossRestart() throws Exception {
        Player first = player("FirstAdmin");
        CountDownLatch unlocked = new CountDownLatch(1);
        doAnswer(call -> { if (call.getArgument(0).equals("Administrator role enabled.")) unlocked.countDown(); return null; })
                .when(first).sendMessage(anyString());
        try (var access = access(true)) {
            access.authenticated(first, new VerifiedSession(SCHOOL, "Hill Person", NOW.plusSeconds(1800)));
            var event = event(first, "/admin unlock " + TOKEN);
            access.onCommand(event);
            assertTrue(unlocked.await(5, TimeUnit.SECONDS));
            verify(event).setCancelled(true); verify(event).setMessage("/admin");
            verify(first.addAttachment(plugin)).setPermission("hill175.roles.manage", true);
        }
        String other = "entra:76b02f9e-4050-43db-807c-e05e683be3de:" + UUID.randomUUID();
        try (var access = access(true)) {
            Player next = player("NextAdmin");
            access.authenticated(next, new VerifiedSession(other, "Other Person", NOW.plusSeconds(1800)));
            access.onCommand(event(next, "/admin unlock " + TOKEN));
        }
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            assertEquals(ServerRole.ADMINISTRATOR, store.account(SCHOOL).role());
            assertEquals(ServerRole.PLAYER, store.account(other).role());
        }
        var metadata = new org.bukkit.configuration.file.YamlConfiguration();
        try (var input = getClass().getResourceAsStream("/plugin.yml")) {
            metadata.load(new java.io.InputStreamReader(java.util.Objects.requireNonNull(input)));
        }
        assertFalse(metadata.contains("commands.admin"));
    }

    @Test void unlockRequiresAuthenticationAndLimitsGuessesPerSchoolAccount() throws Exception {
        Player first = player("First");
        try (var access = access(true)) {
            access.onCommand(event(first, "/admin unlock " + TOKEN));
            verify(first).sendMessage("Unknown command.");
            access.authenticated(first, new VerifiedSession(SCHOOL, "Hill Person", NOW.plusSeconds(1800)));
            for (int i = 0; i < 5; i++) access.onCommand(event(first, "/admin unlock wrong"));
            access.onCommand(event(first, "/admin unlock " + TOKEN));
        }
        try (var store = new AccessStore(directory.resolve("moderation.json"))) {
            assertEquals(ServerRole.PLAYER, store.account(SCHOOL).role());
        }
    }
}
