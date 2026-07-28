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
    operation: str
    threshold_m: float
    cell_count: int
    blocked_cell_count: int
    source_feature_count: int


@dataclass(frozen=True)
class AnalysisResult:
    region_id: str
    analysis_id: str
    scenario_id: str | None
    layers: tuple[LayerResult, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _distance_exclusion(layer: ValidatedLayer, parameters: dict[str, Any]) -> LayerResult:
    parameter = layer.contract.parameters["buffer_m"]
    threshold = parameter.validate_value(parameters.get("buffer_m", parameter.default))
    cell_count = 0
    blocked_count = 0
    with layer.assets.distance_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"hex_id", "distance_m", "intersects"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{layer.assets.distance_path} must contain {sorted(required)}")
        for row in reader:
            cell_count += 1
            intersects = str(row.get("intersects") or "").strip().lower() in {"1", "true", "yes"}
            raw_distance = str(row.get("distance_m") or "").strip()
            distance = float(raw_distance) if raw_distance else float("inf")
            if intersects or distance < threshold:
                blocked_count += 1
    return LayerResult(
        layer_id=layer.contract.id,
        geometry_family=layer.geometry_family,
        processing_adapter=layer.processing_adapter,
        operation=layer.contract.operation,
        threshold_m=threshold,
        cell_count=cell_count,
        blocked_cell_count=blocked_count,
        source_feature_count=layer.assets.feature_count,
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
    for layer_id in requested:
        validated = validate_layer(contract.layers[layer_id])
        if validated.contract.operation == "distance_exclusion":
            results.append(_distance_exclusion(validated, (parameters or {}).get(layer_id, {})))
            continue
        raise ValueError(f"No executor for operation: {validated.contract.operation}")

    return AnalysisResult(
        region_id=region,
        analysis_id=analysis,
        scenario_id=scenario,
        layers=tuple(results),
    )
