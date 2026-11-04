package org.thehill.hill175.ui;

import com.nimbusds.jose.util.JSONObjectUtils;
import net.kyori.adventure.key.Key;
import net.kyori.adventure.nbt.api.BinaryTagHolder;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.TextComponent;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.ShadowColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;
import org.thehill.hill175.world.BuildingCatalog;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class CampusMapLabelsTest {
    @TempDir Path assets;
    private final BuildRegion bounds = new BuildRegion("hill_campus", -100, -64, -100, 100, 319, 100);
    private final BuildingCatalog.Building chapel = new BuildingCatalog.Building("alumni-chapel", "Alumni Chapel", 6, -5, -5, 5, 5);
    private final byte[] pack = "fixture resource pack bytes".getBytes(StandardCharsets.UTF_8);

    @Test void missingOptionalManifestKeepsEveryNamedDestinationAndExplicitUnavailableReason() throws Exception {
        var labels = load(destinations(), List.of(chapel));
        assertEquals(List.of(6, 26, 28), labels.destinations().stream().map(CampusMapLabels.Destination::number).toList());
        assertTrue(labels.artworkWarning().isPresent());
        assertFalse(labels.matchesPack(hash()));
        assertSame(chapel, labels.destination(6).orElseThrow().selection().building());
        assertNull(labels.destination(26).orElseThrow().selection().building());
        assertEquals(80, labels.destination(26).orElseThrow().selection().x());
        var unavailable = labels.destination(28).orElseThrow();
        assertFalse(unavailable.available());
        assertTrue(unavailable.menuLabel().contains("outside campus"));
        assertThrows(IllegalStateException.class, unavailable::selection);
    }

    @Test void invalidOrFractionalCoordinatesCannotCreateATeleportTarget() {
        var outside = point(26, "Madden Stadium", 101, 0);
        assertThrows(IOException.class, () -> load(List.of(outside), List.of(chapel)));
        var fractional = point(26, "Madden Stadium", 0, 0);
        fractional.put("x", 0.5);
        assertThrows(IOException.class, () -> load(List.of(fractional), List.of(chapel)));
    }

    @Test void unavailableRecordCannotSmuggleCoordinatesOrBuildingId() {
        var unavailable = new HashMap<>(destinations().getLast());
        unavailable.put("x", 0);
        assertThrows(IOException.class, () -> load(List.of(unavailable), List.of(chapel)));
        unavailable.remove("x");
        unavailable.put("buildingId", "alumni-chapel");
        assertThrows(IOException.class, () -> load(List.of(unavailable), List.of(chapel)));
    }

    @Test void duplicateNumbersAndUnknownBuildingIdsAreRejected() {
        var target = point(6, "Alumni Chapel", 0, 0);
        assertThrows(IOException.class, () -> load(List.of(target, target), List.of(chapel)));
        target.put("buildingId", "missing-building");
        assertThrows(IOException.class, () -> load(List.of(target), List.of(chapel)));
    }

    @Test void onlyReviewedComplexAliasesMayDifferFromTheCatalogMapNumber() throws Exception {
        var athey = new BuildingCatalog.Building("athey-dining", "Athey", 3, -5, -5, 5, 5);
        var dining = point(4, "Dining Hall", 0, 0);
        dining.put("buildingId", athey.id());
        assertSame(athey, load(List.of(dining), List.of(athey)).destination(4).orElseThrow().building());
        dining.put("number", 5);
        assertThrows(IOException.class, () -> load(List.of(dining), List.of(athey)));
    }

    @Test void resourcePackMismatchDisablesImageCallbacksButKeepsNamedDestinations() throws Exception {
        var manifest = manifest();
        manifest.put("packSha1", "0".repeat(40));
        writeAssets(manifest);
        var labels = load(destinations(), List.of(chapel));
        assertFalse(labels.matchesPack(hash()));
        assertTrue(labels.artworkWarning().orElseThrow().contains("do not match"));
        assertEquals(3, labels.destinations().size());
    }

    @Test void malformedRowCoverageCannotShiftVisibleNumbersOntoAnotherDestination() throws Exception {
        var manifest = manifest();
        firstSegment(manifest).put("x", 1);
        writeAssets(manifest);
        var labels = load(destinations(), List.of(chapel));
        assertFalse(labels.matchesPack(hash()));
        assertTrue(labels.artworkWarning().orElseThrow().contains("cover each row exactly"));
    }

    @Test void aSegmentCannotDeclareAClickOutsideItsNumberRegion() throws Exception {
        var manifest = manifest();
        firstSegment(manifest).put("label", 6);
        writeAssets(manifest);
        var labels = load(destinations(), List.of(chapel));
        assertFalse(labels.matchesPack(hash()));
        assertTrue(labels.artworkWarning().orElseThrow().contains("escapes"));
    }

    @Test void pictureUsesExactRowSpacingAndOneSecureCallbackPerAvailableNumber() throws Exception {
        writeAssets(manifest());
        var labels = load(destinations(), List.of(chapel));
        assertTrue(labels.matchesPack(hash()), labels.artworkWarning().orElse(""));
        AtomicInteger createdCallbacks = new AtomicInteger();
        Component image = labels.render("full", destination -> {
            assertTrue(destination.available());
            createdCallbacks.incrementAndGet();
            return ClickEvent.custom(Key.key("hill175:test"), BinaryTagHolder.binaryTagHolder("{number:" + destination.number() + "}"));
        });
        assertEquals(2, createdCallbacks.get());
        assertEquals(Key.key(CampusMapLabels.fontName), image.font());
        assertEquals(NamedTextColor.WHITE, image.color());
        assertEquals(ShadowColor.none(), image.shadowColor());
        assertEquals(TextDecoration.State.FALSE, image.decoration(TextDecoration.BOLD));
        assertEquals(TextDecoration.State.FALSE, image.decoration(TextDecoration.ITALIC));
        assertImageRowSpacing(image);
        assertTrue(image.children().stream().filter(child -> child.hoverEvent() == null).allMatch(child -> child.clickEvent() == null));
        List<Component> unavailable = image.children().stream().filter(child -> child.hoverEvent() != null
                && child.hoverEvent().value().toString().contains("Brookside")).toList();
        assertEquals(2, unavailable.size());
        assertTrue(unavailable.stream().allMatch(child -> child.clickEvent() == null));
        List<Component> chapelGlyphs = image.children().stream().filter(child -> child.hoverEvent() != null
                && child.hoverEvent().value().toString().contains("Alumni Chapel")).toList();
        assertEquals(2, chapelGlyphs.size());
        assertSame(chapelGlyphs.getFirst().clickEvent(), chapelGlyphs.getLast().clickEvent());
    }

    private void assertImageRowSpacing(Component image) {
        String text = image.children().stream().map(child -> ((TextComponent) child).content()).reduce("", String::concat);
        String[] rows = text.split("\n", -1);
        assertEquals(40, rows.length);
        for (int index = 0; index < rows.length; index++) {
            assertFalse(rows[index].startsWith(CampusMapLabels.gapGlyph));
            assertFalse(rows[index].endsWith(CampusMapLabels.gapGlyph), "A trailing negative gap makes the native height pass wrap again.");
            String[] glyphs = rows[index].split(CampusMapLabels.gapGlyph, -1);
            assertEquals(index < 2 ? 7 : 1, glyphs.length, "Every fixture image segment must appear in its row.");
            assertTrue(java.util.Arrays.stream(glyphs).allMatch(glyph -> glyph.codePointCount(0, glyph.length()) == 1),
                    "Every adjacent image segment needs exactly one negative spacing glyph.");
        }
    }

    private CampusMapLabels load(List<Map<String, Object>> destinations, List<BuildingCatalog.Building> catalog) throws IOException {
        String json = JSONObjectUtils.toJSONString(Map.of("schema", 1, "destinations", destinations));
        return CampusMapLabels.load(assets, new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8)), bounds, catalog);
    }

    private List<Map<String, Object>> destinations() {
        var chapelData = point(6, "Alumni Chapel", 0, 0);
        chapelData.put("buildingId", chapel.id());
        return List.of(chapelData, point(26, "Madden Stadium", 80, 80), new HashMap<>(Map.of(
                "number", 28, "name", "Brookside Country Club", "source", "Official map", "approximate", false,
                "available", false, "unavailableReason", "Brookside Country Club is outside the shared campus.")));
    }

    private Map<String, Object> point(int number, String name, int x, int z) {
        return new HashMap<>(Map.of("number", number, "name", name, "x", x, "z", z,
                "source", "Reviewed destination", "approximate", false));
    }

    private String hash() throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-1").digest(pack)); }

    private void writeAssets(Map<String, Object> manifest) throws IOException {
        Files.write(assets.resolve("campus-pack.zip"), pack);
        Files.writeString(assets.resolve("campus-map-labels.json"), JSONObjectUtils.toJSONString(manifest));
    }

    private Map<String, Object> manifest() throws Exception {
        List<Map<String, Object>> rows = new ArrayList<>();
        int codepoint = 0xE000;
        for (int index = 0; index < 40; index++) {
            List<Map<String, Object>> segments = new ArrayList<>();
            int[] widths = index < 2 ? new int[] {10, 20, 20, 20, 20, 20, 250} : new int[] {360};
            int[] numbers = index < 2 ? new int[] {0, 6, 0, 26, 0, 28, 0} : new int[] {0};
            int x = 0;
            for (int segment = 0; segment < widths.length; segment++) {
                segments.add(new HashMap<>(Map.of("x", x, "width", widths[segment], "label", numbers[segment],
                        "glyph", Character.toString(codepoint++))));
                x += widths[segment];
            }
            rows.add(Map.of("y", index * 9, "segments", segments));
        }
        var view = Map.of("height", 360, "rows", rows, "labels", List.of(
                label(6, 10, 30), label(26, 50, 70), label(28, 90, 110)));
        return new HashMap<>(Map.of("schema", 1, "width", 360, "rowHeight", 9,
                "font", CampusMapLabels.fontName, "gapGlyph", CampusMapLabels.gapGlyph,
                "packSha1", hash(), "views", Map.of("full", view, "core", view)));
    }

    private Map<String, Object> label(int number, int left, int right) {
        return Map.of("number", number, "centerX", (left + right) / 2, "centerY", 9, "bounds", List.of(left, 0, right, 18));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> firstSegment(Map<String, Object> manifest) {
        var views = (Map<String, Object>) manifest.get("views");
        var full = (Map<String, Object>) views.get("full");
        var rows = (List<Map<String, Object>>) full.get("rows");
        return ((List<Map<String, Object>>) rows.getFirst().get("segments")).getFirst();
    }
}
