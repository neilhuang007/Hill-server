package org.thehill.hill175.blueprint;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;

/** Block-level three-way rules shared by approval merges and personal campus updates. */
public final class BlueprintMerge {
    private BlueprintMerge() { }

    public interface Blocks {
        BlockSnapshot read(BlockPosition position) throws IOException;
        void write(BlockPosition position, BlockSnapshot snapshot) throws IOException;

        /** Writes a batch; implementations may order writes so connected blocks keep their shape. */
        default void write(Map<BlockPosition, BlockSnapshot> blocks) throws IOException {
            for (var entry : blocks.entrySet()) write(entry.getKey(), entry.getValue());
        }
    }

    /** A proposed change whose base no longer matches the blueprint. */
    public record Conflict(BlockChange proposed, BlockSnapshot current) {
        public BlockPosition position() { return proposed.position(); }
        BlockChange override() { return new BlockChange(proposed.position(), current, proposed.after()); }
    }

    /** {@code applicable} changes carry the current blueprint block as their before state. */
    public record Plan(List<BlockChange> applicable, List<Conflict> conflicts, int alreadyApplied) {
        public Plan {
            applicable = List.copyOf(applicable);
            conflicts = List.copyOf(conflicts);
        }

        /** The writes for an approval; conflicts either keep the blueprint block or take the proposed block. */
        public List<BlockChange> writes(boolean useProposalForConflicts) {
            if (!useProposalForConflicts) return applicable;
            List<BlockChange> writes = new ArrayList<>(applicable);
            for (Conflict conflict : conflicts) writes.add(conflict.override());
            return List.copyOf(writes);
        }
    }

    /** Result of bringing one approved update into a personal campus. */
    public record Update(List<BlockChange> writes, List<BlockChange> conflicts) {
        public Update {
            writes = List.copyOf(writes);
            conflicts = List.copyOf(conflicts);
        }
    }

    public static Plan plan(List<BlockChange> changes, Blocks target) throws IOException {
        if (changes.size() > BlueprintRepository.MAXIMUM_CHANGES) throw new IOException("Proposal exceeds the safe merge limit.");
        List<BlockChange> applicable = new ArrayList<>();
        List<Conflict> conflicts = new ArrayList<>();
        int alreadyApplied = 0;
        for (BlockChange change : changes) {
            BlockSnapshot current = target.read(change.position());
            if (current.equals(change.after())) alreadyApplied++;
            else if (current.equals(change.before())) applicable.add(change);
            else conflicts.add(new Conflict(change, current));
        }
        return new Plan(applicable, conflicts, alreadyApplied);
    }

    /**
     * Each approved update records the blueprint block before and after it was applied, so its before
     * state is the common base of the campus and the blueprint. Untouched campus blocks take the update,
     * blocks the student also changed become conflicts, and the student's own approved update never
     * overwrites edits made after its snapshot.
     */
    public static Update update(List<BlockChange> revision, Blocks campus, boolean ownRevision,
                                Predicate<BlockPosition> editable) throws IOException {
        List<BlockChange> writes = new ArrayList<>();
        List<BlockChange> conflicts = new ArrayList<>();
        for (BlockChange change : revision) {
            if (!editable.test(change.position())) continue;
            BlockSnapshot mine = campus.read(change.position());
            if (mine.equals(change.after()) || ownRevision) continue;
            if (mine.equals(change.before())) writes.add(new BlockChange(change.position(), mine, change.after()));
            else conflicts.add(change);
        }
        return new Update(writes, conflicts);
    }

    /**
     * The changes that make {@code live} look as it did before the {@code later} updates (oldest first). Each
     * block takes its state from just before the first of those updates changed it.
     */
    public static List<BlockChange> revert(List<List<BlockChange>> later, Blocks live) throws IOException {
        Map<BlockPosition, BlockSnapshot> wanted = new LinkedHashMap<>();
        for (int index = later.size() - 1; index >= 0; index--) {
            for (BlockChange change : later.get(index)) wanted.put(change.position(), change.before());
        }
        List<BlockChange> changes = new ArrayList<>();
        for (var entry : wanted.entrySet()) {
            BlockSnapshot now = live.read(entry.getKey());
            if (!now.equals(entry.getValue())) changes.add(new BlockChange(entry.getKey(), now, entry.getValue()));
        }
        return changes;
    }

    public static void apply(List<BlockChange> writes, Blocks target) throws IOException {
        Map<BlockPosition, BlockSnapshot> blocks = new LinkedHashMap<>();
        for (BlockChange change : writes) blocks.put(change.position(), change.after());
        if (!blocks.isEmpty()) target.write(blocks);
    }

    public static void rollback(List<BlockChange> applied, Blocks target) throws IOException {
        Map<BlockPosition, BlockSnapshot> blocks = new LinkedHashMap<>();
        for (int index = applied.size() - 1; index >= 0; index--) blocks.put(applied.get(index).position(), applied.get(index).before());
        if (!blocks.isEmpty()) target.write(blocks);
    }
}
