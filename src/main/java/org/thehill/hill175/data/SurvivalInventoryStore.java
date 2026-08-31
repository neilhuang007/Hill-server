package org.thehill.hill175.data;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.configuration.InvalidConfigurationException;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.entity.Player;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Optional;
import java.util.Objects;
import java.util.UUID;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class SurvivalInventoryStore {
    private static final String INVENTORY_DIRECTORY = "survival-inventories";
    private static final String RESUME_INTENT_DIRECTORY = "survival-resume-intent";
    private static final String DEATH_PENDING_DIRECTORY = "survival-death-pending";
    private static final String RESUME_INTENT_CONTENT = "version: 1\nactive: true\n";
    private static final String DEATH_PENDING_CONTENT = "version: 1\ndeath-pending: true\n";

    private final Path inventoryDirectory;
    private final Path resumeIntentDirectory;
    private final Path deathPendingDirectory;
    private final Logger logger;

    public SurvivalInventoryStore(File dataFolder, Logger logger) {
        this(
                dataFolderPath(dataFolder).resolve(INVENTORY_DIRECTORY),
                dataFolderPath(dataFolder).resolve(RESUME_INTENT_DIRECTORY),
                dataFolderPath(dataFolder).resolve(DEATH_PENDING_DIRECTORY),
                logger
        );
    }

    public SurvivalInventoryStore(Path inventoryDirectory, Logger logger) {
        this(
                inventoryDirectory,
                Objects.requireNonNull(inventoryDirectory, "inventoryDirectory").resolve(RESUME_INTENT_DIRECTORY),
                inventoryDirectory.resolve(DEATH_PENDING_DIRECTORY),
                logger
        );
    }

    SurvivalInventoryStore(
            Path inventoryDirectory,
            Path resumeIntentDirectory,
            Path deathPendingDirectory,
            Logger logger
    ) {
        this.inventoryDirectory = Objects.requireNonNull(inventoryDirectory, "inventoryDirectory");
        this.resumeIntentDirectory = Objects.requireNonNull(resumeIntentDirectory, "resumeIntentDirectory");
        this.deathPendingDirectory = Objects.requireNonNull(deathPendingDirectory, "deathPendingDirectory");
        this.logger = logger == null ? Logger.getAnonymousLogger() : logger;
    }

    public synchronized void save(Player player) {
        save(player.getUniqueId(), SurvivalPlayerState.capture(player));
    }

    public synchronized void saveAfterDeath(Player player) {
        save(player.getUniqueId(), SurvivalPlayerState.captureAfterDeath(player));
    }

    public synchronized void save(UUID playerId, SurvivalPlayerState state) {
        writeAtomically(
                playerFile(playerId),
                Objects.requireNonNull(state, "state").toYaml().saveToString(),
                "Could not persist survival inventory for " + playerId
        );
    }

    public synchronized void markActive(UUID playerId) {
        writeAtomically(
                resumeIntentFile(playerId),
                RESUME_INTENT_CONTENT,
                "Could not persist survival resume intent for " + playerId
        );
    }

    public synchronized void markInactive(UUID playerId) {
        Path target = resumeIntentFile(playerId);
        try {
            Files.deleteIfExists(target);
        } catch (IOException exception) {
            logger.log(Level.SEVERE, "Could not clear survival resume intent for " + playerId, exception);
        }
    }

    public synchronized boolean isActive(UUID playerId) {
        return Files.isRegularFile(resumeIntentFile(playerId));
    }

    public synchronized void markDeathPending(UUID playerId) {
        writeAtomically(
                deathPendingFile(playerId),
                DEATH_PENDING_CONTENT,
                "Could not persist survival death state for " + playerId
        );
    }

    public synchronized void clearDeathPending(UUID playerId) {
        Path target = deathPendingFile(playerId);
        try {
            Files.deleteIfExists(target);
        } catch (IOException exception) {
            logger.log(Level.SEVERE, "Could not clear survival death state for " + playerId, exception);
        }
    }

    public synchronized boolean isDeathPending(UUID playerId) {
        return Files.isRegularFile(deathPendingFile(playerId));
    }

    private void writeAtomically(Path target, String content, String failureMessage) {
        Path temp = null;
        try {
            Path parent = target.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            temp = Files.createTempFile(parent, target.getFileName() + "-", ".tmp");
            Files.writeString(temp, content, StandardCharsets.UTF_8);
            try {
                Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException exception) {
                Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException exception) {
            logger.log(Level.SEVERE, failureMessage, exception);
        } finally {
            if (temp != null) {
                try {
                    Files.deleteIfExists(temp);
                } catch (IOException exception) {
                    logger.log(Level.WARNING, "Could not remove temporary survival persistence file " + temp, exception);
                }
            }
        }
    }

    public synchronized void restore(Player player) {
        load(player.getUniqueId()).orElseGet(SurvivalPlayerState::firstEntryDefaults).applyTo(player);
    }

    public synchronized Optional<SurvivalPlayerState> load(UUID playerId) {
        Path file = playerFile(playerId);
        if (!Files.isRegularFile(file)) {
            return Optional.empty();
        }
        YamlConfiguration yaml = new YamlConfiguration();
        try {
            yaml.loadFromString(Files.readString(file, StandardCharsets.UTF_8));
        } catch (IOException | InvalidConfigurationException exception) {
            logger.log(Level.WARNING, "Ignoring corrupt survival inventory file for " + playerId + ": " + file, exception);
            return Optional.empty();
        }
        Optional<SurvivalPlayerState> state = SurvivalPlayerState.fromYaml(yaml);
        if (state.isEmpty()) {
            logger.warning("Ignoring invalid survival inventory file for " + playerId + ": " + file);
        }
        return state;
    }

    public synchronized Optional<Location> lastLocation(Player player) {
        return load(player.getUniqueId())
                .flatMap(SurvivalPlayerState::location)
                .flatMap(location -> location.resolve(Bukkit::getWorld));
    }

    private Path playerFile(UUID playerId) {
        return inventoryDirectory.resolve(Objects.requireNonNull(playerId, "playerId") + ".yml");
    }

    private Path resumeIntentFile(UUID playerId) {
        return resumeIntentDirectory.resolve(Objects.requireNonNull(playerId, "playerId") + ".yml");
    }

    private Path deathPendingFile(UUID playerId) {
        return deathPendingDirectory.resolve(Objects.requireNonNull(playerId, "playerId") + ".yml");
    }

    private static Path dataFolderPath(File dataFolder) {
        return Objects.requireNonNull(dataFolder, "dataFolder").toPath();
    }
}
