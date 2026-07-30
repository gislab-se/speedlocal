from __future__ import annotations

import os
import sys
import csv
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal import run_analysis
from speedlocal.catalogs import load_analysis
from speedlocal.engine import _distance_rows
from speedlocal.validation import select_processing_adapter, validate_contract, validate_layer
from speedlocal.sources import resolve_analysis_domain_cell_ids, resolve_layer_assets


DEFAULT_V2_ROOT = Path(r"C:\gislab\data\landskapsanalys-v2-multiregion")
TRONDELAG_R7_DISPLAY_PATH = Path(
    "docs/geocontext/potential_framework/data/"
    "trondelag_r7_app_bundle/hex.geojson"
)
ROAD_LARGE_EXPECTATIONS = {
    300.0: {
        "raw_mean": 0.9690997039924916,
        "display_mean": 0.968838733163451,
        "display_blocked": 428,
    },
    1000.0: {
        "raw_mean": 0.9558480037542414,
        "display_mean": 0.9554751146705496,
        "display_blocked": 434,
    },
}


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


def _trondelag_r7_display_cell_ids(source_root: Path) -> tuple[str, ...]:
    path = source_root / TRONDELAG_R7_DISPLAY_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    cell_ids = tuple(
        str(feature["properties"]["hex_id"])
        for feature in raw.get("features") or []
    )
    if len(cell_ids) != 13_735 or len(set(cell_ids)) != 13_735:
        raise ValueError(
            f"{path} must contain exactly 13,735 unique Trøndelag R7 display cells"
        )
    return cell_ids


