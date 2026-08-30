package org.thehill.hill175.ui;

import net.kyori.adventure.text.Component;
import org.bukkit.Bukkit;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.entity.Player;
import org.bukkit.event.entity.CreatureSpawnEvent;
import org.bukkit.inventory.EquipmentSlot;
import org.bukkit.plugin.java.JavaPlugin;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * A real server-side Player entity used for hub NPCs.
 *
 * Paper deliberately does not expose a public API for spawning a player. The
 * implementation therefore confines the version-specific bridge to this
 * class and keeps the rest of the plugin on the Bukkit API. The bridge is
 * targeted at the pinned Paper 26.2 runtime used by this project.
 */
final class SyntheticPlayerNpc {
    private final JavaPlugin plugin;
    private final RuntimeBridge bridge;
    private final Object nmsPlayer;
    private final Player player;
    private final UUID uniqueId;
    private boolean active;

    private SyntheticPlayerNpc(JavaPlugin plugin, RuntimeBridge bridge, Object nmsPlayer, Player player) {
        this.plugin = plugin;
        this.bridge = bridge;
        this.nmsPlayer = nmsPlayer;
        this.player = player;
        this.uniqueId = player.getUniqueId();
    }

    static SyntheticPlayerNpc spawn(
            JavaPlugin plugin,
            Location location,
            String profileName,
            String skinTexture
    ) {
        try {
            RuntimeBridge bridge = RuntimeBridge.load();
            Object server = bridge.minecraftServer.getMethod("getServer").invoke(null);
            Object serverLevel = location.getWorld().getClass().getMethod("getHandle").invoke(location.getWorld());
            Object propertyBacking = bridge.propertyMapBackingCreate.invoke(null);
            Object textures = bridge.propertyConstructor.newInstance("textures", texturePropertyValue(skinTexture));
            bridge.propertyMapPut.invoke(propertyBacking, "textures", textures);
            Object properties = bridge.propertyMapConstructor.newInstance(propertyBacking);
            Object gameProfile = bridge.gameProfileConstructor.newInstance(
                    UUID.nameUUIDFromBytes(("hill175:npc:" + profileName).getBytes(StandardCharsets.UTF_8)),
                    profileName,
                    properties
            );

            Object clientInformation = withAllSkinLayers(
                    bridge.clientInformationCreateDefault.invoke(null));
            Object nmsPlayer = bridge.serverPlayerConstructor.newInstance(
                    server,
                    serverLevel,
                    gameProfile,
                    clientInformation
            );
            Object bukkitEntity = bridge.getBukkitEntity.invoke(nmsPlayer);
            if (!(bukkitEntity instanceof Player player)) {
                throw new IllegalStateException("Paper returned a non-player wrapper for a synthetic NPC");
            }

            // ServerPlayer.tick() assumes that every player has a connection.
            // A disconnected server-bound connection keeps the entity tick-safe
            // without registering the NPC as an online player.
            Object packetFlow = bridge.serverboundPacketFlow;
            Object connection = bridge.connectionConstructor.newInstance(packetFlow);
            Object listenerCookie = bridge.commonListenerCookieCreateInitial.invoke(null, gameProfile, false);
            Object listener = bridge.serverGamePacketListenerConstructor.newInstance(
                    server,
                    connection,
                    nmsPlayer,
                    listenerCookie
            );
            bridge.serverPlayerConnection.set(nmsPlayer, listener);
            // A connection without a channel must not remain in its initial
            // "preparing" state or normal ServerPlayer ticks queue packets forever.
            connection.getClass().getField("preparing").setBoolean(connection, false);

            bridge.setPos.invoke(nmsPlayer, location.getX(), location.getY(), location.getZ());
            bridge.setYRot.invoke(nmsPlayer, location.getYaw());
            bridge.setXRot.invoke(nmsPlayer, location.getPitch());
            bridge.setYHeadRot.invoke(nmsPlayer, location.getYaw());

            player.setGameMode(GameMode.ADVENTURE);
            player.setAllowFlight(false);
            player.setFlying(false);
            player.setGravity(false);
            // HubNpcModule cancels all incoming damage. Keeping the entity
            // damageable here is intentional so a left-click still produces
            // EntityDamageByEntityEvent and opens the same menu as right-click.
            player.setInvulnerable(false);
            player.setSilent(true);
            player.setPersistent(false);
            player.setCollidable(false);
            player.setCustomNameVisible(false);

            SyntheticPlayerNpc npc = new SyntheticPlayerNpc(plugin, bridge, nmsPlayer, player);
            // Paper normally treats every ServerPlayer as both an entity and a
            // chunk viewer. This NPC is packet-owned below, so suppress that
            // tracker registration before adding it to the world's entity lookup.
            bridge.suppressTrackerForLogin.setBoolean(nmsPlayer, true);
            boolean added = (boolean) bridge.addFreshEntity.invoke(
                    serverLevel,
                    nmsPlayer,
                    CreatureSpawnEvent.SpawnReason.CUSTOM
            );
            if (!added) {
                npc.remove();
                throw new IllegalStateException("Paper rejected the synthetic NPC spawn at " + location);
            }
            // Keep the entity in the world's lookup for ticking and click
            // resolution, but exclude it from World#getPlayers and viewer state.
            @SuppressWarnings("unchecked")
            List<Object> levelPlayers = (List<Object>) serverLevel.getClass().getMethod("players").invoke(serverLevel);
            levelPlayers.remove(nmsPlayer);
            return npc;
        } catch (ReflectiveOperationException | RuntimeException exception) {
            throw new IllegalStateException(
                    "Unable to spawn a real Player NPC. Verify the server is the pinned Paper 26.2 runtime.",
                    exception
            );
        }
    }

