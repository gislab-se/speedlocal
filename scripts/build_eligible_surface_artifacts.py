from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import h3
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import mapping, shape


CHUNK_BYTES = 1024 * 1024
DEFAULT_SOURCE_RELATIVE = (
    "docs/geocontext/potential_framework/data/"
    "trondelag_r7_app_bundle/hex.geojson"
)
DEFAULT_MASK_RELATIVE = (
    "data/processed/trondelag/mask/"
    "trondelag_land_region_mask_wgs84.geojson"
)
DEFAULT_OUTPUT_RELATIVE = (
    "data/generated/eligible_surface/trondelag_onshore_land"
)
OUTPUT_RESOLUTIONS = (7, 6, 5)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _output_path(root: Path, resolution: int) -> Path:
    return root / f"{DEFAULT_OUTPUT_RELATIVE}_r{resolution}.geojson"


def _round_coordinates(value: Any) -> Any:
    if isinstance(value, (tuple, list)):
        if value and all(isinstance(item, (int, float)) for item in value):
            return [round(float(item), 8) for item in value]
        return [_round_coordinates(item) for item in value]
    return value


def _geojson_geometry(geometry: Any) -> dict[str, Any]:
    raw = mapping(geometry)
    return {
        "type": str(raw["type"]),
        "coordinates": _round_coordinates(raw["coordinates"]),
    }


def _read_feature_collection(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError(f"{label} must be a GeoJSON FeatureCollection: {path}")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"{label} has no features: {path}")
    return payload


