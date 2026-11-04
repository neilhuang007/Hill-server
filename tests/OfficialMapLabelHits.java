package org.thehill.smoke;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.blaze3d.font.GlyphBitmap;
import com.mojang.blaze3d.font.GlyphInfo;
import com.mojang.blaze3d.font.UnbakedGlyph;
import com.mojang.serialization.JsonOps;
import net.minecraft.client.StringSplitter;
import net.minecraft.client.gui.ActiveTextCollector;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GlyphSource;
import net.minecraft.client.gui.TextAlignment;
import net.minecraft.client.gui.components.FocusableTextWidget;
import net.minecraft.client.gui.font.TextRenderable;
import net.minecraft.client.gui.font.glyphs.BakedGlyph;
import net.minecraft.client.gui.font.glyphs.BakedSheetGlyph;
import net.minecraft.client.gui.font.glyphs.EffectGlyph;
import net.minecraft.client.gui.font.providers.GlyphProviderDefinition;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ComponentSerialization;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.FontDescription;
import net.minecraft.resources.Identifier;
import net.minecraft.nbt.NbtIo;
import net.minecraft.nbt.NbtOps;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import java.util.List;
import java.util.ArrayList;
import java.util.Optional;
import java.util.zip.ZipFile;

/** Checks actual bitmap providers, complete dialog widget geometry and native click handling. */
public final class OfficialMapLabelHits {
    public static void main(String[] arguments) throws Exception {
        if (arguments.length < 2 || arguments.length > 5) throw new IllegalArgumentException("Supply pack ZIP, campus-map-labels.json, optional outer widget width, trailing gap flag and capture folder.");
        int widgetWidth = arguments.length >= 3 ? Integer.parseInt(arguments[2]) : 370;
        boolean trailingGap = arguments.length >= 4 && Boolean.parseBoolean(arguments[3]);
        if (arguments.length == 5) {
            net.minecraft.SharedConstants.tryDetectVersion();
            net.minecraft.server.Bootstrap.bootStrap();
        }
        var manifest = JsonParser.parseString(Files.readString(Path.of(arguments[1]))).getAsJsonObject();
        String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-1").digest(Files.readAllBytes(Path.of(arguments[0]))));
        if (!hash.equals(manifest.get("packSha1").getAsString())) throw new AssertionError("Pack hash mismatch.");
        try (var pack = new ZipFile(arguments[0])) {
            var glyphs = loadGlyphMetrics(pack);
            var font = nativeFont(glyphs);
            for (String view : new String[]{"full", "core"}) {
                verifyView(font, manifest, view);
                verifyDialogLayout(font, manifest, view, widgetWidth, trailingGap);
                if (arguments.length == 5) verifyCapturedDialog(font, manifest, view, Path.of(arguments[4]));
            }
            System.out.println("Native bitmap metrics checked: " + glyphs.size() + " glyphs, ascent 7 and row height 9.");
        }
    }

    private static void verifyDialogLayout(Font font, JsonObject manifest, String name, int width, boolean trailingGap) {
        var view = manifest.getAsJsonObject("views").getAsJsonObject(name);
        var text = flatText(manifest, view, trailingGap);
        verifyDialogLayout(font, view, name, text, width, trailingGap ? 360 : 361, false);
    }

    private static void verifyDialogLayout(Font font, JsonObject view, String name, Component text, int width, int textWidth, boolean captured) {
        var widget = FocusableTextWidget.builder(text, font).maxWidth(width).alwaysShowBorder(false)
                .backgroundFill(FocusableTextWidget.BackgroundFill.NEVER).build().setCentered(true);
        var collector = new LayoutCollector(font);
        widget.visitLines(collector);
        System.out.println(name + " native plain_message outer limit " + width + ": " + collector.lines.size()
                + " rendered lines; widget " + widget.getWidth() + " by " + widget.getHeight());
        if (collector.lines.size() != 40) throw new AssertionError("Native dialog wraps the map into " + collector.lines.size() + " lines instead of 40.");
        int originX = widget.getWidth() / 2 - textWidth / 2;
        var actions = new HashMap<Integer, ClickEvent>();
        for (int index = 0; index < 40; index++) verifyRenderedRow(collector.lines.get(index), view.getAsJsonArray("rows").get(index).getAsJsonObject(), index, originX, textWidth, captured, actions);
        if (widget.getHeight() != 368) throw new AssertionError("Native padded map height is " + widget.getHeight() + ", expected 368.");
        verifyWholeWidgetHits(font, widget, view, originX, actions);
    }

