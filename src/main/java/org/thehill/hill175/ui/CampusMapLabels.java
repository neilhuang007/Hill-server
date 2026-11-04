package org.thehill.hill175.ui;

import com.nimbusds.jose.util.JSONObjectUtils;
import net.kyori.adventure.key.Key;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.event.HoverEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.ShadowColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.world.BuildingCatalog;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.ParseException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

/** Separates school illustration hit regions from reviewed Minecraft destinations. */
public final class CampusMapLabels {
    static final int imageWidth = 360;
    // Native plain_message widgets reserve four pixels on each side. The two extra text
    // pixels let a bitmap glyph advance before its following negative spacing glyph.
    static final int dialogBodyPadding = 4;
    static final int dialogBodyWidth = imageWidth + 2 + 2 * dialogBodyPadding;
    static final int imageHeight = 360;
    static final int rowHeight = 9;
    static final String fontName = "hill175:campus/map_labels";
    static final String gapGlyph = "\uF8FF";
    private final Map<Integer, Destination> destinations;
    private final Map<String, Artwork> views;
    private final String packSha1;
    private final String artworkWarning;

    private CampusMapLabels(Map<Integer, Destination> destinations, Map<String, Artwork> views,
                            String packSha1, String artworkWarning) {
        this.destinations = Map.copyOf(destinations);
        this.views = Map.copyOf(views);
        this.packSha1 = packSha1;
        this.artworkWarning = artworkWarning;
    }

    /** Closes the bundled stream. Invalid destinations fail; optional artwork safely falls back. */
    public static CampusMapLabels load(Path assetDirectory, InputStream bundledDestinations,
                                       BuildRegion bounds, List<BuildingCatalog.Building> buildings) throws IOException {
        Objects.requireNonNull(assetDirectory);
        Objects.requireNonNull(bounds);
        Map<Integer, Destination> destinations;
        try (InputStream input = bundledDestinations) {
            if (input == null) throw invalid("Bundled campus map destinations are missing.");
            destinations = readDestinations(readJson(input, 256 * 1024), bounds, buildings);
        }
        try {
            Map<String, Object> manifest = readAsset(assetDirectory, "campus-map-labels.json", 2 * 1024 * 1024);
            String hash = verifyPack(assetDirectory, manifest);
            return new CampusMapLabels(destinations, readViews(manifest, destinations), hash, null);
        } catch (IOException exception) {
            return new CampusMapLabels(destinations, Map.of(), null, exception.getMessage());
        }
    }

    public List<Destination> destinations() {
        return destinations.values().stream().sorted(Comparator.comparingInt(Destination::number)).toList();
    }

    public Optional<Destination> destination(int number) { return Optional.ofNullable(destinations.get(number)); }
    public Optional<String> artworkWarning() { return Optional.ofNullable(artworkWarning); }
    public boolean matchesPack(String offeredSha1) { return !views.isEmpty() && packSha1.equals(offeredSha1); }

    public Component render(String viewName, Function<Destination, ClickEvent<?>> callback) {
        Artwork view = views.get(viewName);
        if (view == null) throw new IllegalArgumentException("Unknown campus map view: " + viewName);
        Objects.requireNonNull(callback);
        var image = Component.text().font(Key.key(fontName)).color(NamedTextColor.WHITE)
                .shadowColor(ShadowColor.none()).decoration(TextDecoration.BOLD, false).decoration(TextDecoration.ITALIC, false);
        Map<Integer, ClickEvent<?>> actions = new HashMap<>();
        for (int index = 0; index < view.rows.size(); index++) {
            if (index > 0) image.append(Component.newline());
            List<Segment> segments = view.rows.get(index).segments;
            for (int part = 0; part < segments.size(); part++) {
                // Keep the final bitmap advance so the native height calculation does not wrap the row again.
                if (part > 0) image.append(Component.text(gapGlyph));
                image.append(segmentText(segments.get(part), callback, actions));
            }
        }
        return image.build();
    }

    private Component segmentText(Segment segment, Function<Destination, ClickEvent<?>> callback,
                                  Map<Integer, ClickEvent<?>> actions) {
        Component glyph = Component.text(segment.glyph);
        if (segment.label == 0) return glyph;
        Destination destination = destinations.get(segment.label);
        Component hover = Component.text(destination.tooltip(), NamedTextColor.WHITE).font(Key.key("minecraft:default"))
                .decoration(TextDecoration.ITALIC, false);
        glyph = glyph.hoverEvent(HoverEvent.showText(hover));
        if (!destination.available()) return glyph;
        return glyph.clickEvent(actions.computeIfAbsent(destination.number(), ignored -> Objects.requireNonNull(callback.apply(destination))));
    }

