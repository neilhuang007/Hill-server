package org.thehill.hill175.gallery;

import org.thehill.hill175.model.CameraPose;
import org.thehill.hill175.model.Entry;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.LinkOption;
import java.nio.file.StandardCopyOption;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Properties;
import java.util.UUID;
import java.util.stream.Collectors;

/** Only explicitly submitted entries are public. HTTP callers never receive participant records or world coordinates. */
public final class EntryGalleryPublisher {
    private final Path root;
    private final Map<UUID, PublishedEntry> entries = new LinkedHashMap<>();
    private final Map<UUID, Map<Integer, String>> revisions = new HashMap<>();

    public EntryGalleryPublisher(Path root, Collection<Entry> initialEntries) throws IOException {
        this.root = root.toAbsolutePath().normalize();
        Files.createDirectories(this.root);
        for (Entry entry : initialEntries) {
            Map<Integer, String> images = readImages(entry);
            entries.put(entry.id(), snapshot(entry, images));
        }
    }

    public synchronized void update(Entry entry) {
        PublishedEntry previous = entries.get(entry.id());
        Map<Integer, String> images = previous == null ? Map.of() : matchingImages(entry, previous.images());
        entries.put(entry.id(), snapshot(entry, images));
    }

    public synchronized void invalidateImage(Entry entry, int slot) throws IOException {
        PublishedEntry previous = entries.get(entry.id());
        Map<Integer, String> images = new HashMap<>(previous == null ? Map.of() : previous.images());
        images.remove(slot);
        revisions.computeIfAbsent(entry.id(), ignored -> new HashMap<>()).remove(slot);
        entries.put(entry.id(), snapshot(entry, images));
        writeImages(entry.id(), images);
    }

    public synchronized void invalidateAll(Entry entry) throws IOException {
        revisions.remove(entry.id());
        entries.put(entry.id(), snapshot(entry, Map.of()));
        writeImages(entry.id(), Map.of());
    }

    /** The caller has already checked that the current camera still matches this capture. */
    public synchronized void acceptImage(Entry entry, int slot, CameraPose pose, Path renderedImage) throws IOException {
        if (!entry.cameraPose(slot).filter(pose::equals).isPresent()) {
            throw new IOException("The saved camera changed before its image was ready.");
        }
        Path directory = entryDirectory(entry.id());
        Files.createDirectories(directory);
        String revision = imageRevision(renderedImage);
        atomicMove(renderedImage, directory.resolve("camera-" + slot + ".png"));
        revisions.computeIfAbsent(entry.id(), ignored -> new HashMap<>()).put(slot, revision);
        PublishedEntry previous = entries.get(entry.id());
        Map<Integer, String> images = new HashMap<>(previous == null ? Map.of() : previous.images());
        images.put(slot, signature(pose));
        writeImages(entry.id(), images);
        entries.put(entry.id(), snapshot(entry, images));
    }

    public synchronized void remove(UUID entryId) throws IOException {
        // Revoke access first, including all existing draft links, even if filesystem cleanup fails.
        entries.remove(entryId);
        revisions.remove(entryId);
        Path directory = entryDirectory(entryId);
        for (int slot = 1; slot <= Entry.MAX_CAMERA_SLOTS; slot++) {
            Files.deleteIfExists(directory.resolve("camera-" + slot + ".png"));
        }
        Files.deleteIfExists(directory.resolve("captures.properties"));
        Files.deleteIfExists(directory.resolve("captures.properties.tmp"));
        Files.deleteIfExists(directory);
    }

    public synchronized boolean hasImage(Entry entry, int slot) {
        PublishedEntry published = entries.get(entry.id());
        return published != null && entry.cameraPose(slot)
                .map(pose -> signature(pose).equals(published.images().get(slot)))
                .orElse(false);
    }

    public synchronized String publicIndexJson() {
        return "{\"entries\":[" + entries.values().stream()
                .filter(PublishedEntry::isPublic)
                .sorted(Comparator.comparing(PublishedEntry::id))
                .map(entry -> manifest(entry, false)).collect(Collectors.joining(",")) + "]}";
    }

    public synchronized Optional<String> previewManifest(String token) {
        if (!validToken(token)) {
            return Optional.empty();
        }
        return entries.values().stream().filter(entry -> entry.token().equals(token))
                .findFirst().map(entry -> manifest(entry, true));
    }

    public synchronized Optional<String> entryManifest(UUID id) {
        return Optional.ofNullable(entries.get(id)).filter(PublishedEntry::isPublic)
                .map(entry -> manifest(entry, false));
    }

    public synchronized Optional<byte[]> image(UUID id, int slot, String token) {
        PublishedEntry entry = entries.get(id);
        if (entry == null || !entry.images().containsKey(slot)
                || (!entry.isPublic() && !(validToken(token) && entry.token().equals(token)))) {
            return Optional.empty();
        }
        try {
            Path image = entryDirectory(id).resolve("camera-" + slot + ".png");
            if (!Files.isRegularFile(image, LinkOption.NOFOLLOW_LINKS)) return Optional.empty();
            try (InputStream input = Files.newInputStream(image)) {
                byte[] bytes = input.readNBytes(8 * 1024 * 1024 + 1);
                return bytes.length > 8 * 1024 * 1024 ? Optional.empty() : Optional.of(bytes);
            }
        } catch (IOException exception) {
            return Optional.empty();
        }
    }

    public Path createRenderFile() throws IOException {
        Path temporary = root.resolve("rendering");
        Files.createDirectories(temporary);
        return Files.createTempFile(temporary, "capture-", ".png");
    }

