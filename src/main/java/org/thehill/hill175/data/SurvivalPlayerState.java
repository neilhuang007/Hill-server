package org.thehill.hill175.data;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.potion.PotionEffect;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

public final class SurvivalPlayerState {
    static final int STORAGE_SIZE = 36;
    static final int ARMOR_SIZE = 4;
    static final int DEFAULT_ENDER_CHEST_SIZE = 27;
    private static final int MAX_EFFECTS = 64;
    private static final int MAX_FIRE_TICKS = 20 * 60;

    private final List<ItemStack> storage;
    private final List<ItemStack> armor;
    private final ItemStack offhand;
    private final List<ItemStack> enderChest;
    private final List<PotionEffect> effects;
    private final int level;
    private final float exp;
    private final int totalExperience;
    private final int foodLevel;
    private final float saturation;
    private final float exhaustion;
    private final double health;
    private final int remainingAir;
    private final int fireTicks;
    private final SurvivalLocationSnapshot location;
    private final SurvivalLocationSnapshot respawnLocation;

    public SurvivalPlayerState(
            List<ItemStack> storage,
            List<ItemStack> armor,
            ItemStack offhand,
            List<ItemStack> enderChest,
            List<PotionEffect> effects,
            int level,
            float exp,
            int totalExperience,
            int foodLevel,
            float saturation,
            float exhaustion,
            double health,
            int remainingAir,
            int fireTicks,
            SurvivalLocationSnapshot location,
            SurvivalLocationSnapshot respawnLocation
    ) {
        this.storage = copyItems(storage, STORAGE_SIZE);
        this.armor = copyItems(armor, ARMOR_SIZE);
        this.offhand = cloneItem(offhand);
        this.enderChest = copyItems(enderChest, DEFAULT_ENDER_CHEST_SIZE);
        this.effects = List.copyOf(effects == null ? List.of() : effects.stream()
                .filter(PotionEffect.class::isInstance)
                .limit(MAX_EFFECTS)
                .toList());
        this.level = Math.max(0, level);
        this.exp = clamp(exp, 0.0f, 1.0f);
        this.totalExperience = Math.max(0, totalExperience);
        this.foodLevel = clamp(foodLevel, 0, 20);
        this.saturation = clamp(saturation, 0.0f, 20.0f);
        this.exhaustion = clamp(exhaustion, 0.0f, 40.0f);
        this.health = Double.isFinite(health) && health > 0.0 ? health : 20.0;
        this.remainingAir = Math.max(0, remainingAir);
        this.fireTicks = clamp(fireTicks, 0, MAX_FIRE_TICKS);
        this.location = location;
        this.respawnLocation = respawnLocation;
    }

