package org.thehill.hill175.data;

import org.bukkit.configuration.ConfigurationSection;
import org.bukkit.configuration.file.YamlConfiguration;
import org.thehill.hill175.model.Account;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Category;
import org.thehill.hill175.model.Entry;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class YamlCompetitionStore implements CompetitionStore {
    private final File file;
    private final Logger logger;
    private final Map<String, Account> accounts = new LinkedHashMap<>();
    private final Map<UUID, Entry> entries = new LinkedHashMap<>();
    private final Map<Category, Integer> allocationCounters = new EnumMap<>(Category.class);
    private final ArrayList<Map<String, Object>> connectionAudit = new ArrayList<>();

    public YamlCompetitionStore(File dataFolder, Logger logger) {
        this.file = new File(dataFolder, "competition-data.yml");
        this.logger = logger;
        load();
    }

    @Override
    public synchronized Optional<Account> account(String nicknameKey) {
        return Optional.ofNullable(accounts.get(nicknameKey));
    }

    @Override
    public synchronized void saveAccount(Account account) {
        accounts.put(account.nicknameKey(), account);
        flush();
    }

    @Override
    public synchronized Optional<Entry> entry(UUID id) {
        return Optional.ofNullable(entries.get(id));
    }

    @Override
    public synchronized Collection<Entry> entries() {
        return new ArrayList<>(entries.values());
    }

    @Override
    public synchronized void saveEntry(Entry entry) {
        entries.put(entry.id(), entry);
        flush();
    }

    @Override
    public synchronized void deleteEntry(UUID id) {
        entries.remove(id);
        flush();
    }

    @Override
    public synchronized int nextAllocation(Category category) {
        int next = allocationCounters.getOrDefault(category, 0);
        allocationCounters.put(category, next + 1);
        flush();
        return next;
    }

    @Override
    public synchronized void recordConnection(String nicknameKey, String address, String event) {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("nickname-key", nicknameKey);
        record.put("address", address);
        record.put("event", event);
        record.put("at", Instant.now().toString());
        connectionAudit.add(record);
        if (connectionAudit.size() > 20_000) {
            connectionAudit.removeFirst();
        }
        flush();
    }

    @Override
    public synchronized void flush() {
        YamlConfiguration yaml = new YamlConfiguration();
        for (Account account : accounts.values()) {
            String path = "accounts." + account.nicknameKey();
            yaml.set(path + ".nickname", account.nickname());
            yaml.set(path + ".school-identity", account.schoolIdentity());
            yaml.set(path + ".display-name", account.displayName());
            yaml.set(path + ".password-salt", account.passwordSalt());
            yaml.set(path + ".password-hash", account.passwordHash());
            yaml.set(path + ".password-iterations", account.passwordIterations());
            yaml.set(path + ".registered-at", account.registeredAt().toString());
        }
        for (Entry entry : entries.values()) {
            String path = "entries." + entry.id();
            yaml.set(path + ".category", entry.category().name());
            yaml.set(path + ".members", new ArrayList<>(entry.members()));
            yaml.set(path + ".world", entry.worldName());
            yaml.set(path + ".allocation-index", entry.allocationIndex());
            yaml.set(path + ".title", entry.title());
            yaml.set(path + ".description", entry.description());
            yaml.set(path + ".submitted", entry.submitted());
            yaml.set(path + ".submitted-at", entry.submittedAt() == null ? null : entry.submittedAt().toString());
            writeRegion(yaml, path + ".region", entry.region());
            for (int slot : entry.savedCameraSlots()) {
                entry.cameraPose(slot).ifPresent(pose -> writeCamera(yaml, path + ".cameras." + (slot - 1), pose));
            }
        }
        for (Map.Entry<Category, Integer> counter : allocationCounters.entrySet()) {
            yaml.set("allocation-counters." + counter.getKey().name(), counter.getValue());
        }
        yaml.set("connection-audit", new ArrayList<>(connectionAudit));

        File parent = file.getParentFile();
        if (!parent.exists() && !parent.mkdirs()) {
            logger.severe("Could not create plugin data directory: " + parent);
            return;
        }
        File temporary = new File(parent, file.getName() + ".tmp");
        try {
            yaml.save(temporary);
            try {
                Files.move(
                        temporary.toPath(),
                        file.toPath(),
                        StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE
                );
            } catch (IOException atomicMoveFailure) {
                Files.move(temporary.toPath(), file.toPath(), StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException exception) {
            logger.log(Level.SEVERE, "Could not persist competition data", exception);
        }
    }

    private void load() {
        if (!file.exists()) {
            return;
        }
        YamlConfiguration yaml = YamlConfiguration.loadConfiguration(file);
        ConfigurationSection accountSection = yaml.getConfigurationSection("accounts");
        if (accountSection != null) {
            for (String nicknameKey : accountSection.getKeys(false)) {
                String path = "accounts." + nicknameKey;
                Account account = new Account(
                        nicknameKey,
                        yaml.getString(path + ".nickname", nicknameKey),
                        yaml.getString(path + ".school-identity", "stub:" + nicknameKey),
                        yaml.getString(path + ".display-name", nicknameKey),
                        yaml.getString(path + ".password-salt", ""),
                        yaml.getString(path + ".password-hash", ""),
                        yaml.getInt(path + ".password-iterations", 310_000),
                        parseInstant(yaml.getString(path + ".registered-at"))
                );
                accounts.put(nicknameKey, account);
            }
        }

        ConfigurationSection entrySection = yaml.getConfigurationSection("entries");
        if (entrySection != null) {
            for (String rawId : entrySection.getKeys(false)) {
                try {
                    UUID id = UUID.fromString(rawId);
                    String path = "entries." + rawId;
                    Category category = Category.valueOf(yaml.getString(path + ".category", "JOURNEY"));
                    Set<String> members = new LinkedHashSet<>(yaml.getStringList(path + ".members"));
                    BuildRegion region = readRegion(yaml, path + ".region");
                    Entry entry = new Entry(
                            id,
                            category,
                            members,
                            yaml.getString(path + ".world", region.worldName()),
                            region,
                            yaml.getInt(path + ".allocation-index")
                    );
                    entry.title(yaml.getString(path + ".title", ""));
                    entry.description(yaml.getString(path + ".description", ""));
                    ConfigurationSection cameras = yaml.getConfigurationSection(path + ".cameras");
                    if (cameras != null) {
                        for (String key : cameras.getKeys(false)) {
                            try {
                                int slot = Integer.parseInt(key) + 1;
                                if (!entry.setCameraPose(slot, readCamera(yaml, path + ".cameras." + key))) {
                                    logger.warning("Skipping out-of-range camera slot " + key + " for entry " + rawId);
                                }
                            } catch (NumberFormatException exception) {
                                logger.warning("Skipping malformed camera slot " + key + " for entry " + rawId);
                            }
                        }
                    }
                    if (yaml.getBoolean(path + ".submitted")) {
                        entry.submit(parseInstant(yaml.getString(path + ".submitted-at")));
                    }
                    entries.put(id, entry);
                } catch (IllegalArgumentException exception) {
                    logger.log(Level.WARNING, "Skipping malformed entry " + rawId, exception);
                }
            }
        }

        ConfigurationSection counters = yaml.getConfigurationSection("allocation-counters");
        if (counters != null) {
            for (Category category : Category.values()) {
                allocationCounters.put(category, counters.getInt(category.name(), 0));
            }
        }
        for (Map<?, ?> rawRecord : yaml.getMapList("connection-audit")) {
            Map<String, Object> record = new LinkedHashMap<>();
            rawRecord.forEach((key, value) -> record.put(String.valueOf(key), value));
            connectionAudit.add(record);
        }
    }

    private static void writeRegion(YamlConfiguration yaml, String path, BuildRegion region) {
        yaml.set(path + ".world", region.worldName());
        yaml.set(path + ".min-x", region.minX());
        yaml.set(path + ".min-y", region.minY());
        yaml.set(path + ".min-z", region.minZ());
        yaml.set(path + ".max-x", region.maxX());
        yaml.set(path + ".max-y", region.maxY());
        yaml.set(path + ".max-z", region.maxZ());
    }

    private static BuildRegion readRegion(YamlConfiguration yaml, String path) {
        return new BuildRegion(
                yaml.getString(path + ".world", "hill_journey"),
                yaml.getInt(path + ".min-x"),
                yaml.getInt(path + ".min-y"),
                yaml.getInt(path + ".min-z"),
                yaml.getInt(path + ".max-x"),
                yaml.getInt(path + ".max-y"),
                yaml.getInt(path + ".max-z")
        );
    }

    private static void writeCamera(YamlConfiguration yaml, String path, CameraPose pose) {
        yaml.set(path + ".world", pose.worldName());
        yaml.set(path + ".x", pose.x());
        yaml.set(path + ".y", pose.y());
        yaml.set(path + ".z", pose.z());
        yaml.set(path + ".yaw", pose.yaw());
        yaml.set(path + ".pitch", pose.pitch());
    }

    private static CameraPose readCamera(YamlConfiguration yaml, String path) {
        return new CameraPose(
                yaml.getString(path + ".world", "hill_journey"),
                yaml.getDouble(path + ".x"),
                yaml.getDouble(path + ".y"),
                yaml.getDouble(path + ".z"),
                (float) yaml.getDouble(path + ".yaw"),
                (float) yaml.getDouble(path + ".pitch")
        );
    }

    private static Instant parseInstant(String raw) {
        if (raw == null || raw.isBlank()) {
            return Instant.now();
        }
        try {
            return Instant.parse(raw);
        } catch (DateTimeParseException ignored) {
            return Instant.now();
        }
    }
}
