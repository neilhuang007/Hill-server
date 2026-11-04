package org.thehill.hill175.undo;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Deque;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.Function;
import java.util.function.LongSupplier;

/** Main thread ledger. Actual revisions never rewind, even when a student undoes an edit. */
final class UndoHistory<S> {
    static final long windowMillis = 15_000;
    private static final int maximumActors = 128;
    private static final int maximumBatchesPerActor = 512;
    private static final int maximumTrackedPoints = 65_536;
    private final LongSupplier clock;
    private final LinkedHashMap<Point, Stamp> revisions = new LinkedHashMap<>();
    private final LinkedHashMap<UUID, Deque<Batch<S>>> histories = new LinkedHashMap<>();
    private long sequence;

    UndoHistory(LongSupplier clock) { this.clock = Objects.requireNonNull(clock, "clock"); }

    Map<Point, Revision> reserve(Collection<Point> points) {
        Map<Point, Revision> result = new LinkedHashMap<>();
        long now = clock.getAsLong();
        for (Point point : points) {
            long before = revision(point);
            long after = stamp(point, now);
            result.put(point, new Revision(before, after));
        }
        return Map.copyOf(result);
    }

    boolean record(UUID actor, long at, Map<Point, S> before, Map<Point, S> after, Map<Point, Revision> reserved) {
        if (!before.keySet().equals(after.keySet()) || !before.keySet().equals(reserved.keySet())) return false;
        if (reserved.entrySet().stream().anyMatch(entry -> revision(entry.getKey()) != entry.getValue().after())) return false;
        List<Edit<S>> edits = new ArrayList<>();
        for (Point point : before.keySet()) {
            if (!Objects.equals(before.get(point), after.get(point))) {
                edits.add(new Edit<>(point, before.get(point), after.get(point), reserved.get(point)));
            }
        }
        if (edits.isEmpty()) return false;
        histories.computeIfAbsent(actor, ignored -> new ArrayDeque<>()).addLast(new Batch<>(at, List.copyOf(edits)));
        trim(actor);
        return true;
    }

    boolean tracked(Point point) { return revisions.containsKey(point); }

    void invalidate(Collection<Point> points) {
        long now = clock.getAsLong();
        for (Point point : points) if (tracked(point)) stamp(point, now);
    }

    Session beginUndo(UUID actor) {
        long now = clock.getAsLong();
        prune(now);
        Deque<Batch<S>> history = histories.remove(actor);
        List<Batch<S>> batches = new ArrayList<>();
        if (history != null) {
            Iterator<Batch<S>> reverse = history.descendingIterator();
            while (reverse.hasNext()) {
                Batch<S> batch = reverse.next();
                if (batch.at() <= now && batch.at() >= now - windowMillis) batches.add(batch);
            }
        }
        return new Session(batches);
    }

    void prune() { prune(clock.getAsLong()); }

    private void prune(long now) {
        for (Deque<Batch<S>> history : histories.values()) {
            history.removeIf(batch -> batch.at() < now - windowMillis);
        }
        histories.values().removeIf(Deque::isEmpty);
        revisions.values().removeIf(stamp -> stamp.at() < now - windowMillis * 2);
    }

    void clear() { histories.clear(); revisions.clear(); }
    void forget(UUID actor) { histories.remove(actor); }

    private void trim(UUID actor) {
        Deque<Batch<S>> history = histories.get(actor);
        while (history.size() > maximumBatchesPerActor) history.removeFirst();
        while (histories.size() > maximumActors) histories.remove(histories.keySet().iterator().next());
    }

    private long stamp(Point point, long now) {
        long value = ++sequence;
        revisions.remove(point);
        revisions.put(point, new Stamp(value, now));
        while (revisions.size() > maximumTrackedPoints) revisions.remove(revisions.keySet().iterator().next());
        return value;
    }

    private long revision(Point point) {
        Stamp stamp = revisions.get(point);
        return stamp == null ? 0 : stamp.value();
    }

    record Point(UUID world, int x, int y, int z) { }
    record Revision(long before, long after) { }
    record Edit<S>(Point point, S before, S after, Revision revision) { }
    record Batch<S>(long at, List<Edit<S>> edits) { }
    private record Stamp(long value, long at) { }
    private record Cursor(long logicalRevision, long actualRevision) { }

    final class Session {
        private final Deque<Batch<S>> batches;
        private final Map<Point, Cursor> cursors = new HashMap<>();

        private Session(List<Batch<S>> batches) { this.batches = new ArrayDeque<>(batches); }
        Batch<S> next() { return batches.pollFirst(); }
        boolean hasNext() { return !batches.isEmpty(); }

        boolean canApply(Batch<S> batch, Function<Point, S> current) {
            return batch.edits().stream().allMatch(edit -> matchesRevision(edit)
                    && Objects.equals(edit.after(), current.apply(edit.point())));
        }

        void applied(Batch<S> batch) {
            long now = clock.getAsLong();
            for (Edit<S> edit : batch.edits()) {
                long actual = stamp(edit.point(), now);
                cursors.put(edit.point(), new Cursor(edit.revision().before(), actual));
            }
        }

        private boolean matchesRevision(Edit<S> edit) {
            long actual = revision(edit.point());
            Cursor cursor = cursors.get(edit.point());
            return cursor == null ? actual == edit.revision().after()
                    : cursor.actualRevision() == actual && cursor.logicalRevision() == edit.revision().after();
        }
    }
}