    private static void verifyCapturedDialog(Font font, JsonObject manifest, String name, Path folder) throws Exception {
        var dialog = NbtIo.read(folder.resolve(name + "-dialog.nbt"));
        if (dialog == null) throw new AssertionError("Missing captured dialog.");
        var view = manifest.getAsJsonObject("views").getAsJsonObject(name);
        String firstGlyph = view.getAsJsonArray("rows").get(0).getAsJsonObject().getAsJsonArray("segments").get(0).getAsJsonObject().get("glyph").getAsString();
        for (var entry : dialog.getList("body").orElseThrow()) {
            var body = entry.asCompound().orElseThrow();
            if (!body.getStringOr("type", "").equals("minecraft:plain_message")) continue;
            var component = ComponentSerialization.CODEC.parse(NbtOps.INSTANCE, body.get("contents")).getOrThrow();
            if (!component.getString().contains(firstGlyph)) continue;
            verifyDialogLayout(font, view, name + " captured packet", component, body.getInt("width").orElseThrow(), 361, true);
            return;
        }
        throw new AssertionError("Captured dialog has no map plain_message body.");
    }

    private static Component flatText(JsonObject manifest, JsonObject view, boolean trailingGap) {
        var text = Component.empty().setStyle(Style.EMPTY.withFont(new FontDescription.Resource(Identifier.parse(manifest.get("font").getAsString())))
                .withColor(0xffffff).withoutShadow().withBold(false).withItalic(false));
        boolean first = true;
        for (var value : view.getAsJsonArray("rows")) {
            if (!first) text.append(Component.literal("\n"));
            first = false;
            var segments = value.getAsJsonObject().getAsJsonArray("segments");
            for (int partIndex = 0; partIndex < segments.size(); partIndex++) {
                var partValue = segments.get(partIndex);
                var part = partValue.getAsJsonObject();
                int number = part.get("label").getAsInt();
                var glyph = Component.literal(part.get("glyph").getAsString());
                if (number != 0) glyph.withStyle(Style.EMPTY.withClickEvent(new ClickEvent.RunCommand("/label " + number)));
                text.append(glyph);
                if (trailingGap || partIndex + 1 < segments.size()) text.append(Component.literal(manifest.get("gapGlyph").getAsString()));
            }
        }
        return text;
    }

