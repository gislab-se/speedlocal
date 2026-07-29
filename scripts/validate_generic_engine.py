from __future__ import annotations

import os
import sys
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal import run_analysis
from speedlocal.catalogs import load_analysis
from speedlocal.validation import select_processing_adapter, validate_contract, validate_layer
from speedlocal.sources import resolve_layer_assets


DEFAULT_V2_ROOT = Path(r"C:\gislab\data\landskapsanalys-v2-multiregion")


def _v2_roads_oracle(contract, threshold: float) -> tuple[int, int, float]:
    """Independent implementation of the characterized V2 road semantics."""
    by_hex: dict[str, list[tuple[float, bool]]] = {}
    for layer_id in ("roads_medium", "roads_large"):
        path = resolve_layer_assets(contract.layers[layer_id]).distance_path
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                raw_distance = str(row.get("distance_m") or "").strip()
                distance = float(raw_distance) if raw_distance else float("inf")
                intersects = str(row.get("intersects") or "").lower() in {"1", "true", "yes"}
                by_hex.setdefault(str(row["hex_id"]), []).append((distance, intersects))
    blocked = 0
    acceptance_sum = 0.0
    ramp_end = max(threshold * 2.0, threshold + 1.0)
    for values in by_hex.values():
        distance = min(value[0] for value in values)
        intersects = any(value[1] for value in values)
        blocked += int(intersects or distance <= threshold)
        if intersects:
            acceptance = 0.0
        elif threshold <= 0:
            acceptance = 1.0
        else:
            acceptance = max(0.0, min(1.0, (distance - threshold) / (ramp_end - threshold)))
        acceptance_sum += acceptance
    return len(by_hex), blocked, acceptance_sum / len(by_hex)


def main() -> int:
    os.environ.setdefault("SPEEDLOCAL_V2_SOURCE_ROOT", str(DEFAULT_V2_ROOT))
    checks = 0
    assert select_processing_adapter("population", "point") == "population_points"
    assert select_processing_adapter("population", "polygon") == "population_polygons"
    assert select_processing_adapter("population", "polygon", "grid") == "population_grid"
    checks += 3
    for region_id in ("bornholm", "trondelag"):
        contract = load_analysis(region_id, "wind")
        validate_contract(contract)
        checks += 1
        for layer_id in ("roads_medium", "roads_large"):
            roads = validate_layer(contract.layers[layer_id])
            assert roads.geometry_family == "line"
            assert roads.processing_adapter == "line_distance"
            assert roads.assets.feature_count > 0
            checks += 3

        road_layers = ["roads_medium", "roads_large"]
        default_result = run_analysis(region_id, "wind", road_layers)
        wider_result = run_analysis(
            region_id,
            "wind",
            road_layers,
            {layer_id: {"buffer_m": 500} for layer_id in road_layers},
        )
        default_group = default_result.groups[0]
        wider_group = wider_result.groups[0]
        oracle_count, oracle_blocked, oracle_acceptance = _v2_roads_oracle(contract, 100.0)
        assert default_group.cell_count == oracle_count
        assert default_group.blocked_cell_count == oracle_blocked
        assert abs(default_group.mean_acceptance - oracle_acceptance) < 1e-12
        assert wider_group.blocked_cell_count >= default_group.blocked_cell_count
        checks += 4
        print(
            f"PASS {region_id}: {sum(item.source_feature_count for item in default_result.layers)} "
            f"road features, {default_group.cell_count} H3 cells, "
            f"{default_group.blocked_cell_count} blocked at {default_group.threshold_m:g} m, "
            f"V2 parity confirmed"
        )

    print(f"Generic engine validation passed: {checks}/25 checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