def _v2_layer_cell_oracle(
    contract,
    layer_id: str,
    threshold: float,
    analysis_cell_ids: tuple[str, ...],
) -> dict[str, float]:
    """Independent cellwise implementation of frozen V2 soft-distance semantics."""
    path = resolve_layer_assets(contract.layers[layer_id]).distance_path
    rows: dict[str, tuple[float, bool]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            cell_id = str(row["hex_id"])
            if cell_id in rows:
                raise ValueError(f"Duplicate oracle cell id: {cell_id}")
            rows[cell_id] = (
                float(row["distance_m"]),
                str(row["intersects"]).strip().lower() in {"1", "true", "yes"},
            )

    acceptance: dict[str, float] = {}
    ramp_end = max(threshold * 2.0, threshold + 1.0)
    for cell_id in analysis_cell_ids:
        if cell_id not in rows:
            raise ValueError(f"Oracle is missing analysis cell: {cell_id}")
        distance, intersects = rows[cell_id]
        if intersects:
            value = 0.0
        elif threshold <= 0:
            value = 1.0
        else:
            value = max(
                0.0,
                min(1.0, (distance - threshold) / (ramp_end - threshold)),
            )
        acceptance[cell_id] = value
    return acceptance


def _assert_invalid_distance_rows_fail_closed() -> int:
    fixtures = {
        "duplicate": (
            "hex_id,distance_m,intersects\n"
            "a,10,FALSE\n"
            "a,20,FALSE\n",
            "duplicates hex_id",
        ),
        "invalid_boolean": (
            "hex_id,distance_m,intersects\n"
            "a,10,MAYBE\n",
            "invalid intersects",
        ),
        "blank_distance": (
            "hex_id,distance_m,intersects\n"
            "a,,FALSE\n",
            "blank distance_m",
        ),
    }
    checks = 0
    with tempfile.TemporaryDirectory(prefix="speedlocal-distance-fixtures-") as temp:
        root = Path(temp)
        for name, (content, expected_message) in fixtures.items():
            path = root / f"{name}.csv"
            path.write_text(content, encoding="utf-8")
            layer = SimpleNamespace(
                assets=SimpleNamespace(distance_path=path),
            )
            try:
                _distance_rows(layer)
            except ValueError as exc:
                assert expected_message in str(exc)
            else:
                raise AssertionError(
                    f"Malformed distance fixture did not fail closed: {name}"
                )
            checks += 1
    return checks


def main() -> int:
    os.environ.setdefault("SPEEDLOCAL_V2_SOURCE_ROOT", str(DEFAULT_V2_ROOT))
    source_root = Path(os.environ["SPEEDLOCAL_V2_SOURCE_ROOT"]).resolve()
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
        default_threshold = contract.layers["roads_large"].parameters["buffer_m"].default
        oracle_count, oracle_blocked, oracle_acceptance = _v2_roads_oracle(
            contract,
            default_threshold,
        )
        assert default_group.cell_count == oracle_count
        assert default_group.blocked_cell_count == oracle_blocked
        assert abs(default_group.mean_acceptance - oracle_acceptance) < 1e-12
        assert wider_group.blocked_cell_count >= default_group.blocked_cell_count
        checks += 4
        print(
            f"PASS {region_id}: {sum(item.source_feature_count for item in default_result.layers)} "
            f"road features, {default_group.cell_count} H3 cells, "
            f"{default_group.blocked_cell_count} blocked at {default_group.threshold_m:g} m, "
            f"distance-engine contract behavior validated"
        )

    trondelag = load_analysis("trondelag", "wind")
    for layer_id in ("roads_medium", "roads_large"):
        buffer_contract = trondelag.layers[layer_id].parameters["buffer_m"]
        assert (
            buffer_contract.default,
            buffer_contract.minimum,
            buffer_contract.maximum,
            buffer_contract.step,
        ) == (300.0, 100.0, 2000.0, 25.0)
        assert buffer_contract.validate_value(1000) == 1000.0
        assert buffer_contract.validate_value(312) == 312.0
        checks += 3

    display_cell_ids = _trondelag_r7_display_cell_ids(source_root)
    assert trondelag.analysis_domain is not None
    assert (
        trondelag.analysis_domain.cell_kind,
        trondelag.analysis_domain.resolution,
        trondelag.analysis_domain.expected_cell_count,
    ) == ("h3", 7, 13_735)
    assert resolve_analysis_domain_cell_ids(trondelag) == display_cell_ids
    checks += 2
    for threshold, expected in ROAD_LARGE_EXPECTATIONS.items():
        parameters = {"roads_large": {"buffer_m": threshold}}
        raw_result = run_analysis(
            "trondelag",
            "wind",
            ["roads_large"],
            parameters,
        )
        display_result = run_analysis(
            "trondelag",
            "wind",
            ["roads_large"],
            parameters,
            analysis_cell_ids=display_cell_ids,
        )
        raw_group = raw_result.groups[0]
        display_group = display_result.groups[0]
        assert raw_group.cell_count == 13_851
        assert len(raw_group.cells) == 13_851
        assert abs(raw_group.mean_acceptance - expected["raw_mean"]) < 1e-12
        assert display_group.cell_count == 13_735
        assert len(display_group.cells) == 13_735
        assert display_group.blocked_cell_count == expected["display_blocked"]
        assert abs(display_group.mean_acceptance - expected["display_mean"]) < 1e-12
        assert {cell.cell_id for cell in display_group.cells} == set(display_cell_ids)
        oracle = _v2_layer_cell_oracle(
            trondelag,
            "roads_large",
            threshold,
            display_cell_ids,
        )
        actual = {
            cell.cell_id: cell.acceptance
            for cell in display_group.cells
        }
        assert actual.keys() == oracle.keys()
        assert max(
            abs(actual[cell_id] - oracle[cell_id])
            for cell_id in oracle
        ) < 1e-12
        checks += 9
        print(
            f"PASS trondelag roads_large {threshold:g} m: "
            f"raw universe {raw_group.cell_count} cells at "
            f"{raw_group.mean_acceptance:.15f} mean acceptance; "
            f"R7 display domain {display_group.cell_count} cells at "
            f"{display_group.mean_acceptance:.15f}"
        )

    missing_cell_id = "87fffffffffffff"
    try:
        run_analysis(
            "trondelag",
            "wind",
            ["roads_large"],
            {"roads_large": {"buffer_m": 300}},
            analysis_cell_ids=(*display_cell_ids, missing_cell_id),
        )
    except ValueError as exc:
        assert "missing requested analysis cells" in str(exc)
        assert missing_cell_id in str(exc)
    else:
        raise AssertionError("Missing display-domain cell did not fail closed")
    checks += 2
    checks += _assert_invalid_distance_rows_fail_closed()

    print(f"Generic engine validation passed: {checks}/{checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
