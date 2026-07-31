from __future__ import annotations

import csv
import json
import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h3

from .contracts import (
    AnalysisContract,
    AnalysisDomainContract,
    AnalysisDomainRollupContract,
    LayerContract,
)
from .paths import resolve_source_path


@dataclass(frozen=True)
class LayerAssets:
    geojson_path: Path
    distance_path: Path
    manifest_status: str
    declared_geometry_family: str
    feature_count: int


def _resolve_domain_level_cell_ids(
    level: AnalysisDomainContract | AnalysisDomainRollupContract,
) -> tuple[str, ...]:
    path = resolve_source_path(level.provider, level.path)
    if not path.is_file():
        raise FileNotFoundError(f"Analysis-domain source is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"Analysis-domain source must be a FeatureCollection: {path}")

    cell_ids: list[str] = []
    for index, feature in enumerate(payload.get("features") or []):
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(
                f"Analysis-domain feature {index} has no properties: {path}"
            )
        cell_id = str(properties.get(level.id_field) or "").strip()
        if not cell_id:
            raise ValueError(
                f"Analysis-domain feature {index} has no {level.id_field}: {path}"
            )
        try:
            resolution = int(h3.get_resolution(cell_id))
        except Exception as exc:
            raise ValueError(
                f"Analysis-domain feature {index} has invalid H3 id: {cell_id}"
            ) from exc
        if resolution != level.resolution:
            raise ValueError(
                f"Analysis-domain cell {cell_id} is R{resolution}; "
                f"expected R{level.resolution}"
            )
        cell_ids.append(cell_id)

    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError(f"Analysis-domain source contains duplicate cell ids: {path}")
    if len(cell_ids) != level.expected_cell_count:
        raise ValueError(
            f"Analysis-domain source has {len(cell_ids)} cells; "
            f"expected {level.expected_cell_count}"
        )
    return tuple(cell_ids)


def resolve_analysis_domain_cell_ids(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> tuple[str, ...]:
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis-domain contract"
        )
    if domain.cell_kind != "h3":
        raise ValueError(
            f"Unsupported analysis-domain cell kind: {domain.cell_kind}"
        )
    if domain.resolution < 0 or domain.resolution > 15:
        raise ValueError(
            f"Invalid H3 analysis-domain resolution: {domain.resolution}"
        )
    if domain.expected_cell_count <= 0:
        raise ValueError("Analysis domain expected cell count must be positive")

    if resolution is None:
        requested_resolution = domain.resolution
    else:
        if isinstance(resolution, bool):
            raise TypeError("resolution must be an integer")
        try:
            requested_resolution = int(operator.index(resolution))
        except TypeError as exc:
            raise TypeError("resolution must be an integer") from exc
    if requested_resolution == domain.resolution:
        return _resolve_domain_level_cell_ids(domain)

    rollup = domain.rollups.get(requested_resolution)
    if rollup is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no R{requested_resolution} "
            "analysis-domain rollup"
        )
    target_ids = _resolve_domain_level_cell_ids(rollup)
    source_ids = _resolve_domain_level_cell_ids(domain)
    expected_parent_ids = {
        str(h3.cell_to_parent(cell_id, requested_resolution))
        for cell_id in source_ids
    }
    target_set = set(target_ids)
    if target_set != expected_parent_ids:
        raise ValueError(
            f"Analysis-domain R{requested_resolution} rollup does not match "
            f"the R{domain.resolution} parent domain: "
            f"missing={len(expected_parent_ids - target_set)}, "
            f"unexpected={len(target_set - expected_parent_ids)}"
        )
    return target_ids


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