    private static Map<Integer, Destination> readDestinations(Map<String, Object> data, BuildRegion bounds,
                                                             List<BuildingCatalog.Building> buildings) throws IOException {
        require(integer(data.get("schema"), "destination schema") == 1, "Unsupported campus destination schema.");
        Map<String, BuildingCatalog.Building> catalog = new HashMap<>();
        for (var building : buildings) catalog.put(building.id(), building);
        Map<Integer, Destination> result = new LinkedHashMap<>();
        for (Object value : list(data.get("destinations"), "destinations")) {
            Destination destination = readDestination(object(value, "destination"), bounds, catalog);
            require(result.putIfAbsent(destination.number, destination) == null, "Duplicate campus destination number.");
        }
        require(!result.isEmpty(), "Campus destinations cannot be empty.");
        return result;
    }

    private static Destination readDestination(Map<String, Object> data, BuildRegion bounds,
                                              Map<String, BuildingCatalog.Building> catalog) throws IOException {
        int number = integer(data.get("number"), "destination number");
        require(number >= 1 && number <= 99, "Invalid campus destination number.");
        String name = string(data.get("name"), "destination name", 160);
        String source = string(data.get("source"), "destination source", 2048);
        boolean approximate = bool(data.get("approximate"), "approximate");
        boolean available = !data.containsKey("available") || bool(data.get("available"), "available");
        if (!available) return unavailableDestination(data, number, name, source, approximate);
        require(!data.containsKey("unavailableReason"), "An available destination cannot have an unavailable reason.");
        int x = integer(data.get("x"), "destination X");
        int z = integer(data.get("z"), "destination Z");
        require(bounds.contains(x, bounds.minY(), z), "Campus destination " + number + " is outside the shared campus.");
        BuildingCatalog.Building building = destinationBuilding(data, number, catalog);
        return new Destination(number, name, building, x, z, source, approximate, null);
    }

    private static Destination unavailableDestination(Map<String, Object> data, int number, String name,
                                                     String source, boolean approximate) throws IOException {
        require(!data.containsKey("x") && !data.containsKey("z") && !data.containsKey("buildingId"),
                "An unavailable destination cannot contain a teleport target.");
        String reason = string(data.get("unavailableReason"), "unavailable reason", 300);
        return new Destination(number, name, null, null, null, source, approximate, reason);
    }

    private static BuildingCatalog.Building destinationBuilding(Map<String, Object> data, int number,
                                                                Map<String, BuildingCatalog.Building> catalog) throws IOException {
        if (!data.containsKey("buildingId")) return null;
        String id = string(data.get("buildingId"), "building ID", 120);
        var building = catalog.get(id);
        require(building != null, "Unknown campus building ID: " + id);
        boolean isSharedComplex = number == 4 && id.equals("athey-dining") || number == 13 && id.equals("mercer-sweeney");
        require(number == building.mapNumber() || isSharedComplex, "Building ID does not match school map number " + number + ".");
        return building;
    }

    private static Map<String, Artwork> readViews(Map<String, Object> manifest, Map<Integer, Destination> destinations) throws IOException {
        require(integer(manifest.get("schema"), "manifest schema") == 1, "Unsupported campus label schema.");
        require(integer(manifest.get("width"), "image width") == imageWidth, "Unexpected campus image width.");
        require(integer(manifest.get("rowHeight"), "row height") == rowHeight, "Unexpected campus image row height.");
        require(fontName.equals(manifest.get("font")) && gapGlyph.equals(manifest.get("gapGlyph")), "Unexpected campus image font.");
        var sourceViews = object(manifest.get("views"), "views");
        Map<String, Artwork> result = new HashMap<>();
        Map<String, Integer> glyphWidths = new HashMap<>();
        for (String name : List.of("full", "core")) {
            result.put(name, readView(object(sourceViews.get(name), name + " view"), destinations, glyphWidths));
        }
        require(result.get("full").labels.keySet().equals(destinations.keySet()), "Full school map must include every numbered destination.");
        return result;
    }

