package org.thehill.hill175.data;

import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.inventory.ItemStack;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SurvivalPlayerStateTest {
    @Test
    void roundTripsScalarStateThroughYaml() throws Exception {
        SurvivalLocationSnapshot location = new SurvivalLocationSnapshot("hill_survival", 10.5, 65.0, -22.25, 90.0f, 12.5f);
        SurvivalLocationSnapshot respawn = new SurvivalLocationSnapshot("hill_survival_nether", 1.0, 70.0, 2.0, 180.0f, 0.0f);
        SurvivalPlayerState state = new SurvivalPlayerState(
                List.of(),
                List.of(),
                null,
                List.of(),
                List.of(),
                7,
                0.45f,
                128,
                13,
                4.5f,
                1.25f,
                16.0,
                120,
                80,
                location,
                respawn
        );

        YamlConfiguration reloaded = new YamlConfiguration();
        reloaded.loadFromString(state.toYaml().saveToString());
        SurvivalPlayerState parsed = SurvivalPlayerState.fromYaml(reloaded).orElseThrow();

        assertEquals(SurvivalPlayerState.STORAGE_SIZE, parsed.storage().size());
        assertEquals(SurvivalPlayerState.ARMOR_SIZE, parsed.armor().size());
        assertEquals(SurvivalPlayerState.DEFAULT_ENDER_CHEST_SIZE, parsed.enderChest().size());
        assertNull(parsed.offhand());
        assertEquals(0, parsed.effects().size());
        assertEquals(7, parsed.level());
        assertEquals(0.45f, parsed.exp());
        assertEquals(128, parsed.totalExperience());
        assertEquals(13, parsed.foodLevel());
        assertEquals(4.5f, parsed.saturation());
        assertEquals(1.25f, parsed.exhaustion());
        assertEquals(16.0, parsed.health());
        assertEquals(120, parsed.remainingAir());
        assertEquals(80, parsed.fireTicks());
        assertEquals(location, parsed.location().orElseThrow());
        assertEquals(respawn, parsed.respawnLocation().orElseThrow());
    }

    @Test
    void clampsInvalidScalarsAndDropsInvalidLocationsOrItems() {
        YamlConfiguration yaml = new YamlConfiguration();
        yaml.set("inventory.storage", List.of("not an item"));
        yaml.set("experience.level", -5);
        yaml.set("experience.progress", 99.0);
        yaml.set("experience.total", -100);
        yaml.set("vitals.food", 40);
        yaml.set("vitals.saturation", Double.NaN);
        yaml.set("vitals.exhaustion", 100.0);
        yaml.set("vitals.health", -1.0);
        yaml.set("vitals.remaining-air", -10);
        yaml.set("vitals.fire-ticks", 999_999);
        yaml.set("location.world", "");
        yaml.set("location.x", Double.NaN);

        SurvivalPlayerState parsed = SurvivalPlayerState.fromYaml(yaml).orElseThrow();

        assertNull(parsed.storage().get(0));
        assertEquals(0, parsed.level());
        assertEquals(1.0f, parsed.exp());
        assertEquals(0, parsed.totalExperience());
        assertEquals(20, parsed.foodLevel());
        assertEquals(0.0f, parsed.saturation());
        assertEquals(40.0f, parsed.exhaustion());
        assertEquals(20.0, parsed.health());
        assertEquals(0, parsed.remainingAir());
        assertEquals(20 * 60, parsed.fireTicks());
        assertFalse(parsed.location().isPresent());
    }

    @Test
    void defensivelyCopiesMutableItemStacks() {
        List<ItemStack> storage = emptyItems(SurvivalPlayerState.STORAGE_SIZE);
        ItemStack original = mock(ItemStack.class);
        ItemStack storedCopy = mock(ItemStack.class);
        ItemStack returnedCopy = mock(ItemStack.class);
        when(original.clone()).thenReturn(storedCopy);
        when(storedCopy.clone()).thenReturn(returnedCopy);
        storage.set(0, original);

        SurvivalPlayerState state = new SurvivalPlayerState(
                storage,
                List.of(),
                null,
                List.of(),
                List.of(),
                0,
                0.0f,
                0,
                20,
                5.0f,
                0.0f,
                20.0,
                300,
                0,
                null,
                null
        );

        assertNotSame(original, state.storage().get(0));
        assertSame(returnedCopy, state.storage().get(0));
    }

    private static List<ItemStack> emptyItems(int size) {
        return new ArrayList<>(java.util.Collections.nCopies(size, null));
    }
}
