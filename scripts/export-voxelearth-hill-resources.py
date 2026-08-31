#!/usr/bin/env python3
"""Export Hill School resource GeoJSONs for the local VoxelEarth plugin.

This does not generate a Minecraft world. It prepares the spatial masks that
the VoxelEarth plugin uses after its normal mesh voxelization pass:

* campus parcel clip boundary
* county building footprints
* OSM-derived hard/grass surface hints
* OSM-derived water polygons
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from pyproj import Transformer
from shapely.geometry import LineString, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union


WGS84 = "EPSG:4326"
UTM18N = "EPSG:26918"


def clean(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.is_empty:
        return geometry
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    return geometry


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_geojson(path: Path, features: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "type": "FeatureCollection",
        "features": features,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def feature(geometry: BaseGeometry, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": properties or {},
        "geometry": mapping(geometry),
    }


def polygonal_parts(geometry: BaseGeometry) -> Iterable[BaseGeometry]:
    geometry = clean(geometry)
    if geometry.is_empty:
        return
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        for part in getattr(geometry, "geoms", [geometry]):
            if not part.is_empty and part.area > 0:
                yield part
    elif geometry.geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from polygonal_parts(part)


def linestring_from_osm_geometry(coords: list[dict[str, Any]]) -> LineString | None:
    points = [(node["lon"], node["lat"]) for node in coords if "lon" in node and "lat" in node]
    if len(points) < 2:
        return None
    return LineString(points)


def osm_way_geometry(element: dict[str, Any]) -> BaseGeometry | None:
    line = linestring_from_osm_geometry(element.get("geometry") or [])
    if line is None:
        return None
    tags = element.get("tags", {}) or {}
    coords = list(line.coords)
    closed = len(coords) >= 4 and coords[0] == coords[-1]
    is_area = closed and (
        tags.get("area") == "yes"
        or "amenity" in tags
        or "leisure" in tags
        or "landuse" in tags
        or tags.get("natural") in {"water", "wood", "scrub"}
        or "water" in tags
    )
    try:
        if is_area:
            return clean(Polygon(coords))
        return line
    except Exception:
        return None


def osm_relation_geometry(element: dict[str, Any]) -> BaseGeometry | None:
    outers: list[list[tuple[float, float]]] = []
    inners: list[list[tuple[float, float]]] = []
    open_lines: list[BaseGeometry] = []
    for member in element.get("members", []) or []:
        line = linestring_from_osm_geometry(member.get("geometry") or [])
        if line is None:
            continue
        coords = list(line.coords)
        closed = len(coords) >= 4 and coords[0] == coords[-1]
        role = member.get("role", "")
        if closed and role == "inner":
            inners.append(coords)
        elif closed:
            outers.append(coords)
        else:
            open_lines.append(line)

    polygons: list[BaseGeometry] = []
    inner_polygons = []
    for ring in inners:
        try:
            candidate = clean(Polygon(ring))
            if not candidate.is_empty:
                inner_polygons.append(candidate)
        except Exception:
            continue

    for ring in outers:
        try:
            outer = clean(Polygon(ring))
            if outer.is_empty:
                continue
            holes = [
                list(inner.exterior.coords)
                for inner in inner_polygons
                if outer.contains(inner.representative_point())
            ]
            polygon = clean(Polygon(list(outer.exterior.coords), holes))
            if not polygon.is_empty:
                polygons.append(polygon)
        except Exception:
            continue

    geometries = polygons + open_lines
    if not geometries:
        return None
    return clean(unary_union(geometries))


def osm_geometry(element: dict[str, Any]) -> BaseGeometry | None:
    try:
        if element.get("type") == "relation":
            geometry = osm_relation_geometry(element)
        elif element.get("type") == "way":
            geometry = osm_way_geometry(element)
        else:
            geometry = None
        if geometry is None or geometry.is_empty:
            return None
        return clean(geometry)
    except Exception:
        return None


def metre_buffer(
    geometry_wgs84: BaseGeometry,
    width_metres: float,
    to_utm: Transformer,
    to_wgs84: Transformer,
) -> BaseGeometry:
    if geometry_wgs84.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry_wgs84
    geometry_utm = transform(to_utm.transform, geometry_wgs84)
    buffered = geometry_utm.buffer(max(width_metres, 0.5) / 2.0, cap_style=2, join_style=2)
    return clean(transform(to_wgs84.transform, buffered))


def load_boundary(parcels_path: Path) -> BaseGeometry:
    parcels = read_json(parcels_path)
    geometries = [
        clean(shape(item["geometry"]))
        for item in parcels.get("features", [])
        if item.get("geometry")
    ]
    if not geometries:
        raise RuntimeError(f"No parcel geometries in {parcels_path}")
    return clean(unary_union(geometries))


def copy_buildings(buildings_path: Path, output_path: Path) -> None:
    buildings = read_json(buildings_path)
    features: list[dict[str, Any]] = []
    for item in buildings.get("features", []):
        if not item.get("geometry"):
            continue
        geometry = clean(shape(item["geometry"]))
        for part in polygonal_parts(geometry):
            features.append(feature(part, item.get("properties") or {}))
    write_geojson(output_path, features)


def load_resource_polygons(path: Path) -> list[tuple[BaseGeometry, dict[str, Any]]]:
    if not path.is_file():
        return []
    payload = read_json(path)
    loaded: list[tuple[BaseGeometry, dict[str, Any]]] = []
    for item in payload.get("features", []):
        if not item.get("geometry"):
            continue
        properties = item.get("properties") or {}
        geometry = clean(shape(item["geometry"]))
        for part in polygonal_parts(geometry):
            loaded.append((part, properties))
    return loaded


def export_boundary(boundary: BaseGeometry, output_path: Path) -> None:
    write_geojson(output_path, [feature(boundary, {"kind": "boundary", "source": "montgomery-county-parcel-union"})])


def export_surfaces_and_water(
    osm_path: Path,
    boundary: BaseGeometry,
    surfaces_output: Path,
    water_output: Path,
    core_surfaces_path: Path,
    core_water_path: Path,
) -> None:
    osm = read_json(osm_path)
    to_utm = Transformer.from_crs(WGS84, UTM18N, always_xy=True)
    to_wgs84 = Transformer.from_crs(UTM18N, WGS84, always_xy=True)
    clip = boundary.buffer(0.00002)
    hard: list[BaseGeometry] = []
    grass: list[BaseGeometry] = []
    water: list[BaseGeometry] = []
    core_hard: list[BaseGeometry] = []
    core_grass: list[BaseGeometry] = []
    core_water: list[BaseGeometry] = []

    for element in osm.get("elements", []):
        if element.get("type") not in {"way", "relation"}:
            continue
        tags = element.get("tags", {}) or {}
        geometry = osm_geometry(element)
        if geometry is None or geometry.is_empty:
            continue
        geometry = clean(geometry.intersection(clip))
        if geometry.is_empty:
            continue

        highway = tags.get("highway")
        leisure = tags.get("leisure")
        amenity = tags.get("amenity")
        natural = tags.get("natural")
        landuse = tags.get("landuse")
        sport = tags.get("sport", "")
        surface = tags.get("surface", "")

        if highway:
            if highway in {"footway", "path", "steps", "pedestrian", "cycleway", "bridleway"}:
                hard.append(metre_buffer(geometry, 2.0, to_utm, to_wgs84))
            elif highway in {"service", "track", "driveway"}:
                hard.append(metre_buffer(geometry, 4.0, to_utm, to_wgs84))
            else:
                hard.append(metre_buffer(geometry, 6.0, to_utm, to_wgs84))
            continue
        if amenity == "parking" or tags.get("parking"):
            hard.append(metre_buffer(geometry, 5.0, to_utm, to_wgs84))
            continue
        if natural == "water" or tags.get("water") or tags.get("waterway"):
            water.append(metre_buffer(geometry, 4.0, to_utm, to_wgs84))
            continue
        if leisure == "track":
            hard.append(metre_buffer(geometry, 5.0, to_utm, to_wgs84))
            continue
        if leisure == "pitch":
            if "tennis" in sport or "pickleball" in sport or "basketball" in sport:
                hard.append(geometry)
            else:
                grass.append(geometry)
            continue
        if (
            leisure in {"park", "garden", "sports_centre"}
            or landuse in {"grass", "recreation_ground", "meadow"}
            or surface in {"grass", "turf"}
        ):
            grass.append(geometry)

    for geometry, properties in load_resource_polygons(core_surfaces_path):
        kind = str(properties.get("kind", "")).upper()
        clipped = clean(geometry.intersection(boundary))
        if clipped.is_empty:
            continue
        if kind == "HARD":
            core_hard.append(clipped)
        elif kind == "GRASS":
            core_grass.append(clipped)

    for geometry, _properties in load_resource_polygons(core_water_path):
        clipped = clean(geometry.intersection(boundary))
        if not clipped.is_empty:
            core_water.append(clipped)

    hard.extend(core_hard)
    water.extend(core_water)
    grass.extend(core_grass)

    hard_union = clean(unary_union(hard)) if hard else Polygon()
    water_union = clean(unary_union(water)) if water else Polygon()
    grass_union = clean(unary_union(grass)) if grass else Polygon()
    if not hard_union.is_empty:
        hard_union = clean(hard_union.intersection(boundary))
    if not water_union.is_empty:
        water_union = clean(water_union.intersection(boundary))
    if not grass_union.is_empty:
        grass_union = clean(grass_union.intersection(boundary))
        if not hard_union.is_empty:
            grass_union = clean(grass_union.difference(hard_union))
        if not water_union.is_empty:
            grass_union = clean(grass_union.difference(water_union))

    surface_features: list[dict[str, Any]] = []
    for part in polygonal_parts(hard_union):
        surface_features.append(feature(part, {"kind": "HARD", "source": "osm"}))
    for part in polygonal_parts(grass_union):
        surface_features.append(feature(part, {"kind": "GRASS", "source": "osm"}))
    water_features = [feature(part, {"source": "osm"}) for part in polygonal_parts(water_union)]

    if not surface_features:
        raise RuntimeError(f"No surface polygons generated from {osm_path}")
    if not water_features:
        raise RuntimeError(f"No water polygons generated from {osm_path}")
    write_geojson(surfaces_output, surface_features)
    write_geojson(water_output, water_features)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gis-dir", type=Path, default=Path("runtime/campus-data/gis"))
    parser.add_argument(
        "--resources-dir",
        type=Path,
        default=Path("runtime/campus-reconstruction/voxelearth-campus-palette-chapel-20260831/src/minecraft-plugin/src/main/resources"),
    )
    parser.add_argument("--scope", choices=["full"], default="full")
    args = parser.parse_args()

    parcels_path = args.gis_dir / "montco-hill-parcels-full.geojson"
    buildings_path = args.gis_dir / "montco-hill-buildings-full.geojson"
    osm_path = args.gis_dir / "osm--75.63850-40.24338--75.61808-40.26086.json"
    boundary = load_boundary(parcels_path)
    export_boundary(boundary, args.resources_dir / "hill-campus-boundary.geojson")
    copy_buildings(buildings_path, args.resources_dir / "hill-campus-buildings.geojson")
    export_surfaces_and_water(
        osm_path,
        boundary,
        args.resources_dir / "hill-campus-surfaces.geojson",
        args.resources_dir / "hill-campus-water.geojson",
        args.resources_dir / "hill-campus-surfaces-core-15acre.geojson",
        args.resources_dir / "hill-campus-water-core-15acre.geojson",
    )
    print(f"wrote full resources to {args.resources_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