    private static void verifyRenderedRow(RenderedLine line, JsonObject row, int index, int originX, int textWidth,
                                          boolean captured, Map<Integer, ClickEvent> actions) {
        if (line.width != textWidth || line.x != originX || line.y != 4 + index * 9) {
            throw new AssertionError("Native row " + index + " geometry differs: x=" + line.x + ", y=" + line.y + ", width=" + line.width);
        }
        var expected = row.getAsJsonArray("segments");
        if (line.glyphs.size() != expected.size()) throw new AssertionError("Native visual order changed glyph count.");
        for (int partIndex = 0; partIndex < expected.size(); partIndex++) {
            var part = expected.get(partIndex).getAsJsonObject();
            if (line.codepoints.get(partIndex) != part.get("glyph").getAsString().codePointAt(0)) throw new AssertionError("Native visual order moved image strips.");
            var glyph = line.glyphs.get(partIndex);
            float left = originX + part.get("x").getAsInt(), top = 4 + index * 9;
            if (glyph.left() != left || glyph.right() != left + part.get("width").getAsInt()
                    || glyph.top() != top || glyph.bottom() != top + 9) throw new AssertionError("Native bitmap rectangle differs at row " + index + ", segment " + partIndex);
            int number = part.get("label").getAsInt();
            var action = glyph.style().getClickEvent();
            boolean inactive = number == 0 || captured && number == 28;
            if (inactive && action != null || !inactive && action == null) throw new AssertionError("Native visual order changed click availability.");
            if (!captured && !inactive && !(action instanceof ClickEvent.RunCommand command && command.command().equals("/label " + number))) {
                throw new AssertionError("Native visual order changed inherited click style.");
            }
            if (captured && !inactive && !(action instanceof ClickEvent.Custom)) throw new AssertionError("Captured label has no server callback.");
            if (!inactive && actions.containsKey(number) && !actions.get(number).equals(action)) throw new AssertionError("A label has inconsistent callbacks across strips.");
            if (!inactive) actions.put(number, action);
            if (!glyph.style().getFont().equals(new FontDescription.Resource(Identifier.parse("hill175:campus/map_labels")))
                    || glyph.style().isBold() || glyph.style().isItalic() || glyph.style().getShadowColor() != 0) throw new AssertionError("Inherited map font style differs.");
        }
    }

    private static void verifyWholeWidgetHits(Font font, net.minecraft.client.gui.components.MultiLineTextWidget widget,
                                              JsonObject view, int originX, Map<Integer, ClickEvent> actions) {
        if (new java.util.HashSet<>(actions.values()).size() != actions.size()) throw new AssertionError("Distinct map labels share a callback.");
        for (var value : view.getAsJsonArray("labels")) {
            var label = value.getAsJsonObject();
            var finder = new ActiveTextCollector.ClickableStyleFinder(font, originX + (int) label.get("centerX").getAsDouble(), 4 + (int) label.get("centerY").getAsDouble());
            widget.visitLines(finder);
            var action = finder.result() == null ? null : finder.result().getClickEvent();
            if (!java.util.Objects.equals(action, actions.get(label.get("number").getAsInt()))) throw new AssertionError("Whole dialog click resolves to another label.");
        }
    }

    private record RenderedLine(int x, int y, int width, List<TextRenderable.Styled> glyphs, List<Integer> codepoints) {}

    private static final class LayoutCollector extends ActiveTextCollector.ClickableStyleFinder {
        private final Font font;
        private final List<RenderedLine> lines = new ArrayList<>();
        private LayoutCollector(Font font) { super(font, -1000, -1000); this.font = font; }
        @Override public void accept(TextAlignment alignment, int x, int y, ActiveTextCollector.Parameters parameters, net.minecraft.util.FormattedCharSequence sequence) {
            int left = alignment.calculateLeft(x, font, sequence);
            var glyphs = new ArrayList<TextRenderable.Styled>();
            var codepoints = new ArrayList<Integer>();
            sequence.accept((index, style, codepoint) -> { if (codepoint != 0xf8ff) codepoints.add(codepoint); return true; });
            font.prepareText(sequence, left, y, 0xffffffff, false, false, 0).visit(new Font.GlyphVisitor() {
                @Override public void acceptGlyph(TextRenderable.Styled glyph) { glyphs.add(glyph); }
            });
            lines.add(new RenderedLine(left, y, font.width(sequence), glyphs, codepoints));
        }
    }