    private static Artwork readView(Map<String, Object> data, Map<Integer, Destination> destinations,
                                    Map<String, Integer> glyphWidths) throws IOException {
        require(integer(data.get("height"), "image height") == imageHeight, "Unexpected campus image height.");
        Map<Integer, Label> labels = readLabels(list(data.get("labels"), "labels"), destinations);
        List<?> rawRows = list(data.get("rows"), "rows");
        require(rawRows.size() == imageHeight / rowHeight, "Campus image must contain forty rows.");
        List<Row> rows = new ArrayList<>();
        Map<Integer, Integer> coverage = new HashMap<>();
        for (int index = 0; index < rawRows.size(); index++) {
            rows.add(readRow(object(rawRows.get(index), "row"), index * rowHeight, labels, glyphWidths, coverage));
        }
        require(coverage.keySet().equals(labels.keySet()), "Every school map label must have image segments.");
        return new Artwork(List.copyOf(rows), Map.copyOf(labels));
    }

    private static Map<Integer, Label> readLabels(List<?> values, Map<Integer, Destination> destinations) throws IOException {
        Map<Integer, Label> result = new HashMap<>();
        for (Object value : values) {
            Map<String, Object> data = object(value, "label");
            int number = integer(data.get("number"), "label number");
            require(destinations.containsKey(number), "Unknown destination on school map: " + number);
            List<?> bounds = list(data.get("bounds"), "label bounds");
            require(bounds.size() == 4, "A label needs four pixel bounds.");
            Label label = new Label(integer(bounds.get(0), "left"), integer(bounds.get(1), "top"),
                    integer(bounds.get(2), "right"), integer(bounds.get(3), "bottom"));
            validateLabel(label, decimal(data.get("centerX"), "center X"), decimal(data.get("centerY"), "center Y"));
            require(result.putIfAbsent(number, label) == null, "Duplicate school map label number.");
        }
        validateLabelOverlap(result.values().stream().toList());
        return result;
    }

    private static void validateLabel(Label label, double centerX, double centerY) throws IOException {
        require(label.left >= 0 && label.top >= 0 && label.right <= imageWidth && label.bottom <= imageHeight
                && label.left < label.right && label.top < label.bottom, "Invalid school map label bounds.");
        require(label.top % rowHeight == 0 && label.bottom % rowHeight == 0, "School map label bounds must align with image rows.");
        require(centerX >= label.left && centerX < label.right && centerY >= label.top && centerY < label.bottom,
                "School map label center is outside its click region.");
    }

    private static void validateLabelOverlap(List<Label> labels) throws IOException {
        for (int first = 0; first < labels.size(); first++) {
            for (int second = first + 1; second < labels.size(); second++) {
                Label a = labels.get(first), b = labels.get(second);
                require(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top,
                        "School map click regions overlap.");
            }
        }
    }

    private static Row readRow(Map<String, Object> data, int y, Map<Integer, Label> labels,
                               Map<String, Integer> glyphWidths, Map<Integer, Integer> coverage) throws IOException {
        require(integer(data.get("y"), "row Y") == y, "Campus image rows must be ordered and contiguous.");
        List<Segment> segments = new ArrayList<>();
        int end = 0;
        for (Object value : list(data.get("segments"), "segments")) {
            Map<String, Object> item = object(value, "segment");
            int x = integer(item.get("x"), "segment X"), width = integer(item.get("width"), "segment width");
            int label = integer(item.get("label"), "segment label");
            String glyph = string(item.get("glyph"), "segment glyph", 2);
            require(x == end && width > 0 && width <= imageWidth - x, "Campus image segments must cover each row exactly.");
            validateGlyph(glyph, width, glyphWidths);
            validateSegmentLabel(labels, label, x, y, width);
            if (label != 0) coverage.merge(label, width * rowHeight, Integer::sum);
            segments.add(new Segment(x, width, glyph, label));
            end += width;
        }
        require(end == imageWidth, "Campus image row has an uncovered area.");
        return new Row(y, List.copyOf(segments));
    }

    private static void validateGlyph(String glyph, int width, Map<String, Integer> glyphWidths) throws IOException {
        require(glyph.codePointCount(0, glyph.length()) == 1 && Character.getType(glyph.codePointAt(0)) == Character.PRIVATE_USE
                && !glyph.equals(gapGlyph), "Campus image segment must use a private image glyph.");
        Integer previous = glyphWidths.putIfAbsent(glyph, width);
        require(previous == null || previous == width, "One image glyph cannot have different widths.");
    }

    private static void validateSegmentLabel(Map<Integer, Label> labels, int number, int x, int y, int width) throws IOException {
        if (number == 0) return;
        Label label = labels.get(number);
        require(label != null, "Image segment has an undeclared school map label.");
        require(x >= label.left && x + width <= label.right && y >= label.top && y + rowHeight <= label.bottom,
                "Image segment click target escapes its declared label bounds.");
    }

