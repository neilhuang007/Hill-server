package org.thehill.hill175;

import org.bukkit.Bukkit;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.Mob;
import org.bukkit.entity.Player;
import org.bukkit.plugin.PluginManager;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.auth.IdentityLinker;
import org.thehill.hill175.auth.IdentityLinkerFactory;
import org.thehill.hill175.auth.PasswordHasher;
import org.thehill.hill175.access.AccessControl;
import org.thehill.hill175.auth.sso.MicrosoftSsoService;
import org.thehill.hill175.auth.sso.SsoConfig;
import org.thehill.hill175.command.CommandModule;
import org.thehill.hill175.competition.CompetitionModule;
import org.thehill.hill175.data.CompetitionStore;
import org.thehill.hill175.data.YamlCompetitionStore;
import org.thehill.hill175.listener.ServerListener;
import org.thehill.hill175.ui.HubNpcModule;
import org.thehill.hill175.ui.MenuModule;
import org.thehill.hill175.world.WorldModule;
import org.thehill.hill175.gallery.GalleryHttpServer;
import org.thehill.hill175.backup.CampusBackupService;
import org.thehill.hill175.backup.CampusRecoveryService;
import org.thehill.hill175.backup.CampusRecoveryPreview;
import org.thehill.hill175.listener.CampusSafetyListener;
import org.thehill.hill175.ui.BuildingLocationService;
import org.thehill.hill175.ui.CampusMapMenu;
import org.thehill.hill175.ui.CampusMapPack;
import org.thehill.hill175.ui.CampusWorkshop;
import org.thehill.hill175.undo.CampusUndoService;
import org.thehill.hill175.world.OfficialCampusMapRenderer;
import org.thehill.hill175.download.StudentMapDownloadService;
import org.thehill.hill175.replay.IncidentReplayService;
import org.thehill.hill175.replay.PacketReplayService;
import org.thehill.hill175.blueprint.BlueprintService;
import org.thehill.hill175.party.PartyService;
import org.thehill.hill175.moderation.SchoolChatSafety;

import java.util.List;
import java.util.Objects;
import java.io.IOException;
import java.io.UncheckedIOException;

public final class Hill175Plugin extends JavaPlugin {
    private CompetitionStore store;
    private CompetitionModule competition;
    private HubNpcModule hubNpcs;
    private WorldModule worlds;
    private MicrosoftSsoService schoolIdentity;
    private GalleryHttpServer gallery;
    private MenuModule menus;
    private org.thehill.hill175.ui.PlayerActions actions;
    private CampusRecoveryService campusBackups;
    private CampusRecoveryPreview recoveryPreview;
    private BuildingLocationService locations;
    private CampusMapMenu campusMap;
    private CampusUndoService campusUndo;
    private AccessControl access;
    private StudentMapDownloadService studentDownloads;
    private IncidentReplayService incidentReplay;
    private PacketReplayService packetReplay;
    private BlueprintService blueprint;
    private PartyService parties;

    @Override
    public void onEnable() {
        try {
            CampusBackupService.applyPendingRestore(this);
            initialize();
        } catch (RuntimeException exception) {
            stopAfterStartupFailure(exception);
        }
    }

