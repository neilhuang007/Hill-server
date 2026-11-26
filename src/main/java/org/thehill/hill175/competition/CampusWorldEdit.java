package org.thehill.hill175.competition;

import com.sk89q.worldedit.EditSession;
import com.sk89q.worldedit.EmptyClipboardException;
import com.sk89q.worldedit.IncompleteRegionException;
import com.sk89q.worldedit.WorldEdit;
import com.sk89q.worldedit.WorldEditException;
import com.sk89q.worldedit.bukkit.BukkitAdapter;
import com.sk89q.worldedit.bukkit.BukkitWorld;
import com.sk89q.worldedit.command.tool.SelectionWand;
import com.sk89q.worldedit.entity.BaseEntity;
import com.sk89q.worldedit.entity.Entity;
import com.sk89q.worldedit.event.extent.EditSessionEvent;
import com.sk89q.worldedit.event.platform.CommandEvent;
import com.sk89q.worldedit.extent.AbstractDelegateExtent;
import com.sk89q.worldedit.extent.Extent;
import com.sk89q.worldedit.extent.NullExtent;
import com.sk89q.worldedit.extension.platform.Capability;
import com.sk89q.worldedit.math.BlockVector3;
import com.sk89q.worldedit.regions.Region;
import com.sk89q.worldedit.util.Location;
import com.sk89q.worldedit.util.eventbus.Subscribe;
import com.sk89q.worldedit.world.biome.BiomeType;
import com.sk89q.worldedit.world.block.BlockStateHolder;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.plugin.java.JavaPlugin;
import org.thehill.hill175.blueprint.BlueprintService;
import org.thehill.hill175.model.Entry;
import org.thehill.hill175.replay.BuildRecorder;

