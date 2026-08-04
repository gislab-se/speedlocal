from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal import run_analysis
from speedlocal.catalogs import load_analysis
from speedlocal.sources import resolve_analysis_domain_cell_areas_km2


DistanceRow = tuple[float, bool]


def _read_candidate(
    path: Path,
    expected_ids: set[str],
) -> dict[str, DistanceRow]:
    rows: dict[str, DistanceRow] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or []) != {"hex_id", "distance_m", "intersects"}:
            raise ValueError(f"Unexpected candidate columns: {path}")
        for line_number, row in enumerate(reader, start=2):
            cell_id = str(row.get("hex_id") or "").strip()
            if not cell_id or cell_id in rows:
                raise ValueError(f"Invalid or duplicate id at {path}:{line_number}")
            distance = float(str(row.get("distance_m") or ""))
            if not math.isfinite(distance) or distance < 0:
                raise ValueError(f"Invalid distance at {path}:{line_number}")
            intersects_text = str(row.get("intersects") or "").strip().lower()
            if intersects_text not in {"true", "false"}:
                raise ValueError(f"Invalid intersects at {path}:{line_number}")
            rows[cell_id] = (distance, intersects_text == "true")
    if set(rows) != expected_ids:
        raise ValueError(
            f"Candidate {path.name} does not match the R7 domain: "
            f"missing={len(expected_ids - rows.keys())}, "
            f"unexpected={len(rows.keys() - expected_ids)}"
        )
    return rows


def _rollup(
    rows: dict[str, DistanceRow],
    target_ids: set[str],
    target_resolution: int,
) -> dict[str, DistanceRow]:
    import h3

    rolled: dict[str, DistanceRow] = {}
    for cell_id, (distance, intersects) in rows.items():
        target_id = (
            cell_id
            if int(h3.get_resolution(cell_id)) == target_resolution
            else str(h3.cell_to_parent(cell_id, target_resolution))
        )
        previous = rolled.get(target_id)
        rolled[target_id] = (
            distance if previous is None else min(previous[0], distance),
            intersects if previous is None else previous[1] or intersects,
        )
    if set(rolled) != target_ids:
        raise ValueError(
            f"Direct-distance rollup does not match R{target_resolution}: "
            f"missing={len(target_ids - rolled.keys())}, "
            f"unexpected={len(rolled.keys() - target_ids)}"
        )
    return {cell_id: rolled[cell_id] for cell_id in sorted(target_ids)}


def _combine(
    layer_rows: list[dict[str, DistanceRow]],
) -> dict[str, DistanceRow]:
    cell_ids = set(layer_rows[0])
    if any(set(rows) != cell_ids for rows in layer_rows[1:]):
        raise ValueError("Candidate layers do not share one complete domain.")
    return {
        cell_id: (
            min(rows[cell_id][0] for rows in layer_rows),
            any(rows[cell_id][1] for rows in layer_rows),
        )
        for cell_id in sorted(cell_ids)
    }


def _acceptance(distance: float, intersects: bool, threshold: float) -> float:
    if intersects:
        return 0.0
    return max(0.0, min(1.0, (distance - threshold) / threshold))


