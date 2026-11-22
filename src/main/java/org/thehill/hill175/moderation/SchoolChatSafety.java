package org.thehill.hill175.moderation;

import io.papermc.paper.block.TileStateInventoryHolder;
import io.papermc.paper.event.player.AsyncChatEvent;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.TextComponent;
import net.kyori.adventure.text.flattener.ComponentFlattener;
import net.kyori.adventure.text.flattener.FlattenerListener;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.Style;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.Bukkit;
import org.bukkit.Nameable;
import org.bukkit.block.BlockState;
import org.bukkit.block.Sign;
import org.bukkit.block.sign.Side;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.SignChangeEvent;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.event.inventory.InventoryCreativeEvent;
import org.bukkit.event.inventory.PrepareAnvilEvent;
import org.bukkit.event.player.PlayerEditBookEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.BlockStateMeta;
import org.bukkit.inventory.meta.BookMeta;
import org.bukkit.inventory.meta.BundleMeta;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.inventory.view.AnvilView;
import org.bukkit.plugin.java.JavaPlugin;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public final class SchoolChatSafety implements Listener {
    private static final PlainTextComponentSerializer PLAIN = PlainTextComponentSerializer.plainText();
    private static final String CLEAN_FEEDBACK = "Please use school-appropriate wording. Your text was not shared.";
    private static final String UNAVAILABLE_FEEDBACK = "Chat safety is temporarily unavailable. Please try again later.";
    private static final String ITEM_FEEDBACK = "This item could not pass the school text safety check. It was not accepted.";
    private static final long FEEDBACK_INTERVAL = Duration.ofSeconds(2).toNanos();
    private static final int MAX_ITEM_DEPTH = 8;
    private static final int MAX_ITEM_POSITIONS = 256;
    private static final int MAX_ITEM_TEXT_FIELDS = 1024;
    private static final int MAX_ITEM_COMPONENTS = 4096;
    private static final ComponentFlattener ITEM_FLATTENER = ComponentFlattener.builder()
            .mapper(TextComponent.class, TextComponent::content)
            .nestingLimit(32)
            .unknownMapper(component -> {
                throw new IllegalArgumentException("Item text component cannot be inspected.");
            })
            .build();

    private final JavaPlugin plugin;
    private final Predicate<Player> authenticated;
    private final boolean enabled;
    private final int maxTextLength;
    private final ProfanityMatcher matcher;
    private final Map<UUID, Long> lastFeedback = new ConcurrentHashMap<>();

    public SchoolChatSafety(JavaPlugin plugin, Predicate<Player> authenticated) {
        this.plugin = Objects.requireNonNull(plugin);
        this.authenticated = Objects.requireNonNull(authenticated);
        FileConfiguration config = plugin.getConfig();
        enabled = config.getBoolean("moderation.enabled", true);
        maxTextLength = config.getInt("moderation.max-text-length", 65536);
        ProfanityMatcher loaded = null;
        if (enabled) {
            try {
                int minimumRating = config.getInt("moderation.minimum-rating", 2);
                if (minimumRating < 1 || minimumRating > 2 || maxTextLength < 256 || maxTextLength > 131072) {
                    throw new IllegalArgumentException("Moderation configuration limits are invalid.");
                }
                List<String> terms = new ArrayList<>(CussVocabulary.load(plugin, minimumRating));
                terms.addAll(config.getStringList("moderation.additions"));
                loaded = new ProfanityMatcher(terms, config.getStringList("moderation.allowlist"), maxTextLength);
            } catch (IOException | IllegalArgumentException | IllegalStateException exception) {
                plugin.getLogger().severe("School chat safety could not load its local rules. Public text is blocked until configuration/resources are repaired and the plugin restarts.");
            }
        } else {
            plugin.getLogger().warning("School chat safety is explicitly disabled. Public text is not profanity-filtered.");
        }
        matcher = loaded;
    }

    public boolean allows(String text) {
        return !enabled || (matcher != null && matcher.allows(text));
    }

    public void requireClean(String text) {
        if (!allows(text)) {
            throw new IllegalArgumentException(matcher == null ? UNAVAILABLE_FEEDBACK : CLEAN_FEEDBACK);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onChat(AsyncChatEvent event) {
        if (!authenticated.test(event.getPlayer())) {
            return;
        }
        if (!allows(plain(event.message()))) {
            event.setCancelled(true);
            feedback(event.getPlayer(), rejectionFeedback());
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onSign(SignChangeEvent event) {
        String text = event.lines().stream().map(SchoolChatSafety::plain).collect(Collectors.joining("\n"));
        if (rejectEdit(event.getPlayer(), text)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onBook(PlayerEditBookEvent event) {
        BookMeta meta = event.getNewBookMeta();
        String text = plain(meta.title()) + "\n"
                + meta.pages().stream().map(SchoolChatSafety::plain).collect(Collectors.joining("\n"));
        if (rejectEdit(event.getPlayer(), text)) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST)
    public void onAnvilPrepare(PrepareAnvilEvent event) {
        if (!(event.getView().getPlayer() instanceof Player player)) {
            return;
        }
        if (rejectAnvil(player, event.getView(), event.getResult())) {
            event.setResult(null);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onAnvilTake(InventoryClickEvent event) {
        if (event.getRawSlot() != 2 || !(event.getView() instanceof AnvilView view)
                || !(event.getWhoClicked() instanceof Player player)) {
            return;
        }
        if (rejectAnvil(player, view, event.getCurrentItem())) {
            event.setCancelled(true);
        }
    }

    @EventHandler(priority = EventPriority.HIGHEST, ignoreCancelled = true)
    public void onCreativeItem(InventoryCreativeEvent event) {
        if (event.getWhoClicked() instanceof Player player && rejectItem(player, event.getCursor())) {
            event.setCancelled(true);
        }
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        lastFeedback.remove(event.getPlayer().getUniqueId());
    }

    private boolean rejectAnvil(Player player, AnvilView view, ItemStack result) {
        return rejectEdit(player, view.getRenameText()) || rejectItem(player, result);
    }

    private boolean rejectItem(Player player, ItemStack item) {
        if (!authenticated.test(player)) {
            feedback(player, "Authenticate before editing public text.");
            return true;
        }
        if (!enabled) {
            return false;
        }
        if (matcher == null) {
            feedback(player, UNAVAILABLE_FEEDBACK);
            return true;
        }
        try {
            ItemInspection inspection = new ItemInspection(maxTextLength);
            inspectItem(item, 0, inspection);
            if (allows(inspection.text.toString())) {
                return false;
            }
        } catch (RuntimeException exception) {
            feedback(player, ITEM_FEEDBACK);
            return true;
        }
        feedback(player, ITEM_FEEDBACK);
        return true;
    }

    private static void inspectItem(ItemStack item, int depth, ItemInspection inspection) {
        if (--inspection.remainingPositions < 0) {
            throw new IllegalArgumentException("Item inspection position budget exceeded.");
        }
        if (item == null || item.getType().isAir()) {
            return;
        }
        if (depth > MAX_ITEM_DEPTH) {
            throw new IllegalArgumentException("Item inspection nesting budget exceeded.");
        }
        if (!item.hasItemMeta()) {
            return;
        }
        ItemMeta meta = Objects.requireNonNull(item.getItemMeta());
        inspection.add(meta.displayName());
        if (meta.hasItemName()) {
            inspection.add(Objects.requireNonNull(meta.itemName()));
        }
        List<Component> lore = meta.lore();
        if (lore != null) {
            for (Component line : lore) {
                inspection.add(Objects.requireNonNull(line));
            }
        }
        if (meta instanceof BookMeta book) {
            inspection.add(book.title());
            inspection.add(book.author());
            for (Component page : book.pages()) {
                inspection.add(Objects.requireNonNull(page));
            }
        }
        if (meta instanceof BundleMeta bundle) {
            for (ItemStack nested : bundle.getItems()) {
                inspectItem(nested, depth + 1, inspection);
            }
        }
        if (meta instanceof BlockStateMeta blockMeta) {
            BlockState state = Objects.requireNonNull(blockMeta.getBlockState());
            if (state instanceof Nameable nameable) {
                inspection.add(nameable.customName());
            }
            if (state instanceof Sign sign) {
                for (Side side : Side.values()) {
                    for (Component line : sign.getSide(side).lines()) {
                        inspection.add(Objects.requireNonNull(line));
                    }
                }
            }
            if (state instanceof TileStateInventoryHolder holder) {
                Inventory snapshot = Objects.requireNonNull(holder.getSnapshotInventory());
                int size = snapshot.getSize();
                if (size < 0 || size > inspection.remainingPositions) {
                    throw new IllegalArgumentException("Item inspection inventory budget exceeded.");
                }
                for (int slot = 0; slot < size; slot++) {
                    inspectItem(snapshot.getItem(slot), depth + 1, inspection);
                }
            }
        }
    }

    private static final class ItemInspection implements FlattenerListener {
        private final StringBuilder text = new StringBuilder();
        private final int maxLength;
        private int remainingPositions = MAX_ITEM_POSITIONS;
        private int remainingFields = MAX_ITEM_TEXT_FIELDS;
        private int remainingComponents = MAX_ITEM_COMPONENTS;
        private int componentDepth;

        private ItemInspection(int maxLength) {
            this.maxLength = maxLength;
        }

        private void add(Component component) {
            if (component == null) {
                return;
            }
            if (--remainingFields < 0) {
                throw new IllegalArgumentException("Item inspection text field budget exceeded.");
            }
            if (!text.isEmpty()) {
                component("\n");
            }
            ITEM_FLATTENER.flatten(component, this);
        }

        @Override
        public void pushStyle(Style style) {
            if (--remainingComponents < 0 || ++componentDepth > 32) {
                throw new IllegalArgumentException("Item inspection text component budget exceeded.");
            }
            if (style.hoverEvent() != null || style.clickEvent() != null || style.insertion() != null) {
                throw new IllegalArgumentException("Interactive item text is not accepted.");
            }
        }

        @Override
        public void popStyle(Style style) {
            componentDepth--;
        }

        @Override
        public void component(String value) {
            if (value.length() > maxLength - text.length()) {
                throw new IllegalArgumentException("Item inspection text budget exceeded.");
            }
            text.append(value);
        }
    }

    private boolean rejectEdit(Player player, String text) {
        if (!authenticated.test(player)) {
            feedback(player, "Authenticate before editing public text.");
            return true;
        }
        if (!allows(text)) {
            feedback(player, rejectionFeedback());
            return true;
        }
        return false;
    }

    private String rejectionFeedback() {
        return matcher == null && enabled ? UNAVAILABLE_FEEDBACK : CLEAN_FEEDBACK;
    }

    private void feedback(Player player, String message) {
        UUID id = player.getUniqueId();
        long now = System.nanoTime();
        Long previous = lastFeedback.get(id);
        if (previous != null && now - previous < FEEDBACK_INTERVAL) {
            return;
        }
        lastFeedback.put(id, now);
        Runnable send = () -> {
            if (player.isOnline()) {
                player.sendMessage(Component.text(message, NamedTextColor.RED));
            }
        };
        if (Bukkit.isPrimaryThread()) {
            send.run();
        } else {
            plugin.getServer().getScheduler().runTask(plugin, send);
        }
    }

    private static String plain(Component component) {
        return component == null ? "" : PLAIN.serialize(component);
    }
}