    Player player() {
        return player;
    }

    UUID uniqueId() {
        return uniqueId;
    }

    void activate() {
        if (active) {
            return;
        }
        active = true;
        sendPlayerInfoToOnlinePlayers();
        hideFromTabAfterSpawn();
    }

    void sendTo(Player viewer) {
        if (!active || viewer == null || !viewer.isOnline() || viewer.getUniqueId().equals(uniqueId)) {
            return;
        }
        try {
            sendPacket(viewer, bridge.playerInfoAddConstructor.newInstance(bridge.addPlayerAction, nmsPlayer));
            if (viewer.getWorld().equals(player.getWorld())) {
                sendSpawnPackets(viewer);
            }
            Bukkit.getScheduler().runTaskLater(plugin, () -> sendListedState(viewer, false), 2L);
        } catch (ReflectiveOperationException exception) {
            plugin.getLogger().warning("Unable to send NPC profile " + uniqueId + " to " + viewer.getName() + ": "
                    + exception.getMessage());
        }
    }

    void remove() {
        active = false;
        for (Player viewer : Bukkit.getOnlinePlayers()) {
            if (viewer.getUniqueId().equals(uniqueId)) {
                continue;
            }
            try {
                sendPacket(viewer, bridge.removeEntitiesConstructor.newInstance((Object) new int[]{player.getEntityId()}));
                sendPacket(viewer, bridge.playerInfoRemoveConstructor.newInstance(List.of(uniqueId)));
            } catch (ReflectiveOperationException exception) {
                plugin.getLogger().fine("Unable to remove NPC profile " + uniqueId + " from " + viewer.getName()
                        + ": " + exception.getMessage());
            }
        }
        try {
            bridge.entityRemove.invoke(nmsPlayer, bridge.discardRemovalReason, bridge.pluginRemovalCause);
        } catch (ReflectiveOperationException exception) {
            plugin.getLogger().warning("Unable to remove synthetic NPC entity " + uniqueId + ": "
                    + exception.getMessage());
        }
    }