    private void initialize() {
        saveDefaultConfig();
        getConfig().options().copyDefaults(true);
        saveConfig();
        reloadConfig();
        var microsoftConfig = SsoConfig.fromEnvironment(System.getenv());
        IdentityLinker identityLinker = null;
        if (microsoftConfig.isPresent()) {
            try {
                schoolIdentity = new MicrosoftSsoService(microsoftConfig.orElseThrow(),
                        getDataFolder().toPath().resolve("school-identities.json"));
            } catch (IOException exception) {
                throw new UncheckedIOException("Cannot start Microsoft school verification safely.", exception);
            }
        } else {
            identityLinker = IdentityLinkerFactory.create(getConfig());
            getLogger().warning("DEVELOPMENT AUTHENTICATION IS ACTIVE: any unregistered offline nickname can be claimed while registration is open.");
        }

        boolean personalCampuses = getConfig().getBoolean("personal-campus.enabled", true);
        if (personalCampuses) {
            BlueprintService.prepareTemplate(this);
            getConfig().set("people.structure-file", "");
            getConfig().set("people.require-template", true);
        }
        worlds = new WorldModule(this);
        worlds.initialize();

        store = new YamlCompetitionStore(getDataFolder(), getLogger());
        competition = new CompetitionModule(
                this,
                store,
                worlds,
                new PasswordHasher(),
                identityLinker,
                schoolIdentity
        );
        try {
            access = new AccessControl(this, getDataFolder().toPath().resolve("moderation.json"),
                    competition::isAuthenticated, schoolIdentity != null);
        } catch (IOException exception) {
            throw new UncheckedIOException("Cannot start staff roles and moderation safely.", exception);
        }
        competition.admission(access::authenticated);
        competition.accessAllowed(access::allowed);
        if (schoolIdentity != null) schoolIdentity.admissionGuard(access::requireSchoolAdmission);
        SchoolChatSafety chatSafety = new SchoolChatSafety(this, competition::isAuthenticated);
        competition.textAllowed(chatSafety::allows);
        if (personalCampuses) {
            blueprint = new BlueprintService(this, store, competition, worlds);
            blueprint.textAllowed(chatSafety::allows);
            blueprint.initialize();
            if (blueprint.ready()) getLogger().info("Personal campuses and blueprint ready at update #" + blueprint.latestUpdate() + ".");
            parties = new PartyService(this, competition, store, worlds,
                    blueprint::ensureCanCreateBranch, blueprint::registerBranch,
                    entry -> !blueprint.isRegistered(entry) || blueprint.isFrozen(entry));
            competition.personalCampuses(parties, blueprint);
        }
        if (!personalCampuses && worlds.sharedCampusEntry().isPresent()) {
            campusBackups = new CampusRecoveryService(this, competition::isAuthenticated);
            campusBackups.initialize(worlds);
        }
        if (schoolIdentity != null) {
            // Session construction validates online-mode and Floodgate before any browser endpoint opens.
            try {
                schoolIdentity.start();
            } catch (IOException exception) {
                throw new UncheckedIOException("Cannot open Microsoft school verification safely.", exception);
            }
        }
        if (getConfig().getBoolean("gallery.enabled", true)) {
            java.nio.file.Path assets = java.nio.file.Path.of(getConfig().getString(
                    "gallery.asset-directory", "plugins/Hill175/gallery-assets"));
            if (!assets.isAbsolute()) assets = getServer().getWorldContainer().toPath().resolve(assets);
            gallery = new GalleryHttpServer(getConfig().getInt("gallery.port", 8788), competition.galleryPublisher(), assets);
            try {
                gallery.start();
                getLogger().info("Build gallery listening on loopback port " + gallery.port() + ".");
            } catch (IOException exception) {
                throw new UncheckedIOException("Cannot start the local build gallery.", exception);
            }
        }
        menus = new MenuModule(competition, worlds);
        actions = new org.thehill.hill175.ui.PlayerActions(this, competition, menus, blueprint, access);
        var hillMenu = Objects.requireNonNull(getCommand("hillmenu"));
        hillMenu.setExecutor((sender, command, label, args) -> {
            if (sender instanceof Player player) {
                if (args.length == 1 && args[0].equals("sync") && blueprint != null && competition.isAuthenticated(player)) actions.sync(player);
                else actions.open(player);
            }
            return true;
        });
        hillMenu.setTabCompleter((sender, command, alias, args) -> List.of());
        getServer().getPluginManager().registerEvents(actions, this);
        if (parties != null) parties.playerMenus(actions);
        competition.hillMenu(actions::open);
        hubNpcs = new HubNpcModule(this, competition, menus, worlds);
        if (parties != null) hubNpcs.campusGuides(player -> competition.home(player), actions::blueprint);
        ServerListener serverListener = new ServerListener(this, competition, menus, worlds);
        CommandModule commands = new CommandModule(competition, menus);

        PluginManager pluginManager = getServer().getPluginManager();
        pluginManager.registerEvents(access, this);
        pluginManager.registerEvents(chatSafety, this);
        for (String name : List.of("party", "invite", "blueprint", "review")) {
            var command = Objects.requireNonNull(getCommand(name));
            command.setExecutor((sender, ignoredCommand, label, arguments) -> {
                sender.sendMessage("Personal campuses are disabled on this server.");
                return true;
            });
            command.setTabCompleter((sender, ignoredCommand, alias, arguments) -> List.of());
        }
        if (parties != null) {
            pluginManager.registerEvents(parties, this);
            for (String name : List.of("party", "invite")) {
                var command = Objects.requireNonNull(getCommand(name));
                command.setExecutor(parties);
                command.setTabCompleter(parties);
            }
            var blueprintCommand = Objects.requireNonNull(getCommand("blueprint"));
            var blueprintActions = blueprint.commands();
            blueprintCommand.setExecutor(blueprintActions);
            blueprintCommand.setTabCompleter(blueprintActions);
            var reviewCommand = Objects.requireNonNull(getCommand("review"));
            reviewCommand.setExecutor(blueprintActions);
            reviewCommand.setTabCompleter(blueprintActions);
        }
        var downloadCommand = Objects.requireNonNull(getCommand("download"));
        downloadCommand.setTabCompleter((sender, command, alias, arguments) -> List.of());
        downloadCommand.setExecutor((sender, command, label, arguments) -> {
            sender.sendMessage("Map downloads are not configured yet. Please contact staff.");
            return true;
        });
        try {
            studentDownloads = StudentMapDownloadService.fromEnvironment(getDataFolder().toPath(),
                    competition::isAuthenticated).orElse(null);
            if (studentDownloads != null) {
                studentDownloads.start();
                downloadCommand.setExecutor(studentDownloads);
            }
        } catch (IOException exception) {
            throw new UncheckedIOException("Cannot start protected student map downloads.", exception);
        }
        var replayCommand = Objects.requireNonNull(getCommand("hillreplay"));
        if (getConfig().getBoolean("incident-replay.enabled", true)) {
            incidentReplay = new IncidentReplayService(this, access::mayReviewReplays);
            incidentReplay.register(replayCommand);
        } else {
            replayCommand.setExecutor((sender, command, label, arguments) -> {
                sender.sendMessage("Incident history is disabled.");
                return true;
            });
        }
        String packetReplayEnabled = System.getenv("HILL175_PACKET_REPLAY_ENABLED");
        if (packetReplayEnabled != null) {
            if (!packetReplayEnabled.equals("true") && !packetReplayEnabled.equals("false")) {
                throw new IllegalArgumentException("HILL175_PACKET_REPLAY_ENABLED must be true or false.");
            }
            getConfig().set("packet-replay.enabled", Boolean.parseBoolean(packetReplayEnabled));
        }
        packetReplay = new PacketReplayService(this, competition::isAuthenticated);
        packetReplay.start();
        var staffCommand = Objects.requireNonNull(getCommand("hillstaff"));
        staffCommand.setExecutor(access);
        staffCommand.setTabCompleter(access);
        campusUndo = new CampusUndoService(this,
                (player, location) -> (campusBackups == null || !campusBackups.isRestoring()) && competition.mayBuild(player, location),
                world -> worlds.isSharedCampus(world) || blueprint != null && blueprint.isCampus(world));
        competition.campusUndo(player -> {
            if (campusBackups != null && campusBackups.isRestoring()) {
                player.sendMessage("Undo is paused while a campus area is being restored.");
            } else campusUndo.undo(player);
        });
        pluginManager.registerEvents(campusUndo, this);
        pluginManager.registerEvents(menus, this);
        pluginManager.registerEvents(hubNpcs, this);
        pluginManager.registerEvents(serverListener, this);
        if (blueprint != null) {
            pluginManager.registerEvents(blueprint.listener(), this);
            pluginManager.registerEvents(blueprint.reviewControls(), this);
        }
        pluginManager.registerEvents(new CampusSafetyListener(world -> !worlds.isSurvivalWorld(world)), this);
        locations = new BuildingLocationService(this, worlds::campusBuildings,
                world -> worlds.isSharedCampus(world) || world.getName().startsWith("hill_people_")
                        || world.getName().startsWith("hill_place_") || world.getName().equals("hill_blueprint"),
                player -> competition.isAuthenticated(player) && !competition.isCameraPreviewing(player));
        pluginManager.registerEvents(locations, this);
        locations.start();
        if (campusBackups != null) {
            var backupCommand = Objects.requireNonNull(getCommand("campusbackup"));
            var backupActions = campusBackups.commands();
            backupCommand.setExecutor(backupActions);
            backupCommand.setTabCompleter(backupActions);
        }
        initializeCampusWorkshop(pluginManager);

        for (String commandName : List.of("register", "login", "verify", "hill175", "competition", "hub", "lobby", "help", "rules", "entry", "team", "camera")) {
            var command = Objects.requireNonNull(getCommand(commandName), "Missing command in plugin.yml: " + commandName);
            command.setExecutor(commands);
            command.setTabCompleter(commands);
        }

        Bukkit.getScheduler().runTask(this, () -> {
            try {
                hubNpcs.spawnCategoryNpcs();
            } catch (RuntimeException exception) {
                stopAfterStartupFailure(exception);
            }
        });
        Bukkit.getScheduler().runTask(this, competition::rebuildAllCameraMarkers);
        Bukkit.getScheduler().runTaskTimer(this, competition::tickSessionLocks, 1L, 1L);
        Bukkit.getScheduler().runTaskTimer(this, this::removeForbiddenMobsAndPrimedTnt, 20L, 20L);
        Bukkit.getScheduler().runTaskTimer(this, store::flush, 20L * 300L, 20L * 300L);

        for (Player onlinePlayer : Bukkit.getOnlinePlayers()) {
            competition.handleJoin(onlinePlayer);
        }
        getLogger().info(schoolIdentity == null
                ? "Hill 175 competition server enabled with development identity linking."
                : "Hill 175 competition server enabled with Microsoft school verification.");
    }

