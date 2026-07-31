from __future__ import annotations

import os
import sys
import csv
import json
import math
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import h3

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal import run_analysis
from speedlocal.catalogs import load_analysis
from speedlocal.contracts import (
    AnalysisDomainContract,
    AnalysisDomainRollupContract,
    DefaultRequestContract,
)
from speedlocal.engine import _distance_rows, _rollup_distance_rows
from speedlocal.validation import select_processing_adapter, validate_contract, validate_layer
from speedlocal.sources import (
    resolve_analysis_domain_cell_areas_km2,
    resolve_analysis_domain_cell_ids,
    resolve_layer_assets,
)


DEFAULT_V2_ROOT = Path(r"C:\gislab\data\landskapsanalys-v2-multiregion")
TRONDELAG_DISPLAY_PATHS = {
    7: Path(
        "docs/geocontext/potential_framework/data/"
        "trondelag_r7_app_bundle/hex.geojson"
    ),
    6: Path(
        "docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/"
        "h3/trondelag_landscape_h3_r6_rollup.geojson"
    ),
    5: Path(
        "docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/"
        "h3/trondelag_landscape_h3_r5_rollup.geojson"
    ),
}
TRONDELAG_DISPLAY_COUNTS = {7: 13_735, 6: 2_163, 5: 365}
TRONDELAG_ANALYSIS_DOMAIN_AREA_KM2 = 45_213.18864360976
ROAD_LARGE_EXPECTATIONS = {
    7: {
        300.0: {
            "display_mean": 0.968838733163451,
            "display_blocked": 428,
        },
        1000.0: {
            "display_mean": 0.9554751146705496,
            "display_blocked": 434,
        },
    },
    6: {
        300.0: {
            "display_mean": 0.9223300970873787,
            "display_blocked": 168,
        },
        1000.0: {
            "display_mean": 0.9101944059177069,
            "display_blocked": 170,
        },
    },
    5: {
        300.0: {
            "display_mean": 0.8191780821917808,
            "display_blocked": 66,
        },
        1000.0: {
            "display_mean": 0.8089936986301369,
            "display_blocked": 66,
        },
    },
}
ROAD_LARGE_RAW_MEANS = {
    300.0: 0.9690997039924916,
    1000.0: 0.9558480037542414,
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


def _trondelag_display_cell_ids(
    source_root: Path,
    resolution: int,
) -> tuple[str, ...]:
    path = source_root / TRONDELAG_DISPLAY_PATHS[resolution]
    raw = json.loads(path.read_text(encoding="utf-8"))
    cell_ids = tuple(
        str(feature["properties"]["hex_id"])
        for feature in raw.get("features") or []
    )
    expected_count = TRONDELAG_DISPLAY_COUNTS[resolution]
    if len(cell_ids) != expected_count or len(set(cell_ids)) != expected_count:
        raise ValueError(
            f"{path} must contain exactly {expected_count:,} unique "
            f"Trondelag R{resolution} display cells"
        )
    return cell_ids


def _v2_layer_rollup_oracle(
    contract,
    layer_id: str,
    threshold: float,
    target_resolution: int,
    target_cell_ids: tuple[str, ...],
) -> dict[str, tuple[float, bool, bool, float]]:
    """Independently reproduce frozen raw-distance rollup and soft acceptance."""
    path = resolve_layer_assets(contract.layers[layer_id]).distance_path
    rolled: dict[str, tuple[float, bool]] = {}
    seen_source_ids: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            cell_id = str(row["hex_id"])
            if cell_id in seen_source_ids:
                raise ValueError(f"Duplicate oracle cell id: {cell_id}")
            seen_source_ids.add(cell_id)
            if int(h3.get_resolution(cell_id)) != 7:
                raise ValueError(f"Oracle source cell is not R7: {cell_id}")
            target_id = (
                cell_id
                if target_resolution == 7
                else str(h3.cell_to_parent(cell_id, target_resolution))
            )
            value = (
                float(row["distance_m"]),
                str(row["intersects"]).strip().lower() in {"1", "true", "yes"},
            )
            previous = rolled.get(target_id)
            if previous is None:
                rolled[target_id] = value
            else:
                rolled[target_id] = (
                    min(previous[0], value[0]),
                    previous[1] or value[1],
                )

    oracle: dict[str, tuple[float, bool, bool, float]] = {}
    ramp_end = max(threshold * 2.0, threshold + 1.0)
    for cell_id in target_cell_ids:
        if cell_id not in rolled:
            raise ValueError(f"Oracle is missing analysis cell: {cell_id}")
        distance, intersects = rolled[cell_id]
        blocked = intersects or distance <= threshold
        if intersects:
            acceptance = 0.0
        elif threshold <= 0:
            acceptance = 1.0
        else:
            acceptance = max(
                0.0,
                min(1.0, (distance - threshold) / (ramp_end - threshold)),
            )
        oracle[cell_id] = (distance, intersects, blocked, acceptance)
    return oracle


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


def _assert_invalid_default_requests_fail_closed(contract) -> int:
    fixtures = (
        (
            replace(contract, default_request=None),
            "default_request is required",
        ),
        (
            replace(
                contract,
                default_request=DefaultRequestContract(
                    selected_layer_ids=("roads_large", "roads_large"),
                ),
            ),
            "must not contain duplicates",
        ),
        (
            replace(
                contract,
                default_request=DefaultRequestContract(
                    selected_layer_ids=("undeclared_layer",),
                ),
            ),
            "selects undeclared layers",
        ),
    )
    for invalid_contract, expected_message in fixtures:
        try:
            validate_contract(invalid_contract)
        except ValueError as exc:
            assert expected_message in str(exc)
        else:
            raise AssertionError(
                "Invalid analysis default_request did not fail closed: "
                f"{expected_message}"
            )
    return len(fixtures)


def _analysis_area_feature_collection(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": row,
                "geometry": None,
            }
            for row in rows
        ],
    }


