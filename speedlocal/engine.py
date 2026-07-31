from __future__ import annotations

import csv
import hashlib
import math
import operator
from dataclasses import dataclass, field
from typing import Any, Iterable

import h3

from .catalogs import load_analysis
from .sources import resolve_analysis_domain_cell_ids
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
class GroupCellResult:
    cell_id: str
    min_distance_m: float | None
    any_intersection: bool
    blocked: bool
    acceptance: float
    coverage_missing: bool = False

    @property
    def intersects(self) -> bool:
        """Compatibility alias for consumers that use the source-column name."""
        return self.any_intersection


@dataclass(frozen=True)
class GroupResult:
    group_id: str
    layer_ids: tuple[str, ...]
    threshold_m: float
    cell_count: int
    blocked_cell_count: int
    mean_acceptance: float
    cells: tuple[GroupCellResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AnalysisResult:
    region_id: str
    analysis_id: str
    scenario_id: str | None
    layers: tuple[LayerResult, ...]
    groups: tuple[GroupResult, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


DistanceObservation = tuple[float | None, bool]


def _id_set_sha256(values: Iterable[str]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(values))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _distance_rows(layer: ValidatedLayer) -> dict[str, DistanceObservation]:
    rows: dict[str, tuple[float, bool]] = {}
    declared_resolution = getattr(
        getattr(getattr(layer, "contract", None), "source", None),
        "distance_h3_resolution",
        None,
    )
    with layer.assets.distance_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"hex_id", "distance_m", "intersects"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{layer.assets.distance_path} must contain {sorted(required)}")
        for line_number, row in enumerate(reader, start=2):
            hex_id = str(row["hex_id"] or "").strip()
            if not hex_id:
                raise ValueError(
                    f"{layer.assets.distance_path}:{line_number} has a blank hex_id"
                )
            if hex_id in rows:
                raise ValueError(
                    f"{layer.assets.distance_path}:{line_number} duplicates "
                    f"hex_id {hex_id}"
                )
            if declared_resolution is not None:
                try:
                    actual_resolution = int(h3.get_resolution(hex_id))
                except Exception as exc:
                    raise ValueError(
                        f"{layer.assets.distance_path}:{line_number} has an "
                        f"invalid H3 hex_id {hex_id!r}"
                    ) from exc
                if actual_resolution != declared_resolution:
                    raise ValueError(
                        f"{layer.assets.distance_path}:{line_number} contains "
                        f"an R{actual_resolution} cell; expected declared "
                        f"R{declared_resolution}"
                    )
            raw_intersects = str(row.get("intersects") or "").strip().lower()
            if raw_intersects in {"1", "true", "yes"}:
                intersects = True
            elif raw_intersects in {"0", "false", "no"}:
                intersects = False
            else:
                raise ValueError(
                    f"{layer.assets.distance_path}:{line_number} has invalid "
                    f"intersects value {raw_intersects!r}"
                )
            raw_distance = str(row.get("distance_m") or "").strip()
            if not raw_distance:
                raise ValueError(
                    f"{layer.assets.distance_path}:{line_number} has a blank distance_m"
                )
            try:
                distance = float(raw_distance)
            except ValueError as exc:
                raise ValueError(
                    f"{layer.assets.distance_path}:{line_number} has invalid "
                    f"distance_m {raw_distance!r}"
                ) from exc
            if not math.isfinite(distance) or distance < 0:
                raise ValueError(
                    f"{layer.assets.distance_path}:{line_number} must have a "
                    "finite, non-negative distance_m"
                )
            rows[hex_id] = (distance, intersects)
    if not rows:
        raise ValueError(f"{layer.assets.distance_path} has no distance rows")
    coverage = getattr(
        getattr(getattr(layer, "contract", None), "source", None),
        "distance_coverage",
        None,
    )
    if coverage is not None:
        expected_count = coverage.expected_source_row_count
        if expected_count is not None and len(rows) != expected_count:
            raise ValueError(
                f"{layer.assets.distance_path} has {len(rows)} distance rows; "
                f"expected {expected_count}"
            )
        expected_digest = coverage.source_ids_sha256
        if expected_digest is not None:
            actual_digest = _id_set_sha256(rows)
            if actual_digest != expected_digest:
                raise ValueError(
                    f"{layer.assets.distance_path} source-id coverage digest "
                    "does not match its manifest contract"
                )
    return rows


def _distance_exclusion(
    layer: ValidatedLayer,
    parameters: dict[str, Any],
    analysis_cell_ids: frozenset[str] | None,
    source_resolution: int | None = None,
    target_resolution: int | None = None,
    distance_coverage: Any = None,
) -> tuple[LayerResult, dict[str, DistanceObservation]]:
    parameter = layer.contract.parameters["buffer_m"]
    threshold = parameter.validate_value(parameters.get("buffer_m", parameter.default))
    rows = _distance_rows(layer)
    if target_resolution is not None:
        if source_resolution is None or analysis_cell_ids is None:
            raise ValueError(
                "Distance rollup requires source resolution and target cell domain"
            )
        rows = _rollup_distance_rows(
            rows,
            source_resolution,
            target_resolution,
            analysis_cell_ids,
            distance_coverage,
        )
    elif analysis_cell_ids is not None:
        if (
            distance_coverage is not None
            and distance_coverage.mode == "declared_sparse"
        ):
            raise ValueError(
                "Declared sparse distance coverage requires an exact "
                "target_resolution and signed analysis domain"
            )
        missing = analysis_cell_ids - rows.keys()
        if missing:
            raise ValueError(
                f"Layer {layer.contract.id} is missing requested analysis cells: "
                f"{sorted(missing)}"
            )
        rows = {cell_id: rows[cell_id] for cell_id in sorted(analysis_cell_ids)}
    blocked_count = sum(
        1
        for distance, intersects in rows.values()
        if intersects or (distance is not None and distance <= threshold)
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


def _rollup_distance_rows(
    rows: dict[str, DistanceObservation],
    source_resolution: int,
    target_resolution: int,
    target_cell_ids: frozenset[str],
    distance_coverage: Any = None,
) -> dict[str, DistanceObservation]:
    if target_resolution > source_resolution:
        raise ValueError(
            f"Distance rows cannot roll up from R{source_resolution} "
            f"to finer R{target_resolution}"
        )

    rolled: dict[str, DistanceObservation] = {}
    for cell_id, (distance, intersects) in rows.items():
        if distance is None:
            raise ValueError("Raw distance rows must contain numeric distances")
        try:
            cell_resolution = int(h3.get_resolution(cell_id))
        except Exception as exc:
            raise ValueError(f"Distance rows contain invalid H3 id: {cell_id}") from exc
        if cell_resolution != source_resolution:
            raise ValueError(
                f"Distance row {cell_id} is R{cell_resolution}; "
                f"expected R{source_resolution}"
            )
        target_id = (
            cell_id
            if target_resolution == source_resolution
            else str(h3.cell_to_parent(cell_id, target_resolution))
        )
        previous = rolled.get(target_id)
        if previous is None:
            rolled[target_id] = (distance, intersects)
        else:
            rolled[target_id] = (
                min(previous[0], distance),
                previous[1] or intersects,
            )

    missing = target_cell_ids - rolled.keys()
    outside = rolled.keys() - target_cell_ids
    coverage_mode = (
        str(distance_coverage.mode)
        if distance_coverage is not None
        else "complete"
    )
    if coverage_mode == "declared_sparse":
        target_contract = distance_coverage.targets.get(target_resolution)
        if target_contract is None:
            raise ValueError(
                f"Sparse distance coverage has no R{target_resolution} signature"
            )
        actual_signature = (
            len(target_cell_ids),
            len(target_cell_ids & rolled.keys()),
            len(missing),
            len(outside),
            _id_set_sha256(missing),
            _id_set_sha256(outside),
        )
        expected_signature = (
            target_contract.target_cell_count,
            target_contract.covered_cell_count,
            target_contract.missing_cell_count,
            target_contract.outside_cell_count,
            target_contract.missing_ids_sha256,
            target_contract.outside_ids_sha256,
        )
        if actual_signature != expected_signature:
            raise ValueError(
                f"Sparse distance coverage for R{target_resolution} does not "
                "match its manifest signature"
            )
        if distance_coverage.missing_policy != "zero_acceptance":
            raise ValueError("Unsupported sparse distance missing policy")
        rolled.update({cell_id: (None, False) for cell_id in missing})
    elif missing:
        if coverage_mode == "complete":
            raise ValueError(
                f"Distance rollup is missing R{target_resolution} analysis cells: "
                f"{sorted(missing)}"
            )
        raise ValueError(f"Unsupported distance coverage mode: {coverage_mode}")
    return {
        cell_id: rolled[cell_id]
        for cell_id in sorted(target_cell_ids)
    }


def _distance_group_result(
    group_id: str,
    layer_results: list[tuple[LayerResult, dict[str, DistanceObservation]]],
) -> GroupResult:
    thresholds = {result.threshold_m for result, _ in layer_results}
    if len(thresholds) != 1:
        raise ValueError(f"Layers in group {group_id} must use one shared threshold")
    threshold = thresholds.pop()
    hex_ids = set().union(*(set(rows) for _, rows in layer_results))
    blocked_count = 0
    acceptance_sum = 0.0
    cells: list[GroupCellResult] = []
    ramp_end = max(threshold * 2.0, threshold + 1.0)
    for hex_id in sorted(hex_ids):
        values = [rows[hex_id] for _, rows in layer_results if hex_id in rows]
        observed_distances = [
            distance for distance, _ in values if distance is not None
        ]
        min_distance = min(observed_distances) if observed_distances else None
        intersects = any(intersection for _, intersection in values)
        coverage_missing = not observed_distances
        blocked = intersects or (
            min_distance is not None and min_distance <= threshold
        )
        blocked_count += int(blocked)
        if intersects:
            acceptance = 0.0
        elif coverage_missing:
            acceptance = 0.0
        elif threshold <= 0:
            acceptance = 1.0
        else:
            acceptance = max(0.0, min(1.0, (min_distance - threshold) / (ramp_end - threshold)))
        acceptance_sum += acceptance
        cells.append(
            GroupCellResult(
                cell_id=hex_id,
                min_distance_m=min_distance,
                any_intersection=intersects,
                blocked=blocked,
                acceptance=acceptance,
                coverage_missing=coverage_missing,
            )
        )
    return GroupResult(
        group_id=group_id,
        layer_ids=tuple(result.layer_id for result, _ in layer_results),
        threshold_m=threshold,
        cell_count=len(hex_ids),
        blocked_cell_count=blocked_count,
        mean_acceptance=(acceptance_sum / len(hex_ids)) if hex_ids else 0.0,
        cells=tuple(cells),
    )


def _analysis_cell_domain(
    analysis_cell_ids: Iterable[str] | None,
) -> frozenset[str] | None:
    if analysis_cell_ids is None:
        return None
    if isinstance(analysis_cell_ids, (str, bytes)):
        raise TypeError("analysis_cell_ids must be an iterable of cell ids, not a string")
    normalized = tuple(str(cell_id).strip() for cell_id in analysis_cell_ids)
    if not normalized:
        raise ValueError("analysis_cell_ids must not be empty")
    if any(not cell_id for cell_id in normalized):
        raise ValueError("analysis_cell_ids must not contain blank cell ids")
    if len(normalized) != len(set(normalized)):
        raise ValueError("analysis_cell_ids must not contain duplicate cell ids")
    return frozenset(normalized)


def run_analysis(
    region: str,
    analysis: str,
    layers: list[str],
    parameters: dict[str, dict[str, Any]] | None = None,
    scenario: str | None = None,
    analysis_cell_ids: Iterable[str] | None = None,
    target_resolution: int | None = None,
) -> AnalysisResult:
    contract = load_analysis(region, analysis)
    validate_contract(contract)
    requested = [str(layer_id) for layer_id in layers]
    unknown = set(requested) - set(contract.layers)
    if unknown:
        raise KeyError(f"Layers are not configured for {region}/{analysis}: {sorted(unknown)}")
    cell_domain = _analysis_cell_domain(analysis_cell_ids)
    domain_resolution: int | None = None
    normalized_target_resolution: int | None = None
    if target_resolution is not None:
        if isinstance(target_resolution, bool):
            raise TypeError("target_resolution must be an integer")
        try:
            normalized_target_resolution = int(operator.index(target_resolution))
        except TypeError as exc:
            raise TypeError("target_resolution must be an integer") from exc
        domain = contract.analysis_domain
        if domain is None:
            raise ValueError(
                f"{region}/{analysis} has no analysis-domain contract"
            )
        canonical_target_ids = frozenset(
            resolve_analysis_domain_cell_ids(
                contract,
                normalized_target_resolution,
            )
        )
        if cell_domain is not None and cell_domain != canonical_target_ids:
            raise ValueError(
                f"Requested R{normalized_target_resolution} cells do not match "
                "the canonical analysis domain: "
                f"missing={len(canonical_target_ids - cell_domain)}, "
                f"unexpected={len(cell_domain - canonical_target_ids)}"
            )
        cell_domain = canonical_target_ids
        domain_resolution = domain.resolution

    results: list[LayerResult] = []
    distance_rows_by_group: dict[
        str,
        list[tuple[LayerResult, dict[str, DistanceObservation]]],
    ] = {}
    for layer_id in requested:
        validated = validate_layer(contract.layers[layer_id])
        if validated.contract.operation == "distance_exclusion":
            distance_resolution = (
                validated.contract.source.distance_h3_resolution
                if validated.contract.source.distance_h3_resolution is not None
                else domain_resolution
            )
            result, rows = _distance_exclusion(
                validated,
                (parameters or {}).get(layer_id, {}),
                cell_domain,
                distance_resolution,
                normalized_target_resolution,
                validated.contract.source.distance_coverage,
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
