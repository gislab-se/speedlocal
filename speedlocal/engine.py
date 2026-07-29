from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Any

from .catalogs import load_analysis
from .validation import ValidatedLayer, validate_contract, validate_layer


@dataclass(frozen=True)
class LayerResult:
    layer_id: str
    geometry_family: str
    processing_adapter: str
    geometry_validation: str
    operation: str
    threshold_m: float
    cell_count: int
    blocked_cell_count: int
    source_feature_count: int


@dataclass(frozen=True)
class GroupResult:
    group_id: str
    layer_ids: tuple[str, ...]
    threshold_m: float
    cell_count: int
    blocked_cell_count: int
    mean_acceptance: float


@dataclass(frozen=True)
class AnalysisResult:
    region_id: str
    analysis_id: str
    scenario_id: str | None
    layers: tuple[LayerResult, ...]
    groups: tuple[GroupResult, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _distance_rows(layer: ValidatedLayer) -> dict[str, tuple[float, bool]]:
    rows: dict[str, tuple[float, bool]] = {}
    with layer.assets.distance_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"hex_id", "distance_m", "intersects"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{layer.assets.distance_path} must contain {sorted(required)}")
        for row in reader:
            hex_id = str(row["hex_id"])
            intersects = str(row.get("intersects") or "").strip().lower() in {"1", "true", "yes"}
            raw_distance = str(row.get("distance_m") or "").strip()
            distance = float(raw_distance) if raw_distance else float("inf")
            rows[hex_id] = (distance, intersects)
    return rows


def _distance_exclusion(
    layer: ValidatedLayer,
    parameters: dict[str, Any],
) -> tuple[LayerResult, dict[str, tuple[float, bool]]]:
    parameter = layer.contract.parameters["buffer_m"]
    threshold = parameter.validate_value(parameters.get("buffer_m", parameter.default))
    rows = _distance_rows(layer)
    blocked_count = sum(
        1 for distance, intersects in rows.values() if intersects or distance <= threshold
    )
    return (
        LayerResult(
            layer_id=layer.contract.id,
            geometry_family=layer.geometry_family,
            processing_adapter=layer.processing_adapter,
            geometry_validation=layer.geometry_validation,
            operation=layer.contract.operation,
            threshold_m=threshold,
            cell_count=len(rows),
            blocked_cell_count=blocked_count,
            source_feature_count=layer.assets.feature_count,
        ),
        rows,
    )


def _distance_group_result(
    group_id: str,
    layer_results: list[tuple[LayerResult, dict[str, tuple[float, bool]]]],
) -> GroupResult:
    thresholds = {result.threshold_m for result, _ in layer_results}
    if len(thresholds) != 1:
        raise ValueError(f"Layers in group {group_id} must use one shared threshold")
    threshold = thresholds.pop()
    hex_ids = set().union(*(set(rows) for _, rows in layer_results))
    blocked_count = 0
    acceptance_sum = 0.0
    ramp_end = max(threshold * 2.0, threshold + 1.0)
    for hex_id in hex_ids:
        values = [rows[hex_id] for _, rows in layer_results if hex_id in rows]
        min_distance = min(distance for distance, _ in values)
        intersects = any(intersection for _, intersection in values)
        blocked = intersects or min_distance <= threshold
        blocked_count += int(blocked)
        if intersects:
            acceptance = 0.0
        elif threshold <= 0:
            acceptance = 1.0
        else:
            acceptance = max(0.0, min(1.0, (min_distance - threshold) / (ramp_end - threshold)))
        acceptance_sum += acceptance
    return GroupResult(
        group_id=group_id,
        layer_ids=tuple(result.layer_id for result, _ in layer_results),
        threshold_m=threshold,
        cell_count=len(hex_ids),
        blocked_cell_count=blocked_count,
        mean_acceptance=(acceptance_sum / len(hex_ids)) if hex_ids else 0.0,
    )


def run_analysis(
    region: str,
    analysis: str,
    layers: list[str],
    parameters: dict[str, dict[str, Any]] | None = None,
    scenario: str | None = None,
) -> AnalysisResult:
    contract = load_analysis(region, analysis)
    validate_contract(contract)
    requested = [str(layer_id) for layer_id in layers]
    unknown = set(requested) - set(contract.layers)
    if unknown:
        raise KeyError(f"Layers are not configured for {region}/{analysis}: {sorted(unknown)}")

    results: list[LayerResult] = []
    distance_rows_by_group: dict[
        str,
        list[tuple[LayerResult, dict[str, tuple[float, bool]]]],
    ] = {}
    for layer_id in requested:
        validated = validate_layer(contract.layers[layer_id])
        if validated.contract.operation == "distance_exclusion":
            result, rows = _distance_exclusion(
                validated,
                (parameters or {}).get(layer_id, {}),
            )
            results.append(result)
            distance_rows_by_group.setdefault(validated.contract.group_id, []).append(
                (result, rows)
            )
            continue
        raise ValueError(f"No executor for operation: {validated.contract.operation}")

    return AnalysisResult(
        region_id=region,
        analysis_id=analysis,
        scenario_id=scenario,
        layers=tuple(results),
        groups=tuple(
            _distance_group_result(group_id, group_results)
            for group_id, group_results in distance_rows_by_group.items()
        ),
    )