    private static String verifyPack(Path assets, Map<String, Object> manifest) throws IOException {
        String expected = string(manifest.get("packSha1"), "resource pack hash", 40);
        require(expected.matches("[a-f0-9]{40}"), "Invalid campus resource pack hash.");
        byte[] bytes = readAssetBytes(assets, "campus-pack.zip", 8 * 1024 * 1024);
        try {
            String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-1").digest(bytes));
            require(expected.equals(actual), "Campus image labels and resource pack do not match.");
            return expected;
        } catch (NoSuchAlgorithmException exception) { throw new IllegalStateException("SHA1 is unavailable.", exception); }
    }

    private static Map<String, Object> readAsset(Path assets, String filename, int maximumBytes) throws IOException {
        return parseJson(new String(readAssetBytes(assets, filename, maximumBytes), StandardCharsets.UTF_8));
    }

    private static byte[] readAssetBytes(Path assets, String filename, int maximumBytes) throws IOException {
        Path path = assets.resolve(filename);
        require(Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS), "Optional campus image asset is missing: " + filename);
        require(path.toRealPath().getParent().equals(assets.toRealPath()), "Campus image asset escaped its directory.");
        try (InputStream input = Files.newInputStream(path)) { return readBytes(input, maximumBytes); }
    }

    private static Map<String, Object> readJson(InputStream input, int maximumBytes) throws IOException {
        return parseJson(new String(readBytes(input, maximumBytes), StandardCharsets.UTF_8));
    }

    private static byte[] readBytes(InputStream input, int maximumBytes) throws IOException {
        byte[] bytes = input.readNBytes(maximumBytes + 1);
        require(bytes.length <= maximumBytes, "Campus map data exceeds the supported size.");
        return bytes;
    }

    private static Map<String, Object> parseJson(String value) throws IOException {
        try { return JSONObjectUtils.parse(value); }
        catch (ParseException exception) { throw new IOException("Campus map data is not valid JSON.", exception); }
    }

    private static Map<String, Object> object(Object value, String name) throws IOException {
        require(value instanceof Map<?, ?>, "Expected an object for " + name + ".");
        Map<String, Object> result = new LinkedHashMap<>();
        for (var entry : ((Map<?, ?>) value).entrySet()) {
            require(entry.getKey() instanceof String, "Expected text keys for " + name + ".");
            result.put((String) entry.getKey(), entry.getValue());
        }
        return result;
    }

    private static List<?> list(Object value, String name) throws IOException {
        if (value instanceof List<?> list) return list;
        throw invalid("Expected a list for " + name + ".");
    }

    private static String string(Object value, String name, int limit) throws IOException {
        if (value instanceof String string && !string.isBlank() && string.length() <= limit) return string;
        throw invalid("Invalid " + name + ".");
    }

    private static int integer(Object value, String name) throws IOException {
        require(value instanceof Number, "Expected a number for " + name + ".");
        try { return new BigDecimal(value.toString()).intValueExact(); }
        catch (ArithmeticException | NumberFormatException exception) { throw invalid("Expected a whole number for " + name + "."); }
    }

    private static double decimal(Object value, String name) throws IOException {
        require(value instanceof Number && Double.isFinite(((Number) value).doubleValue()), "Invalid " + name + ".");
        return ((Number) value).doubleValue();
    }

    private static boolean bool(Object value, String name) throws IOException {
        if (value instanceof Boolean bool) return bool;
        throw invalid("Expected true or false for " + name + ".");
    }

    private static void require(boolean condition, String message) throws IOException { if (!condition) throw invalid(message); }
    private static IOException invalid(String message) { return new IOException(message); }

    public record Destination(int number, String name, BuildingCatalog.Building building, Integer x, Integer z,
                              String source, boolean approximate, String unavailableReason) {
        public boolean available() { return unavailableReason == null; }
        public String label() { return number + ". " + name; }
        public String menuLabel() { return label() + (available() ? "" : " (outside campus)"); }
        public String tooltip() { return label() + (available() ? approximate ? "\nApproximate starting point." : "" : "\n" + unavailableReason); }
        public CampusMapMenu.Selection selection() {
            if (!available()) throw new IllegalStateException("This school map destination is outside the shared campus.");
            return new CampusMapMenu.Selection(building, x, z, false);
        }
        static Destination fromBuilding(BuildingCatalog.Building building) {
            return new Destination(building.mapNumber(), building.name(), building, building.centerX(), building.centerZ(),
                    "Measured building catalog", false, null);
        }
    }

    private record Label(int left, int top, int right, int bottom) { }
    private record Segment(int x, int width, String glyph, int label) { }
    private record Row(int y, List<Segment> segments) { }
    private record Artwork(List<Row> rows, Map<Integer, Label> labels) { }
}
