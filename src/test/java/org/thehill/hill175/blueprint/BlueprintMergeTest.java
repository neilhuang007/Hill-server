package org.thehill.hill175.blueprint;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BlueprintMergeTest {
    private static final BlockSnapshot GRASS = block("minecraft:grass_block[snowy=false]");
    private static final BlockSnapshot STONE = block("minecraft:stone");
    private static final BlockSnapshot BRICK = block("minecraft:bricks");
    private static final BlockSnapshot GLASS = block("minecraft:glass");

    @Test
    void campusUpdateAppliesCleanBlocksAndReportsOverlaps() throws Exception {
        BlockPosition untouched = new BlockPosition(0, 64, 0);
        BlockPosition alreadyMatching = new BlockPosition(1, 64, 0);
        BlockPosition studentChanged = new BlockPosition(2, 64, 0);
        BlockPosition outside = new BlockPosition(500, 64, 0);
        Blocks campus = new Blocks(Map.of(untouched, GRASS, alreadyMatching, STONE, studentChanged, BRICK, outside, GRASS));
        List<BlockChange> revision = List.of(new BlockChange(untouched, GRASS, STONE), new BlockChange(alreadyMatching, GRASS, STONE),
                new BlockChange(studentChanged, GRASS, STONE), new BlockChange(outside, GRASS, STONE));

        var update = BlueprintMerge.update(revision, campus, false, position -> position.blockX() < 100);

        assertEquals(List.of(new BlockChange(untouched, GRASS, STONE)), update.writes());
        assertEquals(List.of(new BlockChange(studentChanged, GRASS, STONE)), update.conflicts());

        var own = BlueprintMerge.update(revision, campus, true, position -> true);
        assertTrue(own.writes().isEmpty() && own.conflicts().isEmpty(), "A student's own approved snapshot never overwrites later edits.");
    }

    @Test
    void approvalPlanLetsModeratorChooseTheConflictWinner() throws Exception {
        BlockPosition clean = new BlockPosition(0, 64, 0);
        BlockPosition done = new BlockPosition(1, 64, 0);
        BlockPosition overlap = new BlockPosition(2, 64, 0);
        Blocks blueprint = new Blocks(Map.of(clean, GRASS, done, BRICK, overlap, GLASS));
        List<BlockChange> request = List.of(new BlockChange(clean, GRASS, BRICK), new BlockChange(done, GRASS, BRICK), new BlockChange(overlap, GRASS, BRICK));

        var plan = BlueprintMerge.plan(request, blueprint);

        assertEquals(1, plan.alreadyApplied());
        assertEquals(List.of(new BlockChange(clean, GRASS, BRICK)), plan.writes(false));
        assertEquals(List.of(new BlockChange(clean, GRASS, BRICK), new BlockChange(overlap, GLASS, BRICK)), plan.writes(true));

        BlueprintMerge.apply(plan.writes(true), blueprint);
        assertEquals(BRICK, blueprint.read(overlap));
    }

    @Test
    void rollbackRestoresEachBlockToItsStateBeforeTheFirstLaterUpdate() throws Exception {
        BlockPosition twice = new BlockPosition(0, 64, 0);
        BlockPosition once = new BlockPosition(1, 64, 0);
        BlockPosition editedSince = new BlockPosition(2, 64, 0);
        Blocks live = new Blocks(Map.of(twice, GLASS, once, BRICK, editedSince, GLASS));
        List<BlockChange> update2 = List.of(new BlockChange(twice, GRASS, STONE), new BlockChange(editedSince, GRASS, BRICK));
        List<BlockChange> update3 = List.of(new BlockChange(twice, STONE, GLASS), new BlockChange(once, STONE, BRICK));

        var changes = BlueprintMerge.revert(List.of(update2, update3), live);
        BlueprintMerge.apply(changes, live);

        assertEquals(GRASS, live.read(twice));
        assertEquals(STONE, live.read(once));
        assertEquals(GRASS, live.read(editedSince));
        assertTrue(BlueprintMerge.revert(List.of(update2, update3), live).isEmpty(), "Rolling back twice changes nothing.");
    }

    @Test
    void nearbyChangesShareOneBoxAndDistantChangesGetTheirOwn() {
        var areas = ChangeAreas.of(List.of(new BlockPosition(0, 64, 0), new BlockPosition(5, 70, 3), new BlockPosition(200, 64, 200)));

        assertEquals(2, areas.size());
        assertEquals(List.of(0, 64, 0, 5, 70, 3), List.of(areas.get(0).minX(), areas.get(0).minY(), areas.get(0).minZ(),
                areas.get(0).maxX(), areas.get(0).maxY(), areas.get(0).maxZ()));
        assertEquals(1, areas.get(1).size());
    }

    private static BlockSnapshot block(String data) { return new BlockSnapshot(data, null); }

    private static final class Blocks implements BlueprintMerge.Blocks {
        private final Map<BlockPosition, BlockSnapshot> blocks;
        Blocks(Map<BlockPosition, BlockSnapshot> blocks) { this.blocks = new HashMap<>(blocks); }
        @Override public BlockSnapshot read(BlockPosition position) { return blocks.getOrDefault(position, block("minecraft:air")); }
        @Override public void write(BlockPosition position, BlockSnapshot snapshot) { blocks.put(position, snapshot); }
    }
}
