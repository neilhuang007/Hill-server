package org.thehill.hill175.competition;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Server;
import org.bukkit.World;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.plugin.PluginManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.mockito.MockedStatic;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.auth.SsoPlayerSessions;
import org.thehill.hill175.auth.sso.VerifiedSession;
import org.thehill.hill175.auth.sso.MicrosoftSsoService;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.world.WorldModule;

import java.lang.reflect.Field;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class SchoolParticipantOwnershipTest {
    private static final String PARTICIPANT = "entra:school-tenant:student-object-id";
    @TempDir Path directory;

    @Test
    void eitherEditionCanEditTheSameSchoolOwnedEntry() throws Exception {
        Fixture f = new Fixture();
        Entry entry = f.entry(Category.JOURNEY, PARTICIPANT);
        Player java = f.player("JavaBuilder");
        Player bedrock = f.player(".BedrockBuilder");
        assertTrue(f.competition.mayBuild(java, java.getLocation()));
        assertTrue(f.competition.mayBuild(bedrock, bedrock.getLocation()));
        f.competition.setTitle(bedrock, entry, "Our Hill project");
        assertEquals("Our Hill project", entry.title());
        assertEquals(Set.of(PARTICIPANT), entry.members());
        verify(f.store).saveEntry(entry);
    }

    @Test
    void switchingMinecraftAccountsCannotCreateAThirdEntry() throws Exception {
        Fixture f = new Fixture();
        f.entry(Category.JOURNEY, PARTICIPANT);
        f.entry(Category.PLACE, PARTICIPANT);
        assertTrue(f.competition.createEntry(f.player(".NewAlias"), Category.PEOPLE).isEmpty());
        verify(f.worlds, never()).allocate(any(Category.class), anyInt(), any(UUID.class));
    }

    @Test
    void switchingMinecraftAccountsCannotDuplicateACategory() throws Exception {
        Fixture f = new Fixture();
        f.entry(Category.JOURNEY, PARTICIPANT);
        assertTrue(f.competition.createEntry(f.player(".NewAlias"), Category.JOURNEY).isEmpty());
        verify(f.worlds, never()).allocate(any(Category.class), anyInt(), any(UUID.class));
    }

    @Test
    void refusesTeamInvitesToAnAliasOfTheSameStudent() throws Exception {
        Fixture f = new Fixture();
        f.entry(Category.JOURNEY, PARTICIPANT);
        Player java = f.player("JavaBuilder");
        Player bedrock = f.player(".BedrockBuilder");
        try (MockedStatic<Bukkit> bukkit = mockStatic(Bukkit.class)) {
            bukkit.when(() -> Bukkit.getPlayerExact(".BedrockBuilder")).thenReturn(bedrock);
            f.competition.invite(java, ".BedrockBuilder");
        }
        Field invites = CompetitionModule.class.getDeclaredField("invitesByTarget");
        invites.setAccessible(true);
        assertTrue(((Map<?, ?>) invites.get(f.competition)).isEmpty());
    }

    @Test
    void schoolVerificationNeverClaimsLegacyEntriesByMatchingTheNickname() throws Exception {
        Fixture f = new Fixture();
        f.entry(Category.JOURNEY, "javabuilder");
        Player java = f.player("JavaBuilder");
        assertFalse(f.competition.mayBuild(java, java.getLocation()));
    }

    @Test
    void savesBothSubmissionFieldsTogetherWithOneWrite() throws Exception {
        Fixture f = new Fixture();
        Entry entry = f.entry(Category.JOURNEY, PARTICIPANT);
        Player player = f.player("JavaBuilder");

        assertEquals(CompetitionModule.DetailsUpdateResult.SAVED,
                f.competition.saveSubmissionDetails(player, entry, "  Our Hill  ", "  A restored chapel.  "));

        assertEquals("Our Hill", entry.title());
        assertEquals("A restored chapel.", entry.description());
        verify(f.store, times(1)).saveEntry(entry);
    }

    @Test
    void invalidSubmissionDetailsDoNotPartiallyUpdateTheEntry() throws Exception {
        Fixture f = new Fixture();
        Entry entry = f.entry(Category.JOURNEY, PARTICIPANT);
        entry.title("Original title");
        entry.description("Original description");
        Player player = f.player("JavaBuilder");

        for (String invalidDescription : List.of("  ", "x".repeat(Entry.MAX_DESCRIPTION_LENGTH + 1))) {
            assertEquals(CompetitionModule.DetailsUpdateResult.INVALID_DETAILS,
                    f.competition.saveSubmissionDetails(player, entry, "New title", invalidDescription));
        }
        assertEquals(CompetitionModule.DetailsUpdateResult.INVALID_DETAILS,
                f.competition.saveSubmissionDetails(player, entry, "x".repeat(Entry.MAX_TITLE_LENGTH + 1), "New description"));

        assertEquals("Original title", entry.title());
        assertEquals("Original description", entry.description());
        verify(f.store, never()).saveEntry(any());
    }

    @ParameterizedTest
    @EnumSource(EditRestriction.class)
    void commandAndDialogEditsEnforceTheSameAccessRules(EditRestriction restriction) throws Exception {
        Fixture f = new Fixture();
        Entry entry = f.entry(Category.JOURNEY,
                restriction == EditRestriction.OTHER_OWNER ? "entra:school-tenant:other-student" : PARTICIPANT);
        entry.title("Original title");
        entry.description("Original description");
        Player player = f.player("JavaBuilder");
        switch (restriction) {
            case UNAUTHENTICATED -> f.sessions.clear();
            case SUBMITTED -> entry.submit(Instant.now());
            case RESETTING -> when(f.worlds.isResetting(entry.id())).thenReturn(true);
            case OTHER_OWNER -> { }
        }

        assertFalse(f.competition.canEditEntry(player, entry));
        assertFalse(f.competition.mayBuild(player, player.getLocation()));
        assertEquals(CompetitionModule.DetailsUpdateResult.ACCESS_DENIED,
                f.competition.saveSubmissionDetails(player, entry, "New title", "New description"));
        f.competition.setTitle(player, "New command title");
        f.competition.setDescription(player, "New command description");

        assertEquals("Original title", entry.title());
        assertEquals("Original description", entry.description());
        assertEquals(restriction == EditRestriction.SUBMITTED, entry.submitted());
        verify(f.store, never()).saveEntry(any());
    }

    @Test
    void cameraCommandsCannotChangeAnEntryDuringReset() throws Exception {
        Fixture f = new Fixture();
        Entry entry = f.entry(Category.JOURNEY, PARTICIPANT);
        CameraPose pose = new CameraPose(entry.worldName(), 10, 72, 10, 0, 0);
        entry.setCameraPose(1, pose);
        Player player = f.player("JavaBuilder");
        when(f.worlds.isResetting(entry.id())).thenReturn(true);

        assertFalse(f.competition.recordCamera(player));
        assertFalse(f.competition.recordCamera(player, 1));
        assertFalse(f.competition.removeCamera(player, 1));

        assertEquals(pose, entry.cameraPose(1).orElseThrow());
        verify(f.store, never()).saveEntry(any());
    }

    private enum EditRestriction {
        UNAUTHENTICATED, OTHER_OWNER, SUBMITTED, RESETTING
    }

    private final class Fixture {
        private final List<Entry> entries = new ArrayList<>();
        private final CompetitionStore store = mock(CompetitionStore.class);
        private final WorldModule worlds = mock(WorldModule.class);
        private final Map<UUID, VerifiedSession> sessions;
        private final CompetitionModule competition;
        private final World world = mock(World.class);

        @SuppressWarnings("unchecked")
        private Fixture() throws Exception {
            JavaPlugin plugin = mock(JavaPlugin.class);
            when(plugin.getName()).thenReturn("Hill175");
            when(plugin.namespace()).thenReturn("hill175");
            when(plugin.getDataFolder()).thenReturn(directory.toFile());
            when(plugin.getConfig()).thenReturn(new YamlConfiguration());
            when(plugin.getLogger()).thenReturn(Logger.getAnonymousLogger());
            Server server = mock(Server.class);
            when(plugin.getServer()).thenReturn(server);
            when(server.getOnlineMode()).thenReturn(true);
            when(server.getPluginManager()).thenReturn(mock(PluginManager.class));
            when(store.entries()).thenReturn(entries);
            when(world.getName()).thenReturn("hill_journey");
            competition = new CompetitionModule(plugin, store, worlds, mock(PasswordHasher.class),
                    mock(IdentityLinker.class), mock(MicrosoftSsoService.class));
            Field field = CompetitionModule.class.getDeclaredField("schoolSessions");
            field.setAccessible(true);
            Field authenticated = SsoPlayerSessions.class.getDeclaredField("sessions");
            authenticated.setAccessible(true);
            sessions = (Map<UUID, VerifiedSession>) authenticated.get(field.get(competition));
        }

        private Entry entry(Category category, String owner) {
            Entry entry = new Entry(UUID.randomUUID(), category, Set.of(owner), "hill_journey",
                    new BuildRegion("hill_journey", 0, 0, 0, 63, 127, 63), 0);
            entries.add(entry);
            return entry;
        }

        private Player player(String name) {
            Player player = mock(Player.class);
            when(player.getUniqueId()).thenReturn(UUID.randomUUID());
            when(player.getName()).thenReturn(name);
            when(player.getWorld()).thenReturn(world);
            when(player.getLocation()).thenReturn(new Location(world, 10, 70, 10));
            sessions.put(player.getUniqueId(), new VerifiedSession(PARTICIPANT,
                    "Student Name", Instant.now().plusSeconds(1800)));
            return player;
        }
    }
}