def _assert_analysis_domain_areas_fail_closed(contract) -> int:
    parent_a = "86083312fffffff"
    parent_b = sorted(h3.grid_ring(parent_a, 1))[0]
    source_ids = [
        *sorted(h3.cell_to_children(parent_a, 7))[:2],
        *sorted(h3.cell_to_children(parent_b, 7))[:2],
    ]
    source_rows = [
        {"hex_id": cell_id, "display_area_m2": float(index)}
        for index, cell_id in enumerate(source_ids, start=1)
    ]
    rollup_rows = [
        {"hex_id": parent_a, "display_area_m2": 3.0},
        {"hex_id": parent_b, "display_area_m2": 7.0},
    ]
    rollup = AnalysisDomainRollupContract(
        provider="v2_archive",
        path="rollup.geojson",
        id_field="hex_id",
        area_field="display_area_m2",
        area_unit="m2",
        resolution=6,
        expected_cell_count=2,
    )
    domain = AnalysisDomainContract(
        provider="v2_archive",
        path="source.geojson",
        id_field="hex_id",
        area_field="display_area_m2",
        area_unit="m2",
        cell_kind="h3",
        resolution=7,
        expected_cell_count=4,
        rollups={6: rollup},
    )
    fixture_contract = replace(contract, analysis_domain=domain)
    checks = 0
    previous_source_root = os.environ.get("SPEEDLOCAL_V2_SOURCE_ROOT")
    try:
        with tempfile.TemporaryDirectory(
            prefix="speedlocal-analysis-area-fixtures-"
        ) as temp:
            root = Path(temp)
            source_path = root / "source.geojson"
            rollup_path = root / "rollup.geojson"
            os.environ["SPEEDLOCAL_V2_SOURCE_ROOT"] = str(root)

            def write_source(rows: list[dict[str, object]]) -> None:
                source_path.write_text(
                    json.dumps(_analysis_area_feature_collection(rows)),
                    encoding="utf-8",
                )

            def write_rollup(rows: list[dict[str, object]]) -> None:
                rollup_path.write_text(
                    json.dumps(_analysis_area_feature_collection(rows)),
                    encoding="utf-8",
                )

            write_source(source_rows)
            write_rollup(rollup_rows)
            source_areas = resolve_analysis_domain_cell_areas_km2(
                fixture_contract
            )
            rollup_areas = resolve_analysis_domain_cell_areas_km2(
                fixture_contract,
                6,
            )
            assert math.isclose(
                math.fsum(source_areas.values()),
                10.0 / 1_000_000.0,
                rel_tol=0.0,
                abs_tol=1e-15,
            )
            assert math.isclose(
                math.fsum(rollup_areas.values()),
                math.fsum(source_areas.values()),
                rel_tol=0.0,
                abs_tol=1e-15,
            )
            checks += 2

            invalid_contracts = (
                (
                    replace(
                        fixture_contract,
                        analysis_domain=replace(domain, area_field=""),
                    ),
                    "area field is required",
                ),
                (
                    replace(
                        fixture_contract,
                        analysis_domain=replace(
                            domain,
                            rollups={
                                6: replace(rollup, area_unit="hectare")
                            },
                        ),
                    ),
                    "Unsupported analysis-domain R6 area unit",
                ),
            )
            for invalid_contract, expected_message in invalid_contracts:
                try:
                    validate_contract(invalid_contract)
                except ValueError as exc:
                    assert expected_message in str(exc)
                else:
                    raise AssertionError(
                        "Invalid analysis-area contract did not fail closed: "
                        f"{expected_message}"
                    )
                checks += 1

            malformed_sources: list[
                tuple[str, list[dict[str, object]], str]
            ] = []
            missing_area = [dict(row) for row in source_rows]
            missing_area[0].pop("display_area_m2")
            malformed_sources.append(
                ("missing area", missing_area, "has no display_area_m2")
            )
            zero_area = [dict(row) for row in source_rows]
            zero_area[0]["display_area_m2"] = 0.0
            malformed_sources.append(
                ("zero area", zero_area, "non-positive or non-finite")
            )
            non_finite_area = [dict(row) for row in source_rows]
            non_finite_area[0]["display_area_m2"] = "nan"
            malformed_sources.append(
                (
                    "non-finite area",
                    non_finite_area,
                    "non-positive or non-finite",
                )
            )
            wrong_resolution = [dict(row) for row in source_rows]
            wrong_resolution[0]["hex_id"] = parent_a
            malformed_sources.append(
                ("wrong resolution", wrong_resolution, "expected R7")
            )
            malformed_sources.append(
                (
                    "wrong count",
                    [dict(row) for row in source_rows[:-1]],
                    "has 3 cells; expected 4",
                )
            )
            duplicate_ids = [dict(row) for row in source_rows]
            duplicate_ids[-1]["hex_id"] = duplicate_ids[0]["hex_id"]
            malformed_sources.append(
                ("duplicate ids", duplicate_ids, "duplicate cell ids")
            )
            for name, rows, expected_message in malformed_sources:
                write_source(rows)
                try:
                    resolve_analysis_domain_cell_areas_km2(fixture_contract)
                except ValueError as exc:
                    assert expected_message in str(exc)
                else:
                    raise AssertionError(
                        f"Malformed analysis-area fixture did not fail: {name}"
                    )
                checks += 1

            write_source(source_rows)
            rollup_area_failures = (
                (
                    [
                        {"hex_id": parent_a, "display_area_m2": 3.0},
                        {"hex_id": parent_b, "display_area_m2": 8.0},
                    ],
                    "rollup area total",
                ),
                (
                    [
                        {"hex_id": parent_a, "display_area_m2": 4.0},
                        {"hex_id": parent_b, "display_area_m2": 6.0},
                    ],
                    "does not match its R7 children",
                ),
            )
            for rows, expected_message in rollup_area_failures:
                write_rollup(rows)
                try:
                    resolve_analysis_domain_cell_areas_km2(
                        fixture_contract,
                        6,
                    )
                except ValueError as exc:
                    assert expected_message in str(exc)
                else:
                    raise AssertionError(
                        "Invalid analysis-area rollup did not fail closed: "
                        f"{expected_message}"
                    )
                checks += 1
    finally:
        if previous_source_root is None:
            os.environ.pop("SPEEDLOCAL_V2_SOURCE_ROOT", None)
        else:
            os.environ["SPEEDLOCAL_V2_SOURCE_ROOT"] = previous_source_root
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
        assert contract.default_request is not None
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

    bornholm = load_analysis("bornholm", "wind")
    assert bornholm.analysis_domain is None
    try:
        resolve_analysis_domain_cell_areas_km2(bornholm)
    except ValueError as exc:
        assert "has no analysis-domain contract" in str(exc)
    else:
        raise AssertionError(
            "Bornholm area resolution did not fail without a declared domain"
        )
    checks += 2

    trondelag = load_analysis("trondelag", "wind")
    assert trondelag.default_request is not None
    assert trondelag.default_request.selected_layer_ids == ()
    checks += 2
    checks += _assert_invalid_default_requests_fail_closed(trondelag)
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

    display_cell_ids_by_resolution = {
        resolution: _trondelag_display_cell_ids(source_root, resolution)
        for resolution in (7, 6, 5)
    }
    display_cell_ids = display_cell_ids_by_resolution[7]
    assert trondelag.analysis_domain is not None
    assert (
        trondelag.analysis_domain.cell_kind,
        trondelag.analysis_domain.resolution,
        trondelag.analysis_domain.expected_cell_count,
        trondelag.analysis_domain.area_field,
        trondelag.analysis_domain.area_unit,
    ) == ("h3", 7, 13_735, "display_area_m2", "m2")
    assert set(trondelag.analysis_domain.rollups) == {6, 5}
    assert all(
        (rollup.area_field, rollup.area_unit)
        == ("display_area_m2", "m2")
        for rollup in trondelag.analysis_domain.rollups.values()
    )
    checks += 2

    area_by_resolution: dict[int, dict[str, float]] = {}
    for resolution, target_cell_ids in display_cell_ids_by_resolution.items():
        cell_areas = resolve_analysis_domain_cell_areas_km2(
            trondelag,
            resolution,
        )
        area_by_resolution[resolution] = cell_areas
        assert (
            resolve_analysis_domain_cell_ids(trondelag, resolution)
            == target_cell_ids
        )
        assert tuple(cell_areas) == target_cell_ids
        assert len(target_cell_ids) == TRONDELAG_DISPLAY_COUNTS[resolution]
        assert all(
            math.isfinite(area_km2) and area_km2 > 0.0
            for area_km2 in cell_areas.values()
        )
        assert math.isclose(
            math.fsum(cell_areas.values()),
            TRONDELAG_ANALYSIS_DOMAIN_AREA_KM2,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
        if resolution < 7:
            assert {
                str(h3.cell_to_parent(cell_id, resolution))
                for cell_id in display_cell_ids
            } == set(target_cell_ids)
            expected_parent_areas: dict[str, float] = {}
            for cell_id, area_km2 in area_by_resolution[7].items():
                parent_id = str(h3.cell_to_parent(cell_id, resolution))
                expected_parent_areas[parent_id] = (
                    expected_parent_areas.get(parent_id, 0.0) + area_km2
                )
            assert cell_areas.keys() == expected_parent_areas.keys()
            assert all(
                math.isclose(
                    cell_areas[parent_id],
                    expected_area,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
                for parent_id, expected_area in expected_parent_areas.items()
            )
        checks += 7

        for threshold, expected in ROAD_LARGE_EXPECTATIONS[resolution].items():
            parameters = {"roads_large": {"buffer_m": threshold}}
            if resolution == 7:
                raw_result = run_analysis(
                    "trondelag",
                    "wind",
                    ["roads_large"],
                    parameters,
                )
                raw_group = raw_result.groups[0]
                assert raw_group.cell_count == 13_851
                assert len(raw_group.cells) == 13_851
                assert (
                    abs(
                        raw_group.mean_acceptance
                        - ROAD_LARGE_RAW_MEANS[threshold]
                    )
                    < 1e-12
                )
                checks += 3

            display_result = run_analysis(
                "trondelag",
                "wind",
                ["roads_large"],
                parameters,
                target_resolution=resolution,
            )
            display_group = display_result.groups[0]
            assert display_group.cell_count == TRONDELAG_DISPLAY_COUNTS[resolution]
            assert len(display_group.cells) == TRONDELAG_DISPLAY_COUNTS[resolution]
            assert (
                display_group.blocked_cell_count
                == expected["display_blocked"]
            )
            assert (
                abs(
                    display_group.mean_acceptance
                    - expected["display_mean"]
                )
                < 1e-12
            )
            assert {
                cell.cell_id for cell in display_group.cells
            } == set(target_cell_ids)

            oracle = _v2_layer_rollup_oracle(
                trondelag,
                "roads_large",
                threshold,
                resolution,
                target_cell_ids,
            )
            actual = {
                cell.cell_id: cell
                for cell in display_group.cells
            }
            assert actual.keys() == oracle.keys()
            for cell_id, (
                expected_distance,
                expected_intersection,
                expected_blocked,
                expected_acceptance,
            ) in oracle.items():
                cell = actual[cell_id]
                assert abs(cell.min_distance_m - expected_distance) < 1e-12
                assert cell.any_intersection is expected_intersection
                assert cell.blocked is expected_blocked
                assert abs(cell.acceptance - expected_acceptance) < 1e-12
            checks += 10
            print(
                f"PASS trondelag roads_large R{resolution} "
                f"{threshold:g} m: {display_group.cell_count} cells, "
                f"{display_group.blocked_cell_count} blocked, "
                f"{display_group.mean_acceptance:.15f} mean acceptance"
            )

    assert len({round(value, 12) for value in area_by_resolution[7].values()}) > 1
    checks += 1
    checks += _assert_analysis_domain_areas_fail_closed(trondelag)

    r6_anchor = run_analysis(
        "trondelag",
        "wind",
        ["roads_large"],
        {"roads_large": {"buffer_m": 300}},
        target_resolution=6,
    ).groups[0]
    r5_anchor = run_analysis(
        "trondelag",
        "wind",
        ["roads_large"],
        {"roads_large": {"buffer_m": 300}},
        target_resolution=5,
    ).groups[0]
    assert {
        cell.cell_id: cell.min_distance_m
        for cell in r6_anchor.cells
    }["86083312fffffff"] == 26161.1
    assert {
        cell.cell_id: cell.min_distance_m
        for cell in r5_anchor.cells
    }["85083313fffffff"] == 25717.5
    checks += 2

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

    try:
        run_analysis(
            "trondelag",
            "wind",
            ["roads_large"],
            {"roads_large": {"buffer_m": 300}},
            analysis_cell_ids=display_cell_ids_by_resolution[6][:-1],
            target_resolution=6,
        )
    except ValueError as exc:
        assert "do not match the canonical analysis domain" in str(exc)
    else:
        raise AssertionError("Incomplete R6 target domain did not fail closed")
    checks += 1

    for undeclared_resolution in (8, 4):
        try:
            run_analysis(
                "trondelag",
                "wind",
                ["roads_large"],
                {"roads_large": {"buffer_m": 300}},
                target_resolution=undeclared_resolution,
            )
        except ValueError as exc:
            assert "has no R" in str(exc)
        else:
            raise AssertionError(
                f"Undeclared R{undeclared_resolution} did not fail closed"
            )
        checks += 1

    for invalid_resolution in (6.5, True, "6"):
        try:
            run_analysis(
                "trondelag",
                "wind",
                ["roads_large"],
                {"roads_large": {"buffer_m": 300}},
                target_resolution=invalid_resolution,
            )
        except TypeError as exc:
            assert "must be an integer" in str(exc)
        else:
            raise AssertionError(
                f"Non-integral target resolution {invalid_resolution!r} "
                "did not fail closed"
            )
        checks += 1

    source_id = display_cell_ids_by_resolution[7][0]
    mixed_resolution_id = display_cell_ids_by_resolution[6][0]
    try:
        _rollup_distance_rows(
            {
                source_id: (100.0, False),
                mixed_resolution_id: (200.0, False),
            },
            7,
            6,
            frozenset({str(h3.cell_to_parent(source_id, 6))}),
        )
    except ValueError as exc:
        assert "expected R7" in str(exc)
    else:
        raise AssertionError("Mixed-resolution distance rows did not fail closed")
    checks += 1

    try:
        _rollup_distance_rows(
            {source_id: (100.0, False)},
            7,
            8,
            frozenset(),
        )
    except ValueError as exc:
        assert "cannot roll up" in str(exc)
    else:
        raise AssertionError("Upward distance rollup did not fail closed")
    checks += 1

    checks += _assert_invalid_distance_rows_fail_closed()

    print(f"Generic engine validation passed: {checks}/{checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
