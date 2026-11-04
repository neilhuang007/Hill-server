package org.thehill.hill175.command;

import org.bukkit.command.Command;
import org.bukkit.entity.Player;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.ui.MenuModule;

import java.util.Optional;

import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CommandModuleTest {
    private final CompetitionModule competition = mock(CompetitionModule.class);
    private final MenuModule menus = mock(MenuModule.class);
    private final Player player = mock(Player.class);
    private final CommandModule commands = new CommandModule(competition, menus);

    private void run(String commandName, String... args) {
        Command command = mock(Command.class);
        when(command.getName()).thenReturn(commandName);
        when(competition.isAuthenticated(player)).thenReturn(true);
        commands.onCommand(player, command, commandName, args);
    }

    @Test
    void previewUsesTheRequestedSlotInsteadOfCyclingToAnotherView() {
        Entry entry = mock(Entry.class);
        when(competition.currentEntry(player)).thenReturn(Optional.of(entry));
        run("camera", "preview", "2");
        verify(competition).previewCamera(player, entry, 2);
        verify(competition, never()).previewNextCamera(player);
    }

    @Test
    void replacingOrRemovingACameraGoesThroughConfirmation() {
        run("camera", "save", "2");
        run("camera", "remove", "2");
        verify(menus).requestCameraSave(player, 2);
        verify(menus).requestCameraRemove(player, 2);
        verify(competition, never()).recordCamera(player, 2);
        verify(competition, never()).removeCamera(player, 2);
    }

    @Test
    void placeCreationStartsWithTheHeldBuildingMap() {
        run("entry", "create", "place");
        verify(menus).openCategory(player, Category.PLACE);
        verify(competition, never()).createEntry(any(), any());
    }

    @Test
    void registrationRequiresOnlyThePasswordAndConfirmation() {
        run("register", "testPassword", "testPassword");
        verify(competition).register(player, "testPassword", "testPassword");
        verify(competition, never()).register(any(), anyString(), anyString(), anyString());
    }

    @Test
    void legacyRegistrationStillValidatesTheSuppliedNickname() {
        run("register", ".BedrockBuilder", "testPassword", "testPassword");
        verify(competition).register(player, ".BedrockBuilder", "testPassword", "testPassword");
    }

    @Test
    void authenticationNeverOffersCredentialOrPlayerNameCompletion() {
        for (String commandName : new String[]{"register", "login", "verify"}) {
            Command command = mock(Command.class);
            when(command.getName()).thenReturn(commandName);
            assertTrue(commands.onTabComplete(player, command, commandName, new String[]{""}).isEmpty());
            assertTrue(commands.onTabComplete(player, command, commandName, new String[]{"secret", ""}).isEmpty());
        }
    }
}
