from __future__ import annotations

import csv
import json
import math
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


DECLARED_GEOMETRY_FAMILY_ALIASES = {
    "polygon_proxy_from_250m_centroids": "polygon",
}


def _declared_geometry_family(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    return DECLARED_GEOMETRY_FAMILY_ALIASES.get(normalized, normalized)


def _domain_level_area_to_km2(
    raw_value: Any,
    level: AnalysisDomainContract | AnalysisDomainRollupContract,
    feature_index: int,
    path: Path,
) -> float:
    if not level.area_field.strip():
        raise ValueError("Analysis-domain area field is required")
    if level.area_unit not in {"m2", "km2"}:
        raise ValueError(
            f"Unsupported analysis-domain area unit: {level.area_unit}"
        )
    if isinstance(raw_value, bool):
        raise ValueError(
            f"Analysis-domain feature {feature_index} has invalid "
            f"{level.area_field}: {raw_value!r} ({path})"
        )
    try:
        area = float(raw_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"Analysis-domain feature {feature_index} has invalid "
            f"{level.area_field}: {raw_value!r} ({path})"
        ) from exc
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError(
            f"Analysis-domain feature {feature_index} has non-positive or "
            f"non-finite {level.area_field}: {raw_value!r} ({path})"
        )
    return area / 1_000_000.0 if level.area_unit == "m2" else area


def _resolve_domain_level_cell_areas_km2(
    level: AnalysisDomainContract | AnalysisDomainRollupContract,
) -> dict[str, float]:
    path = resolve_source_path(level.provider, level.path)
    if not path.is_file():
        raise FileNotFoundError(f"Analysis-domain source is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"Analysis-domain source must be a FeatureCollection: {path}")

    cell_areas: dict[str, float] = {}
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
        if cell_id in cell_areas:
            raise ValueError(
                f"Analysis-domain source contains duplicate cell ids: {path}"
            )
        if level.area_field not in properties:
            raise ValueError(
                f"Analysis-domain feature {index} has no {level.area_field}: "
                f"{path}"
            )
        cell_areas[cell_id] = _domain_level_area_to_km2(
            properties[level.area_field],
            level,
            index,
            path,
        )

    if len(cell_areas) != level.expected_cell_count:
        raise ValueError(
            f"Analysis-domain source has {len(cell_areas)} cells; "
            f"expected {level.expected_cell_count}"
        )
    return cell_areas


def resolve_analysis_domain_cell_areas_km2(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> dict[str, float]:
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
    if not domain.area_field.strip():
        raise ValueError("Analysis domain area field is required")
    if domain.area_unit not in {"m2", "km2"}:
        raise ValueError(
            f"Unsupported analysis-domain area unit: {domain.area_unit}"
        )

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
        return _resolve_domain_level_cell_areas_km2(domain)

    rollup = domain.rollups.get(requested_resolution)
    if rollup is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no R{requested_resolution} "
            "analysis-domain rollup"
        )
    target_areas = _resolve_domain_level_cell_areas_km2(rollup)
    source_areas = _resolve_domain_level_cell_areas_km2(domain)
    expected_parent_areas: dict[str, float] = {}
    for cell_id, area_km2 in source_areas.items():
        parent_id = str(h3.cell_to_parent(cell_id, requested_resolution))
        expected_parent_areas[parent_id] = (
            expected_parent_areas.get(parent_id, 0.0) + area_km2
        )
    expected_parent_ids = set(expected_parent_areas)
    target_set = set(target_areas)
    if target_set != expected_parent_ids:
        raise ValueError(
            f"Analysis-domain R{requested_resolution} rollup does not match "
            f"the R{domain.resolution} parent domain: "
            f"missing={len(expected_parent_ids - target_set)}, "
            f"unexpected={len(target_set - expected_parent_ids)}"
        )
    source_total = math.fsum(source_areas.values())
    target_total = math.fsum(target_areas.values())
    if not math.isclose(
        target_total,
        source_total,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"Analysis-domain R{requested_resolution} rollup area total "
            f"{target_total:.12f} km2 does not match R{domain.resolution} "
            f"total {source_total:.12f} km2"
        )
    for parent_id, expected_area in expected_parent_areas.items():
        actual_area = target_areas[parent_id]
        if not math.isclose(
            actual_area,
            expected_area,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Analysis-domain R{requested_resolution} parent "
                f"{parent_id} area {actual_area:.12f} km2 does not match "
                f"its R{domain.resolution} children {expected_area:.12f} km2"
            )
    return target_areas


def resolve_analysis_domain_cell_ids(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> tuple[str, ...]:
    return tuple(
        resolve_analysis_domain_cell_areas_km2(contract, resolution)
    )


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
    distance_path = (
        resolve_source_path(source.distance_provider, source.distance_path)
        if source.distance_provider is not None and source.distance_path is not None
        else resolve_source_path(
            source.provider,
            _clean_relative(row.get("distance_path"), "distance_path"),
        )
    )
    return LayerAssets(
        geojson_path=resolve_source_path(source.provider, _clean_relative(row.get("geojson_path"), "geojson_path")),
        distance_path=distance_path,
        manifest_status=str(row.get("status") or ""),
        declared_geometry_family=_declared_geometry_family(
            row.get("geometry_family")
        ),
        feature_count=int(float(row.get("feature_count") or 0)),
    )


def detect_geojson_geometry_family(
    path: Path,
    geometry_collection_policy: str = "reject_mixed",
) -> str:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    geometry_types: set[str] = set()

    def add_geometry_types(geometry: Any) -> None:
        if not isinstance(geometry, dict):
            return
        geometry_type = str(geometry.get("type") or "").lower()
        if geometry_type == "geometrycollection":
            for child in geometry.get("geometries") or []:
                add_geometry_types(child)
        elif geometry_type:
            geometry_types.add(geometry_type)

    if payload.get("type") == "FeatureCollection":
        for feature in payload.get("features") or []:
            add_geometry_types(feature.get("geometry"))
    elif payload.get("type") == "Feature":
        add_geometry_types(payload.get("geometry"))
    elif payload.get("type"):
        add_geometry_types(payload)

    families = set()
    for geometry_type in geometry_types:
        if "point" in geometry_type:
            families.add("point")
        elif "line" in geometry_type:
            families.add("line")
        elif "polygon" in geometry_type:
            families.add("polygon")
    if len(families) > 1 and geometry_collection_policy == "highest_dimension":
        dimensions = {"point": 0, "line": 1, "polygon": 2}
        return max(families, key=dimensions.__getitem__)
    if len(families) != 1:
        raise ValueError(f"Expected one geometry family in {path}, found: {sorted(families)}")
    return families.pop()
