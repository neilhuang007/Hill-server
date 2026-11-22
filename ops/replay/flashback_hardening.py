"""Narrow, fail-closed source overlay for pinned MIT FlashbackServer 1.2.4.

Only RefusedPackets and FlashbackRecorder are recompiled. Version-specific NMS
adapters and all other upstream classes remain byte-for-byte unchanged.
"""

POLICY_SOURCE = '''package dev.zeffut.flashbackserver.record;

import java.nio.file.Path;
import java.util.Set;
import java.util.UUID;
import java.util.Map;
import java.util.function.UnaryOperator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

/** Hill overlay v1. Upstream MIT source: Zeffut/FlashbackServer 1.2.4. */
public final class HillRecordingPolicy {
    public static final long MAX_RETAINED_BYTES = 16L * 1024 * 1024;
    public static final int MAX_RETAINED_ACTIONS = 100_000;
    private static final Set<UUID> GAPS = ConcurrentHashMap.newKeySet();
    private static final Map<UUID, UnaryOperator<byte[]>> MOVEMENT_FILTERS = new ConcurrentHashMap<>();
    private HillRecordingPolicy() {}
    public static int version() { return 1; }
    public static boolean consumeGap(UUID player) { return GAPS.remove(player); }
    public static void setMovementFilter(UUID player, UnaryOperator<byte[]> filter) {
        if (filter == null) MOVEMENT_FILTERS.remove(player);
        else MOVEMENT_FILTERS.put(player, filter);
    }
    private static UUID playerId(Path path) {
        String name = path.getFileName().toString();
        if (name.endsWith(".flashback") && name.length() >= 46) {
            try { return UUID.fromString(name.substring(name.length() - 46, name.length() - 10)); }
            catch (IllegalArgumentException ignored) {}
        }
        return null;
    }
    public static byte[] filterMovement(Path path, byte[] payload) {
        UUID player = playerId(path);
        UnaryOperator<byte[]> filter = player == null ? null : MOVEMENT_FILTERS.get(player);
        if (filter == null) return null;
        try { return filter.apply(payload); }
        catch (RuntimeException error) { markGap(path, "movement visibility filter failed"); return null; }
    }
    public static void markGap(Path path, String reason) {
        UUID player = playerId(path);
        if (player != null) GAPS.add(player);
        Logger.getLogger("FlashbackServer").warning("REPLAY GAP: " + path.getFileName() + " " + reason
            + "; this segment is incomplete, not lossless evidence");
    }
}
'''

# Deliberately broader than just signed chat: commands and one-time links are
# generally sent in system chat, and plugins may display them in UI overlays.
PRIVATE_PACKETS = (
    "ClientboundSystemChatPacket", "ClientboundDisguisedChatPacket",
    "ClientboundSetActionBarTextPacket", "ClientboundSetTitleTextPacket",
    "ClientboundSetSubtitleTextPacket", "ClientboundTabListPacket",
    "ClientboundBossEventPacket", "ClientboundSetObjectivePacket",
    "ClientboundSetScorePacket", "ClientboundSetPlayerTeamPacket",
    "ClientboundResetScorePacket", "ClientboundSetDisplayObjectivePacket",
)


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("Pinned upstream source no longer matches hardening patch")
    return text.replace(old, new, 1)


def patch_refused(text: str) -> str:
    extra = "\n".join('            "' + name + '",' for name in PRIVATE_PACKETS)
    return replace_once(text, '    private static final Set<String> REFUSED = Set.of(',
                        '    private static final Set<String> REFUSED = Set.of(\n' + extra)


def patch_recorder(text: str) -> str:
    text = replace_once(text, '    private boolean stopped = false;', '''    private boolean stopped = false;
    private long retainedBytes;
    private boolean hillSnapshotReady;
    private int retainedActions;
    private boolean capped;

    private boolean accept(byte[] payload) {
        if (capped) return false;
        long cost = (long) payload.length + 128;
        if (retainedActions >= HillRecordingPolicy.MAX_RETAINED_ACTIONS
                || cost > HillRecordingPolicy.MAX_RETAINED_BYTES - retainedBytes) {
            capped = true;
            HillRecordingPolicy.markGap(output, "retained byte/action limit reached");
            return false;
        }
        retainedActions++;
        retainedBytes += cost;
        return true;
    }''')
    text = replace_once(text, '            this.snapshot = List.copyOf(snapshot);', '''            if (stopped || capped) return;
            long bytes = 0;
            for (ReplayAction action : snapshot) bytes += (long) action.payload().length + 128;
            if (snapshot.size() > HillRecordingPolicy.MAX_RETAINED_ACTIONS - retainedActions
                    || bytes > HillRecordingPolicy.MAX_RETAINED_BYTES - retainedBytes) {
                capped = true;
                HillRecordingPolicy.markGap(output, "initial snapshot exceeds bound; not renderable");
                return;
            }
            retainedActions += snapshot.size();
            retainedBytes += bytes;
            this.snapshot = List.copyOf(snapshot);
            hillSnapshotReady = true;''')
    text = replace_once(text, '            currentChunk.add(new ReplayAction(GAME_PACKET_ACTION, idAndPayload));',
                        '            if (accept(idAndPayload)) currentChunk.add(new ReplayAction(GAME_PACKET_ACTION, idAndPayload));')
    text = replace_once(text, '            currentChunk.add(new ReplayAction(MOVE_ENTITIES_ACTION, payload));',
                        '            payload = HillRecordingPolicy.filterMovement(output, payload);\n            if (payload != null && accept(payload)) currentChunk.add(new ReplayAction(MOVE_ENTITIES_ACTION, payload));')
    text = replace_once(text, '            currentChunk.add(new ReplayAction(NEXT_TICK_ACTION, new byte[0]));',
                        '            if (!accept(new byte[0])) return;\n            currentChunk.add(new ReplayAction(NEXT_TICK_ACTION, new byte[0]));')
    text = replace_once(text, '            stopped = true;', '''            if (!hillSnapshotReady) HillRecordingPolicy.markGap(output, "missing/failed initial snapshot; not renderable");
            stopped = true;''')
    return text


def patch_plugin_yml(text: str) -> str:
    return replace_once(text, '    default: op', '    default: false')


def patch_config_yml(text: str) -> str:
    text = replace_once(text, '  auto-clip-on-death: true', '  auto-clip-on-death: false')
    return replace_once(text, '  enabled: true', '  enabled: false')
