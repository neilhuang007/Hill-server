"""Check diagonal glass joints directly in exported building archives."""

import argparse
from functools import lru_cache
import json
from pathlib import Path

import numpy as np
from campus_study_io import digest, write_json
from campus_window_frames import pane_joint_report, pane_perimeter_report

ROOT = Path(__file__).resolve().parents[1]


class ArchiveStates:
    """Sparse lookup retaining all backing blocks without a dense world grid."""
    def __init__(self, path):
        with np.load(path, allow_pickle=False) as a:
            self.coords, self.states = a["coords"], a["state_ids"]
            self.palette = json.loads(str(a["palette_json"]))
        if self.palette[0]["Name"] != "minecraft:air":
            raise ValueError("Expected archive palette zero to be air")
        self.low = self.coords.min(axis=0)
        self.high = self.coords.max(axis=0) + 1
        self.width, self.depth = int(self.high[0]-self.low[0]), int(self.high[2]-self.low[2])
        self.keys = self.encode(self.coords)
        if np.any(self.keys[1:] <= self.keys[:-1]):
            order = np.argsort(self.keys)
            self.keys, self.states, self.coords = self.keys[order], self.states[order], self.coords[order]
            if np.any(self.keys[1:] == self.keys[:-1]):
                raise ValueError("Duplicate archive coordinates")

    def encode(self, q):
        q = np.asarray(q, dtype=np.int64) - self.low
        return (q[...,1] * self.depth + q[...,2]) * self.width + q[...,0]

    @lru_cache(maxsize=None)
    def get(self, x, y, z):
        q = np.array([x,y,z])
        if np.any(q < self.low) or np.any(q >= self.high):
            return 0
        key = self.encode(q)
        index = int(np.searchsorted(self.keys, key))
        return int(self.states[index]) if index < len(self.keys) and self.keys[index] == key else 0

    def iter_panes(self):
        ids = [i for i, p in enumerate(self.palette) if p["Name"].endswith("_pane")]
        return (tuple(map(int,q)) for q in self.coords[np.isin(self.states, ids)])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", type=Path, action="append", default=[])
    ap.add_argument("--config", type=Path, action="append", default=[])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    studies = list(args.study)
    for config in args.config:
        p = json.loads(config.read_text(encoding="utf-8"))
        specs = p if isinstance(p,list) else p["components"]
        studies.extend(ROOT / c["study"] for c in specs)
    reports = []
    for path in dict.fromkeys(p.resolve() for p in studies):
        archive = path / "sample-blocks.npz"
        lookup = ArchiveStates(archive)
        report = pane_joint_report(lookup)
        report["perimeter"] = pane_perimeter_report(lookup)
        report.update(study=str(path), archive_sha256=digest(archive))
        reports.append(report)
        print(json.dumps({"study": path.name, "panes": report["panes"], "diagonal_gaps": report["unbridged_diagonal_pairs"], "bad_connections": report["disconnected_adjacent_pairs"], "horizontal_frame_candidates": report["perimeter"]["fewer_than_two_horizontal_joins"], "vertical_frame_candidates": report["perimeter"]["vertical_air_or_reversed_slab_contacts"]}), flush=True)
        lookup.get.cache_clear()
        del lookup
    write_json(args.output, {"scope": "Diagonal and adjacent-pane joints plus candidate frame-contact defects; full wall, partial block and roof closure require occupied-shape/native review.", "studies": reports})


if __name__ == "__main__":
    main()
