# Current work and historical outputs

Server logistics updated 2026-09-28: operational tooling moved to `ops/`, and the
server's People template now selects frozen v19 via `server-assets/campus-template.env`.
The local launcher selection and reconstruction paths below remain unchanged.
See the [cleanup record](operations/repository-cleanup-20260928.md) and
[deployment guide](operations/deployment.md).

Updated 2026-09-27. Construction is paused at the user's request. The combined v19 campus has separately verified Minecraft Java 26.1.2 and 1.21.11 ZIPs. The 1.21.11 port was converted from the frozen build source and its 15,624 chunks passed full block state parity after the official server loaded and saved it; see the [port handoff](hill-campus-port-12111.md). The 26.1.2 save was visually reviewed in 22 useful native views. The authoritative launcher still selects the older v14. See the [download handoff](hill-campus-download-20260927.md), [session checkpoint](../runtime/campus-reconstruction/core-demo-20260927/working-handoff.json) and [44-component inventory](research/hill-campus-exterior-draft-20260927.md). All earlier worlds and separate unfinished building/road drafts remain preserved.

## Start here

- **Open the campus:** [Open-Hill-Campus.cmd](../Open-Hill-Campus.cmd).
- **Agent handoff:** [AGENTS.md](../AGENTS.md).
- **Current selection:** [hill-campus-current.json](../server-assets/hill-campus-current.json).
- **Assembly/environment inputs:** [hill-campus-context-v14.json](../server-assets/hill-campus-context-v14.json).

## Working folders

Paths below are relative to `runtime/campus-reconstruction/`.

| Purpose | Folder | State |
| --- | --- | --- |
| Latest downloadable combined campus | `campus-context-v19-2x/` | Bounded core exterior review complete; 44 components retained, 23 unfinished measured shells. |
| V19 playable demonstration save | `campus-preview-v19-2x/` | Creative save converted in Java 26.1.2; client closed normally; source of the verified ZIP. |
| Download package | `exports/Hill-School-175th-v19-Java-26.1.2.zip` | 10,746,614 bytes; CRC and every archived file hash verified against the save. |
| 1.21.11 port and download | `campus-port-1.21.11-v19b/`, `exports/Hill-School-175th-v19-Java-1.21.11.zip` | Full 15,624-chunk official conversion; exact source block states, 9,018,267-byte verified ZIP. |
| 1.21.11 persistent playable save | `campus-playable-v19-1.21.11/` | Launched directly by root `Open-Hill-Campus-1.21.11.ps1`; Creative Quick Play join and responsive native window verified. |
| Unchanged launcher selection | `campus-context-v14-2x/` | Earlier September 23 demo environment revision. |
| Current player save target | `campus-playable-v14-2x/` | Persistent demonstration save; earlier player saves remain preserved. |
| Demo preparation and source inventory | `demo-prep-20260923/` | Environment plan, source inventory, review cameras and prior launcher selection. |
| Required accepted environment base | `campus-context-v13-2x/` | Immutable input to v14; do not archive or delete. |
| Davy | `davy-v11-2x/` | Individually reviewed and integrated into campus v9. |
| Sherrill | `sherrill-v11-2x/` | Bounded dormer acceptance, retained in v12; all-height proof confirms minimum wall steps. |
| Quadrivium | `quadrivium-v8-2x/` | Bounded native acceptance, integrated v10. |
| Dining / CFTA | `athey-dining-v6-2x/`, `cfta-v5-2x/` | Accepted and integrated into campus v12. |
| Tuck / Rink | `tuck-rink-v6-2x/` | Accepted and integrated into campus v12, with connected wall corners. |
| Integrated individual buildings | `athey-frame-v4-2x/`, `feroe-v7-2x/`, `business-office-v4-2x/`, `meigs-v4-2x/`, `thomas-v5-2x/`, `east-faculty3-v8-2x/`, `foster-v14-2x/`, `rolfe-v7-2x/` | Included in campus v8 within their documented review limits. |
| Native screenshots and reports | `chapel-native-qa/runs/` | Building and campus visual evidence. Historical campus capture save copies were archived; their screenshots/reports remain. |

**Dining/Athey v6, CFTA v5 and Tuck/Rink v6 remain integrated within their documented review limits.** Davy v11, Sherrill v11, Quadrivium v8, Rolfe v7, Foster v14, Annan v2 and Mercer/Day/Sweeney v6 are all retained. Both covered Athey courtyard passages pass all 20 actual-player routes. V14 adds eight verified exterior route connections; follow the [live progress record](hill-anniversary-build-progress-20260915.md).

### Required inputs

Keep `campus-full-detail-terrain-v2/`, `campus-developed-ground-v6-2x/`, `campus-envelopes-v2-ground/`, the preparation/terrain directories, `roofer-chapel-trial/`, and `component-cache/`. Older revision numbers do not mean these are obsolete: the current assembly and building generators still use them.

Research and source data remain in `runtime/research/`, `runtime/campus-data/`, `data/` and the retained tool/source directories. The legacy VoxelEarth v11 terrain source and v15 datum/deployment source remain because tools still reference them. The deployed People template and its v15 distribution archives also remain separate from local construction.

## Historical archive

Early Arnis worlds, old one-block-per-metre hybrid attempts, old render caches, combined campus v1–v7 exports, and duplicate historical campus capture worlds were moved out of the working folders:

```text
runtime/campus-history/cleanup-20260915/
  outputs/runtime/...          # Original relative paths of 113 obsolete outputs
  saved-worlds/                # Previous v3 and v6 interactive player saves
  archive-moves.json           # Exact source-to-archive path mapping
  archive-journal.jsonl        # Completed moves
  summary.json                # Totals and protected-artifact verification
```

The archive contains about 7.33 GiB of generated outputs plus the two player saves. This was a reversible move, not deletion or disk-space reclamation. The current campus and all individual building studies stayed in place; 50 protected artifact hashes matched before and after the moves.

Historical manifests and research can quote their original output paths. Use `archive-moves.json` to locate those archived files. Do not select an archived world as the current campus or treat an old experimental generator's default output as active work.
