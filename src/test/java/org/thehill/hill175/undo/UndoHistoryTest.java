package org.thehill.hill175.undo;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class UndoHistoryTest {
    private final AtomicLong clock = new AtomicLong(100_000);
    private final UndoHistory<String> history = new UndoHistory<>(clock::get);
    private final UUID alice = UUID.randomUUID();
    private final UUID bob = UUID.randomUUID();
    private final UndoHistory.Point point = new UndoHistory.Point(UUID.randomUUID(), 1, 80, 2);
    private final Map<UndoHistory.Point, String> world = new HashMap<>();

    @Test void includesExactlyFifteenSecondsButNotOlderEdits() {
        edit(alice, "air", "stone");
        clock.addAndGet(15_000);
        var session = history.beginUndo(alice);
        assertTrue(session.canApply(session.next(), world::get));
        edit(alice, "stone", "bricks");
        clock.addAndGet(15_001);
        assertFalse(history.beginUndo(alice).hasNext());
    }

    @Test void reversesMultipleEditsOfTheSameBlockWithinOneSession() {
        edit(alice, "air", "stone");
        edit(alice, "stone", "air");
        edit(alice, "air", "bricks");
        undoAll(alice);
        assertEquals("air", world.get(point));
        assertFalse(history.beginUndo(alice).hasNext());
    }

    @Test void leavesAnotherActorsUnrelatedBlocksAlone() {
        UndoHistory.Point other = new UndoHistory.Point(point.world(), 3, 80, 2);
        edit(alice, "air", "stone");
        record(bob, Map.of(other, "air"), Map.of(other, "bricks"));
        undoAll(alice);
        assertEquals("bricks", world.get(other));
        assertTrue(history.beginUndo(bob).hasNext());
    }

    @Test void refusesAnotherActorsReplacementEvenIfItHasTheSameMaterial() {
        edit(alice, "air", "stone");
        edit(bob, "stone", "air");
        edit(bob, "air", "stone");
        var session = history.beginUndo(alice);
        assertFalse(session.canApply(session.next(), world::get));
    }

    @Test void anotherActorsUndoCannotReenableAnOlderUndo() {
        edit(alice, "air", "stone");
        edit(bob, "stone", "bricks");
        undoAll(bob);
        assertEquals("stone", world.get(point));
        var session = history.beginUndo(alice);
        assertFalse(session.canApply(session.next(), world::get));
    }

    @Test void environmentInvalidationPreventsSameMaterialAba() {
        edit(alice, "air", "stone");
        history.invalidate(List.of(point));
        var session = history.beginUndo(alice);
        assertFalse(session.canApply(session.next(), world::get));
    }

    @Test void requiresCurrentFullStateToMatchEvenWithoutAnEvent() {
        edit(alice, "air", "oak_stairs[facing=north]");
        world.put(point, "oak_stairs[facing=south]");
        var session = history.beginUndo(alice);
        assertFalse(session.canApply(session.next(), world::get));
    }

    @Test void oneConflictRejectsTheEntireMultiBlockGroup() {
        UndoHistory.Point upper = new UndoHistory.Point(point.world(), 1, 81, 2);
        record(alice, Map.of(point, "air", upper, "air"), Map.of(point, "door-bottom", upper, "door-top"));
        history.invalidate(List.of(upper));
        var session = history.beginUndo(alice);
        assertFalse(session.canApply(session.next(), world::get));
    }

    @Test void peerEditsDuringAnUndoSessionInvalidateItsCursor() {
        edit(alice, "air", "stone");
        edit(alice, "stone", "bricks");
        var session = history.beginUndo(alice);
        apply(session, session.next());
        edit(bob, "stone", "air");
        edit(bob, "air", "stone");
        assertFalse(session.canApply(session.next(), world::get));
    }

    @Test void doesNotRecordAPendingChangeOvertakenByAnotherEdit() {
        var reserved = history.reserve(List.of(point));
        history.reserve(List.of(point));
        assertFalse(history.record(alice, clock.get(), Map.of(point, "air"), Map.of(point, "stone"), reserved));
        assertFalse(history.beginUndo(alice).hasNext());
    }

    @Test void boundedHistoryDropsOldestAndPruningRemovesExpiredActors() {
        for (int count = 0; count < 520; count++) edit(alice, Integer.toString(count), Integer.toString(count + 1));
        var session = history.beginUndo(alice);
        int batches = 0;
        while (session.hasNext()) { session.next(); batches++; }
        assertEquals(512, batches);
        edit(bob, "air", "stone");
        clock.addAndGet(31_000);
        history.prune();
        assertFalse(history.tracked(point));
        assertFalse(history.beginUndo(bob).hasNext());
    }

    private void edit(UUID actor, String before, String after) { record(actor, Map.of(point, before), Map.of(point, after)); }

    private void record(UUID actor, Map<UndoHistory.Point, String> before, Map<UndoHistory.Point, String> after) {
        var reserved = history.reserve(before.keySet());
        world.putAll(after);
        assertTrue(history.record(actor, clock.get(), before, after, reserved));
    }

    private void undoAll(UUID actor) {
        var session = history.beginUndo(actor);
        while (session.hasNext()) apply(session, session.next());
    }

    private void apply(UndoHistory<String>.Session session, UndoHistory.Batch<String> batch) {
        assertTrue(session.canApply(batch, world::get));
        batch.edits().forEach(edit -> world.put(edit.point(), edit.before()));
        session.applied(batch);
    }
}
