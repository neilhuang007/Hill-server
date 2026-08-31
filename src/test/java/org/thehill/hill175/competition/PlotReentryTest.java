package org.thehill.hill175.competition;

import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.model.Account;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.world.WorldModule;

import java.lang.reflect.Field;
import java.nio.file.Path;
import java.util.Collection;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class PlotReentryTest {
    private static final UUID PLAYER_ID = UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final UUID ENTRY_ID = UUID.fromString("00000000-0000-0000-0000-000000000002");

    @TempDir
    Path tempDir;

    @Test
    void restoresCreativeModeWhenOwnerReentersWithAnAlreadyActiveOwnerKit() throws Exception {
        World buildWorld = mock(World.class);
        when(buildWorld.getName()).thenReturn("hill_journey");
        Entry entry = new Entry(
                ENTRY_ID,
                Category.JOURNEY,
                Set.of("builder"),
                "hill_journey",
                new BuildRegion("hill_journey", 0, 0, 0, 63, 63, 63),
                0
        );

        JavaPlugin plugin = mock(JavaPlugin.class);
        when(plugin.getName()).thenReturn("Hill175");
        when(plugin.namespace()).thenReturn("hill175");
        when(plugin.getDataFolder()).thenReturn(tempDir.toFile());
        FileConfiguration config = mock(FileConfiguration.class);
        when(plugin.getConfig()).thenReturn(config);
        WorldModule worlds = mock(WorldModule.class);
        when(worlds.isResetting(ENTRY_ID)).thenReturn(false);

        CompetitionModule competition = new CompetitionModule(
                plugin,
                new SingleEntryStore(entry),
                worlds,
                mock(PasswordHasher.class),
                mock(IdentityLinker.class)
        );

        AtomicReference<GameMode> mode = new AtomicReference<>(GameMode.SPECTATOR);
        Player player = mock(Player.class);
        when(player.getUniqueId()).thenReturn(PLAYER_ID);
        when(player.getName()).thenReturn("Builder");
        when(player.getGameMode()).thenAnswer(ignored -> mode.get());
        doAnswer(invocation -> {
            mode.set(invocation.getArgument(0));
            return null;
        }).when(player).setGameMode(any(GameMode.class));

        authenticatedSessions(competition).add(PLAYER_ID);
        activeKits(competition).put(PLAYER_ID, "owner:" + ENTRY_ID);

        competition.refreshMovementMode(player, new Location(buildWorld, 1.5, 2.0, 1.5));

        assertEquals(
                GameMode.CREATIVE,
                mode.get(),
                "crossing back into an editable owned plot must restore Owner Mode even when the owner kit is unchanged"
        );
    }

    @SuppressWarnings("unchecked")
    private static Set<UUID> authenticatedSessions(CompetitionModule competition) throws Exception {
        Field field = CompetitionModule.class.getDeclaredField("authenticatedSessions");
        field.setAccessible(true);
        return (Set<UUID>) field.get(competition);
    }

    @SuppressWarnings("unchecked")
    private static Map<UUID, String> activeKits(CompetitionModule competition) throws Exception {
        Field field = CompetitionModule.class.getDeclaredField("activeKitByPlayer");
        field.setAccessible(true);
        return (Map<UUID, String>) field.get(competition);
    }

    private record SingleEntryStore(Entry entry) implements CompetitionStore {
        @Override
        public Optional<Account> account(String nicknameKey) {
            return Optional.empty();
        }

        @Override
        public void saveAccount(Account account) {
        }

        @Override
        public Optional<Entry> entry(UUID id) {
            return entry.id().equals(id) ? Optional.of(entry) : Optional.empty();
        }

        @Override
        public Collection<Entry> entries() {
            return Set.of(entry);
        }

        @Override
        public void saveEntry(Entry entry) {
        }

        @Override
        public void deleteEntry(UUID id) {
        }

        @Override
        public int nextAllocation(Category category) {
            return 0;
        }

        @Override
        public void recordConnection(String nicknameKey, String address, String event) {
        }

        @Override
        public void flush() {
        }
    }
}
