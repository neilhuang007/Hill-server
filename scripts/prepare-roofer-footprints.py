#!/usr/bin/env python3
"""Reproject GeoJSON roofprints and add deterministic IDs for Roofer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-crs", default="EPSG:4326")
    parser.add_argument("--target-crs", default="EPSG:6347")
    parser.add_argument("--source-id", default="STRUCTUREID")
    parser.add_argument("--output-id", default="ROOFER_ID")
    return parser.parse_args()


def stable_feature_id(feature: dict, source_id: str) -> str:
    properties = feature.get("properties") or {}
    prefix = str(properties.get(source_id) or "building")
    geometry = json.dumps(
        feature["geometry"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}-{hashlib.sha1(geometry).hexdigest()[:10]}"


def main() -> int:
    args = parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    project = Transformer.from_crs(
        args.source_crs, args.target_crs, always_xy=True
    ).transform

    features = []
    for feature in source.get("features", []):
        properties = dict(feature.get("properties") or {})
        properties[args.output_id] = stable_feature_id(feature, args.source_id)
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": mapping(transform(project, shape(feature["geometry"]))),
            }
        )

    identifiers = [feature["properties"][args.output_id] for feature in features]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{args.output_id} values are not unique")

    output = {
        "type": "FeatureCollection",
        "name": f"{args.input.stem}_{args.target_crs.lower().replace(':', '')}",
        "crs": {
            "type": "name",
            "properties": {"name": args.target_crs},
        },
        "features": features,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, separators=(",", ":")), encoding="utf-8"
    )
    print(f"Prepared {len(features)} unique roofprints at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