    private void initializeCampusWorkshop(PluginManager pluginManager) {
        CampusWorkshop workshop = new CampusWorkshop(competition, worlds);
        java.nio.file.Path assets = java.nio.file.Path.of(getConfig().getString(
                "gallery.asset-directory", "plugins/Hill175/gallery-assets"));
        if (!assets.isAbsolute()) assets = getServer().getWorldContainer().toPath().resolve(assets);
        java.nio.file.Path heldMap = assets.resolve("campus-held.png");
        if (java.nio.file.Files.isRegularFile(heldMap)) {
            try {
                java.awt.image.BufferedImage image = javax.imageio.ImageIO.read(heldMap.toFile());
                if (image == null) throw new IOException("The held campus map is not a readable image.");
                competition.officialMapRenderer(() -> new OfficialCampusMapRenderer(image));
                getLogger().info("Official campus illustration loaded for held maps.");
            } catch (IOException exception) {
                throw new UncheckedIOException("Cannot load the official held campus map.", exception);
            }
        }
        CampusMapPack pack = null;
        if (java.nio.file.Files.isRegularFile(assets.resolve("campus-pack.zip"))) {
            String publicUrl = System.getenv("HILL175_GALLERY_PUBLIC_URL");
            if (publicUrl == null || publicUrl.isBlank()) publicUrl = getConfig().getString("gallery.public-base-url", "http://localhost:8788");
            try { pack = new CampusMapPack(assets, publicUrl); }
            catch (IOException | IllegalArgumentException exception) {
                getLogger().log(java.util.logging.Level.WARNING, "Campus imagery is unavailable. Named selection remains active.", exception);
            }
        }
        java.nio.file.Path template = java.nio.file.Path.of(getConfig().getString("people.template-folder"));
        if (!template.isAbsolute()) template = getServer().getWorldContainer().toPath().resolve(template);
        String revision = org.bukkit.configuration.file.YamlConfiguration.loadConfiguration(
                template.resolve("hill-campus-template.yml").toFile()).getString("revision", "Selected campus");
        campusMap = new CampusMapMenu(this, revision, worlds.campusSelectionRegion(), worlds.buildings(), pack,
                competition::isAuthenticated, workshop::select, player -> player.closeInventory());
        if (!competition.personalCampusesEnabled()) campusMap.undoAction(competition::undoRecentBuild);
        if (campusBackups != null) {
            recoveryPreview = new CampusRecoveryPreview(this, campusBackups, competition);
            competition.recoveryPreview(recoveryPreview::contains);
            recoveryPreview.initialize();
            campusBackups.menuAction(recoveryPreview::open);
            campusMap.recoveryAction(recoveryPreview::canOpen, recoveryPreview::open);
        }
        try {
            var labels = org.thehill.hill175.ui.CampusMapLabels.load(assets,
                    getResource("campus-map-destinations.json"), worlds.campusSelectionRegion(), worlds.buildings());
            campusMap.labels(labels);
            labels.artworkWarning().ifPresent(warning -> getLogger().warning(
                    "Clickable campus artwork is unavailable. Named destinations remain active. " + warning));
        } catch (IOException exception) {
            throw new UncheckedIOException("Cannot load safe campus map destinations.", exception);
        }
        workshop.map(campusMap);
        menus.campusWorkshop(workshop::open);
        pluginManager.registerEvents(campusMap, this);
        var command = Objects.requireNonNull(getCommand("campus"));
        command.setExecutor(workshop);
        command.setTabCompleter(workshop);
    }

