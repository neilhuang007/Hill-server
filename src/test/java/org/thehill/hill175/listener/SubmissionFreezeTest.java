package org.thehill.hill175.listener;

import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.event.block.BlockFromToEvent;
import org.bukkit.event.block.BlockGrowEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.Test;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;

import java.time.Instant;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import static org.mockito.Mockito.*;

class SubmissionFreezeTest {
    private final CompetitionModule competition = mock(CompetitionModule.class);
    private final WorldModule worlds = mock(WorldModule.class);
    private final ServerListener listener = new ServerListener(mock(JavaPlugin.class), competition, mock(MenuModule.class), worlds);
    private final World world = mock(World.class);
    private final Block source = mock(Block.class);
    private final Block target = mock(Block.class);
    private final Entry entry = new Entry(UUID.randomUUID(), Category.JOURNEY, Set.of("builder"), "hill_journey",
            new BuildRegion("hill_journey", 0, 64, 0, 63, 110, 63), 0);

    private BlockFromToEvent flow() {
        when(world.getName()).thenReturn("hill_journey");
        Location location = new Location(world, 10, 65, 10);
        when(source.getWorld()).thenReturn(world);
        when(target.getWorld()).thenReturn(world);
        when(source.getLocation()).thenReturn(location);
        when(target.getLocation()).thenReturn(new Location(world, 11, 65, 10));
        when(competition.entryAt(location)).thenReturn(Optional.of(entry));
        BlockFromToEvent event = mock(BlockFromToEvent.class);
        when(event.getBlock()).thenReturn(source);
        when(event.getToBlock()).thenReturn(target);
        return event;
    }

    @Test void liquidsStopWhileImagesAreBeingCaptured() {
        BlockFromToEvent event = flow();
        when(competition.isPreparingSubmission(entry)).thenReturn(true);
        listener.onFluidFlow(event);
        verify(event).setCancelled(true);
    }

    @Test void submittedBuildsDoNotKeepGrowingBehindTheirPublishedImages() {
        flow();
        entry.submit(Instant.now());
        BlockGrowEvent event = mock(BlockGrowEvent.class);
        when(event.getBlock()).thenReturn(source);
        listener.onGrow(event);
        verify(event).setCancelled(true);
    }

    @Test void editableEntriesKeepNormalInternalFluidFlow() {
        BlockFromToEvent event = flow();
        listener.onFluidFlow(event);
        verify(event, never()).setCancelled(true);
    }

    @Test void fluidCannotEnterAGapInsideTheOverallAreaBounds() {
        BlockFromToEvent event = flow();
        entry.editableRegions(java.util.List.of(
                new BuildRegion("hill_journey", 0, 64, 0, 10, 110, 63),
                new BuildRegion("hill_journey", 20, 64, 0, 63, 110, 63)));
        listener.onFluidFlow(event);
        verify(event).setCancelled(true);
    }
}
