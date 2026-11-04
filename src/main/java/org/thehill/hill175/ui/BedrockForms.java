package org.thehill.hill175.ui;

import org.bukkit.entity.Player;
import org.bukkit.plugin.IllegalPluginAccessException;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.java.JavaPlugin;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;
import java.util.function.IntConsumer;
import java.util.logging.Level;

/** Optional public Floodgate/Cumulus bridge. No transport identity is inferred from a name. */
public final class BedrockForms implements AutoCloseable {
    public static final String mapTitle = "Hill Campus Map";
    private final JavaPlugin plugin;
    private final FormTransport transport;
    private final Map<UUID, PendingForm> activeForms = new ConcurrentHashMap<>();
    private volatile boolean isClosed;

    public BedrockForms(JavaPlugin plugin) {
        this(plugin, loadTransport(plugin));
    }

    BedrockForms(JavaPlugin plugin, FormTransport transport) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.transport = transport;
    }

    public boolean isBedrock(Player player) {
        return player != null && transport != null && transport.isBedrock(player.getUniqueId());
    }

    public boolean show(Player player, String title, String content, List<String> labels,
                        IntConsumer response, Runnable close) {
        requireTitle(title);
        List<String> buttons = List.copyOf(labels);
        Objects.requireNonNull(response, "response");
        Objects.requireNonNull(close, "close");
        if (buttons.isEmpty()) throw new IllegalArgumentException("A button form needs at least one button.");
        PendingForm pending = begin(player);
        if (pending == null) return false;
        return send(pending, () -> transport.show(player.getUniqueId(), title,
                Objects.requireNonNullElse(content, ""), buttons,
                index -> dispatch(pending, () -> {
                    if (index >= 0 && index < buttons.size()) response.accept(index);
                    else close.run();
                }), () -> dispatch(pending, close)));
    }

    /** Native CustomForm inputs use Bedrock's Submit action; supplied limits are enforced on the server. */
    public boolean showFields(Player player, String title, String content, List<Field> fields,
                              Consumer<List<String>> response, Runnable close) {
        requireTitle(title);
        List<Field> inputs = List.copyOf(fields);
        Objects.requireNonNull(response, "response");
        Objects.requireNonNull(close, "close");
        if (inputs.isEmpty() || inputs.stream().map(Field::name).distinct().count() != inputs.size()) {
            throw new IllegalArgumentException("A field form needs uniquely named fields.");
        }
        PendingForm pending = begin(player);
        if (pending == null) return false;
        String instructions = Objects.requireNonNullElse(content, "") + "\nChoose Submit to save your changes.";
        return send(pending, () -> transport.showFields(player.getUniqueId(), title, instructions, inputs,
                values -> dispatch(pending, () -> acceptFields(player, inputs, values, response, close)),
                () -> dispatch(pending, close)));
    }

    public void clear(Player player) {
        if (player != null && activeForms.remove(player.getUniqueId()) != null) closeForm(player.getUniqueId());
    }

    @Override
    public void close() {
        isClosed = true;
        List<UUID> players = List.copyOf(activeForms.keySet());
        activeForms.clear();
        players.forEach(this::closeForm);
    }

    private PendingForm begin(Player player) {
        if (isClosed || player == null || !player.isOnline() || !isBedrock(player)) return null;
        PendingForm pending = new PendingForm(player);
        if (activeForms.put(player.getUniqueId(), pending) != null) closeForm(player.getUniqueId());
        return pending;
    }

    private boolean send(PendingForm pending, java.util.function.BooleanSupplier sender) {
        try {
            if (sender.getAsBoolean()) return true;
            activeForms.remove(pending.player().getUniqueId(), pending);
            plugin.getLogger().warning("Floodgate declined a Hill175 form for an online Bedrock player.");
            return false;
        } catch (RuntimeException exception) {
            activeForms.remove(pending.player().getUniqueId(), pending);
            throw exception;
        }
    }

    private void dispatch(PendingForm pending, Runnable callback) {
        if (isClosed || !plugin.isEnabled()) return;
        try {
            plugin.getServer().getScheduler().runTask(plugin, () -> complete(pending, callback));
        } catch (IllegalPluginAccessException exception) {
            if (!isClosed && plugin.isEnabled()) throw exception;
        }
    }

    private void complete(PendingForm pending, Runnable callback) {
        Player player = pending.player();
        if (isClosed || !plugin.isEnabled() || !activeForms.remove(player.getUniqueId(), pending)) return;
        if (!player.isOnline() || plugin.getServer().getPlayer(player.getUniqueId()) != player) return;
        callback.run();
    }

    private static void acceptFields(Player player, List<Field> fields, List<String> values,
                                     Consumer<List<String>> response, Runnable close) {
        if (values.size() != fields.size()) {
            close.run();
            return;
        }
        for (int index = 0; index < fields.size(); index++) {
            Field field = fields.get(index);
            if (values.get(index) == null || values.get(index).length() > field.maxLength()) {
                player.sendMessage("Keep " + field.label() + " to " + field.maxLength() + " characters, then try again.");
                close.run();
                return;
            }
        }
        response.accept(List.copyOf(values));
    }

    private void closeForm(UUID playerId) {
        try {
            transport.close(playerId);
        } catch (RuntimeException exception) {
            plugin.getLogger().log(Level.WARNING, "Could not close a Hill175 Bedrock form.", exception);
        }
    }

    private static FormTransport loadTransport(JavaPlugin plugin) {
        Plugin floodgate = plugin.getServer().getPluginManager().getPlugin("floodgate");
        if (floodgate == null) return null;
        if (!floodgate.isEnabled()) {
            throw new IllegalStateException("Installed Floodgate must be enabled before Hill175 forms start.");
        }
        try {
            return new FloodgateTransport(floodgate.getClass().getClassLoader());
        } catch (ReflectiveOperationException | LinkageError exception) {
            throw new IllegalStateException("Installed Floodgate has an unsupported public forms API.", exception);
        }
    }

    private static void requireTitle(String title) {
        if (title == null || title.isBlank()) throw new IllegalArgumentException("A form title is required.");
    }

    public record Field(String name, String label, String initial, int maxLength) {
        public Field {
            if (name == null || name.isBlank() || label == null || label.isBlank() || maxLength < 1) {
                throw new IllegalArgumentException("A form field needs a name, label and positive length limit.");
            }
            initial = Objects.requireNonNullElse(initial, "");
            if (initial.length() > maxLength) throw new IllegalArgumentException("Initial field value exceeds its limit.");
        }
    }

    // Identity equality is intentional: opening an identical form invalidates every earlier response.
    private static final class PendingForm {
        private final Player player;
        private PendingForm(Player player) { this.player = player; }
        private Player player() { return player; }
    }

    interface FormTransport {
        boolean isBedrock(UUID playerId);
        boolean show(UUID playerId, String title, String content, List<String> buttons,
                     IntConsumer response, Runnable close);
        boolean showFields(UUID playerId, String title, String content, List<Field> fields,
                           Consumer<List<String>> response, Runnable close);
        void close(UUID playerId);
    }

    private static final class FloodgateTransport implements FormTransport {
        private final Object api;
        private final Method isBedrock;
        private final Method sendForm;
        private final Method closeForm;
        private final Method simpleBuilder;
        private final Method customBuilder;
        private final Method title;
        private final Method content;
        private final Method button;
        private final Method label;
        private final Method input;
        private final Method build;
        private final Method validHandler;
        private final Method closeHandler;
        private final Method clickedButtonId;
        private final Method inputAt;

        private FloodgateTransport(ClassLoader loader) throws ReflectiveOperationException {
            Class<?> apiType = load(loader, "org.geysermc.floodgate.api.FloodgateApi");
            Class<?> formType = load(loader, "org.geysermc.cumulus.form.Form");
            Class<?> builderType = load(loader, "org.geysermc.cumulus.form.util.FormBuilder");
            Class<?> simpleType = load(loader, "org.geysermc.cumulus.form.SimpleForm");
            Class<?> customType = load(loader, "org.geysermc.cumulus.form.CustomForm");
            api = apiType.getMethod("getInstance").invoke(null);
            if (api == null) throw new IllegalStateException("Floodgate's forms API is unavailable.");
            isBedrock = apiType.getMethod("isFloodgatePlayer", UUID.class);
            sendForm = apiType.getMethod("sendForm", UUID.class, formType);
            closeForm = apiType.getMethod("closeForm", UUID.class);
            simpleBuilder = simpleType.getMethod("builder");
            customBuilder = customType.getMethod("builder");
            title = builderType.getMethod("title", String.class);
            build = builderType.getMethod("build");
            validHandler = builderType.getMethod("validResultHandler", Consumer.class);
            closeHandler = builderType.getMethod("closedOrInvalidResultHandler", Runnable.class);
            content = simpleBuilder.getReturnType().getMethod("content", String.class);
            button = simpleBuilder.getReturnType().getMethod("button", String.class);
            label = customBuilder.getReturnType().getMethod("label", String.class);
            input = customBuilder.getReturnType().getMethod("input", String.class, String.class, String.class);
            clickedButtonId = load(loader, "org.geysermc.cumulus.response.SimpleFormResponse").getMethod("clickedButtonId");
            inputAt = load(loader, "org.geysermc.cumulus.response.CustomFormResponse").getMethod("asInput", int.class);
        }

        @Override
        public boolean isBedrock(UUID playerId) { return (boolean) invoke(isBedrock, api, playerId); }

        @Override
        public boolean show(UUID playerId, String formTitle, String formContent, List<String> buttons,
                            IntConsumer response, Runnable close) {
            Object builder = invoke(simpleBuilder, null);
            invoke(title, builder, formTitle);
            invoke(content, builder, formContent);
            buttons.forEach(text -> invoke(button, builder, text));
            return send(playerId, builder, value -> response.accept((int) invoke(clickedButtonId, value)), close);
        }

        @Override
        public boolean showFields(UUID playerId, String formTitle, String formContent, List<Field> fields,
                                  Consumer<List<String>> response, Runnable close) {
            Object builder = invoke(customBuilder, null);
            invoke(title, builder, formTitle);
            invoke(label, builder, formContent);
            fields.forEach(field -> invoke(input, builder, field.label(), "", field.initial()));
            return send(playerId, builder, value -> response.accept(readFields(value, fields.size())), close);
        }

        private List<String> readFields(Object response, int fieldCount) {
            List<String> values = new ArrayList<>(fieldCount);
            for (int index = 0; index < fieldCount; index++) {
                values.add((String) invoke(inputAt, response, index + 1)); // The first component is the instruction label.
            }
            return values;
        }

        private boolean send(UUID playerId, Object builder, Consumer<Object> response, Runnable close) {
            invoke(validHandler, builder, response);
            invoke(closeHandler, builder, close);
            return (boolean) invoke(sendForm, api, playerId, invoke(build, builder));
        }

        @Override
        public void close(UUID playerId) { invoke(closeForm, api, playerId); }

        private static Class<?> load(ClassLoader loader, String name) throws ClassNotFoundException {
            return Class.forName(name, true, loader);
        }

        private static Object invoke(Method method, Object target, Object... arguments) {
            try {
                return method.invoke(target, arguments);
            } catch (ReflectiveOperationException exception) {
                throw new IllegalStateException("Floodgate could not perform " + method.getName() + ".", exception);
            }
        }
    }
}