import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class CampusWorldEdit implements Listener, AutoCloseable {
    private static final int MAX_BLOCKS = 16_384;
    private static final Pattern BLOCK_STATE = Pattern.compile("(?:minecraft:)?[a-z0-9_]+(?:\\[[a-z0-9_]+=[a-z0-9_]+(?:,[a-z0-9_]+=[a-z0-9_]+)*\\])?");
    private static final Map<String, String> PERMISSIONS = Map.ofEntries(
            Map.entry("wand", "worldedit.wand"), Map.entry("pos1", "worldedit.selection.pos"), Map.entry("pos2", "worldedit.selection.pos"),
            Map.entry("size", "worldedit.selection.size"), Map.entry("set", "worldedit.region.set"),
            Map.entry("replace", "worldedit.region.replace"), Map.entry("walls", "worldedit.region.walls"),
            Map.entry("faces", "worldedit.region.faces"), Map.entry("copy", "worldedit.clipboard.copy"),
            Map.entry("paste", "worldedit.clipboard.paste"), Map.entry("undo", "worldedit.history.undo.self"),
            Map.entry("redo", "worldedit.history.redo.self"));
    private static final Set<String> SELECTION_COMMANDS = Set.of("size", "set", "replace", "walls", "faces", "copy");
    private static final Set<String> BLOCKED_BLOCKS = Set.of("minecraft:bedrock", "minecraft:barrier",
            "minecraft:command_block", "minecraft:chain_command_block", "minecraft:repeating_command_block",
            "minecraft:structure_block", "minecraft:jigsaw", "minecraft:structure_void", "minecraft:light",
            "minecraft:spawner", "minecraft:trial_spawner", "minecraft:vault", "minecraft:nether_portal",
            "minecraft:end_portal", "minecraft:end_portal_frame", "minecraft:end_gateway");

    private final JavaPlugin plugin;
    private final CompetitionModule competition;
    private final BlueprintService blueprint;
    private final BuildRecorder recorder;
    private final WorldEdit worldEdit = WorldEdit.getInstance();
    private EditScope active;

    public CampusWorldEdit(JavaPlugin plugin, CompetitionModule competition, BlueprintService blueprint) {
        this(plugin, competition, blueprint, null);
    }

    public CampusWorldEdit(JavaPlugin plugin, CompetitionModule competition, BlueprintService blueprint, BuildRecorder recorder) {
        this.plugin = plugin;
        this.competition = competition;
        this.blueprint = blueprint;
        this.recorder = recorder;
        worldEdit.getEventBus().register(this);
    }

    public boolean handleCommand(Player player, String message) {
        if (!message.startsWith("//")) return false;
        String[] words = message.substring(2).strip().split("\\s+");
        String command = words[0].toLowerCase(Locale.ROOT);
        String permission = PERMISSIONS.get(command);
        if (permission == null) return false;
        if (!Bukkit.isPrimaryThread() || active != null || !plugin.getServer().getPluginManager().isPluginEnabled("WorldEdit")) {
            player.sendMessage("WorldEdit is not available right now.");
            return true;
        }
        Entry entry = competition.worldEditEntry(player).orElse(null);
        if (entry == null) {
            player.sendMessage("WorldEdit is available only while building in your own campus.");
            return true;
        }
        if (!validArguments(command, words)) {
            player.sendMessage("Use //wand or mark corners with //pos1 and //pos2, then //set <block>, //replace <from> <to>, "
                    + "//walls <block>, //faces <block>, //copy, //paste [-a], //size, //undo or //redo.");
            return true;
        }
        World world = player.getWorld();
        var actor = BukkitAdapter.adapt(player);
        var session = worldEdit.getSessionManager().get(actor);
        if (session.hasWorldOverride()) {
            player.sendMessage("WorldEdit cannot use a different world from your campus.");
            return true;
        }
        try {
            if (SELECTION_COMMANDS.contains(command)) {
                Region selection = session.getSelection(BukkitAdapter.adapt(world));
                if (!boundedSelection(entry, selection)) {
                    player.sendMessage("Select up to " + MAX_BLOCKS + " blocks inside one editable area of your campus.");
                    return true;
                }
            } else if (command.equals("paste") && session.getClipboard().getClipboard().getRegion().getVolume() > MAX_BLOCKS) {
                player.sendMessage("The clipboard is larger than the campus WorldEdit limit of " + MAX_BLOCKS + " blocks.");
                return true;
            }
        } catch (IncompleteRegionException exception) {
            player.sendMessage("Stand at each corner and use //pos1 and //pos2 before editing.");
            return true;
        } catch (EmptyClipboardException exception) {
            player.sendMessage("Select an area and use //copy before pasting.");
            return true;
        }
        EditScope scope = new EditScope(player, world, entry);
        int previousLimit = session.getBlockChangeLimit();
        var attachment = player.addAttachment(plugin, permission, true);
        active = scope;
        try {
            if (command.equals("wand")) attachment.setPermission("worldedit.selection.pos", true);
            session.setBlockChangeLimit(previousLimit < 0 ? MAX_BLOCKS : Math.min(previousLimit, MAX_BLOCKS));
            words[0] = "//" + command;
            worldEdit.getEventBus().post(new CommandEvent(actor, String.join(" ", words)));
        } finally {
            active = null;
            session.setBlockChangeLimit(previousLimit);
            attachment.remove();
        }
        if (scope.skipped) player.sendMessage("WorldEdit skipped blocks outside your editable area or protected by Hill.");
        return true;
    }

    @EventHandler(priority = EventPriority.LOW, ignoreCancelled = true)
    public void onWandClick(PlayerInteractEvent event) {
        var block = event.getClickedBlock();
        var item = event.getItem();
        Action action = event.getAction();
        if (event.getHand() != EquipmentSlot.HAND || block == null || item == null || item.getType() != Material.WOODEN_AXE
                || (action != Action.LEFT_CLICK_BLOCK && action != Action.RIGHT_CLICK_BLOCK)
                || !plugin.getServer().getPluginManager().isPluginEnabled("WorldEdit")) return;
        Player player = event.getPlayer();
        Entry entry = competition.worldEditEntry(player).orElse(null);
        if (entry == null) return;
        var actor = BukkitAdapter.adapt(player);
        var session = worldEdit.getSessionManager().get(actor);
        if (session.hasWorldOverride() || !(session.getTool(BukkitAdapter.adapt(item).getType()) instanceof SelectionWand wand)) return;
        event.setCancelled(true);
        if (!entry.containsEditable(block.getLocation())) {
            player.sendMessage("Choose a block inside your campus's editable area.");
            return;
        }
        var platform = worldEdit.getPlatformManager().queryCapability(Capability.WORLD_EDITING);
        var position = BukkitAdapter.adapt(block.getLocation());
        var direction = BukkitAdapter.adapt(event.getBlockFace());
        if (action == Action.LEFT_CLICK_BLOCK) {
            wand.actSecondary(platform, worldEdit.getConfiguration(), actor, session, position, direction);
        } else {
            wand.actPrimary(platform, worldEdit.getConfiguration(), actor, session, position, direction);
        }
    }

    private static boolean validArguments(String command, String[] words) {
        return switch (command) {
            case "set", "walls", "faces" -> words.length == 2 && BLOCK_STATE.matcher(words[1]).matches();
            case "replace" -> words.length == 3 && BLOCK_STATE.matcher(words[1]).matches() && BLOCK_STATE.matcher(words[2]).matches();
            case "paste" -> words.length == 1 || words.length == 2 && words[1].equals("-a");
            default -> words.length == 1;
        };
    }

    private static boolean boundedSelection(Entry entry, Region selection) {
        var min = selection.getMinimumPoint();
        var max = selection.getMaximumPoint();
        return entry.editableRegions().stream().anyMatch(bounds -> bounds.contains(min.x(), min.y(), min.z())
                && bounds.contains(max.x(), max.y(), max.z())) && selection.getVolume() > 0 && selection.getVolume() <= MAX_BLOCKS;
    }

    @Subscribe(priority = com.sk89q.worldedit.util.eventbus.EventHandler.Priority.VERY_LATE)
    public void guardEditSession(EditSessionEvent event) {
        if (event.getStage() != EditSession.Stage.BEFORE_CHANGE || event.getActor() == null || !event.getActor().isPlayer()) return;
        EditScope scope = active;
        if (!Bukkit.isPrimaryThread() || scope == null || !scope.player.getUniqueId().equals(event.getActor().getUniqueId())
                || !(event.getWorld() instanceof BukkitWorld world) || !scope.world.equals(world.getWorld())) {
            event.setExtent(new NullExtent());
            return;
        }
        event.setExtent(new CampusExtent(event.getExtent(), scope));
    }

    @Override
    public void close() {
        worldEdit.getEventBus().unregister(this);
    }

    private final class CampusExtent extends AbstractDelegateExtent {
        private final EditScope scope;

        private CampusExtent(Extent extent, EditScope scope) {
            super(extent);
            this.scope = scope;
        }

        @Override
        public <State extends BlockStateHolder<State>> boolean setBlock(BlockVector3 position, State state) throws WorldEditException {
            if (!Bukkit.isPrimaryThread() || active != scope || !scope.world.equals(scope.player.getWorld())
                    || blueprint.protects(scope.world)) return false;
            int blockX = position.x();
            int blockY = position.y();
            int blockZ = position.z();
            var target = new org.bukkit.Location(scope.world, blockX, blockY, blockZ);
            if (++scope.writes > MAX_BLOCKS || !scope.entry.containsEditable(target)
                    || blockY < scope.world.getMinHeight() || blockY >= scope.world.getMaxHeight()
                    || BLOCKED_BLOCKS.contains(state.getBlockType().id()) || state.toBaseBlock().getNbtReference() != null
                    || getFullBlock(position).getNbtReference() != null) {
                scope.skipped = true;
                return false;
            }
            long chunk = ((long) (blockX >> 4) << 32) | Integer.toUnsignedLong(blockZ >> 4);
            if (!scope.journaled.contains(chunk)) {
                if (!blueprint.changed(scope.world, blockX, blockZ)) return false;
                scope.journaled.add(chunk);
            }
            if (recorder == null) return super.setBlock(position, state);
            if (!scope.preparedReplay) {
                scope.replay = recorder.prepareWorldEdit(scope.player, scope.world);
                scope.preparedReplay = true;
            }
            if (scope.replay == null) return super.setBlock(position, state);
            String before = getBlock(position).getAsString();
            scope.replay.beforeWrite(blockX, blockZ);
            boolean changed = super.setBlock(position, state);
            if (changed) scope.replay.successful(blockX, blockY, blockZ, before, state.toImmutableState().getAsString());
            return changed;
        }

        @Override
        public Entity createEntity(Location location, BaseEntity entity) { return null; }

        @Override
        public boolean setBiome(BlockVector3 position, BiomeType biome) { return false; }
    }

    private static final class EditScope {
        private final Player player;
        private final World world;
        private final Entry entry;
        private final Set<Long> journaled = new HashSet<>();
        private int writes;
        private boolean skipped;
        private boolean preparedReplay;
        private BuildRecorder.EditCapture replay;

        private EditScope(Player player, World world, Entry entry) {
            this.player = player;
            this.world = world;
            this.entry = entry;
        }
    }
}