    private void sendSpawnPackets(Player viewer) throws ReflectiveOperationException {
        int entityId = (int) bridge.entityGetId.invoke(nmsPlayer);
        Object packet = bridge.addEntityConstructor.newInstance(
                entityId,
                bridge.entityGetUuid.invoke(nmsPlayer),
                bridge.entityGetX.invoke(nmsPlayer),
                bridge.entityGetY.invoke(nmsPlayer),
                bridge.entityGetZ.invoke(nmsPlayer),
                bridge.entityGetXRot.invoke(nmsPlayer),
                bridge.entityGetYRot.invoke(nmsPlayer),
                bridge.entityGetType.invoke(nmsPlayer),
                0,
                bridge.entityGetDeltaMovement.invoke(nmsPlayer),
                ((Number) bridge.entityGetYHeadRot.invoke(nmsPlayer)).doubleValue()
        );
        sendPacket(viewer, packet);
        Object entityData = bridge.entityGetData.invoke(nmsPlayer);
        @SuppressWarnings("unchecked")
        List<Object> packedData = (List<Object>) bridge.entityDataPackAll.invoke(entityData);
        sendPacket(viewer, bridge.setEntityDataConstructor.newInstance(entityId, packedData));
        float headYaw = ((Number) bridge.entityGetYHeadRot.invoke(nmsPlayer)).floatValue();
        sendPacket(viewer, bridge.rotateHeadConstructor.newInstance(nmsPlayer, (byte) (headYaw * 256.0f / 360.0f)));
        Map<EquipmentSlot, org.bukkit.inventory.ItemStack> equipment = new EnumMap<>(EquipmentSlot.class);
        equipment.put(EquipmentSlot.HAND, player.getInventory().getItemInMainHand());
        equipment.put(EquipmentSlot.OFF_HAND, player.getInventory().getItemInOffHand());
        viewer.sendEquipmentChange(player, equipment);
    }

    private void sendPlayerInfoToOnlinePlayers() {
        for (Player viewer : Bukkit.getOnlinePlayers()) {
            sendTo(viewer);
        }
    }

