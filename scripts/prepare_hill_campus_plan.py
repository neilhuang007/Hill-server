"""Create a georeferenced footprint register and a searchable campus plan.

County rings are retained verbatim in WGS84 and transformed into the project's
local metre frame. Official school identities are a separate evidence layer:
one school name need not correspond to one county polygon.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import hybridize_voxelearth_roofer_world as anvil
import numpy as np
from build_hill_measured_terrain import (
    DEFAULT_OSM,
    MATERIAL_PRIORITY,
    load_surface_features,
    lonlat_geometry_to_world,
)
from campus_roof_geometry import (
    DEFAULT_MEASURED_TERRAIN_MANIFEST,
    _world_transform_from_measured_manifest,
    load_measured_building,
)
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as transform_geometry

ROOT = Path(__file__).resolve().parents[1]
BUILDINGS = ROOT / "runtime/campus-data/gis/montco-hill-buildings-full.geojson"
IDENTITIES = ROOT / "server-assets/hill-campus-building-identities.json"
OFFICIAL_MAP = "https://resources.finalsite.net/images/v1787600757/thehillorg/fky5ch2qhgl6lcsvhz06/FY26CampusMap_Labeled.pdf"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_id(feature):
    prefix = str(feature["properties"].get("STRUCTUREID") or "building")
    encoded = json.dumps(
        feature["geometry"], sort_keys=True, separators=(",", ":")
    ).encode()
    return f"{prefix}-{hashlib.sha1(encoded).hexdigest()[:10]}"


def svg_path(geometry):
    if geometry.is_empty:
        return ""
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    return " ".join(
        "M" + " L".join(f"{x:.3f},{z:.3f}" for x, z in ring.coords) + " Z"
        for polygon in polygons
        if polygon.geom_type == "Polygon"
        for ring in (polygon.exterior, *polygon.interiors)
    )


def prepare(output, identities_path=IDENTITIES, context=None):
    output.mkdir(parents=True, exist_ok=True)
    transform = _world_transform_from_measured_manifest(
        DEFAULT_MEASURED_TERRAIN_MANIFEST
    )
    if transform.blocks_per_metre != 1:
        raise ValueError(
            "Authoritative campus registry must use metres, not scaled block coordinates"
        )
    source = json.loads(BUILDINGS.read_text(encoding="utf-8"))
    city = json.loads(anvil.DEFAULT_ROOFER_CITYJSON.read_text(encoding="utf-8"))
    identities = (
        json.loads(identities_path.read_text(encoding="utf-8"))
        if identities_path.exists()
        else {}
    )
    current_studies = {}
    interpreted_studies = []
    landscape_layer = []
    context = context or ROOT / "server-assets/hill-campus-context.json"
    if context.is_file():
        context_profile = json.loads(context.read_text(encoding="utf-8"))
        for component in context_profile["components"]:
            study = ROOT / component["study"]
            profile = json.loads((study / "profile.json").read_text(encoding="utf-8"))
            if profile.get("interpreted_source"):
                interpreted_studies.append((component, profile))
            parent = profile.get("parent_id")
            if not parent:
                parent = next(
                    (
                        r["roofer_parent_id"]
                        for r in identities.get("buildings", [])
                        if r["name"] == component["name"]
                    ),
                    None,
                )
            if parent:
                current_studies[parent] = {
                    "path": component["study"],
                    "blocks_per_metre": profile["blocks_per_metre"],
                    "stage": component.get("detail_status", "developed_exterior"),
                    "detail_status": profile.get(
                        "detail_status",
                        "Developed exterior study; further photo refinement remains.",
                    ),
                }
        if context_profile.get("landscape"):
            landscape = json.loads(
                (ROOT / context_profile["landscape"]).read_text(encoding="utf-8")
            )
            landscape_layer.append(
                {
                    "path": svg_path(shape(landscape["lawn"]["outer_polygon_xz"])),
                    "kind": "quad_lawn",
                }
            )
            for bed in landscape["planting_beds"]:
                landscape_layer.append(
                    {"path": svg_path(shape(bed["polygon_xz"])), "kind": "quad_bed"}
                )
            for path in landscape["paths"]:
                landscape_layer.append(
                    {
                        "path": svg_path(shape(path["polygon_xz"])),
                        "kind": "quad_red_path"
                        if path["id"] == "quad_central_red_crosswalk"
                        else "quad_path",
                    }
                )
            for terrace in landscape.get("engineered_terraces", []):
                landscape_layer.append(
                    {
                        "path": svg_path(shape(terrace["polygon_xz"])),
                        "kind": "quad_path",
                    }
                )
            from shapely.geometry import LineString, Point

            for terrace in landscape.get("engineered_terraces", []):
                red = LineString(
                    [terrace["approach_start_xz_m"], terrace["threshold_xz_m"]]
                ).buffer(terrace.get("central_brick_width_m", 2.7) / 2)
                landscape_layer.append({"path": svg_path(red), "kind": "quad_red_path"})
            for tree in landscape["trees"]:
                landscape_layer.append(
                    {
                        "path": svg_path(
                            Point(tree["center_xz_m"]).buffer(tree["crown_radius_m"])
                        ),
                        "kind": "quad_tree",
                    }
                )
    records, local_features, geographic_features = [], [], []
    for index, feature in enumerate(source["features"], 1):
        geographic = shape(feature["geometry"])
        local = lonlat_geometry_to_world(geographic, transform)
        parent = stable_id(feature)
        matches = [
            r
            for r in identities.get("buildings", [])
            if r.get("roofer_parent_id") == parent
        ]
        attributes = city["CityObjects"].get(parent, {}).get("attributes", {})
        centre, ll = local.centroid, geographic.centroid
        bounds = list(local.bounds)
        record = {
            "index": index,
            "id": parent,
            "school_names": [r["name"] for r in matches],
            "school_map_numbers": [r["school_map_number"] for r in matches],
            "structure_id": feature["properties"].get("STRUCTUREID"),
            "parcel_id": feature["properties"].get("PARID"),
            "county_label": feature["properties"].get("IMPRNAME"),
            "county_category": feature["properties"].get("Category"),
            "centre_xz_m": [centre.x, centre.y],
            "centre_minecraft_xz_blocks": [centre.x * 2, centre.y * 2],
            "centre_lonlat": [ll.x, ll.y],
            "bounds_xz_m": bounds,
            "area_m2": local.area,
            "ring_count": sum(
                1 + len(p.interiors)
                for p in ([local] if local.geom_type == "Polygon" else local.geoms)
            ),
            "path": svg_path(local),
            "source_geometry": mapping(local),
            "roof": {
                "source_parent_exists": parent in city["CityObjects"],
                "reconstruction_success": attributes.get("rf_success"),
                "ground_navd88_m": attributes.get("rf_h_ground"),
                "ridge_navd88_m": attributes.get("rf_h_roof_ridge"),
                "rmse_m": attributes.get("rf_rmse_lod22"),
            },
            "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={ll.y:.8f},{ll.x:.8f}",
            "status": "included_in_shared_world"
            if parent in current_studies
            else "footprint_registered",
            "study": current_studies.get(parent),
            "google_ring_review": "Not individually certified; use linked map comparison",
        }
        records.append(record)
        props = {
            key: value
            for key, value in record.items()
            if key not in ("path", "source_geometry")
        }
        local_features.append(
            {"type": "Feature", "geometry": mapping(local), "properties": props}
        )
        geographic_features.append(
            {"type": "Feature", "geometry": feature["geometry"], "properties": props}
        )
    # Newer structures have their own interpreted layer. Never fabricate a
    # county parent or present plan/photo estimates as LiDAR measurements.
    east, _up, south = transform._basis()
    inverse = Transformer.from_crs("EPSG:4978", "EPSG:4979", always_xy=True)

    def local_to_lonlat(x, z, _height=None):
        x, z = np.asarray(x), np.asarray(z)
        ecef = [transform.origin_ecef[i] + east[i] * x + south[i] * z for i in range(3)]
        lon, lat, _alt = inverse.transform(*ecef)
        return lon, lat

    for component, profile in interpreted_studies:
        proposal = profile["interpreted_source"]
        local = shape(proposal["polygon_xz"])
        geographic = transform_geometry(local_to_lonlat, local)
        centre, ll = local.centroid, geographic.centroid
        record = {
            "index": len(records) + 1,
            "id": proposal["id"],
            "school_names": [proposal["name"]],
            "school_map_numbers": [proposal["school_map_number"]],
            "structure_id": None,
            "parcel_id": None,
            "county_label": None,
            "county_category": None,
            "centre_xz_m": [centre.x, centre.y],
            "centre_minecraft_xz_blocks": [centre.x * 2, centre.y * 2],
            "centre_lonlat": [ll.x, ll.y],
            "bounds_xz_m": list(local.bounds),
            "area_m2": local.area,
            "ring_count": 1,
            "path": svg_path(local),
            "source_geometry": mapping(local),
            "geometry_evidence": proposal["status"],
            "horizontal_uncertainty_m": proposal["horizontal_uncertainty_m"],
            "roof": {
                "source_parent_exists": False,
                "reconstruction_success": None,
                "ground_navd88_m": None,
                "ridge_navd88_m": None,
                "rmse_m": None,
            },
            "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={ll.y:.8f},{ll.x:.8f}",
            "status": "included_in_shared_world",
            "study": {
                "path": component["study"],
                "blocks_per_metre": 2,
                "stage": "interpreted_structure",
                "detail_status": profile["detail_status"],
            },
            "google_ring_review": "Separate plan/photo interpretation; no county ring or survey claim.",
        }
        records.append(record)
        props = {
            k: v for k, v in record.items() if k not in ("path", "source_geometry")
        }
        local_features.append(
            {"type": "Feature", "geometry": mapping(local), "properties": props}
        )
        geographic_features.append(
            {"type": "Feature", "geometry": mapping(geographic), "properties": props}
        )
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Duplicate stable footprint identifiers")

    # Restore intentional pond/field/path classes from OSM tags; the old
    # surface export collapses everything to only 'hard' and 'grass'.
    features, surface_evidence = load_surface_features(
        anvil.DEFAULT_CAMPUS_SURFACES, DEFAULT_OSM, transform
    )
    features.sort(
        key=lambda f: (
            MATERIAL_PRIORITY.index(f.material)
            if f.material in MATERIAL_PRIORITY
            else -1
        )
    )
    surfaces = [
        {
            "path": svg_path(f.geometry),
            "kind": f.material,
            "name": f.name,
            "source_id": f.source_id,
        }
        for f in features
    ]
    academic = next(b for b in records if b["id"] == "16001511600613C-92645e8573")
    measured = load_measured_building(parent_id=academic["id"])
    academic["county_path"] = academic["path"]
    academic["path"] = svg_path(measured.footprint)
    academic["display_geometry_source"] = (
        "Roofer ground footprint; open court retained, county ring is shown faintly behind it"
    )
    academic["construction_geometry"] = mapping(measured.footprint)
    academic["google_ring_review"] = {
        "reviewed_utc_date": "2026-09-05",
        "url": "https://www.google.com/maps/@40.2445816,-75.6345728,19z",
        "result": "Visual location/orientation and separate Athey/Dining court relation agree. Google displays simplified rings; detailed geometry retains independent county and LiDAR sources.",
    }
    parcels = []
    for feature in json.loads(
        anvil.DEFAULT_CAMPUS_BOUNDARY.read_text(encoding="utf-8")
    )["features"]:
        geo = lonlat_geometry_to_world(shape(feature["geometry"]), transform)
        parcels.append(svg_path(geo))

    dataset = {
        "format": "hill-campus-footprint-register-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "origin_lat_lon": [transform.center_latitude, transform.center_longitude],
        "origin_ecef_m": list(transform.origin_ecef),
        "axis": "+X east, +Z south; local units are metres, north is -Z",
        "detailed_minecraft_frame": {
            "blocks_per_metre": 2,
            "vertical_offset_m": -25,
            "mapping": "X=local east metres*2; Z=local south metres*2; Y=(NAVD88 metres-25)*2",
            "status": "Current campus assembly uses 2 blocks per metre throughout, following the user's preferred player-relative scale. Earlier 4x studies remain archived.",
        },
        "scope": "108 county source footprints, including nearby context and outbuildings, plus separately marked post-survey structures. This is not a count of distinct school buildings.",
        "official_map": OFFICIAL_MAP,
        "sources": {
            "county": {
                "path": str(BUILDINGS),
                "sha256": digest(BUILDINGS),
                "url": "https://services1.arcgis.com/kOChldNuKsox8qZD/arcgis/rest/services/Montgomery_County_Building_Outlines/FeatureServer/6",
            },
            "roofer": {
                "path": str(anvil.DEFAULT_ROOFER_CITYJSON),
                "sha256": digest(anvil.DEFAULT_ROOFER_CITYJSON),
            },
            "school": "https://www.thehill.org/about/our-campus",
            "identities_sha256": digest(identities_path)
            if identities_path.exists()
            else None,
        },
        "view_bounds": {
            "quad": [-24, -66, 168, 92],
            "core": [-265, -315, 585, 180],
            "campus": [-285, -1020, 740, 185],
            "all": [-310, -1830, 1390, 205],
        },
        "buildings": records,
        "identities": identities,
        "surfaces": surfaces,
        "landscape": landscape_layer,
        "surface_evidence": surface_evidence,
        "parcels": parcels,
        "notes": [
            "Building names and official map numbers are distinct from stale county labels.",
            "The Athey/Dining county aggregate has no court hole. Preserve the open court from the measured roof and the official current aerial when constructing architecture.",
            "Google Maps is a linked visual cross-check. The exported coordinates come from county data, not a claim of extracted Google polygons.",
            "Block scale and vertical datum are export choices; never rescale or relocate a single building within a campus world.",
        ],
    }
    (output / "campus-register.json").write_text(
        json.dumps(dataset, indent=2) + "\n", encoding="utf-8"
    )
    for name, features in (
        ("footprints-wgs84.geojson", geographic_features),
        ("footprints-local-metres.json", local_features),
    ):
        (output / name).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "coordinate_system": "WGS84 longitude/latitude"
                    if "wgs84" in name
                    else dataset["axis"],
                    "features": features,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    with (output / "building-positions.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Index",
                "Stable ID",
                "School map numbers",
                "Verified school names",
                "County label (unverified current name)",
                "X metres",
                "Z metres",
                "X Minecraft blocks (2 per metre)",
                "Z Minecraft blocks (2 per metre)",
                "Longitude",
                "Latitude",
                "Footprint area m2",
                "Google Maps",
            ]
        )
        for b in records:
            writer.writerow(
                [
                    b["index"],
                    b["id"],
                    "/".join(map(str, b["school_map_numbers"])),
                    " / ".join(b["school_names"]),
                    b["county_label"],
                    *b["centre_xz_m"],
                    *b["centre_minecraft_xz_blocks"],
                    *b["centre_lonlat"],
                    b["area_m2"],
                    b["google_maps_url"],
                ]
            )
    template = (ROOT / "server-assets/hill-campus-plan.template.html").read_text(
        encoding="utf-8"
    )
    (output / "index.html").write_text(
        template.replace(
            "/*__CAMPUS_DATA__*/", json.dumps(dataset).replace("<", "\\u003c")
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "footprints": len(records),
                "source_parents_matched": sum(
                    b["roof"]["source_parent_exists"] for b in records
                ),
                "surfaces": len(surfaces),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT / "runtime/campus-reconstruction/campus-plan-v1",
    )
    p.add_argument("--identities", type=Path, default=IDENTITIES)
    p.add_argument("--context", type=Path)
    a = p.parse_args()
    prepare(a.output, a.identities, a.context)
