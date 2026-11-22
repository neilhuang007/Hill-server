package org.thehill.hill175.blueprint;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.plugin.java.JavaPlugin;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class BlueprintBackups {
    private final JavaPlugin plugin;
    private final BlueprintBackupStore snapshots;

    public BlueprintBackups(JavaPlugin plugin) throws IOException {
        this.plugin = plugin;
        snapshots = new BlueprintBackupStore(plugin.getServer().getWorldContainer().toPath().resolve("blueprint-backups"));
    }

    public String capture(World blueprint, String reason) throws IOException {
        if (!Bukkit.isPrimaryThread()) throw new IllegalStateException("Backups require the server thread.");
        blueprint.save(true);
        Map<String, Path> sources = new LinkedHashMap<>();
        Path actualWorld = blueprint.getWorldFolder().toPath();
        BlueprintWorldFiles.validateWorld(actualWorld);
        sources.put("canonical", actualWorld);
        Path state = plugin.getDataFolder().toPath().resolve("blueprint");
        for (String name : List.of("current.properties", "branches", "submissions", "operations", "submission-baselines")) {
            Path source = state.resolve(name);
            if (Files.exists(source)) sources.put(name, source);
        }
        long started = System.nanoTime();
        String id = snapshots.capture(sources, reason);
        plugin.getLogger().info("Blueprint-only recovery snapshot " + id + " completed in "
                + ((System.nanoTime() - started) / 1_000_000) + " ms. Canonical source: " + actualWorld);
        return id;
    }

    public List<String> list() throws IOException { return snapshots.list(); }
}