    private Map<Integer, String> readImages(Entry entry) throws IOException {
        Path metadata = entryDirectory(entry.id()).resolve("captures.properties");
        if (!Files.isRegularFile(metadata)) {
            return Map.of();
        }
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(metadata)) {
            properties.load(input);
        }
        Map<Integer, String> images = new HashMap<>();
        for (int slot : entry.savedCameraSlots()) {
            String expected = signature(entry.cameraPose(slot).orElseThrow());
            if (expected.equals(properties.getProperty(Integer.toString(slot)))
                    && Files.isRegularFile(entryDirectory(entry.id()).resolve("camera-" + slot + ".png"))) {
                images.put(slot, expected);
                revisions.computeIfAbsent(entry.id(), ignored -> new HashMap<>()).put(slot,
                        imageRevision(entryDirectory(entry.id()).resolve("camera-" + slot + ".png")));
            }
        }
        return images;
    }

    private void writeImages(UUID id, Map<Integer, String> images) throws IOException {
        Path directory = entryDirectory(id);
        Files.createDirectories(directory);
        Properties properties = new Properties();
        images.forEach((slot, signature) -> properties.setProperty(Integer.toString(slot), signature));
        Path temporary = directory.resolve("captures.properties.tmp");
        try (OutputStream output = Files.newOutputStream(temporary)) {
            properties.store(output, "Private camera capture cache; never served by HTTP");
        }
        atomicMove(temporary, directory.resolve("captures.properties"));
    }

    private PublishedEntry snapshot(Entry entry, Map<Integer, String> images) {
        String title = entry.title().isBlank() ? entry.category().displayName() + " entry "
                + entry.id().toString().substring(0, 8) : entry.title();
        return new PublishedEntry(entry.id(), entry.previewToken(), title, entry.description(),
                entry.category().name().toLowerCase(java.util.Locale.ROOT), entry.submitted(),
                entry.submittedAt() == null ? null : entry.submittedAt().toString(),
                entry.savedCameraSlots().size(), Map.copyOf(images), Map.copyOf(revisions.getOrDefault(entry.id(), Map.of())));
    }

    private static Map<Integer, String> matchingImages(Entry entry, Map<Integer, String> images) {
        Map<Integer, String> matched = new HashMap<>();
        for (int slot : entry.savedCameraSlots()) {
            String signature = signature(entry.cameraPose(slot).orElseThrow());
            if (signature.equals(images.get(slot))) {
                matched.put(slot, signature);
            }
        }
        return matched;
    }

    private static String manifest(PublishedEntry entry, boolean privatePreview) {
        String images = entry.images().keySet().stream().sorted().map(slot -> {
            String url = "/api/entries/" + entry.id() + "/images/" + slot;
            if (privatePreview) {
                url += "?token=" + entry.token();
            }
            return "{\"slot\":" + slot + ",\"url\":" + json(url)
                    + ",\"revision\":" + json(entry.revisions().get(slot))
                    + ",\"label\":" + json("Camera " + slot + " — server-rendered view") + "}";
        }).collect(Collectors.joining(","));
        return "{\"id\":" + json(entry.id().toString()) + ",\"title\":" + json(entry.title())
                + ",\"description\":" + json(entry.description()) + ",\"category\":" + json(entry.category())
                + ",\"submitted\":" + entry.isPublic() + ",\"submittedAt\":" + json(entry.submittedAt())
                + ",\"status\":" + json(entry.isPublic() ? "submitted" : "draft")
                + ",\"renderer\":" + json("Server-rendered block preview; approximate materials and shapes, 80-block range. Players, entities, sign text, textures and client shaders are not captured.")
                + ",\"images\":[" + images + "]}";
    }

    static String json(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder escaped = new StringBuilder("\"");
        for (char character : value.toCharArray()) {
            switch (character) {
                case '"' -> escaped.append("\\\"");
                case '\\' -> escaped.append("\\\\");
                case '\n' -> escaped.append("\\n");
                case '\r' -> escaped.append("\\r");
                case '\t' -> escaped.append("\\t");
                default -> escaped.append(character < 32 ? String.format("\\u%04x", (int) character) : character);
            }
        }
        return escaped.append('"').toString();
    }

    private Path entryDirectory(UUID id) {
        return root.resolve("entries").resolve(id.toString());
    }

    private static String imageRevision(Path image) throws IOException {
        try {
            var digest = java.security.MessageDigest.getInstance("SHA-256");
            try (InputStream stream = Files.newInputStream(image)) {
                byte[] chunk = new byte[8192];
                int total = 0;
                for (int count; (count = stream.read(chunk)) != -1;) {
                    total += count;
                    if (total > 8 * 1024 * 1024) throw new IOException("Camera image exceeds the size limit.");
                    digest.update(chunk, 0, count);
                }
            }
            return java.util.HexFormat.of().formatHex(digest.digest());
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is required by Java.", impossible);
        }
    }

    private static String signature(CameraPose pose) {
        return pose.worldName() + ":" + pose.x() + ":" + pose.y() + ":" + pose.z() + ":" + pose.yaw() + ":" + pose.pitch();
    }

    private static boolean validToken(String token) {
        return token != null && token.matches("[A-Za-z0-9_-]{22,64}");
    }

    private static void atomicMove(Path source, Path destination) throws IOException {
        try {
            Files.move(source, destination, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException exception) {
            Files.move(source, destination, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private record PublishedEntry(UUID id, String token, String title, String description, String category,
                                  boolean submitted, String submittedAt, int cameraCount, Map<Integer, String> images,
                                  Map<Integer, String> revisions) {
        boolean isPublic() {
            return submitted && cameraCount > 0 && images.size() == cameraCount;
        }
    }
}
