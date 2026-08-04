from __future__ import annotations

import os
import sys
import csv
import hashlib
import json
import math
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import h3
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal import run_analysis
from speedlocal.area_result import (
    calculate_remaining_area_cells,
    run_area_analysis,
)
from speedlocal.catalogs import load_analysis
from speedlocal.contracts import (
    AnalysisDomainContract,
    AnalysisDomainRollupContract,
    DefaultRequestContract,
)
from speedlocal.engine import _distance_rows, _rollup_distance_rows
from speedlocal.geometry import build_direct_distance_artifact
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
ROAD_SELECTION_EXPECTATIONS = {
    ("roads_large",): {
        7: {300.0: (0.968838733163451, 428), 1000.0: (0.9554751146705496, 434)},
        6: {300.0: (0.9223300970873787, 168), 1000.0: (0.9101944059177069, 170)},
        5: {300.0: (0.8191780821917808, 66), 1000.0: (0.8089936986301369, 66)},
    },
    ("roads_medium",): {
        7: {300.0: (0.7682562795777211, 3183), 1000.0: (0.6956854532216964, 3227)},
        6: {300.0: (0.5501618122977346, 973), 1000.0: (0.5073281091077207, 975)},
        5: {300.0: (0.3123287671232877, 251), 1000.0: (0.2952065753424657, 251)},
    },
    ("roads_medium", "roads_large"): {
        7: {300.0: (0.7501274117218785, 3432), 1000.0: (0.6743830797233345, 3475)},
        6: {300.0: (0.5228848821081831, 1032), 1000.0: (0.4787505316689782, 1034)},
        5: {300.0: (0.2712328767123288, 266), 1000.0: (0.2553369863013699, 266)},
    },
}
ROAD_SELECTION_RAW_EXPECTATIONS = {
    ("roads_large",): {
        300.0: (0.9690997039924916, 428),
        1000.0: (0.9558480037542414, 434),
    },
    ("roads_medium",): {
        300.0: (0.7701970976824778, 3183),
        1000.0: (0.6982340408634755, 3227),
    },
    ("roads_medium", "roads_large"): {
        300.0: (0.7522200563136235, 3432),
        1000.0: (0.6771100714749835, 3475),
    },
}
POPULATION_EXPECTATIONS = {
    7: {
        100.0: (0.7073170731707317, 4_020, 4_020, 32_033.294765366558),
        500.0: (0.7070320705559044, 4_020, 4_020, 32_020.544812344022),
        1000.0: (0.6323414159520412, 4_083, 4_083, 28_655.258106115540),
        3000.0: (0.3307196735844324, 7_588, 7_588, 15_028.059399211797),
    },
    6: {
        100.0: (0.4785020804438280, 1_128, 1_128, 21_299.369535789352),
        500.0: (0.4783465515504408, 1_128, 1_128, 21_293.754330461623),
        1000.0: (0.4315900619940833, 1_136, 1_136, 19_183.049121041375),
        3000.0: (0.2355616618057175, 1_483, 1_483, 10_181.075326368010),
    },
    5: {
        100.0: (0.2438356164383562, 276, 276, 7_521.183269500072),
        500.0: (0.2435574779369594, 276, 276, 7_504.290681082110),
        1000.0: (0.2160813563563715, 277, 277, 6_453.775000831103),
        3000.0: (0.1446149421386573, 302, 302, 3_669.016755527792),
    },
}
OPTIONAL_POPULATION_EXPECTATIONS = {
    ("built_centre",): {
        7: (0.9793580709868845, 283, 44_282.970771188660),
        6: (0.9398818476005033, 130, 42_412.804166986470),
        5: (0.8245600996161335, 64, 36_217.147640343540),
    },
    ("built_low_selection",): {
        7: (0.5390864250386150, 6_318, 24_400.317787201784),
        6: (0.1901581210110947, 1_751, 7_580.237267448478),
        5: (0.0819100927881540, 335, 953.603137445545),
    },
    ("population_points", "built_centre", "built_low_selection"): {
        7: (0.4724434286333389, 7_237, 21_408.783172646607),
        6: (0.1822993069821105, 1_768, 7_329.037424675471),
        5: (0.0819100927881540, 335, 953.603137445545),
    },
}
NATURE_EXPECTATIONS = {
    7: {
        0.0: (0.7116126683654896, 3_961),
        250.0: (0.7116126683654896, 3_961),
        1000.0: (0.7096468875136513, 3_988),
        2000.0: (0.6018929741536221, 5_468),
    },
    6: {
        0.0: (0.5141007859454462, 1_051),
        250.0: (0.5141007859454462, 1_051),
        1000.0: (0.5108645399907536, 1_058),
        2000.0: (0.4077669902912621, 1_281),
    },
    5: {
        0.0: (0.1726027397260274, 302),
        250.0: (0.1726027397260274, 302),
        1000.0: (0.1726027397260274, 302),
        2000.0: (0.1287671232876712, 318),
    },
}
CULTURE_SELECTION_EXPECTATIONS = {
    ("cultural_preservation",): {
        7: {0.0: (12_665 / 13_735, 1_070), 250.0: (12_665 / 13_735, 1_070), 1000.0: (12_662 / 13_735, 1_073), 1500.0: (12_619 / 13_735, 1_116)},
        6: {0.0: (1_966 / 2_163, 197), 250.0: (1_966 / 2_163, 197), 1000.0: (1_966 / 2_163, 197), 1500.0: (1_960 / 2_163, 203)},
        5: {0.0: (317 / 365, 48), 250.0: (317 / 365, 48), 1000.0: (317 / 365, 48), 1500.0: (314 / 365, 51)},
    },
    ("valuable_cultural_environment",): {
        7: {0.0: (13_212 / 13_735, 523), 250.0: (13_212 / 13_735, 523), 1000.0: (13_204 / 13_735, 531), 1500.0: (12_995 / 13_735, 740)},
        6: {0.0: (1_909 / 2_163, 254), 250.0: (1_909 / 2_163, 254), 1000.0: (1_908 / 2_163, 255), 1500.0: (1_863 / 2_163, 300)},
        5: {0.0: (235 / 365, 130), 250.0: (235 / 365, 130), 1000.0: (234 / 365, 131), 1500.0: (227 / 365, 138)},
    },
    ("cultural_preservation", "valuable_cultural_environment"): {
        7: {0.0: (12_206 / 13_735, 1_529), 250.0: (12_206 / 13_735, 1_529), 1000.0: (12_199 / 13_735, 1_536), 1500.0: (11_980 / 13_735, 1_755)},
        6: {0.0: (1_751 / 2_163, 412), 250.0: (1_751 / 2_163, 412), 1000.0: (1_750 / 2_163, 413), 1500.0: (1_709 / 2_163, 454)},
        5: {0.0: (212 / 365, 153), 250.0: (212 / 365, 153), 1000.0: (212 / 365, 153), 1500.0: (205 / 365, 160)},
    },
}
GRID_LAYER_IDS = (
    "high_voltage_lines",
    "underground_cables",
    "existing_wind_turbines",
)
GRID_FIXED_ANCHORS = {
    (("high_voltage_lines",), 7, 500.0): (0.34692391700036, 8_970, 15_626.037306365233),
    (("high_voltage_lines",), 7, 2000.0): (0.38929144521296, 6_732, 17_534.576905796115),
    (("high_voltage_lines",), 7, 15000.0): (0.78842961970635, 364, 35_596.448814965464),
    (("high_voltage_lines",), 6, 2000.0): (0.60600873786408, 711, 28_150.881843896183),
    (("high_voltage_lines",), 5, 2000.0): (0.79991726027397, 61, 39_981.102141200048),
    (GRID_LAYER_IDS, 7, 2000.0): (0.39481352384419, 6_673, 17_780.848461686470),
    (GRID_LAYER_IDS, 6, 2000.0): (0.61125457697642, 702, 28_295.255871122208),
    (GRID_LAYER_IDS, 5, 2000.0): (0.80542534246575, 59, 40_000.610596470484),
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


def _v2_distance_selection_rollup_oracle(
    contract,
    layer_ids: tuple[str, ...],
    threshold: float,
    source_resolution: int,
    target_resolution: int,
    target_cell_ids: tuple[str, ...],
    missing_distance_policy: str = "error",
    analysis_kind: str = "distance_conflict",
) -> dict[str, tuple[float | None, bool, bool, float]]:
    """Independently reproduce frozen raw-distance rollup and acceptance."""
    rolled: dict[str, tuple[float, bool]] = {}
    for layer_id in layer_ids:
        path = resolve_layer_assets(contract.layers[layer_id]).distance_path
        seen_source_ids: set[str] = set()
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                cell_id = str(row["hex_id"])
                if cell_id in seen_source_ids:
                    raise ValueError(
                        f"Duplicate {layer_id} oracle cell id: {cell_id}"
                    )
                seen_source_ids.add(cell_id)
                if int(h3.get_resolution(cell_id)) != source_resolution:
                    raise ValueError(
                        f"{layer_id} oracle source cell is not "
                        f"R{source_resolution}: {cell_id}"
                    )
                target_id = (
                    cell_id
                    if target_resolution == source_resolution
                    else str(h3.cell_to_parent(cell_id, target_resolution))
                )
                value = (
                    float(row["distance_m"]),
                    str(row["intersects"]).strip().lower()
                    in {"1", "true", "yes"},
                )
                previous = rolled.get(target_id)
                if previous is None:
                    rolled[target_id] = value
                else:
                    rolled[target_id] = (
                        min(previous[0], value[0]),
                        previous[1] or value[1],
                    )

    oracle: dict[str, tuple[float | None, bool, bool, float]] = {}
    ramp_end = max(threshold * 2.0, threshold + 1.0)
    for cell_id in target_cell_ids:
        if cell_id not in rolled:
            if missing_distance_policy == "zero_acceptance":
                distance, intersects = None, False
            else:
                raise ValueError(f"Oracle is missing analysis cell: {cell_id}")
        else:
            distance, intersects = rolled[cell_id]
        if analysis_kind == "proximity_feasibility":
            blocked = (distance is None and not intersects) or (
                not intersects and distance > threshold
            )
            if intersects:
                acceptance = 1.0
            elif distance is None:
                acceptance = 0.0
            else:
                acceptance = max(
                    0.0,
                    min(1.0, 1.0 - (distance / max(threshold, 1.0))),
                )
        else:
            blocked = intersects or (
                distance is not None and distance <= threshold
            )
            if intersects:
                acceptance = 0.0
            elif distance is None:
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

        declared_path = root / "declared_resolution.csv"
        r7_cell = str(h3.latlng_to_cell(63.4, 10.4, 7))
        declared_path.write_text(
            "hex_id,distance_m,intersects\n"
            f"{r7_cell},10,FALSE\n",
            encoding="utf-8",
        )
        declared_layer = SimpleNamespace(
            assets=SimpleNamespace(distance_path=declared_path),
            contract=SimpleNamespace(
                source=SimpleNamespace(distance_h3_resolution=8),
            ),
        )
        try:
            _distance_rows(declared_layer)
        except ValueError as exc:
            assert "expected declared R8" in str(exc)
        else:
            raise AssertionError(
                "A distance row outside its declared H3 resolution did not "
                "fail closed"
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

    population = validate_layer(trondelag.layers["population_points"])
    population_buffer = population.contract.parameters["buffer_m"]
    assert population.contract.group_id == "population"
    assert population.geometry_family == "polygon"
    assert population.processing_adapter == "population_grid"
    assert population.assets.feature_count == 26_029
    assert population.contract.source.distance_h3_resolution == 7
    population_coverage = population.contract.source.distance_coverage
    assert population_coverage.mode == "complete"
    assert population_coverage.missing_policy == "error"
    assert population_coverage.expected_source_row_count == 13_735
    assert population_coverage.source_ids_sha256 == (
        "fdea5973b898319643b7c94ad43b3480c98e639a8f378cbc23e8bc56751fcbba"
    )
    assert (
        population_buffer.default,
        population_buffer.minimum,
        population_buffer.maximum,
        population_buffer.step,
    ) == (100.0, 100.0, 3000.0, 50.0)
    checks += 10

    built_centre = validate_layer(trondelag.layers["built_centre"])
    built_low = validate_layer(trondelag.layers["built_low_selection"])
    assert built_centre.contract.group_id == "population"
    assert built_centre.geometry_family == "polygon"
    assert built_centre.processing_adapter == "population_polygons"
    assert built_centre.assets.feature_count == 1
    assert built_low.contract.group_id == "population"
    assert built_low.geometry_family == "point"
    assert built_low.processing_adapter == "population_points"
    assert built_low.assets.feature_count == 10_966
    assert all(
        layer.contract.source.distance_h3_resolution == 7
        and layer.contract.source.distance_coverage == population_coverage
        for layer in (built_centre, built_low)
    )
    checks += 9

    direct_population_evidence = {
        "population_points": (
            population,
            7_057,
            4_020,
            "82bab4e1e3e2506244f402a9f098b60bdde6a56848a183ac1384dbca076a2ebe",
        ),
        "built_centre": (
            built_centre,
            85,
            283,
            "0d83c8230dc42c29c4be0a92af6e1fb0d6a948cd465da28646161426040d1656",
        ),
        "built_low_selection": (
            built_low,
            10_966,
            6_318,
            "143711984e8a25fac4773495302c4d699b33e6b32312550d54b0d52bfa2c665d",
        ),
    }
    for layer_id, (
        validated_layer,
        expected_parts,
        expected_intersections,
        expected_sha256,
    ) in direct_population_evidence.items():
        artifact = build_direct_distance_artifact(
            validated_layer.contract,
            analysis_domain=trondelag.analysis_domain,
            native_crs="EPSG:25832",
        )
        generated_rows = _distance_rows(validated_layer)
        digest = hashlib.sha256(
            validated_layer.assets.distance_path.read_bytes()
        ).hexdigest()
        assert artifact.layer_id == layer_id
        assert artifact.resolution == 7
        assert len(artifact.rows) == 13_735
        assert artifact.source_part_count == expected_parts
        assert sum(row.intersects for row in artifact.rows) == expected_intersections
        assert digest == expected_sha256
        assert all(
            row.cell_id in generated_rows
            and abs(generated_rows[row.cell_id][0] - row.distance_m) < 1e-9
            and generated_rows[row.cell_id][1] is row.intersects
            for row in artifact.rows
        )
        checks += 7

    nature = validate_layer(trondelag.layers["protected_areas"])
    nature_buffer = nature.contract.parameters["buffer_m"]
    assert nature.contract.group_id == "nature"
    assert nature.contract.operation == "hard_exclusion"
    assert nature.geometry_family == "polygon"
    assert nature.processing_adapter == "polygon_generic"
    assert nature.assets.feature_count == 420
    assert nature.contract.source.distance_h3_resolution == 7
    assert nature.contract.source.geometry_collection_policy == "highest_dimension"
    assert (
        nature_buffer.default,
        nature_buffer.minimum,
        nature_buffer.maximum,
        nature_buffer.step,
    ) == (0.0, 0.0, 2000.0, 50.0)
    checks += 8

    culture_layers = tuple(
        validate_layer(trondelag.layers[layer_id])
        for layer_id in (
            "cultural_preservation",
            "valuable_cultural_environment",
        )
    )
    assert all(
        layer.contract.group_id == "culture"
        and layer.contract.operation == "hard_exclusion"
        and layer.geometry_family == "polygon"
        and layer.processing_adapter == "polygon_generic"
        and layer.contract.source.distance_h3_resolution == 7
        for layer in culture_layers
    )
    assert [layer.assets.feature_count for layer in culture_layers] == [64, 146]
    assert (
        culture_layers[0].contract.source.geometry_validity_policy
        == "make_valid"
    )
    assert (
        culture_layers[1].contract.source.geometry_validity_policy
        == "reject_invalid"
    )
    assert all(
        (
            layer.contract.parameters["buffer_m"].default,
            layer.contract.parameters["buffer_m"].minimum,
            layer.contract.parameters["buffer_m"].maximum,
            layer.contract.parameters["buffer_m"].step,
        )
        == (0.0, 0.0, 1500.0, 50.0)
        for layer in culture_layers
    )
    checks += 5
    try:
        replace(
            culture_layers[0].contract.source,
            geometry_validity_policy="silently_fix",
        )
    except ValueError as exc:
        assert "geometry_validity_policy" in str(exc)
    else:
        raise AssertionError(
            "Unknown geometry-validity policy did not fail closed"
        )
    checks += 1

    grid_layers = tuple(
        validate_layer(trondelag.layers[layer_id])
        for layer_id in GRID_LAYER_IDS
    )
    assert all(
        layer.contract.group_id == "grid_infrastructure"
        and layer.contract.operation == "proximity_feasibility"
        and layer.contract.source.distance_h3_resolution == 7
        for layer in grid_layers
    )
    assert [layer.geometry_family for layer in grid_layers] == [
        "line",
        "line",
        "point",
    ]
    assert [layer.processing_adapter for layer in grid_layers] == [
        "line_generic",
        "line_generic",
        "point_generic",
    ]
    assert [layer.assets.feature_count for layer in grid_layers] == [
        16_932,
        330,
        470,
    ]
    assert all(
        (
            layer.contract.parameters["buffer_m"].default,
            layer.contract.parameters["buffer_m"].minimum,
            layer.contract.parameters["buffer_m"].maximum,
            layer.contract.parameters["buffer_m"].step,
        )
        == (2000.0, 500.0, 15000.0, 250.0)
        for layer in grid_layers
    )
    checks += 5

    try:
        validate_layer(
            replace(
                nature.contract,
                source=replace(
                    nature.contract.source,
                    geometry_collection_policy="reject_mixed",
                ),
            )
        )
    except ValueError as exc:
        assert "Expected one geometry family" in str(exc)
    else:
        raise AssertionError(
            "Mixed nature geometry passed without its manifest policy"
        )
    checks += 1
    for invalid_distance_resolution in (True, 6.5, -1, 16):
        try:
            replace(
                population.contract.source,
                distance_h3_resolution=invalid_distance_resolution,
            )
        except ValueError as exc:
            assert "distance_h3_resolution" in str(exc)
        else:
            raise AssertionError(
                "Invalid distance_h3_resolution did not fail closed: "
                f"{invalid_distance_resolution!r}"
            )
        checks += 1
    try:
        replace(
            population_coverage,
            missing_policy="unconstrained",
        )
    except ValueError as exc:
        assert "missing policy" in str(exc)
    else:
        raise AssertionError("Unknown missing-distance policy did not fail closed")
    checks += 1
    try:
        replace(
            population_coverage,
            source_ids_sha256="not-a-digest",
        )
    except ValueError as exc:
        assert "source_ids_sha256" in str(exc)
    else:
        raise AssertionError("Invalid distance source digest did not fail closed")
    checks += 1

    def population_contract_with_source(source):
        return replace(
            trondelag,
            layers={
                **trondelag.layers,
                "population_points": replace(
                    population.contract,
                    source=source,
                ),
            },
        )

    try:
        replace(
            population.contract.source,
            distance_path=None,
        )
    except ValueError as exc:
        assert "must be declared together" in str(exc)
    else:
        raise AssertionError(
            "Population distance override accepted a missing path"
        )
    checks += 1

    try:
        replace(
            population.contract.source,
            distance_provider=None,
        )
    except ValueError as exc:
        assert "must be declared together" in str(exc)
    else:
        raise AssertionError(
            "Population distance override accepted a missing provider"
        )
    checks += 1

    try:
        validate_contract(
            population_contract_with_source(
                replace(
                    population.contract.source,
                    distance_h3_resolution=6,
                )
            )
        )
    except ValueError as exc:
        assert "finer than its R6 distance source" in str(exc)
    else:
        raise AssertionError(
            "Population coverage accepted a coarser distance source"
        )
    checks += 1

    for coverage_drift, expected_message in (
        (
            replace(
                population_coverage,
                expected_source_row_count=(
                    population_coverage.expected_source_row_count - 1
                ),
            ),
            "distance rows; expected",
        ),
        (
            replace(
                population_coverage,
                source_ids_sha256="0" * 64,
            ),
            "source-id coverage digest",
        ),
    ):
        drifted_layer = replace(
            population,
            contract=replace(
                population.contract,
                source=replace(
                    population.contract.source,
                    distance_coverage=coverage_drift,
                ),
            ),
        )
        try:
            _distance_rows(drifted_layer)
        except ValueError as exc:
            assert expected_message in str(exc)
        else:
            raise AssertionError(
                "Population source coverage drift did not fail closed"
            )
        checks += 1

    try:
        run_analysis(
            "trondelag",
            "wind",
            ["population_points"],
            {"population_points": {"buffer_m": 500}},
            analysis_cell_ids=["not-an-h3-cell"],
        )
    except ValueError as exc:
        assert "missing requested analysis cells" in str(exc)
    else:
        raise AssertionError(
            "Population coverage bypassed its signed target domain"
        )
    checks += 1

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

    population_rows = _distance_rows(population)
    direct_r7_rows = _rollup_distance_rows(
        population_rows,
        7,
        7,
        frozenset(display_cell_ids_by_resolution[7]),
        population_coverage,
    )
    assert direct_r7_rows == population_rows
    checks += 1
    missing_population_rows = dict(population_rows)
    missing_population_rows.pop(next(iter(missing_population_rows)))
    try:
        _rollup_distance_rows(
            missing_population_rows,
            7,
            7,
            frozenset(display_cell_ids_by_resolution[7]),
            population_coverage,
        )
    except ValueError as exc:
        assert "missing R7 analysis cells" in str(exc)
    else:
        raise AssertionError(
            "Direct R7 population coverage accepted a missing analysis cell"
        )
    checks += 1

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

        for layer_ids, selection_expectations in (
            ROAD_SELECTION_EXPECTATIONS.items()
        ):
            for threshold, (expected_mean, expected_blocked) in (
                selection_expectations[resolution].items()
            ):
                parameters = {
                    layer_id: {"buffer_m": threshold}
                    for layer_id in layer_ids
                }
                if resolution == 7:
                    raw_result = run_analysis(
                        "trondelag",
                        "wind",
                        list(layer_ids),
                        parameters,
                    )
                    raw_group = raw_result.groups[0]
                    expected_raw_mean, expected_raw_blocked = (
                        ROAD_SELECTION_RAW_EXPECTATIONS[layer_ids][threshold]
                    )
                    assert tuple(raw_group.layer_ids) == layer_ids
                    assert raw_group.cell_count == 13_851
                    assert len(raw_group.cells) == 13_851
                    assert raw_group.blocked_cell_count == expected_raw_blocked
                    assert (
                        abs(raw_group.mean_acceptance - expected_raw_mean)
                        < 1e-12
                    )
                    checks += 5

                display_result = run_analysis(
                    "trondelag",
                    "wind",
                    list(layer_ids),
                    parameters,
                    target_resolution=resolution,
                )
                display_group = display_result.groups[0]
                assert tuple(display_group.layer_ids) == layer_ids
                assert (
                    display_group.cell_count
                    == TRONDELAG_DISPLAY_COUNTS[resolution]
                )
                assert (
                    len(display_group.cells)
                    == TRONDELAG_DISPLAY_COUNTS[resolution]
                )
                assert display_group.blocked_cell_count == expected_blocked
                assert (
                    abs(display_group.mean_acceptance - expected_mean)
                    < 1e-12
                )
                assert {
                    cell.cell_id for cell in display_group.cells
                } == set(target_cell_ids)

                oracle = _v2_distance_selection_rollup_oracle(
                    trondelag,
                    layer_ids,
                    threshold,
                    7,
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
                    expected_cell_blocked,
                    expected_acceptance,
                ) in oracle.items():
                    cell = actual[cell_id]
                    assert abs(cell.min_distance_m - expected_distance) < 1e-12
                    assert cell.any_intersection is expected_intersection
                    assert cell.blocked is expected_cell_blocked
                    assert abs(cell.acceptance - expected_acceptance) < 1e-12
                checks += 11
                selection_label = "+".join(layer_ids)
                print(
                    f"PASS trondelag {selection_label} R{resolution} "
                    f"{threshold:g} m: {display_group.cell_count} cells, "
                    f"{display_group.blocked_cell_count} blocked, "
                    f"{display_group.mean_acceptance:.15f} mean acceptance"
                )

    for resolution, expectations in POPULATION_EXPECTATIONS.items():
        target_cell_ids = display_cell_ids_by_resolution[resolution]
        for threshold, (
            expected_mean,
            expected_blocked,
            expected_zero_acceptance,
            expected_area_km2,
        ) in expectations.items():
            result = run_analysis(
                "trondelag",
                "wind",
                ["population_points"],
                {"population_points": {"buffer_m": threshold}},
                target_resolution=resolution,
            )
            assert len(result.layers) == 1
            layer_result = result.layers[0]
            group = result.groups[0]
            assert layer_result.geometry_family == "polygon"
            assert layer_result.processing_adapter == "population_grid"
            assert group.group_id == "population"
            assert group.layer_ids == ("population_points",)
            assert group.cell_count == TRONDELAG_DISPLAY_COUNTS[resolution]
            assert len(group.cells) == TRONDELAG_DISPLAY_COUNTS[resolution]
            assert group.blocked_cell_count == expected_blocked
            assert layer_result.blocked_cell_count == expected_blocked
            assert abs(group.mean_acceptance - expected_mean) < 1e-12
            assert {cell.cell_id for cell in group.cells} == set(target_cell_ids)
            assert sum(
                cell.acceptance == 0.0 for cell in group.cells
            ) == expected_zero_acceptance
            assert not any(cell.coverage_missing for cell in group.cells)

            oracle = _v2_distance_selection_rollup_oracle(
                trondelag,
                ("population_points",),
                threshold,
                7,
                resolution,
                target_cell_ids,
                "error",
            )
            actual = {cell.cell_id: cell for cell in group.cells}
            assert actual.keys() == oracle.keys()
            for cell_id, (
                expected_distance,
                expected_intersection,
                expected_cell_blocked,
                expected_acceptance,
            ) in oracle.items():
                cell = actual[cell_id]
                if expected_distance is None:
                    assert cell.min_distance_m is None
                    assert cell.coverage_missing is True
                else:
                    assert cell.min_distance_m is not None
                    assert abs(cell.min_distance_m - expected_distance) < 1e-12
                    assert cell.coverage_missing is False
                assert cell.any_intersection is expected_intersection
                assert cell.blocked is expected_cell_blocked
                assert abs(cell.acceptance - expected_acceptance) < 1e-12

            model_area_km2 = math.fsum(
                cell.acceptance
                * area_by_resolution[resolution][cell.cell_id]
                for cell in group.cells
            )
            assert math.isclose(
                model_area_km2,
                expected_area_km2,
                rel_tol=1e-12,
                abs_tol=1e-8,
            )
            checks += 16
            print(
                f"PASS trondelag population_points R{resolution} "
                f"{threshold:g} m: {group.cell_count} cells, "
                f"{group.blocked_cell_count} blocked, "
                f"{expected_zero_acceptance} zero-acceptance, "
                f"{group.mean_acceptance:.15f} mean acceptance, "
                f"{model_area_km2:.9f} km2 model area"
            )

    for layer_ids, expectations in OPTIONAL_POPULATION_EXPECTATIONS.items():
        for resolution, (
            expected_mean,
            expected_zero_acceptance,
            expected_area_km2,
        ) in expectations.items():
            target_cell_ids = display_cell_ids_by_resolution[resolution]
            result = run_analysis(
                "trondelag",
                "wind",
                list(layer_ids),
                {
                    layer_id: {"buffer_m": 500.0}
                    for layer_id in layer_ids
                },
                target_resolution=resolution,
            )
            group = result.groups[0]
            assert group.group_id == "population"
            assert group.layer_ids == layer_ids
            assert group.cell_count == TRONDELAG_DISPLAY_COUNTS[resolution]
            assert abs(group.mean_acceptance - expected_mean) < 1e-12
            assert sum(
                cell.acceptance == 0.0 for cell in group.cells
            ) == expected_zero_acceptance
            oracle = _v2_distance_selection_rollup_oracle(
                trondelag,
                layer_ids,
                500.0,
                7,
                resolution,
                target_cell_ids,
                "error",
            )
            actual = {cell.cell_id: cell for cell in group.cells}
            assert actual.keys() == oracle.keys()
            assert all(
                abs(actual[cell_id].acceptance - values[3]) < 1e-12
                for cell_id, values in oracle.items()
            )
            model_area_km2 = math.fsum(
                cell.acceptance
                * area_by_resolution[resolution][cell.cell_id]
                for cell in group.cells
            )
            assert math.isclose(
                model_area_km2,
                expected_area_km2,
                rel_tol=1e-12,
                abs_tol=1e-8,
            )
            checks += 9
            print(
                f"PASS trondelag {'+'.join(layer_ids)} R{resolution} "
                f"500 m: {group.cell_count} cells, "
                f"{expected_zero_acceptance} zero-acceptance, "
                f"{group.mean_acceptance:.15f} mean acceptance, "
                f"{model_area_km2:.9f} km2 model area"
            )

    for resolution, expectations in NATURE_EXPECTATIONS.items():
        target_cell_ids = display_cell_ids_by_resolution[resolution]
        for threshold, (expected_mean, expected_blocked) in expectations.items():
            result = run_analysis(
                "trondelag",
                "wind",
                ["protected_areas"],
                {"protected_areas": {"buffer_m": threshold}},
                target_resolution=resolution,
            )
            assert len(result.layers) == 1
            layer_result = result.layers[0]
            group = result.groups[0]
            assert layer_result.operation == "hard_exclusion"
            assert layer_result.geometry_family == "polygon"
            assert layer_result.processing_adapter == "polygon_generic"
            assert group.group_id == "nature"
            assert group.layer_ids == ("protected_areas",)
            assert group.cell_count == TRONDELAG_DISPLAY_COUNTS[resolution]
            assert group.blocked_cell_count == expected_blocked
            assert layer_result.blocked_cell_count == expected_blocked
            assert abs(group.mean_acceptance - expected_mean) < 1e-12
            assert {cell.cell_id for cell in group.cells} == set(target_cell_ids)
            assert all(cell.acceptance in {0.0, 1.0} for cell in group.cells)
            assert sum(cell.blocked for cell in group.cells) == expected_blocked
            checks += 12
            print(
                f"PASS trondelag protected_areas R{resolution} "
                f"{threshold:g} m: {group.cell_count} cells, "
                f"{group.blocked_cell_count} blocked, "
                f"{group.mean_acceptance:.15f} mean acceptance"
            )

    for layer_ids, resolution_expectations in CULTURE_SELECTION_EXPECTATIONS.items():
        for resolution, expectations in resolution_expectations.items():
            target_cell_ids = display_cell_ids_by_resolution[resolution]
            for threshold, (expected_mean, expected_blocked) in expectations.items():
                result = run_analysis(
                    "trondelag",
                    "wind",
                    list(layer_ids),
                    {
                        layer_id: {"buffer_m": threshold}
                        for layer_id in layer_ids
                    },
                    target_resolution=resolution,
                )
                group = result.groups[0]
                assert all(layer.operation == "hard_exclusion" for layer in result.layers)
                assert all(layer.geometry_family == "polygon" for layer in result.layers)
                assert all(layer.processing_adapter == "polygon_generic" for layer in result.layers)
                assert group.group_id == "culture"
                assert group.layer_ids == layer_ids
                assert group.cell_count == TRONDELAG_DISPLAY_COUNTS[resolution]
                assert group.blocked_cell_count == expected_blocked
                assert abs(group.mean_acceptance - expected_mean) < 1e-12
                assert {cell.cell_id for cell in group.cells} == set(target_cell_ids)
                assert all(cell.acceptance in {0.0, 1.0} for cell in group.cells)
                checks += 10
                print(
                    f"PASS trondelag {'+'.join(layer_ids)} R{resolution} "
                    f"{threshold:g} m: {group.cell_count} cells, "
                    f"{group.blocked_cell_count} blocked, "
                    f"{group.mean_acceptance:.15f} mean acceptance"
                )

    grid_selections = tuple((layer_id,) for layer_id in GRID_LAYER_IDS) + (
        GRID_LAYER_IDS,
    )
    for layer_ids in grid_selections:
        for resolution in (7, 6, 5):
            target_cell_ids = display_cell_ids_by_resolution[resolution]
            for threshold in (500.0, 2000.0, 15000.0):
                oracle = _v2_distance_selection_rollup_oracle(
                    trondelag,
                    layer_ids,
                    threshold,
                    7,
                    resolution,
                    target_cell_ids,
                    analysis_kind="proximity_feasibility",
                )
                result = run_analysis(
                    "trondelag",
                    "wind",
                    list(layer_ids),
                    {
                        layer_id: {"buffer_m": threshold}
                        for layer_id in layer_ids
                    },
                    target_resolution=resolution,
                )
                group = result.groups[0]
                actual = {
                    cell.cell_id: (
                        cell.min_distance_m,
                        cell.any_intersection,
                        cell.blocked,
                        cell.acceptance,
                    )
                    for cell in group.cells
                }
                assert all(
                    layer.operation == "proximity_feasibility"
                    for layer in result.layers
                )
                assert group.group_id == "grid_infrastructure"
                assert group.layer_ids == layer_ids
                assert group.cell_count == TRONDELAG_DISPLAY_COUNTS[resolution]
                assert actual.keys() == oracle.keys()
                assert all(
                    actual[cell_id][:3] == values[:3]
                    and abs(actual[cell_id][3] - values[3]) < 1e-12
                    for cell_id, values in oracle.items()
                )
                expected_blocked = sum(values[2] for values in oracle.values())
                expected_mean = math.fsum(
                    values[3] for values in oracle.values()
                ) / len(oracle)
                model_area_km2 = math.fsum(
                    values[3] * area_by_resolution[resolution][cell_id]
                    for cell_id, values in oracle.items()
                )
                assert group.blocked_cell_count == expected_blocked
                assert math.isclose(
                    group.mean_acceptance,
                    expected_mean,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                fixed = GRID_FIXED_ANCHORS.get(
                    (layer_ids, resolution, threshold)
                )
                if fixed is not None:
                    fixed_mean, fixed_zero, fixed_area = fixed
                    assert math.isclose(
                        group.mean_acceptance,
                        fixed_mean,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    assert sum(
                        values[3] == 0.0 for values in oracle.values()
                    ) == fixed_zero
                    assert math.isclose(
                        model_area_km2,
                        fixed_area,
                        rel_tol=1e-12,
                        abs_tol=1e-8,
                    )
                checks += 10 + (3 if fixed is not None else 0)
                print(
                    f"PASS trondelag {'+'.join(layer_ids)} R{resolution} "
                    f"{threshold:g} m: {group.cell_count} cells, "
                    f"{group.blocked_cell_count} infeasible, "
                    f"{group.mean_acceptance:.15f} mean acceptance"
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

    medium_r5_anchor = run_analysis(
        "trondelag",
        "wind",
        ["roads_medium"],
        {"roads_medium": {"buffer_m": 300}},
        target_resolution=5,
    ).groups[0]
    assert {
        cell.cell_id: cell.min_distance_m
        for cell in medium_r5_anchor.cells
    }["850803b3fffffff"] == 10_560.1
    checks += 1

    combined_parameters = {
        layer_id: {"buffer_m": 300}
        for layer_id in ("roads_medium", "roads_large")
    }
    combined_forward = run_analysis(
        "trondelag",
        "wind",
        ["roads_medium", "roads_large"],
        combined_parameters,
        target_resolution=7,
    ).groups[0]
    combined_reversed = run_analysis(
        "trondelag",
        "wind",
        ["roads_large", "roads_medium"],
        combined_parameters,
        target_resolution=7,
    ).groups[0]
    assert {
        cell.cell_id: (
            cell.min_distance_m,
            cell.any_intersection,
            cell.blocked,
            cell.acceptance,
        )
        for cell in combined_forward.cells
    } == {
        cell.cell_id: (
            cell.min_distance_m,
            cell.any_intersection,
            cell.blocked,
            cell.acceptance,
        )
        for cell in combined_reversed.cells
    }
    checks += 1

    for layer_ids in ROAD_SELECTION_EXPECTATIONS:
        endpoint_results = []
        for threshold in (100.0, 2000.0):
            group = run_analysis(
                "trondelag",
                "wind",
                list(layer_ids),
                {
                    layer_id: {"buffer_m": threshold}
                    for layer_id in layer_ids
                },
                target_resolution=7,
            ).groups[0]
            endpoint_results.append(group)
        narrow, wide = endpoint_results
        assert wide.blocked_cell_count >= narrow.blocked_cell_count
        assert wide.mean_acceptance <= narrow.mean_acceptance
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

    synthetic_model_cells = {"cell": box(0.0, 0.0, 10.0, 10.0)}
    synthetic_model_areas = {"cell": 2.0}
    overlap_result = calculate_remaining_area_cells(
        synthetic_model_cells,
        synthetic_model_areas,
        exclusion_groups=(
            (
                box(0.0, 0.0, 6.0, 10.0),
                box(4.0, 0.0, 8.0, 10.0),
            ),
        ),
    )[0]
    assert math.isclose(
        overlap_result.remaining_area_km2,
        0.4,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        overlap_result.potential_pct,
        20.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    checks += 2

    reordered_overlap = calculate_remaining_area_cells(
        synthetic_model_cells,
        synthetic_model_areas,
        exclusion_groups=(
            (
                box(4.0, 0.0, 8.0, 10.0),
                box(0.0, 0.0, 6.0, 10.0),
            ),
        ),
    )[0]
    assert reordered_overlap == overlap_result
    checks += 1

    feasibility_result = calculate_remaining_area_cells(
        synthetic_model_cells,
        synthetic_model_areas,
        exclusion_groups=((box(0.0, 0.0, 2.0, 10.0),),),
        feasibility_groups=((box(0.0, 0.0, 5.0, 10.0),),),
    )[0]
    assert math.isclose(
        feasibility_result.remaining_area_km2,
        0.6,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        feasibility_result.potential_pct,
        30.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    checks += 2

    unfiltered_area = calculate_remaining_area_cells(
        synthetic_model_cells,
        synthetic_model_areas,
    )[0]
    assert unfiltered_area.remaining_area_km2 == 2.0
    assert unfiltered_area.potential_pct == 100.0
    checks += 2

    direct_population_area = run_area_analysis(
        "trondelag",
        "wind",
        ["population_points"],
        {"population_points": {"buffer_m": 100.0}},
        target_resolution=7,
    )
    assert direct_population_area.technology == "wind"
    assert direct_population_area.active_group_ids == ("population",)
    assert len(direct_population_area.cells) == 13_735
    assert math.isclose(
        direct_population_area.model_area_km2,
        TRONDELAG_ANALYSIS_DOMAIN_AREA_KM2,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert math.isclose(
        direct_population_area.potential_pct,
        93.1071645226975,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    checks += 5

    solar_contract = load_analysis("trondelag", "solar")
    assert solar_contract.area_result is not None
    assert solar_contract.area_result.technology == "solar"
    assert solar_contract.groups == trondelag.groups
    assert tuple(solar_contract.layers) == tuple(trondelag.layers)
    assert solar_contract.analysis_domain == trondelag.analysis_domain
    direct_solar_population_area = run_area_analysis(
        "trondelag",
        "solar",
        ["population_points"],
        {"population_points": {"buffer_m": 100.0}},
        target_resolution=7,
    )
    assert direct_solar_population_area.technology == "solar"
    assert direct_solar_population_area.cells == direct_population_area.cells
    assert math.isclose(
        direct_solar_population_area.model_area_km2,
        TRONDELAG_ANALYSIS_DOMAIN_AREA_KM2,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert math.isclose(
        direct_solar_population_area.potential_pct,
        93.1071645226975,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    checks += 9

    for rollup_resolution, expected_count in ((6, 2_163), (5, 365)):
        rolled_area = run_area_analysis(
            "trondelag",
            "wind",
            ["population_points"],
            {"population_points": {"buffer_m": 100.0}},
            target_resolution=rollup_resolution,
        )
        target_areas = resolve_analysis_domain_cell_areas_km2(
            trondelag,
            rollup_resolution,
        )
        child_model: dict[str, float] = {}
        child_remaining: dict[str, float] = {}
        for cell in direct_population_area.cells:
            parent = str(h3.cell_to_parent(cell.cell_id, rollup_resolution))
            child_model[parent] = child_model.get(parent, 0.0) + cell.model_area_km2
            child_remaining[parent] = (
                child_remaining.get(parent, 0.0) + cell.remaining_area_km2
            )
        assert rolled_area.resolution == rollup_resolution
        assert len(rolled_area.cells) == expected_count
        assert set(target_areas) == {cell.cell_id for cell in rolled_area.cells}
        assert math.isclose(
            rolled_area.model_area_km2,
            math.fsum(target_areas.values()),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for cell in rolled_area.cells:
            expected_fraction = (
                child_remaining[cell.cell_id] / child_model[cell.cell_id]
            )
            assert math.isclose(
                cell.potential_pct,
                expected_fraction * 100.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                cell.remaining_area_km2,
                target_areas[cell.cell_id] * expected_fraction,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        rolled_solar_area = run_area_analysis(
            "trondelag",
            "solar",
            ["population_points"],
            {"population_points": {"buffer_m": 100.0}},
            target_resolution=rollup_resolution,
        )
        assert rolled_solar_area.technology == "solar"
        assert rolled_solar_area.cells == rolled_area.cells
        checks += 6 + expected_count * 2

    for invalid_resolution in (6.5, True, "6"):
        try:
            run_area_analysis(
                "trondelag",
                "wind",
                ["population_points"],
                {"population_points": {"buffer_m": 100.0}},
                target_resolution=invalid_resolution,
            )
        except TypeError as exc:
            assert "must be an integer" in str(exc)
        else:
            raise AssertionError(
                f"Area-result resolution {invalid_resolution!r} did not fail closed"
            )
        checks += 1

    for undeclared_resolution in (8, 4):
        try:
            run_area_analysis(
                "trondelag",
                "wind",
                ["population_points"],
                {"population_points": {"buffer_m": 100.0}},
                target_resolution=undeclared_resolution,
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"Area-result R{undeclared_resolution} did not fail closed"
            )
        checks += 1

    checks += _assert_invalid_distance_rows_fail_closed()

    print(f"Generic engine validation passed: {checks}/{checks} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