def _source_cells(
    payload: dict[str, Any],
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    cell_ids: list[str] = []
    geometries: list[Any] = []
    for index, feature in enumerate(payload["features"]):
        properties = feature.get("properties")
        cell_id = (
            str(properties.get("hex_id") or "").strip()
            if isinstance(properties, dict)
            else ""
        )
        if not cell_id or not h3.is_valid_cell(cell_id):
            raise ValueError(f"Source feature {index} has an invalid hex_id")
        if h3.get_resolution(cell_id) != 7:
            raise ValueError(f"Source cell {cell_id} is not R7")
        raw_geometry = feature.get("geometry")
        if not isinstance(raw_geometry, dict):
            raise ValueError(f"Source cell {cell_id} has no geometry")
        geometry = shape(raw_geometry)
        if geometry.is_empty or geometry.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError(f"Source cell {cell_id} is not a usable polygon")
        cell_ids.append(cell_id)
        geometries.append(geometry)
    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Source cells contain duplicate hex ids")
    return np.asarray(cell_ids, dtype=str), np.asarray(geometries, dtype=object)


def _mask_geometry(payload: dict[str, Any]) -> Any:
    parts: list[Any] = []
    for index, feature in enumerate(payload["features"]):
        raw_geometry = feature.get("geometry")
        if not isinstance(raw_geometry, dict):
            raise ValueError(f"Mask feature {index} has no geometry")
        geometry = shape(raw_geometry)
        if geometry.is_empty or geometry.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError(f"Mask feature {index} is not a usable polygon")
        parts.append(geometry)
    result = shapely.union_all(np.asarray(parts, dtype=object))
    if result.is_empty:
        raise ValueError("Eligible-surface mask is empty")
    return result


def _rollup(
    cell_ids: np.ndarray[Any, Any],
    geometries: np.ndarray[Any, Any],
    areas_m2: np.ndarray[Any, Any],
    resolution: int,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    grouped: dict[str, list[Any]] = {}
    grouped_areas: dict[str, list[float]] = {}
    for cell_id, geometry, area_m2 in zip(
        cell_ids,
        geometries,
        areas_m2,
        strict=True,
    ):
        parent = str(h3.cell_to_parent(str(cell_id), resolution))
        grouped.setdefault(parent, []).append(geometry)
        grouped_areas.setdefault(parent, []).append(float(area_m2))
    parent_ids = np.asarray(sorted(grouped), dtype=str)
    parent_geometries = np.asarray(
        [
            shapely.union_all(np.asarray(grouped[parent], dtype=object))
            for parent in parent_ids
        ],
        dtype=object,
    )
    parent_areas = np.asarray(
        [math.fsum(grouped_areas[parent]) for parent in parent_ids],
        dtype=float,
    )
    return parent_ids, parent_geometries, parent_areas


def _write_level(
    path: Path,
    cell_ids: np.ndarray[Any, Any],
    native_geometries: np.ndarray[Any, Any],
    declared_areas_m2: np.ndarray[Any, Any],
    resolution: int,
    to_web: Transformer,
    overwrite: bool,
) -> dict[str, Any]:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite eligible surface: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    web_geometries = shapely.transform(
        native_geometries,
        to_web.transform,
        interleaved=False,
    )
    geometry_areas = np.asarray(shapely.area(native_geometries), dtype=float)
    areas = np.asarray(declared_areas_m2, dtype=float)
    if not bool(np.all(np.isfinite(geometry_areas) & (geometry_areas > 0.0))):
        raise ValueError(f"R{resolution} eligible geometries must have positive area")
    if not bool(np.all(np.isfinite(areas) & (areas > 0.0))):
        raise ValueError(f"R{resolution} eligible geometries must have positive area")
    features = []
    for cell_id, geometry, area_m2 in zip(
        cell_ids,
        web_geometries,
        areas,
        strict=True,
    ):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "hex_id": str(cell_id),
                    "eligible_area_m2": round(float(area_m2), 6),
                    "surface_id": "onshore_land",
                    "surface_scope": "onshore_wind_and_large_scale_land_solar",
                    "water_policy": "exclude_sea_retain_inland_water",
                    "source_h3_resolution": 7,
                    "target_h3_resolution": int(resolution),
                    "geometry_status": "eligible_surface_intersection",
                },
                "geometry": _geojson_geometry(geometry),
            }
        )
    payload = {
        "type": "FeatureCollection",
        "name": f"trondelag_onshore_land_r{resolution}",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {
        "resolution": int(resolution),
        "path": path.as_posix(),
        "cell_count": int(len(features)),
        "eligible_area_km2": math.fsum(float(value) for value in areas) / 1_000_000.0,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic manifest-ready H3 eligible-surface artifacts "
            "without modifying the reviewed source archive."
        )
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--native-crs", default="EPSG:25832")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        output_root.relative_to(repository_root)
    except ValueError:
        pass
    else:
        raise ValueError("Eligible-surface runtime artifacts must stay outside Git")
    source_path = source_root / DEFAULT_SOURCE_RELATIVE
    mask_path = source_root / DEFAULT_MASK_RELATIVE
    source_payload = _read_feature_collection(source_path, "Analysis domain")
    mask_payload = _read_feature_collection(mask_path, "Eligible-surface mask")
    source_ids, source_web = _source_cells(source_payload)
    mask_web = _mask_geometry(mask_payload)

    to_native = Transformer.from_crs("EPSG:4326", args.native_crs, always_xy=True)
    to_web = Transformer.from_crs(args.native_crs, "EPSG:4326", always_xy=True)
    source_native = shapely.transform(
        source_web,
        to_native.transform,
        interleaved=False,
    )
    mask_native = shapely.transform(
        mask_web,
        to_native.transform,
        interleaved=False,
    )
    clipped = np.asarray(
        shapely.intersection(source_native, mask_native),
        dtype=object,
    )
    empty = np.asarray(shapely.is_empty(clipped), dtype=bool)
    if bool(empty.any()):
        raise ValueError(
            "Eligible-surface clipping removed declared analysis cells: "
            + ", ".join(source_ids[empty][:5])
        )
    if not bool(np.all(shapely.is_valid(clipped))):
        clipped = np.asarray(shapely.make_valid(clipped), dtype=object)
    if not bool(np.all(np.isin(shapely.get_type_id(clipped), (3, 6)))):
        raise ValueError("Eligible-surface clipping produced non-polygon geometry")

    source_areas = np.asarray(shapely.area(clipped), dtype=float)
    levels: dict[
        int,
        tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]],
    ] = {
        7: (source_ids, clipped, source_areas)
    }
    for resolution in (6, 5):
        levels[resolution] = _rollup(
            source_ids,
            clipped,
            source_areas,
            resolution,
        )

    summaries = []
    for resolution in OUTPUT_RESOLUTIONS:
        cell_ids, geometries, areas_m2 = levels[resolution]
        output_path = _output_path(output_root, resolution)
        summary = _write_level(
            output_path,
            cell_ids,
            geometries,
            areas_m2,
            resolution,
            to_web,
            args.overwrite,
        )
        summary["path"] = output_path.relative_to(output_root).as_posix()
        summaries.append(summary)

    metadata_path = output_root / (
        DEFAULT_OUTPUT_RELATIVE + "_metadata.json"
    )
    if metadata_path.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite metadata: {metadata_path}")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": "1.0",
        "surface_id": "onshore_land",
        "surface_scope": "onshore_wind_and_large_scale_land_solar",
        "geometry_operation": "intersection",
        "water_policy": "exclude_sea_retain_inland_water",
        "outside_region_policy": "exclude",
        "native_crs": args.native_crs,
        "source": {
            "provider": "v2_archive",
            "path": DEFAULT_SOURCE_RELATIVE,
            "bytes": source_path.stat().st_size,
            "sha256": _sha256(source_path),
        },
        "mask": {
            "provider": "v2_archive",
            "path": DEFAULT_MASK_RELATIVE,
            "bytes": mask_path.stat().st_size,
            "sha256": _sha256(mask_path),
        },
        "levels": summaries,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata["metadata"] = {
        "path": metadata_path.relative_to(output_root).as_posix(),
        "bytes": metadata_path.stat().st_size,
        "sha256": _sha256(metadata_path),
    }
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