    private void stopAfterStartupFailure(RuntimeException exception) {
        // Disabling only this plugin would remove admission and world protections
        // while leaving Paper open to player connections.
        getLogger().log(java.util.logging.Level.SEVERE,
                "Stopping Paper because Hill175 could not start safely.", exception);
        getServer().shutdown();
    }

    @Override
    public void onDisable() {
        if (actions != null) actions.close();
        if (parties != null) parties.close();
        if (blueprint != null) blueprint.close();
        if (studentDownloads != null) studentDownloads.close();
        if (incidentReplay != null) incidentReplay.close();
        if (packetReplay != null) packetReplay.close();
        if (access != null) {
            try { access.close(); }
            catch (IOException exception) { getLogger().severe("Moderation storage did not close safely. Review the protected records before restarting."); }
        }
        if (recoveryPreview != null) recoveryPreview.close();
        if (campusMap != null) campusMap.close();
        if (campusUndo != null) campusUndo.close();
        if (locations != null) locations.close();
        if (campusBackups != null) campusBackups.close();
        if (menus != null) menus.shutdown();
        if (gallery != null) gallery.close();
        if (schoolIdentity != null && !getServer().isStopping()) {
            // Hot-disabling admission protection must not leave an unprotected production server open.
            getServer().shutdown();
        }
        if (competition != null) {
            competition.shutdown();
        }
        if (hubNpcs != null) {
            hubNpcs.shutdown();
        }
        if (store != null) {
            store.flush();
        }
        if (schoolIdentity != null) {
            schoolIdentity.close();
        }
    }

    private void removeForbiddenMobsAndPrimedTnt() {
        for (var world : Bukkit.getWorlds()) {
            if (worlds.isSurvivalWorld(world)) {
                continue;
            }
            for (var entity : world.getEntities()) {
                if (entity instanceof Mob && !entity.getScoreboardTags().contains("hill175_category_npc")) {
                    entity.remove();
                } else if (entity.getType() == EntityType.TNT) {
                    entity.remove();
                }
            }
        }
    }
}