    private static Map<Integer, BakedGlyph> loadGlyphMetrics(ZipFile pack) throws Exception {
        ResourceManager resources = (ResourceManager) Proxy.newProxyInstance(ResourceManager.class.getClassLoader(),
                new Class<?>[]{ResourceManager.class}, (proxy, method, arguments) -> {
                    if (method.isDefault()) return InvocationHandler.invokeDefault(proxy, method, arguments);
                    if (!method.getName().equals("getResource")) throw new UnsupportedOperationException(method.getName());
                    Identifier id = (Identifier) arguments[0];
                    var entry = pack.getEntry("assets/" + id.getNamespace() + "/" + id.getPath());
                    return entry == null ? Optional.empty() : Optional.of(new Resource(null, () -> pack.getInputStream(entry)));
                });
        var metrics = new HashMap<Integer, BakedGlyph>();
        var stitcher = new MetricStitcher();
        var font = read(pack, "assets/hill175/font/campus/map_labels.json");
        for (var value : font.getAsJsonArray("providers")) {
            var json = value.getAsJsonObject();
            var definition = GlyphProviderDefinition.MAP_CODEC.codec().parse(JsonOps.INSTANCE, json).getOrThrow();
            try (var provider = definition.unpack().left().orElseThrow().load(resources)) {
                for (int codepoint : provider.getSupportedGlyphs()) {
                    var glyph = provider.getGlyph(codepoint);
                    if (codepoint == 0xf8ff) {
                        if (glyph.info().getAdvance() != -1) throw new AssertionError("Gap advance must be -1.");
                    }
                    metrics.put(codepoint, glyph.bake(stitcher));
                }
            }
        }
        return metrics;
    }

    private static void verifyView(Font font, JsonObject manifest, String name) {
        StringSplitter splitter = font.getSplitter();
        var view = manifest.getAsJsonObject("views").getAsJsonObject(name);
        var rows = view.getAsJsonArray("rows");
        var textRows = new java.util.ArrayList<TextRow>();
        var completeText = Component.empty();
        int hits = 0, blankHits = 0;
        for (var rowValue : rows) {
            var row = rowValue.getAsJsonObject();
            var text = rowText(row, manifest.get("gapGlyph").getAsString());
            if (!textRows.isEmpty()) completeText.append("\n");
            completeText.append(text.text());
            textRows.add(text);
            if (splitter.stringWidth(text.text()) != 360) throw new AssertionError("Native row width is not 360.");
            for (var partValue : row.getAsJsonArray("segments")) {
                var part = partValue.getAsJsonObject();
                if (part.get("label").getAsInt() != 0 || part.get("width").getAsInt() <= 2) continue;
                int center = part.get("x").getAsInt() + part.get("width").getAsInt() / 2;
                if (clickAt(splitter, text, center) != null) throw new AssertionError("Blank artwork has a click action.");
                if (widgetClick(font, text, center, row.get("y").getAsInt() + 4, row.get("y").getAsInt()) != null) {
                    throw new AssertionError("Native widget resolves a blank segment to an action.");
                }
                blankHits++;
            }
        }
        if (splitter.splitLines(completeText, 362, Style.EMPTY).size() != 40) throw new AssertionError("Native wrapping must produce forty lines.");
        for (var value : view.getAsJsonArray("labels")) {
            var label = value.getAsJsonObject();
            int rowIndex = (int) label.get("centerY").getAsDouble() / 9;
            var action = clickAt(splitter, textRows.get(rowIndex), (int) label.get("centerX").getAsDouble());
            if (!(action instanceof ClickEvent.RunCommand command) || !command.command().equals("/label " + label.get("number").getAsInt())) {
                throw new AssertionError("Native label hit mismatch: " + label);
            }
            var widgetAction = widgetClick(font, textRows.get(rowIndex), (int) label.get("centerX").getAsDouble(),
                    (int) label.get("centerY").getAsDouble(), rowIndex * 9);
            if (!action.equals(widgetAction)) throw new AssertionError("Native ClickableStyleFinder selected another action: " + label);
            hits++;
        }
        System.out.println(name + ": " + hits + " label centers select their own ClickEvent; " + blankHits
                + " blank centers have no action; native widget hits agree; wrapping produces 40 lines.");
    }

