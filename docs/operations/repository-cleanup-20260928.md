# September 28 repository cleanup

Server operations now live in `ops/`, separate from Java source and campus tools.
The README links current deployment, player, and SSO design documents. Full prior
construction state is preserved in `docs/campus/BUILD_STATE.md`.

Reconstruction paths, immutable revisions, player saves, reference packets, and
dependencies are retained. Existing uncommitted source/tests are checkpointed,
not discarded.

Generated BlueMap `web/`, log-only `data/`, an empty dependency `io/` tree,
`roofer.log.json`, unprovenanced `structure (1).nbt`, and old Word proposals moved to:

```text
runtime/repository-archive/cleanup-20260928/
```

`archive-manifest.json` records exact source/destination paths and hashes for
**1,671 files / 101,643,723 bytes**. Each hash matched after moving. No file content
was deleted. The previous README is also saved there. This archive is local-only
and should be backed up separately from Git.

`structure.nbt` and `combined_3d_tiles.glb` remain at their existing ignored paths
because tools reference them. Shared ignore rules exclude generated maps, logs,
caches, office locks, credentials, and dependencies. The local `.git/info/exclude`
adds machine-only artifact exclusions. `.gitattributes` keeps Linux scripts LF
on Windows checkouts; `.editorconfig` records whitespace conventions.

This cleanup separates source and artifacts; it does not reclaim disk space.
