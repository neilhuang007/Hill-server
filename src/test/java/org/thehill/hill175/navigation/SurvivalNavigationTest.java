package org.thehill.hill175.navigation;

import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.auth.GameIdentityResolver;

import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

class SurvivalNavigationTest {
    @Test
    void localTravelRequiresAuthentication() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        when(plugin.getConfig()).thenReturn(new YamlConfiguration());
        Player player = mock(Player.class);
        @SuppressWarnings("unchecked") Consumer<Player> local = mock(Consumer.class);
        new SurvivalNavigation(plugin, candidate -> false, local).travel(player);
        verifyNoInteractions(local);
        verify(player, never()).transfer(anyString(), anyInt());
        new SurvivalNavigation(plugin, candidate -> true, local).travel(player);
        verify(local).accept(player);
    }

    @Test
    void disabledSurvivalDoesNotTransferOrTeleport() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        YamlConfiguration config = new YamlConfiguration();
        config.set("survival-navigation.mode", "disabled");
        when(plugin.getConfig()).thenReturn(config);
        Player player = mock(Player.class);
        @SuppressWarnings("unchecked") Consumer<Player> local = mock(Consumer.class);
        new SurvivalNavigation(plugin, candidate -> true, local).travel(player);
        verifyNoInteractions(local);
        verify(player, never()).transfer(anyString(), anyInt());
    }

    @Test
    void transferKeepsBedrockLocalAndSendsOnlyJavaToIndependentServer() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        YamlConfiguration config = new YamlConfiguration();
        config.set("survival-navigation.mode", "transfer");
        config.set("survival-navigation.java-host", "survival.example.org");
        config.set("survival-navigation.destination-access-configured", true);
        when(plugin.getConfig()).thenReturn(config);
        Player javaPlayer = mock(Player.class);
        Player bedrockPlayer = mock(Player.class);
        @SuppressWarnings("unchecked") Consumer<Player> local = mock(Consumer.class);
        try (var resolvers = mockConstruction(GameIdentityResolver.class, (resolver, context) -> {
            when(resolver.resolve(javaPlayer)).thenReturn("java:verified");
            when(resolver.resolve(bedrockPlayer)).thenReturn("bedrock:1234");
        })) {
            SurvivalNavigation navigation = new SurvivalNavigation(plugin, candidate -> true, local);
            navigation.travel(bedrockPlayer);
            verify(local).accept(bedrockPlayer);
            verify(bedrockPlayer, never()).transfer(anyString(), anyInt());
            navigation.travel(javaPlayer);
            verify(javaPlayer).transfer("survival.example.org", 25567);
            verify(local, never()).accept(javaPlayer);
            when(resolvers.constructed().getFirst().resolve(javaPlayer)).thenThrow(new IllegalStateException());
            navigation.travel(javaPlayer);
            verify(javaPlayer, times(1)).transfer(anyString(), anyInt());
        }
    }

    @Test
    void transferFailsClosedUntilDestinationAdmissionIsConfigured() {
        JavaPlugin plugin = mock(JavaPlugin.class);
        YamlConfiguration config = new YamlConfiguration();
        config.set("survival-navigation.mode", "transfer");
        config.set("survival-navigation.java-host", "survival.example.org");
        when(plugin.getConfig()).thenReturn(config);
        assertThrows(IllegalArgumentException.class,
                () -> new SurvivalNavigation(plugin, candidate -> true, player -> {}));
    }
}
