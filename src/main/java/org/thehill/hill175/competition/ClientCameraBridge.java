package org.thehill.hill175.competition;

import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.logging.Logger;

/**
 * Pinned Paper 26.2 bridge for Java's client camera packet.
 *
 * Bukkit only exposes spectator targeting, which also mutates server-side
 * spectator state. This bridge sends the same camera packet directly so the
 * player can stay in Adventure mode with Hill hotbar controls.
 */
final class ClientCameraBridge {
    private final boolean available;
    private final Method craftEntityGetHandle;
    private final Method craftPlayerGetHandle;
    private final Field serverPlayerConnection;
    private final Constructor<?> setCameraPacketConstructor;
    private final Method connectionSend;

    private ClientCameraBridge(
            boolean available,
            Method craftEntityGetHandle,
            Method craftPlayerGetHandle,
            Field serverPlayerConnection,
            Constructor<?> setCameraPacketConstructor,
            Method connectionSend
    ) {
        this.available = available;
        this.craftEntityGetHandle = craftEntityGetHandle;
        this.craftPlayerGetHandle = craftPlayerGetHandle;
        this.serverPlayerConnection = serverPlayerConnection;
        this.setCameraPacketConstructor = setCameraPacketConstructor;
        this.connectionSend = connectionSend;
    }

    static ClientCameraBridge create(JavaPlugin plugin) {
        try {
            ClassLoader loader = ClientCameraBridge.class.getClassLoader();
            Class<?> craftEntity = Class.forName("org.bukkit.craftbukkit.entity.CraftEntity", true, loader);
            Class<?> craftPlayer = Class.forName("org.bukkit.craftbukkit.entity.CraftPlayer", true, loader);
            Class<?> nmsEntity = Class.forName("net.minecraft.world.entity.Entity", true, loader);
            Class<?> serverPlayer = Class.forName("net.minecraft.server.level.ServerPlayer", true, loader);
            Class<?> packet = Class.forName("net.minecraft.network.protocol.Packet", true, loader);
            Class<?> setCameraPacket = Class.forName(
                    "net.minecraft.network.protocol.game.ClientboundSetCameraPacket",
                    true,
                    loader
            );
            Class<?> serverListener = Class.forName(
                    "net.minecraft.server.network.ServerGamePacketListenerImpl",
                    true,
                    loader
            );
            return new ClientCameraBridge(
                    true,
                    methodReturning(craftEntity, "getHandle", nmsEntity),
                    methodReturning(craftPlayer, "getHandle", serverPlayer),
                    serverPlayer.getField("connection"),
                    setCameraPacket.getConstructor(nmsEntity),
                    serverListener.getMethod("send", packet)
            );
        } catch (ReflectiveOperationException | LinkageError exception) {
            Logger logger = plugin.getLogger();
            if (logger != null) {
                logger.warning("Fixed camera packet bridge is unavailable; camera previews will fall back to player pose locking: "
                        + exception.getMessage());
            }
            return unavailable();
        }
    }

    boolean focus(Player viewer, Entity cameraTarget) {
        if (!available || viewer == null || cameraTarget == null || !viewer.isOnline()) {
            return false;
        }
        try {
            Object viewerHandle = craftPlayerGetHandle.invoke(viewer);
            Object targetHandle = craftEntityGetHandle.invoke(cameraTarget);
            Object packet = setCameraPacketConstructor.newInstance(targetHandle);
            Object connection = serverPlayerConnection.get(viewerHandle);
            connectionSend.invoke(connection, packet);
            return true;
        } catch (ReflectiveOperationException | RuntimeException exception) {
            return false;
        }
    }

    boolean reset(Player viewer) {
        return focus(viewer, viewer);
    }

    boolean isAvailable() {
        return available;
    }

    private static ClientCameraBridge unavailable() {
        return new ClientCameraBridge(false, null, null, null, null, null);
    }

    private static Method methodReturning(Class<?> owner, String name, Class<?> returnType) throws NoSuchMethodException {
        return Arrays.stream(owner.getMethods())
                .filter(method -> method.getName().equals(name))
                .filter(method -> method.getParameterCount() == 0)
                .filter(method -> method.getReturnType().equals(returnType))
                .findFirst()
                .orElseThrow(() -> new NoSuchMethodException(owner.getName() + "." + name
                        + " returning " + returnType.getName()));
    }
}
