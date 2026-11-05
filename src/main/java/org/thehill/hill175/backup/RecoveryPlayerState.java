package org.thehill.hill175.backup;

import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Base64;
import java.util.Properties;

/** Paper's native item codec preserves exact player contents across preview cancellation or a crash. */
record RecoveryPlayerState(Properties values) {
    static RecoveryPlayerState capture(Player player) {
        Properties p = new Properties();
        p.setProperty("inventory", Base64.getEncoder().encodeToString(ItemStack.serializeItemsAsBytes(player.getInventory().getContents())));
        p.setProperty("held", Integer.toString(player.getInventory().getHeldItemSlot()));
        p.setProperty("mode", player.getGameMode().name());
        p.setProperty("flight", Boolean.toString(player.getAllowFlight()));
        p.setProperty("flying", Boolean.toString(player.isFlying()));
        p.setProperty("gravity", Boolean.toString(player.hasGravity()));
        Location l = player.getLocation();
        p.setProperty("world", l.getWorld().getName());
        p.setProperty("x", Double.toString(l.getX())); p.setProperty("y", Double.toString(l.getY())); p.setProperty("z", Double.toString(l.getZ()));
        p.setProperty("yaw", Float.toString(l.getYaw())); p.setProperty("pitch", Float.toString(l.getPitch()));
        return new RecoveryPlayerState(p);
    }
    void save(Path path) throws IOException { BackupFiles.writeProperties(path, values); }
    static RecoveryPlayerState read(Path path) throws IOException { return new RecoveryPlayerState(BackupFiles.readProperties(path)); }
    Location location() {
        var world = Bukkit.getWorld(values.getProperty("world"));
        if (world == null) throw new IllegalStateException("The return world is not available.");
        return new Location(world, Double.parseDouble(values.getProperty("x")), Double.parseDouble(values.getProperty("y")),
                Double.parseDouble(values.getProperty("z")), Float.parseFloat(values.getProperty("yaw")), Float.parseFloat(values.getProperty("pitch")));
    }
    void applyInventory(Player player) {
        player.getInventory().setContents(ItemStack.deserializeItemsFromBytes(Base64.getDecoder().decode(values.getProperty("inventory"))));
        player.getInventory().setHeldItemSlot(Integer.parseInt(values.getProperty("held")));
    }
    void apply(Player player) {
        applyInventory(player);
        player.setGameMode(GameMode.valueOf(values.getProperty("mode")));
        player.setAllowFlight(Boolean.parseBoolean(values.getProperty("flight")));
        player.setFlying(player.getAllowFlight() && Boolean.parseBoolean(values.getProperty("flying")));
        player.setGravity(Boolean.parseBoolean(values.getProperty("gravity")));
        player.setFallDistance(0);
    }
}