def _summary(
    old_cells: dict[str, Any],
    new_rows: dict[str, DistanceRow],
    threshold: float,
    areas_km2: dict[str, float],
) -> dict[str, Any]:
    if set(old_cells) != set(new_rows) or set(new_rows) != set(areas_km2):
        raise ValueError("Old result, new candidate, and area domain differ.")
    changed = 0
    max_delta = 0.0
    old_sum = 0.0
    new_sum = 0.0
    old_area = 0.0
    new_area = 0.0
    old_zero = 0
    new_zero = 0
    old_blocked = 0
    new_blocked = 0
    old_missing = 0
    for cell_id in sorted(new_rows):
        old = old_cells[cell_id]
        new_distance, new_intersects = new_rows[cell_id]
        new_acceptance = _acceptance(new_distance, new_intersects, threshold)
        delta = new_acceptance - float(old.acceptance)
        changed += int(not math.isclose(delta, 0.0, rel_tol=0.0, abs_tol=1e-12))
        max_delta = max(max_delta, abs(delta))
        old_sum += float(old.acceptance)
        new_sum += new_acceptance
        old_area += float(old.acceptance) * areas_km2[cell_id]
        new_area += new_acceptance * areas_km2[cell_id]
        old_zero += int(math.isclose(float(old.acceptance), 0.0, abs_tol=1e-12))
        new_zero += int(math.isclose(new_acceptance, 0.0, abs_tol=1e-12))
        old_blocked += int(bool(old.blocked))
        new_blocked += int(new_intersects or new_distance <= threshold)
        old_missing += int(bool(old.coverage_missing))
    count = len(new_rows)
    old_mean = old_sum / count
    new_mean = new_sum / count
    return {
        "cell_count": count,
        "changed_cell_count": changed,
        "max_absolute_acceptance_delta": max_delta,
        "old_mean_acceptance": old_mean,
        "new_mean_acceptance": new_mean,
        "mean_acceptance_delta_percentage_points": (new_mean - old_mean) * 100.0,
        "old_zero_acceptance_cell_count": old_zero,
        "new_zero_acceptance_cell_count": new_zero,
        "old_blocked_cell_count": old_blocked,
        "new_blocked_cell_count": new_blocked,
        "old_coverage_missing_cell_count": old_missing,
        "new_coverage_missing_cell_count": 0,
        "old_model_potential_area_km2": old_area,
        "new_model_potential_area_km2": new_area,
        "model_potential_area_delta_km2": new_area - old_area,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare direct-distance candidates with current canonical results."
    )
    parser.add_argument("--region", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threshold", action="append", type=float)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    candidate_dir = args.candidate_dir.expanduser().resolve()
    output = args.output.expanduser().resolve()
    try:
        output.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Generated drift evidence must stay outside Git.")
    if output.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {output}. Pass --overwrite to replace it."
        )
    output.parent.mkdir(parents=True, exist_ok=True)

    contract = load_analysis(args.region, args.analysis)
    if contract.analysis_domain is None:
        raise ValueError("Analysis has no canonical domain.")
    layer_ids = [
        layer.id
        for layer in contract.layers.values()
        if layer.group_id == args.group
    ]
    if not layer_ids:
        raise KeyError(f"Group {args.group!r} has no layers.")
    source_resolution = contract.analysis_domain.resolution
    domain_areas = {
        resolution: resolve_analysis_domain_cell_areas_km2(contract, resolution)
        for resolution in (
            source_resolution,
            *sorted(contract.analysis_domain.rollups, reverse=True),
        )
    }
    source_ids = set(domain_areas[source_resolution])
    candidates_r7 = {
        layer_id: _read_candidate(candidate_dir / f"{layer_id}.csv", source_ids)
        for layer_id in layer_ids
    }
    candidates = {
        resolution: {
            layer_id: (
                rows
                if resolution == source_resolution
                else _rollup(rows, set(domain_areas[resolution]), resolution)
            )
            for layer_id, rows in candidates_r7.items()
        }
        for resolution in domain_areas
    }
    thresholds = args.threshold or [100.0, 500.0, 1000.0, 3000.0]
    combinations = [
        combination
        for size in range(1, len(layer_ids) + 1)
        for combination in itertools.combinations(layer_ids, size)
    ]
    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "region_id": args.region,
        "analysis_id": args.analysis,
        "group_id": args.group,
        "old_distance_basis": "manifest_declared_current_artifacts",
        "new_distance_basis": (
            "declared_R7_representative_point_to_source_plus_full_cell_intersection"
        ),
        "new_rollup_basis": "minimum_R7_child_distance_and_any_R7_intersection",
        "thresholds_m": thresholds,
        "comparisons": [],
    }
    for resolution in domain_areas:
        target_ids = list(domain_areas[resolution])
        for combination in combinations:
            new_rows = _combine(
                [candidates[resolution][layer_id] for layer_id in combination]
            )
            for threshold in thresholds:
                parameters = {
                    layer_id: {"buffer_m": threshold}
                    for layer_id in combination
                }
                old_result = run_analysis(
                    args.region,
                    args.analysis,
                    list(combination),
                    parameters,
                    analysis_cell_ids=target_ids,
                    target_resolution=resolution,
                )
                old_group = next(
                    group for group in old_result.groups if group.group_id == args.group
                )
                old_cells = {cell.cell_id: cell for cell in old_group.cells}
                evidence["comparisons"].append(
                    {
                        "resolution": resolution,
                        "layer_ids": list(combination),
                        "threshold_m": threshold,
                        **_summary(
                            old_cells,
                            new_rows,
                            threshold,
                            domain_areas[resolution],
                        ),
                    }
                )
                summary = evidence["comparisons"][-1]
                print(
                    f"R{resolution} {'+'.join(combination)} {threshold:g} m: "
                    f"{summary['old_mean_acceptance'] * 100:.6f}% -> "
                    f"{summary['new_mean_acceptance'] * 100:.6f}% "
                    f"({summary['mean_acceptance_delta_percentage_points']:+.6f} pp), "
                    f"changed={summary['changed_cell_count']:,}"
                )
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
