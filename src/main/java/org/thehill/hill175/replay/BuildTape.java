package org.thehill.hill175.replay;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.ToLongFunction;

public final class BuildTape {
    public record Profile(UUID id, String name) { }
    public record BlockPos(int x, int y, int z) {
        long chunk() { return chunkKey(x >> 4, z >> 4); }
    }
    public record Pose(long time, double x, double y, double z, float yaw, float pitch) { }
    public record Edit(long time, int x, int y, int z, String before, String after, boolean subject) {
        public Edit(long time, int x, int y, int z, String before, String after) {
            this(time, x, y, z, before, after, true);
        }
        BlockPos position() { return new BlockPos(x, y, z); }
    }

    public static final class Segment {
        private final UUID scene;
        private final String world;
        private final long duration;
        private final List<Pose> poses;
        private final List<Edit> edits;
        private final Map<Long, Map<BlockPos, List<Edit>>> chunks = new HashMap<>();

        public Segment(UUID scene, String world, long duration, List<Pose> poses, List<Edit> edits) {
            this.scene = Objects.requireNonNull(scene);
            this.world = Objects.requireNonNull(world);
            this.duration = duration;
            this.poses = List.copyOf(poses);
            this.edits = List.copyOf(edits);
            if (poses.isEmpty() || duration < 0) throw new IllegalArgumentException("Missing replay scene or duration.");
            for (Edit edit : this.edits) {
                BlockPos pos = edit.position();
                chunks.computeIfAbsent(pos.chunk(), ignored -> new HashMap<>())
                        .computeIfAbsent(pos, ignored -> new ArrayList<>()).add(edit);
            }
        }

        public UUID scene() { return scene; }
        public String world() { return world; }
        public long duration() { return duration; }
        public List<Pose> poses() { return poses; }
        public List<Edit> edits() { return edits; }
        int editCountAt(long time) { return upperBound(edits, time, Edit::time); }
        Iterable<BlockPos> positions(long chunk) { return chunks.getOrDefault(chunk, Map.of()).keySet(); }
        String stateAt(BlockPos position, long time) { return stateAt(chunks.get(position.chunk()).get(position), time); }

        private static String stateAt(List<Edit> history, long time) {
            int count = upperBound(history, time, Edit::time);
            return count == 0 ? history.getFirst().before() : history.get(count - 1).after();
        }

        Map<BlockPos, String> frame(long time) {
            Map<BlockPos, String> frame = new HashMap<>();
            chunks.values().forEach(positions -> positions.forEach((pos, history) -> frame.put(pos, stateAt(history, time))));
            return frame;
        }

        Pose poseAt(long time) {
            int next = upperBound(poses, time, Pose::time);
            Pose previous = poses.get(Math.max(0, next - 1));
            if (next == 0 || next == poses.size()) return previous;
            Pose following = poses.get(next);
            long interval = following.time - previous.time;
            double dx = following.x - previous.x, dy = following.y - previous.y, dz = following.z - previous.z;
            if (interval > 1200 || dx * dx + dy * dy + dz * dz > 144) return previous;
            double fraction = (double) (time - previous.time) / interval;
            return new Pose(time, previous.x + dx * fraction, previous.y + dy * fraction, previous.z + dz * fraction,
                    previous.yaw + (float) (Math.IEEEremainder(following.yaw - previous.yaw, 360) * fraction),
                    previous.pitch + (float) ((following.pitch - previous.pitch) * fraction));
        }
    }

    record Cursor(Segment segment, long time) { }
    private final String name;
    private final List<Segment> segments;
    private final long[] starts;
    private final int windowIndex;
    private final int windowCount;
    private final long duration;

    public BuildTape(String name, List<Segment> segments) { this(name, segments, 0, 1); }
    public BuildTape(String name, List<Segment> segments, int windowIndex, int windowCount) {
        if (windowIndex < 0 || windowIndex >= windowCount) throw new IllegalArgumentException("Invalid replay part.");
        this.windowIndex = windowIndex;
        this.windowCount = windowCount;
        this.name = name;
        this.segments = List.copyOf(segments);
        starts = new long[segments.size()];
        long total = 0;
        for (int index = 0; index < starts.length; index++) {
            starts[index] = total;
            total = Math.addExact(total, segments.get(index).duration());
        }
        duration = total;
    }
    public String name() { return name; }
    public int windowIndex() { return windowIndex; }
    public int windowCount() { return windowCount; }
    public List<Segment> segments() { return segments; }
    public long duration() { return duration; }
    Cursor at(long time) {
        long clamped = Math.clamp(time, 0L, duration);
        if (segments.isEmpty()) throw new IllegalStateException("There is no recorded session to play.");
        int low = 0, high = starts.length;
        while (low < high) {
            int middle = (low + high) >>> 1;
            if (starts[middle] <= clamped) low = middle + 1; else high = middle;
        }
        return new Cursor(segments.get(low - 1), clamped - starts[low - 1]);
    }

    static long chunkKey(int chunkX, int chunkZ) { return ((long) chunkX << 32) | Integer.toUnsignedLong(chunkZ); }
    private static <T> int upperBound(List<T> events, long time, ToLongFunction<T> timestamp) {
        int low = 0, high = events.size();
        while (low < high) {
            int middle = (low + high) >>> 1;
            if (timestamp.applyAsLong(events.get(middle)) <= time) low = middle + 1; else high = middle;
        }
        return low;
    }
}
