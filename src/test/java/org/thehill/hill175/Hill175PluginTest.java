package org.thehill.hill175;

import org.bukkit.Server;
import org.junit.jupiter.api.Test;

import java.util.logging.Logger;

import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class Hill175PluginTest {
    @Test
    void startupFailureStopsPaperInsteadOfLeavingAdmissionUnprotected() {
        Hill175Plugin plugin = mock(Hill175Plugin.class, CALLS_REAL_METHODS);
        Server server = mock(Server.class);
        when(plugin.getServer()).thenReturn(server);
        when(plugin.getLogger()).thenReturn(mock(Logger.class));
        doThrow(new IllegalStateException("Invalid authentication configuration"))
                .when(plugin).saveDefaultConfig();

        plugin.onEnable();

        verify(server).shutdown();
    }
}
