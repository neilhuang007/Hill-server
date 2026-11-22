package org.thehill.hill175.replay;

import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Collection;
import java.util.EnumSet;
import java.util.Map;
import java.util.UUID;
import java.util.function.Consumer;

/** Exact Paper 26.2 pairing snapshot; writes only to the recorder, never the live connection. */
final class PacketReplayBootstrap {
    private final Object manager;
    private final Field active;
    private final Object adapter;
    private final Method translatorFor;
    private final Method expand;
    private final Method encode;
    private final Method refused;
    private final Class<?> serverPlayer;
    private final Class<?> playerInfo;
    private final Class<? extends Enum> infoAction;

    @SuppressWarnings("unchecked")
    PacketReplayBootstrap(Plugin upstream, Object manager) throws ReflectiveOperationException {
        this.manager = manager;
        ClassLoader loader = upstream.getClass().getClassLoader();
        active = manager.getClass().getDeclaredField("active");
        active.setAccessible(true);
        adapter = Class.forName("dev.zeffut.flashbackserver.version.VersionAdapters", true, loader).getMethod("current").invoke(null);
        Class<?> versionAdapter = Class.forName("dev.zeffut.flashbackserver.version.VersionAdapter", true, loader);
        translatorFor = versionAdapter.getMethod("translatorFor", Player.class);
        Class<?> translator = Class.forName("dev.zeffut.flashbackserver.version.PacketTranslator", true, loader);
        expand = translator.getMethod("expand", Object.class);
        encode = translator.getMethod("encode", Object.class);
        refused = Class.forName("dev.zeffut.flashbackserver.capture.RefusedPackets", true, loader).getMethod("isRefused", String.class);
        serverPlayer = Class.forName("net.minecraft.server.level.ServerPlayer", true, loader);
        playerInfo = Class.forName("net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket", true, loader);
        infoAction = (Class<? extends Enum>) Class.forName("net.minecraft.network.protocol.game.ClientboundPlayerInfoUpdatePacket$Action", true, loader);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    int capture(Player viewer) throws ReflectiveOperationException {
        Object session = ((Map<UUID, ?>) active.get(manager)).get(viewer.getUniqueId());
        if (session == null) throw new IllegalStateException("Native bootstrap has no active recorder");
        Method accessor = session.getClass().getDeclaredMethod("recorder");
        accessor.setAccessible(true);
        Object recorder = accessor.invoke(session);
        Method onPacket = recorder.getClass().getMethod("onPacket", byte[].class);
        Object translator = translatorFor.invoke(adapter, viewer);
        Object viewerHandle = viewer.getClass().getMethod("getHandle").invoke(viewer);
        Consumer<Object> sink = packet -> {
            try {
                for (Object part : (Collection<?>) expand.invoke(translator, packet)) {
                    if (Boolean.TRUE.equals(refused.invoke(null, part.getClass().getName()))) continue;
                    byte[] bytes = (byte[]) encode.invoke(translator, part);
                    if (bytes == null || bytes.length == 0) throw new IllegalStateException("Native pairing packet could not be encoded");
                    onPacket.invoke(recorder, (Object) bytes);
                }
            } catch (ReflectiveOperationException error) { throw new IllegalStateException("Native pairing capture failed", error); }
        };
        int captured = 0;
        for (Entity entity : viewer.getWorld().getEntities()) {
            if (!mayCapture(viewer, entity)) continue;
            Object handle = entity.getClass().getMethod("getHandle").invoke(entity);
            Object tracked = handle.getClass().getMethod("moonrise$getTrackedEntity").invoke(handle);
            if (tracked == null) throw new IllegalStateException("Visible tracked entity has no native pairing state");
            if (entity instanceof Player) {
                EnumSet actions = EnumSet.of(Enum.valueOf(infoAction, "ADD_PLAYER"), Enum.valueOf(infoAction, "UPDATE_LISTED"));
                Object info = playerInfo.getConstructor(EnumSet.class, Collection.class).newInstance(actions, java.util.List.of(handle));
                sink.accept(info);
            }
            Object serverEntity = tracked.getClass().getField("serverEntity").get(tracked);
            serverEntity.getClass().getMethod("sendPairingData", serverPlayer, Consumer.class).invoke(serverEntity, viewerHandle, sink);
            captured++;
        }
        return captured;
    }

    static boolean mayCapture(Player viewer, Entity entity) {
        return entity != viewer && entity.getWorld().equals(viewer.getWorld()) && entity.getTrackedBy().contains(viewer) && viewer.canSee(entity);
    }
}