    public static SurvivalPlayerState firstEntryDefaults() {
        return new SurvivalPlayerState(
                List.of(),
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
    }

    public static SurvivalPlayerState capture(Player player) {
        return new SurvivalPlayerState(
                Arrays.asList(player.getInventory().getStorageContents()),
                Arrays.asList(player.getInventory().getArmorContents()),
                player.getInventory().getItemInOffHand(),
                Arrays.asList(player.getEnderChest().getContents()),
                new ArrayList<>(player.getActivePotionEffects()),
                player.getLevel(),
                player.getExp(),
                player.getTotalExperience(),
                player.getFoodLevel(),
                player.getSaturation(),
                player.getExhaustion(),
                player.getHealth(),
                player.getRemainingAir(),
                player.getFireTicks(),
                SurvivalLocationSnapshot.from(player.getLocation()).orElse(null),
                SurvivalLocationSnapshot.from(player.getRespawnLocation(false)).orElse(null)
        );
    }

    /** Captures vanilla's post-death state without touching the already-created death drops. */
    public static SurvivalPlayerState captureAfterDeath(Player player) {
        SurvivalLocationSnapshot respawn = SurvivalLocationSnapshot.from(player.getRespawnLocation(false)).orElse(null);
        return new SurvivalPlayerState(
                List.of(),
                List.of(),
                null,
                Arrays.asList(player.getEnderChest().getContents()),
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
                respawn,
                respawn
        );
    }

    public void applyTo(Player player) {
        player.getInventory().clear();
        player.getInventory().setStorageContents(itemsForSize(storage, STORAGE_SIZE));
        player.getInventory().setArmorContents(itemsForSize(armor, ARMOR_SIZE));
        player.getInventory().setItemInOffHand(cloneItem(offhand));
        player.getEnderChest().clear();
        player.getEnderChest().setContents(itemsForSize(enderChest, player.getEnderChest().getSize()));
        for (PotionEffect effect : player.getActivePotionEffects()) {
            player.removePotionEffect(effect.getType());
        }
        for (PotionEffect effect : effects) {
            player.addPotionEffect(effect);
        }
        player.setLevel(level);
        player.setExp(exp);
        player.setTotalExperience(totalExperience);
        player.setFoodLevel(foodLevel);
        player.setSaturation(saturation);
        player.setExhaustion(exhaustion);
        if (player.getHealth() > 0.0) {
            player.setHealth(Math.min(player.getMaxHealth(), health));
        }
        player.setRemainingAir(Math.min(player.getMaximumAir(), remainingAir));
        player.setFireTicks(fireTicks);
        Optional<Location> respawn = respawnLocation == null
                ? Optional.empty()
                : respawnLocation.resolve(Bukkit::getWorld);
        player.setRespawnLocation(respawn.orElse(null), false);
    }

    public Optional<SurvivalLocationSnapshot> location() {
        return Optional.ofNullable(location);
    }

    public Optional<SurvivalLocationSnapshot> respawnLocation() {
        return Optional.ofNullable(respawnLocation);
    }

    public List<ItemStack> storage() {
        return copyItems(storage, STORAGE_SIZE);
    }

    public List<ItemStack> armor() {
        return copyItems(armor, ARMOR_SIZE);
    }

    public ItemStack offhand() {
        return cloneItem(offhand);
    }

    public List<ItemStack> enderChest() {
        return copyItems(enderChest, DEFAULT_ENDER_CHEST_SIZE);
    }

    public List<PotionEffect> effects() {
        return effects;
    }

    public int level() {
        return level;
    }

    public float exp() {
        return exp;
    }

    public int totalExperience() {
        return totalExperience;
    }

    public int foodLevel() {
        return foodLevel;
    }

    public float saturation() {
        return saturation;
    }

    public float exhaustion() {
        return exhaustion;
    }

    public double health() {
        return health;
    }

    public int remainingAir() {
        return remainingAir;
    }

    public int fireTicks() {
        return fireTicks;
    }

    YamlConfiguration toYaml() {
        YamlConfiguration yaml = new YamlConfiguration();
        yaml.set("version", 1);
        yaml.set("inventory.storage", storage);
        yaml.set("inventory.armor", armor);
        yaml.set("inventory.offhand", offhand);
        yaml.set("ender-chest", enderChest);
        yaml.set("effects", effects);
        yaml.set("experience.level", level);
        yaml.set("experience.progress", (double) exp);
        yaml.set("experience.total", totalExperience);
        yaml.set("vitals.food", foodLevel);
        yaml.set("vitals.saturation", (double) saturation);
        yaml.set("vitals.exhaustion", (double) exhaustion);
        yaml.set("vitals.health", health);
        yaml.set("vitals.remaining-air", remainingAir);
        yaml.set("vitals.fire-ticks", fireTicks);
        writeLocation(yaml, "location", location);
        writeLocation(yaml, "respawn-location", respawnLocation);
        return yaml;
    }

    static Optional<SurvivalPlayerState> fromYaml(YamlConfiguration yaml) {
        if (yaml == null) {
            return Optional.empty();
        }
        try {
            return Optional.of(new SurvivalPlayerState(
                    readItems(yaml, "inventory.storage", STORAGE_SIZE),
                    readItems(yaml, "inventory.armor", ARMOR_SIZE),
                    readItem(yaml, "inventory.offhand"),
                    readItems(yaml, "ender-chest", DEFAULT_ENDER_CHEST_SIZE),
                    readEffects(yaml),
                    yaml.getInt("experience.level", 0),
                    (float) yaml.getDouble("experience.progress", 0.0),
                    yaml.getInt("experience.total", 0),
                    yaml.getInt("vitals.food", 20),
                    (float) yaml.getDouble("vitals.saturation", 5.0),
                    (float) yaml.getDouble("vitals.exhaustion", 0.0),
                    yaml.getDouble("vitals.health", 20.0),
                    yaml.getInt("vitals.remaining-air", 300),
                    yaml.getInt("vitals.fire-ticks", 0),
                    readLocation(yaml, "location").orElse(null),
                    readLocation(yaml, "respawn-location").orElse(null)
            ));
        } catch (IllegalArgumentException exception) {
            return Optional.empty();
        }
    }

    private static void writeLocation(YamlConfiguration yaml, String path, SurvivalLocationSnapshot location) {
        if (location == null) {
            return;
        }
        yaml.set(path + ".world", location.worldName());
        yaml.set(path + ".x", location.x());
        yaml.set(path + ".y", location.y());
        yaml.set(path + ".z", location.z());
        yaml.set(path + ".yaw", (double) location.yaw());
        yaml.set(path + ".pitch", (double) location.pitch());
    }

    private static Optional<SurvivalLocationSnapshot> readLocation(YamlConfiguration yaml, String path) {
        ConfigurationSection section = yaml.getConfigurationSection(path);
        if (section == null) {
            return Optional.empty();
        }
        String world = section.getString("world", "");
        double x = section.getDouble("x", Double.NaN);
        double y = section.getDouble("y", Double.NaN);
        double z = section.getDouble("z", Double.NaN);
        float yaw = (float) section.getDouble("yaw", 0.0);
        float pitch = (float) section.getDouble("pitch", 0.0);
        if (world.isBlank() || !Double.isFinite(x) || !Double.isFinite(y) || !Double.isFinite(z)
                || !Float.isFinite(yaw) || !Float.isFinite(pitch)) {
            return Optional.empty();
        }
        return Optional.of(new SurvivalLocationSnapshot(world, x, y, z, yaw, pitch));
    }

    private static List<ItemStack> readItems(YamlConfiguration yaml, String path, int size) {
        List<ItemStack> items = new ArrayList<>(size);
        List<?> values = yaml.getList(path, List.of());
        for (int index = 0; index < size; index++) {
            Object value = index < values.size() ? values.get(index) : null;
            items.add(value instanceof ItemStack item ? item.clone() : null);
        }
        return items;
    }

    private static ItemStack readItem(YamlConfiguration yaml, String path) {
        Object value = yaml.get(path);
        return value instanceof ItemStack item ? item.clone() : null;
    }

    private static List<PotionEffect> readEffects(YamlConfiguration yaml) {
        List<PotionEffect> result = new ArrayList<>();
        for (Object value : yaml.getList("effects", List.of())) {
            if (value instanceof PotionEffect effect) {
                result.add(effect);
                if (result.size() >= MAX_EFFECTS) {
                    break;
                }
            }
        }
        return result;
    }

    private static List<ItemStack> copyItems(List<ItemStack> source, int size) {
        List<ItemStack> result = new ArrayList<>(size);
        List<ItemStack> safeSource = source == null ? List.of() : source;
        for (int index = 0; index < size; index++) {
            ItemStack item = index < safeSource.size() ? safeSource.get(index) : null;
            result.add(cloneItem(item));
        }
        return result;
    }

    private static ItemStack[] itemsForSize(List<ItemStack> source, int size) {
        ItemStack[] result = new ItemStack[size];
        for (int index = 0; index < size && index < source.size(); index++) {
            result[index] = cloneItem(source.get(index));
        }
        return result;
    }

    private static ItemStack cloneItem(ItemStack item) {
        return item == null ? null : item.clone();
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private static float clamp(float value, float min, float max) {
        if (!Float.isFinite(value)) {
            return min;
        }
        return Math.max(min, Math.min(max, value));
    }
}