    private static TextRow rowText(JsonObject row, String gap) {
        var text = Component.empty();
        var styles = new java.util.ArrayList<Style>();
        for (var partValue : row.getAsJsonArray("segments")) {
            var part = partValue.getAsJsonObject();
            int number = part.get("label").getAsInt();
            Style style = number == 0 ? Style.EMPTY : Style.EMPTY.withClickEvent(new ClickEvent.RunCommand("/label " + number));
            text.append(Component.literal(part.get("glyph").getAsString()).setStyle(style));
            text.append(Component.literal(gap).setStyle(Style.EMPTY));
            styles.add(style);
            styles.add(Style.EMPTY);
        }
        return new TextRow(text, styles);
    }

    private static ClickEvent clickAt(StringSplitter splitter, TextRow row, int x) {
        int index = splitter.plainIndexAtWidth(row.text().getString(), x, Style.EMPTY);
        return row.styles().get(index).getClickEvent();
    }

    private record TextRow(Component text, List<Style> styles) {}

    private static ClickEvent widgetClick(Font font, TextRow row, int x, int y, int rowY) {
        var finder = new ActiveTextCollector.ClickableStyleFinder(font, x, y);
        finder.accept(TextAlignment.LEFT, 0, rowY, row.text());
        return finder.result() == null ? null : finder.result().getClickEvent();
    }

    private static Font nativeFont(Map<Integer, BakedGlyph> glyphs) {
        var source = new GlyphSource() {
            @Override public BakedGlyph getGlyph(int codepoint) {
                if (codepoint == '\n') return new net.minecraft.client.gui.font.glyphs.EmptyGlyph(0).bake(new MetricStitcher());
                return java.util.Objects.requireNonNull(glyphs.get(codepoint), "Unknown glyph: " + codepoint);
            }
            @Override public BakedGlyph getRandomGlyph(net.minecraft.util.RandomSource random, int codepoint) { return getGlyph(codepoint); }
        };
        return new Font(new Font.Provider() {
            @Override public GlyphSource glyphs(FontDescription description) { return source; }
            @Override public EffectGlyph effect() { return new BakedSheetGlyph(GlyphInfo.simple(0), null, null, 0, 1, 0, 1, 0, 1, 0, 1); }
        });
    }

    private static JsonObject read(ZipFile pack, String path) throws Exception {
        try (var input = pack.getInputStream(pack.getEntry(path))) {
            return JsonParser.parseString(new String(input.readAllBytes(), StandardCharsets.UTF_8)).getAsJsonObject();
        }
    }

    private static final class MetricStitcher implements UnbakedGlyph.Stitcher {
        private net.minecraft.client.renderer.texture.DynamicAtlasTree atlas = new net.minecraft.client.renderer.texture.DynamicAtlasTree(0, 0, 256, 256);
        @Override public BakedGlyph stitch(GlyphInfo info, GlyphBitmap bitmap) {
            if (bitmap.getPixelHeight() != 9 || bitmap.getBearingTop() != 7 || bitmap.getOversample() != 1
                    || info.getAdvance() != bitmap.getPixelWidth() + 1 || bitmap.getTop() != 0 || bitmap.getBottom() != 9) {
                throw new AssertionError("Native glyph metrics differ from the declared row geometry.");
            }
            if (atlas.insert(bitmap.getPixelWidth(), bitmap.getPixelHeight(), 1) == null) {
                atlas = new net.minecraft.client.renderer.texture.DynamicAtlasTree(0, 0, 256, 256);
                if (atlas.insert(bitmap.getPixelWidth(), bitmap.getPixelHeight(), 1) == null) {
                    throw new AssertionError("Native font atlas cannot fit glyph " + bitmap.getPixelWidth() + " by " + bitmap.getPixelHeight());
                }
            }
            // Screen geometry uses the actual client glyph class. No GPU texture is uploaded in this headless check.
            return new BakedSheetGlyph(info, null, null, 0, 1, 0, 1,
                    bitmap.getLeft(), bitmap.getRight(), bitmap.getTop(), bitmap.getBottom());
        }
        @Override public BakedGlyph getMissing() { throw new AssertionError("A bitmap glyph was missing."); }
    }
}