    private void hideFromTabAfterSpawn() {
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            for (Player viewer : Bukkit.getOnlinePlayers()) {
                sendListedState(viewer, false);
            }
        }, 2L);
    }

    private void sendListedState(Player viewer, boolean listed) {
        if (!active || viewer == null || !viewer.isOnline() || viewer.getUniqueId().equals(uniqueId)) {
            return;
        }
        try {
            Object packet = bridge.playerInfoUpdateListed.invoke(null, uniqueId, listed);
            sendPacket(viewer, packet);
        } catch (ReflectiveOperationException exception) {
            plugin.getLogger().fine("Unable to update NPC tab-list state " + uniqueId + " for " + viewer.getName()
                    + ": " + exception.getMessage());
        }
    }

    private void sendPacket(Player viewer, Object packet) throws ReflectiveOperationException {
        Object handle = viewer.getClass().getMethod("getHandle").invoke(viewer);
        Object connection = bridge.serverPlayerConnection.get(handle);
        bridge.connectionSend.invoke(connection, packet);
    }

    private static String texturePropertyValue(String textureHash) {
        String json = "{\"textures\":{\"SKIN\":{\"url\":\"https://textures.minecraft.net/texture/"
                + textureHash
                + "\"}}}";
        return Base64.getEncoder().encodeToString(json.getBytes(StandardCharsets.UTF_8));
    }

    private static Object withAllSkinLayers(Object defaultInformation) throws ReflectiveOperationException {
        Class<?> informationClass = defaultInformation.getClass();
        java.lang.reflect.RecordComponent[] components = informationClass.getRecordComponents();
        Class<?>[] parameterTypes = new Class<?>[components.length];
        Object[] arguments = new Object[components.length];
        for (int index = 0; index < components.length; index++) {
            java.lang.reflect.RecordComponent component = components[index];
            parameterTypes[index] = component.getType();
            arguments[index] = component.getAccessor().invoke(defaultInformation);
            if (component.getName().equals("modelCustomisation")) {
                arguments[index] = 0x7F;
            }
        }
        return informationClass.getConstructor(parameterTypes).newInstance(arguments);
    }

    private static final class RuntimeBridge {
        private final Class<?> entityClass;
        private final Class<?> minecraftServer;
        private final Constructor<?> gameProfileConstructor;
        private final Constructor<?> propertyMapConstructor;
        private final Method propertyMapBackingCreate;
        private final Constructor<?> propertyConstructor;
        private final Method propertyMapPut;
        private final Method clientInformationCreateDefault;
        private final Constructor<?> serverPlayerConstructor;
        private final Method getBukkitEntity;
        private final Class<?> packetFlowClass;
        private final Object serverboundPacketFlow;
        private final Constructor<?> connectionConstructor;
        private final Method commonListenerCookieCreateInitial;
        private final Constructor<?> serverGamePacketListenerConstructor;
        private final Field serverPlayerConnection;
        private final Field suppressTrackerForLogin;
        private final Method setPos;
        private final Method setYRot;
        private final Method setXRot;
        private final Method setYHeadRot;
        private final Method addFreshEntity;
        private final Class<?> packetClass;
        private final Constructor<?> playerInfoAddConstructor;
        private final Object addPlayerAction;
        private final Method playerInfoUpdateListed;
        private final Constructor<?> playerInfoRemoveConstructor;
        private final Constructor<?> addEntityConstructor;
        private final Constructor<?> setEntityDataConstructor;
        private final Constructor<?> rotateHeadConstructor;
        private final Constructor<?> removeEntitiesConstructor;
        private final Method entityGetId;
        private final Method entityGetUuid;
        private final Method entityGetX;
        private final Method entityGetY;
        private final Method entityGetZ;
        private final Method entityGetXRot;
        private final Method entityGetYRot;
        private final Method entityGetYHeadRot;
        private final Method entityGetType;
        private final Method entityGetDeltaMovement;
        private final Method entityGetData;
        private final Method entityDataPackAll;
        private final Method entityRemove;
        private final Object discardRemovalReason;
        private final Object pluginRemovalCause;
        private final Method connectionSend;

        private RuntimeBridge(
                Class<?> entityClass,
                Class<?> minecraftServer,
                Constructor<?> gameProfileConstructor,
                Constructor<?> propertyMapConstructor,
                Method propertyMapBackingCreate,
                Constructor<?> propertyConstructor,
                Method propertyMapPut,
                Method clientInformationCreateDefault,
                Constructor<?> serverPlayerConstructor,
                Method getBukkitEntity,
                Class<?> packetFlowClass,
                Object serverboundPacketFlow,
                Constructor<?> connectionConstructor,
                Method commonListenerCookieCreateInitial,
                Constructor<?> serverGamePacketListenerConstructor,
                Field serverPlayerConnection,
                Field suppressTrackerForLogin,
                Method setPos,
                Method setYRot,
                Method setXRot,
                Method setYHeadRot,
                Method addFreshEntity,
                Class<?> packetClass,
                Constructor<?> playerInfoAddConstructor,
                Object addPlayerAction,
                Method playerInfoUpdateListed,
                Constructor<?> playerInfoRemoveConstructor,
                Constructor<?> addEntityConstructor,
                Constructor<?> setEntityDataConstructor,
                Constructor<?> rotateHeadConstructor,
                Constructor<?> removeEntitiesConstructor,
                Method entityGetId,
                Method entityGetUuid,
                Method entityGetX,
                Method entityGetY,
                Method entityGetZ,
                Method entityGetXRot,
                Method entityGetYRot,
                Method entityGetYHeadRot,
                Method entityGetType,
                Method entityGetDeltaMovement,
                Method entityGetData,
                Method entityDataPackAll,
                Method entityRemove,
                Object discardRemovalReason,
                Object pluginRemovalCause,
                Method connectionSend
        ) {
            this.entityClass = entityClass;
            this.minecraftServer = minecraftServer;
            this.gameProfileConstructor = gameProfileConstructor;
            this.propertyMapConstructor = propertyMapConstructor;
            this.propertyMapBackingCreate = propertyMapBackingCreate;
            this.propertyConstructor = propertyConstructor;
            this.propertyMapPut = propertyMapPut;
            this.clientInformationCreateDefault = clientInformationCreateDefault;
            this.serverPlayerConstructor = serverPlayerConstructor;
            this.getBukkitEntity = getBukkitEntity;
            this.packetFlowClass = packetFlowClass;
            this.serverboundPacketFlow = serverboundPacketFlow;
            this.connectionConstructor = connectionConstructor;
            this.commonListenerCookieCreateInitial = commonListenerCookieCreateInitial;
            this.serverGamePacketListenerConstructor = serverGamePacketListenerConstructor;
            this.serverPlayerConnection = serverPlayerConnection;
            this.suppressTrackerForLogin = suppressTrackerForLogin;
            this.setPos = setPos;
            this.setYRot = setYRot;
            this.setXRot = setXRot;
            this.setYHeadRot = setYHeadRot;
            this.addFreshEntity = addFreshEntity;
            this.packetClass = packetClass;
            this.playerInfoAddConstructor = playerInfoAddConstructor;
            this.addPlayerAction = addPlayerAction;
            this.playerInfoUpdateListed = playerInfoUpdateListed;
            this.playerInfoRemoveConstructor = playerInfoRemoveConstructor;
            this.addEntityConstructor = addEntityConstructor;
            this.setEntityDataConstructor = setEntityDataConstructor;
            this.rotateHeadConstructor = rotateHeadConstructor;
            this.removeEntitiesConstructor = removeEntitiesConstructor;
            this.entityGetId = entityGetId;
            this.entityGetUuid = entityGetUuid;
            this.entityGetX = entityGetX;
            this.entityGetY = entityGetY;
            this.entityGetZ = entityGetZ;
            this.entityGetXRot = entityGetXRot;
            this.entityGetYRot = entityGetYRot;
            this.entityGetYHeadRot = entityGetYHeadRot;
            this.entityGetType = entityGetType;
            this.entityGetDeltaMovement = entityGetDeltaMovement;
            this.entityGetData = entityGetData;
            this.entityDataPackAll = entityDataPackAll;
            this.entityRemove = entityRemove;
            this.discardRemovalReason = discardRemovalReason;
            this.pluginRemovalCause = pluginRemovalCause;
            this.connectionSend = connectionSend;
        }

        private static RuntimeBridge load() throws ReflectiveOperationException {
            ClassLoader loader = SyntheticPlayerNpc.class.getClassLoader();
            Class<?> entityClass = Class.forName("net.minecraft.world.entity.Entity", true, loader);
            Class<?> removalReason = Class.forName("net.minecraft.world.entity.Entity$RemovalReason", true, loader);
            Class<?> removalCause = Class.forName("org.bukkit.event.entity.EntityRemoveEvent$Cause", true, loader);
            Class<?> minecraftServer = Class.forName("net.minecraft.server.MinecraftServer", true, loader);
            Class<?> serverLevel = Class.forName("net.minecraft.server.level.ServerLevel", true, loader);
            Class<?> gameProfile = Class.forName("com.mojang.authlib.GameProfile", true, loader);
            Class<?> property = Class.forName("com.mojang.authlib.properties.Property", true, loader);
            Class<?> propertyMap = Class.forName("com.mojang.authlib.properties.PropertyMap", true, loader);
            Class<?> multimap = Class.forName("com.google.common.collect.Multimap", true, loader);
            Class<?> hashMultimap = Class.forName("com.google.common.collect.HashMultimap", true, loader);
            Class<?> clientInformation = Class.forName("net.minecraft.server.level.ClientInformation", true, loader);
            Class<?> serverPlayer = Class.forName("net.minecraft.server.level.ServerPlayer", true, loader);
            Class<?> packetFlow = Class.forName("net.minecraft.network.protocol.PacketFlow", true, loader);
            Class<?> connection = Class.forName("net.minecraft.network.Connection", true, loader);
            Class<?> commonCookie = Class.forName("net.minecraft.server.network.CommonListenerCookie", true, loader);
            Class<?> serverListener = Class.forName(
                    "net.minecraft.server.network.ServerGamePacketListenerImpl",
                    true,
                    loader
            );
            Class<?> packet = Class.forName("net.minecraft.network.protocol.Packet", true, loader);
            Class<?> playerInfo = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket",
                    true,
                    loader
            );
            Class<?> playerInfoAction = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket$Action",
                    true,
                    loader
            );
            Class<?> playerInfoRemove = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundPlayerInfoRemovePacket",
                    true,
                    loader
            );
            Class<?> entityType = Class.forName("net.minecraft.world.entity.EntityType", true, loader);
            Class<?> vec3 = Class.forName("net.minecraft.world.phys.Vec3", true, loader);
            Class<?> entityData = Class.forName("net.minecraft.network.syncher.SynchedEntityData", true, loader);
            Class<?> addEntity = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundAddEntityPacket",
                    true,
                    loader
            );
            Class<?> setEntityData = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundSetEntityDataPacket",
                    true,
                    loader
            );
            Class<?> rotateHead = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundRotateHeadPacket",
                    true,
                    loader
            );
            Class<?> removeEntities = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundRemoveEntitiesPacket",
                    true,
                    loader
            );

            Object serverbound = Enum.valueOf(
                    (Class<? extends Enum>) packetFlow.asSubclass(Enum.class),
                    "SERVERBOUND"
            );
            Object addPlayer = Enum.valueOf(
                    (Class<? extends Enum>) playerInfoAction.asSubclass(Enum.class),
                    "ADD_PLAYER"
            );

            return new RuntimeBridge(
                    entityClass,
                    minecraftServer,
                    gameProfile.getConstructor(UUID.class, String.class, propertyMap),
                    propertyMap.getConstructor(multimap),
                    hashMultimap.getMethod("create"),
                    property.getConstructor(String.class, String.class),
                    multimap.getMethod("put", Object.class, Object.class),
                    clientInformation.getMethod("createDefault"),
                    serverPlayer.getConstructor(minecraftServer, serverLevel, gameProfile, clientInformation),
                    entityClass.getMethod("getBukkitEntity"),
                    packetFlow,
                    serverbound,
                    connection.getConstructor(packetFlow),
                    commonCookie.getMethod("createInitial", gameProfile, boolean.class),
                    serverListener.getConstructor(minecraftServer, connection, serverPlayer, commonCookie),
                    serverPlayer.getField("connection"),
                    serverPlayer.getField("suppressTrackerForLogin"),
                    entityClass.getMethod("setPos", double.class, double.class, double.class),
                    entityClass.getMethod("setYRot", float.class),
                    entityClass.getMethod("setXRot", float.class),
                    entityClass.getMethod("setYHeadRot", float.class),
                    serverLevel.getMethod("addFreshEntity", entityClass, CreatureSpawnEvent.SpawnReason.class),
                    packet,
                    playerInfo.getConstructor(playerInfoAction, serverPlayer),
                    addPlayer,
                    playerInfo.getMethod("updateListed", UUID.class, boolean.class),
                    playerInfoRemove.getConstructor(List.class),
                    addEntity.getConstructor(
                            int.class,
                            UUID.class,
                            double.class,
                            double.class,
                            double.class,
                            float.class,
                            float.class,
                            entityType,
                            int.class,
                            vec3,
                            double.class
                    ),
                    setEntityData.getConstructor(int.class, List.class),
                    rotateHead.getConstructor(entityClass, byte.class),
                    removeEntities.getConstructor(int[].class),
                    entityClass.getMethod("getId"),
                    entityClass.getMethod("getUUID"),
                    entityClass.getMethod("getX"),
                    entityClass.getMethod("getY"),
                    entityClass.getMethod("getZ"),
                    entityClass.getMethod("getXRot"),
                    entityClass.getMethod("getYRot"),
                    entityClass.getMethod("getYHeadRot"),
                    entityClass.getMethod("getType"),
                    entityClass.getMethod("getDeltaMovement"),
                    entityClass.getMethod("getEntityData"),
                    entityData.getMethod("packAll"),
                    entityClass.getMethod("remove", removalReason, removalCause),
                    Enum.valueOf((Class<? extends Enum>) removalReason.asSubclass(Enum.class), "DISCARDED"),
                    Enum.valueOf((Class<? extends Enum>) removalCause.asSubclass(Enum.class), "PLUGIN"),
                    serverListener.getMethod("send", packet)
            );
        }
    }
}
