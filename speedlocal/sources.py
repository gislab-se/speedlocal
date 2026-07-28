from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import LayerContract
from .paths import resolve_source_path


@dataclass(frozen=True)
class LayerAssets:
    geojson_path: Path
    distance_path: Path
    manifest_status: str
    declared_geometry_family: str
    feature_count: int


def _clean_relative(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == "NA":
        raise FileNotFoundError(f"Layer asset has no {field}")
    return text


def resolve_layer_assets(layer: LayerContract) -> LayerAssets:
    source = layer.source
    manifest_path = resolve_source_path(source.provider, source.asset_manifest)
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next((item for item in rows if item.get("layer_id") == source.layer_id), None)
    if row is None:
        raise KeyError(f"{source.layer_id} is missing from {manifest_path}")
    return LayerAssets(
        geojson_path=resolve_source_path(source.provider, _clean_relative(row.get("geojson_path"), "geojson_path")),
        distance_path=resolve_source_path(source.provider, _clean_relative(row.get("distance_path"), "distance_path")),
        manifest_status=str(row.get("status") or ""),
        declared_geometry_family=str(row.get("geometry_family") or "unknown").lower(),
        feature_count=int(float(row.get("feature_count") or 0)),
    )


def detect_geojson_geometry_family(path: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    geometry_types: set[str] = set()
    if payload.get("type") == "FeatureCollection":
        for feature in payload.get("features") or []:
            geometry = feature.get("geometry") or {}
            if geometry.get("type"):
                geometry_types.add(str(geometry["type"]).lower())
    elif payload.get("type") == "Feature":
        geometry = payload.get("geometry") or {}
        if geometry.get("type"):
            geometry_types.add(str(geometry["type"]).lower())
    elif payload.get("type"):
        geometry_types.add(str(payload["type"]).lower())

    families = set()
    for geometry_type in geometry_types:
        if "point" in geometry_type:
            families.add("point")
        elif "line" in geometry_type:
            families.add("line")
        elif "polygon" in geometry_type:
            families.add("polygon")
    if len(families) != 1:
        raise ValueError(f"Expected one geometry family in {path}, found: {sorted(families)}")
    return families.pop()
