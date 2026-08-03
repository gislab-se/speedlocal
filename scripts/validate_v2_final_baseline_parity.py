from __future__ import annotations

import os
import sys
from pathlib import Path

import h3
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PORT_ROOT = ROOT / "apps" / "v2_port"
PORT_APPS = PORT_ROOT / "apps"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
FULL_DEFAULT_EXPECTATIONS = {
    7: {
        300.0: 6.734336366945759,
        1000.0: 6.235573178012377,
    },
    6: {
        300.0: 2.3102432732316234,
        1000.0: 2.2271300046232083,
    },
    5: {
        300.0: 0.6860021917808219,
        1000.0: 0.6860021917808219,
    },
}
ROADS_LARGE_EXPECTATIONS = {
    7: {
        300.0: (96.8838733163451, 428),
        1000.0: (95.54751146705496, 434),
    },
    6: {
        300.0: (92.23300970873787, 168),
        1000.0: (91.01944059177069, 170),
    },
    5: {
        300.0: (81.91780821917808, 66),
        1000.0: (80.8993698630137, 66),
    },
}
ROAD_MEDIUM_AND_COMBINED_EXPECTATIONS = {
    ("roads_medium",): {
        7: {
            300.0: (76.82562795777211, 3183, 34_782.45959671358),
            1000.0: (69.56854532216964, 3227, 31_517.54459863800),
        },
        6: {
            300.0: (55.016181229773466, 973, 24_111.32845244986),
            1000.0: (50.73281091077208, 975, 22_267.33676707529),
        },
        5: {
            300.0: (31.232876712328768, 251, 9_824.02466410935),
            1000.0: (29.520657534246578, 251, 9_034.54651309651),
        },
    },
    ("roads_medium", "roads_large"): {
        7: {
            300.0: (75.01274117218784, 3432, 33_957.99514111903),
            1000.0: (67.43830797233346, 3475, 30_548.72439396808),
        },
        6: {
            300.0: (52.28848821081831, 1032, 22_789.15790342790),
            1000.0: (47.87505316689782, 1034, 20_879.03706801618),
        },
        5: {
            300.0: (27.123287671232877, 266, 8_023.09983239515),
            1000.0: (25.533698630136985, 266, 7_308.52821170669),
        },
    },
}
ROADS_LARGE_R7_AREA_EXPECTATIONS = {
    300.0: (43_798.14161191527, 96.87027817735104),
    1000.0: (43_191.99545890840, 95.52963804293191),
}
ROADS_LARGE_DOWNSTREAM_EXPECTATIONS = {
    7: {
        300.0: (43_798.14161191527, 96.8838733163451),
        1000.0: (43_191.99545890840, 95.54743356388788),
    },
    6: {
        300.0: (41_463.27456688615, 92.23300970873787),
        1000.0: (40_880.86125903301, 91.01937124364309),
    },
    5: {
        300.0: (35_946.74693295628, 81.91780821917808),
        1000.0: (35_350.10859539235, 80.89917808219177),
    },
}
ROADS_LARGE_APP_ROLLUP_EXPECTATIONS = {
    300.0: {
        7: (96.8838733163451, 13_307, 428),
        6: (97.04147018030514, 2_126, 37),
        5: (97.03287671232877, 364, 1),
    },
    1000.0: {
        7: (95.54743356388788, 13_301, 434),
        6: (95.74826629680999, 2_123, 40),
        5: (95.80219178082193, 364, 1),
    },
}
TRONDELAG_MODEL_DOMAIN_AREA_KM2 = 45_213.18864360976
DISPLAY_COUNTS = {7: 13_735, 6: 2_163, 5: 365}
POPULATION_EXPECTATIONS = {
    7: {
        100.0: (84.22249588642156, 1_485, 38_119.151592087590),
        500.0: (66.11716764470330, 4_048, 29_960.271522643929),
        1000.0: (55.59792629777940, 5_203, 25_213.340431058976),
        3000.0: (29.36284590947701, 8_260, 13_350.050589430422),
    },
    6: {
        100.0: (63.16790337494221, 636, 28_522.089594840058),
        500.0: (45.22473888118354, 1_125, 20_357.789476729769),
        1000.0: (38.21757836338419, 1_244, 17_125.905968613042),
        3000.0: (20.72386372322392, 1_553, 9_041.916962610443),
    },
    5: {
        100.0: (35.02184931506849, 213, 12_878.835458336256),
        500.0: (22.30698575342466, 278, 6_930.123791379062),
        1000.0: (19.15868438356164, 289, 5_866.145655584355),
        3000.0: (12.83255305936073, 309, 3_363.591524290177),
    },
}
NATURE_EXPECTATIONS = {
    7: {
        0.0: (71.16126683654896, 3_961),
        250.0: (71.16126683654896, 3_961),
        1000.0: (70.96468875136513, 3_988),
        2000.0: (60.18929741536221, 5_468),
    },
    6: {
        0.0: (51.41007859454462, 1_051),
        250.0: (51.41007859454462, 1_051),
        1000.0: (51.08645399907536, 1_058),
        2000.0: (40.77669902912621, 1_281),
    },
    5: {
        0.0: (17.26027397260274, 302),
        250.0: (17.26027397260274, 302),
        1000.0: (17.26027397260274, 302),
        2000.0: (12.87671232876712, 318),
    },
}

for import_root in (ROOT, PORT_ROOT, PORT_APPS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import potential_app as app  # noqa: E402
from acceptance_model.layers import (  # noqa: E402
    distance_table_for_layer,
    load_registry,
)


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        (self.passes if condition else self.failures).append(
            ok if condition else fail
        )

    def emit(self) -> int:
        print("SpeedLocal V2 Final Trondelag frozen-V2 parity")
        print("=" * 50)
        print("\nBLOCKERS")
        if self.failures:
            for index, failure in enumerate(self.failures, start=1):
                print(f"{index}. FAIL {failure}")
        else:
            print("None")
        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")
        status = "FAIL" if self.failures else "PASS"
        print(
            f"\nRESULT: {status} "
            f"({len(self.passes)} passed, {len(self.failures)} blocker(s))"
        )
        return 1 if self.failures else 0


def _roads_acceptance_oracle(
    registry: dict,
    layer_ids: tuple[str, ...],
    threshold_m: float,
    target_resolution: int,
    target_cell_ids: set[str],
) -> dict[str, float]:
    ramp_end = max(threshold_m * 2.0, threshold_m + 1.0)
    rolled: dict[str, tuple[float, bool]] = {}
    for layer_id in layer_ids:
        distance = distance_table_for_layer(registry, layer_id)
        if distance["hex_id"].astype(str).duplicated().any():
            raise ValueError(
                f"Frozen {layer_id} distance table has duplicate hex ids"
            )
        for row in distance.itertuples(index=False):
            cell_id = str(row.hex_id)
            if int(h3.get_resolution(cell_id)) != 7:
                raise ValueError(
                    f"Frozen {layer_id} row is not R7: {cell_id}"
                )
            target_id = (
                cell_id
                if target_resolution == 7
                else str(h3.cell_to_parent(cell_id, target_resolution))
            )
            intersects = str(row.intersects).strip().lower() in {
                "1",
                "true",
                "yes",
            }
            value = (float(row.distance_m), intersects)
            previous = rolled.get(target_id)
            if previous is None:
                rolled[target_id] = value
            else:
                rolled[target_id] = (
                    min(previous[0], value[0]),
                    previous[1] or value[1],
                )

    oracle: dict[str, float] = {}
    for cell_id in target_cell_ids:
        if cell_id not in rolled:
            raise ValueError(
                "Frozen roads rollup is missing target cell: "
                f"{cell_id}"
            )
        distance_m, intersects = rolled[cell_id]
        if intersects:
            acceptance = 0.0
        else:
            acceptance = max(
                0.0,
                min(
                    1.0,
                    (distance_m - threshold_m)
                    / (ramp_end - threshold_m),
                ),
            )
        oracle[cell_id] = acceptance
    return oracle


def _population_acceptance_oracle(
    registry: dict,
    layer_ids: tuple[str, ...],
    threshold_m: float,
    target_resolution: int,
    target_cell_ids: set[str],
) -> dict[str, float]:
    """Reproduce frozen sparse population/settlement semantics."""
    rolled: dict[str, tuple[float, bool]] = {}
    for layer_id in layer_ids:
        distance = distance_table_for_layer(registry, layer_id)
        if distance["hex_id"].astype(str).duplicated().any():
            raise ValueError(
                f"Frozen {layer_id} distance table has duplicate hex ids"
            )
        for row in distance.itertuples(index=False):
            cell_id = str(row.hex_id)
            source_resolution = int(h3.get_resolution(cell_id))
            if source_resolution < target_resolution:
                raise ValueError(
                    f"Frozen {layer_id} row R{source_resolution} cannot "
                    f"roll up to R{target_resolution}"
                )
            target_id = (
                cell_id
                if source_resolution == target_resolution
                else str(h3.cell_to_parent(cell_id, target_resolution))
            )
            value = (
                float(row.distance_m),
                str(row.intersects).strip().lower()
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

    ramp_end = max(threshold_m * 2.0, threshold_m + 1.0)
    oracle: dict[str, float] = {}
    for cell_id in target_cell_ids:
        observation = rolled.get(cell_id)
        if observation is None:
            oracle[cell_id] = 0.0
            continue
        distance_m, intersects = observation
        oracle[cell_id] = (
            0.0
            if intersects
            else max(
                0.0,
                min(
                    1.0,
                    (distance_m - threshold_m)
                    / (ramp_end - threshold_m),
                ),
            )
        )
    return oracle


def _nature_acceptance_oracle(
    registry: dict,
    threshold_m: float,
    target_resolution: int,
    target_cell_ids: set[str],
) -> dict[str, float]:
    """Reproduce frozen protected-nature hard-exclusion semantics."""
    distance = distance_table_for_layer(registry, "protected_areas")
    rolled: dict[str, tuple[float, bool]] = {}
    for row in distance.itertuples(index=False):
        source_id = str(row.hex_id)
        target_id = (
            source_id
            if target_resolution == 7
            else str(h3.cell_to_parent(source_id, target_resolution))
        )
        value = (
            float(row.distance_m),
            str(row.intersects).strip().lower() in {"1", "true", "yes"},
        )
        previous = rolled.get(target_id)
        rolled[target_id] = value if previous is None else (
            min(previous[0], value[0]),
            previous[1] or value[1],
        )
    oracle: dict[str, float] = {}
    for cell_id in target_cell_ids:
        if cell_id not in rolled:
            raise ValueError(
                f"Frozen protected_areas is missing target cell: {cell_id}"
            )
        distance_m, intersects = rolled[cell_id]
        blocked = intersects or (
            threshold_m > 0 and distance_m <= threshold_m
        )
        oracle[cell_id] = 0.0 if blocked else 1.0
    return oracle


def main() -> int:
    report = Report()
    source_value = os.environ.get(V2_SOURCE_ROOT_ENV, "").strip()
    source_root = Path(source_value).expanduser() if source_value else None
    report.check(
        bool(source_root and source_root.is_dir()),
        "Frozen V2 source root exists.",
        f"Frozen V2 source root is unavailable: {source_root}",
    )
    if source_root is None or not source_root.is_dir():
        return report.emit()

    trondelag_region = app.load_region("trondelag")
    _, _, trondelag_registry = load_registry("trondelag")
    behavior_reference = trondelag_region.get("behavior_reference") or {}
    report.check(
        trondelag_registry.get("_runtime_strategy") == "fast_distance"
        and trondelag_registry.get("_distance_conflict_semantics")
        == "soft_ramp"
        and behavior_reference.get("status") == "authoritative"
        and behavior_reference.get("scope") == "trondelag_only"
        and behavior_reference.get("frozen_v2_parity") is True,
        "Trøndelag declares the authoritative frozen-V2 soft-distance behavior.",
        "Trøndelag frozen-V2 behavior authority or runtime strategy is invalid.",
    )

    selection = app._reference_default_wind_layer_selection("trondelag")
    report.check(
        app._wind_region_id("TrOndElAg") == "trondelag",
        "Wind helpers normalize an explicitly supplied region id.",
        "Wind helpers did not normalize an explicitly supplied region id.",
    )
    try:
        app._wind_region_id("")
    except ValueError as exc:
        report.check(
            "region id is required" in str(exc).lower(),
            "Wind helpers fail closed when neither an explicit nor active "
            "region id exists.",
            f"Wind helpers raised the wrong missing-region error: {exc}",
        )
    else:
        report.check(
            False,
            "",
            "Wind helpers still fall back to an implicit region id.",
        )
    for resolution, expectations in FULL_DEFAULT_EXPECTATIONS.items():
        for road_distance, expected_share in expectations.items():
            params = app._reference_default_wind_params()
            params["road_distance_m"] = road_distance
            result = app._wind_fast_distance_runtime_result(
                trondelag_region,
                params,
                selection,
                resolution,
            )
            actual_share = float(
                ((result or {}).get("combined") or {}).get(
                    "land_share_pct",
                    -1.0,
                )
            )
            report.check(
                result is not None
                and result.get("fast_distance") is True
                and result.get("canonical_layer_ids")
                == [
                    "population_points",
                    "protected_areas",
                    "roads_large",
                    "roads_medium",
                ]
                and abs(actual_share - expected_share) <= 1e-12,
                f"Trøndelag R{resolution} at {road_distance:.0f} m preserves "
                f"frozen full-flow output ({expected_share:.12f}%).",
                f"Trøndelag R{resolution} at {road_distance:.0f} m drifted: "
                f"expected {expected_share:.12f}%, got {actual_share:.12f}%, "
                f"canonical={((result or {}).get('canonical_layer_ids') or [])}.",
            )
    population_only = {
        group_id: []
        for group_id in app.public_wind_group_ids("trondelag")
    }
    population_only[app.WIND_POPULATION_GROUP_ID] = [
        app.WIND_POPULATION_SOURCE_LAYER_ID
    ]
    for resolution, expectations in POPULATION_EXPECTATIONS.items():
        display_geometry_path = app._h3_display_geometry_path(
            trondelag_region,
            resolution,
        )
        target_cell_ids = set(
            app.load_h3_display_geometries(display_geometry_path)
        )
        for distance_m, (
            expected_share,
            expected_zero_acceptance,
            expected_area,
        ) in expectations.items():
            params = app._reference_default_wind_params()
            params["settlement_distance_m"] = distance_m
            result = app._wind_fast_distance_runtime_result(
                trondelag_region,
                params,
                population_only,
                resolution,
            )
            frame = (
                (result or {}).get("fast_distance_frame")
                if isinstance(result, dict)
                else None
            )
            actual_share = float(
                ((result or {}).get("combined") or {}).get(
                    "land_share_pct",
                    -1.0,
                )
            )
            actual_area = (
                float(frame["potential_area_km2"].sum())
                if frame is not None
                else -1.0
            )
            actual_zero_acceptance = (
                int(frame["potential_area_share_pct"].eq(0.0).sum())
                if frame is not None
                else -1
            )
            oracle = _population_acceptance_oracle(
                trondelag_registry,
                (app.WIND_POPULATION_SOURCE_LAYER_ID,),
                distance_m,
                resolution,
                target_cell_ids,
            )
            actual_by_hex = (
                {
                    str(row.hex_id):
                    float(row.potential_area_share_pct) / 100.0
                    for row in frame.itertuples(index=False)
                }
                if frame is not None
                else {}
            )
            max_cell_error = (
                max(
                    abs(actual_by_hex[cell_id] - oracle[cell_id])
                    for cell_id in actual_by_hex
                )
                if actual_by_hex
                and actual_by_hex.keys() == oracle.keys()
                else float("inf")
            )
            report.check(
                result is not None
                and result.get("canonical_layer_ids")
                == [app.WIND_POPULATION_SOURCE_LAYER_ID]
                and frame is not None
                and len(frame) == DISPLAY_COUNTS[resolution]
                and set(frame["hex_id"].astype(str)) == target_cell_ids
                and actual_zero_acceptance == expected_zero_acceptance
                and abs(actual_share - expected_share) <= 1e-12
                and abs(actual_area - expected_area) <= 1e-9
                and max_cell_error <= 1e-12,
                f"Trøndelag population_points R{resolution} uses the "
                f"canonical sparse contract at {distance_m:.0f} m "
                f"({expected_share:.12f}%, {expected_zero_acceptance} "
                "zero-acceptance cells).",
                f"Trøndelag population_points R{resolution} drifted at "
                f"{distance_m:.0f} m: share={actual_share:.12f}, "
                f"zero={actual_zero_acceptance}, area={actual_area:.12f}, "
                f"max_cell_error={max_cell_error}, canonical="
                f"{((result or {}).get('canonical_layer_ids') or [])}.",
            )

    nature_only = {
        group_id: []
        for group_id in app.public_wind_group_ids("trondelag")
    }
    nature_only[app.WIND_NATURE_GROUP_ID] = ["protected_areas"]
    for resolution, expectations in NATURE_EXPECTATIONS.items():
        display_geometry_path = app._h3_display_geometry_path(
            trondelag_region,
            resolution,
        )
        target_cell_ids = set(
            app.load_h3_display_geometries(display_geometry_path)
        )
        for buffer_m, (expected_share, expected_blocked) in expectations.items():
            params = app._reference_default_wind_params()
            params[app.WIND_NATURE_PARAM_KEY] = buffer_m
            result = app._wind_fast_distance_runtime_result(
                trondelag_region,
                params,
                nature_only,
                resolution,
            )
            frame = (
                (result or {}).get("fast_distance_frame")
                if isinstance(result, dict)
                else None
            )
            oracle = _nature_acceptance_oracle(
                trondelag_registry,
                buffer_m,
                resolution,
                target_cell_ids,
            )
            actual = (
                {
                    str(row.hex_id):
                    float(row.potential_area_share_pct) / 100.0
                    for row in frame.itertuples(index=False)
                }
                if isinstance(frame, pd.DataFrame)
                else {}
            )
            max_cell_error = (
                max(
                    abs(actual[cell_id] - oracle[cell_id])
                    for cell_id in actual
                )
                if actual and actual.keys() == oracle.keys()
                else float("inf")
            )
            actual_share = float(
                ((result or {}).get("combined") or {}).get(
                    "land_share_pct",
                    -1.0,
                )
            )
            actual_blocked = (
                int(frame["potential_area_share_pct"].eq(0.0).sum())
                if isinstance(frame, pd.DataFrame)
                else -1
            )
            report.check(
                result is not None
                and result.get("canonical_layer_ids") == ["protected_areas"]
                and len(frame) == DISPLAY_COUNTS[resolution]
                and actual_blocked == expected_blocked
                and abs(actual_share - expected_share) <= 1e-12
                and max_cell_error <= 1e-12,
                f"Trøndelag protected_areas R{resolution} uses canonical "
                f"hard exclusion at {buffer_m:.0f} m "
                f"({expected_share:.12f}%, {expected_blocked} blocked).",
                f"Trøndelag protected_areas R{resolution} drifted at "
                f"{buffer_m:.0f} m: share={actual_share:.12f}, "
                f"blocked={actual_blocked}, max_cell_error={max_cell_error}, "
                f"canonical={((result or {}).get('canonical_layer_ids') or [])}.",
            )

    roads_large_only = {
        group_id: []
        for group_id in app.public_wind_group_ids("trondelag")
    }
    roads_large_r7_frames: dict[float, pd.DataFrame] = {}
    roads_large_only["roads"] = ["roads_large"]
    for resolution, expectations in ROADS_LARGE_EXPECTATIONS.items():
        display_geometry_path = app._h3_display_geometry_path(
            trondelag_region,
            resolution,
        )
        target_cell_ids = set(
            app.load_h3_display_geometries(display_geometry_path)
        )
        for road_distance, (
            expected_share,
            expected_blocked,
        ) in expectations.items():
            params = app._reference_default_wind_params()
            params["road_distance_m"] = road_distance
            result = app._wind_fast_distance_runtime_result(
                trondelag_region,
                params,
                roads_large_only,
                resolution,
            )
            frame = (
                (result or {}).get("fast_distance_frame")
                if isinstance(result, dict)
                else None
            )
            actual_share = float(
                ((result or {}).get("combined") or {}).get(
                    "land_share_pct",
                    -1.0,
                )
            )
            actual_blocked = (
                int(frame["potential_area_share_pct"].eq(0.0).sum())
                if frame is not None
                else -1
            )
            oracle = _roads_acceptance_oracle(
                trondelag_registry,
                ("roads_large",),
                road_distance,
                resolution,
                target_cell_ids,
            )
            actual_by_hex = (
                {
                    str(row.hex_id):
                    float(row.potential_area_share_pct) / 100.0
                    for row in frame.itertuples(index=False)
                }
                if frame is not None
                else {}
            )
            max_cell_error = (
                max(
                    abs(actual_by_hex[cell_id] - oracle[cell_id])
                    for cell_id in actual_by_hex
                )
                if actual_by_hex
                and actual_by_hex.keys() == oracle.keys()
                else float("inf")
            )
            report.check(
                result is not None
                and result.get("canonical_layer_ids") == ["roads_large"]
                and frame is not None
                and len(frame) == DISPLAY_COUNTS[resolution]
                and set(frame["hex_id"].astype(str)) == target_cell_ids
                and not frame["hex_id"].astype(str).duplicated().any()
                and actual_blocked == expected_blocked
                and abs(actual_share - expected_share) <= 1e-12
                and max_cell_error <= 1e-12,
                f"Trøndelag roads_large R{resolution} uses SpeedLocal on "
                f"{DISPLAY_COUNTS[resolution]:,} cells at "
                f"{road_distance:.0f} m ({expected_share:.12f}%, "
                f"{expected_blocked} blocked).",
                f"Trøndelag roads_large R{resolution} drifted at "
                f"{road_distance:.0f} m: share={actual_share:.12f}, "
                f"blocked={actual_blocked}, "
                f"max_cell_error={max_cell_error}, "
                f"canonical={((result or {}).get('canonical_layer_ids') or [])}.",
            )
            if frame is not None:
                if resolution == 7:
                    roads_large_r7_frames[road_distance] = frame.copy()
                model_areas = app.wind_analysis_domain_cell_areas_km2(
                    "trondelag",
                    resolution,
                )
                downstream = app._potential_establishment_source_frame(
                    frame,
                    "wind",
                    resolution,
                    resolution,
                    source_cell_areas_km2=model_areas,
                    target_cell_areas_km2=model_areas,
                )
                expected_downstream_area, expected_downstream_score = (
                    ROADS_LARGE_DOWNSTREAM_EXPECTATIONS[resolution][road_distance]
                )
                downstream_area = float(
                    downstream["wind_potential_area_km2"].sum()
                )
                downstream_score = float(
                    downstream["wind_potential_score"].mean()
                )
                report.check(
                    len(downstream) == DISPLAY_COUNTS[resolution]
                    and abs(
                        downstream_area - expected_downstream_area
                    ) <= 1e-9
                    and abs(
                        downstream_score - expected_downstream_score
                    ) <= 1e-12,
                    f"Trøndelag roads_large R{resolution} at "
                    f"{road_distance:.0f} m preserves manifest model area "
                    "in downstream establishment scoring.",
                    f"Trøndelag roads_large R{resolution} downstream drifted "
                    f"at {road_distance:.0f} m: area={downstream_area:.12f}, "
                    f"score={downstream_score:.12f}.",
                )
            if resolution == 7 and frame is not None:
                expected_area, expected_weighted_share = (
                    ROADS_LARGE_R7_AREA_EXPECTATIONS[road_distance]
                )
                actual_area = float(frame["potential_area_km2"].sum())
                actual_domain_area = float(frame["display_area_km2"].sum())
                actual_weighted_share = float(
                    ((result or {}).get("combined") or {}).get(
                        "area_weighted_land_share_pct",
                        -1.0,
                    )
                )
                report.check(
                    abs(actual_domain_area - TRONDELAG_MODEL_DOMAIN_AREA_KM2)
                    <= 1e-9
                    and abs(actual_area - expected_area) <= 1e-9
                    and abs(actual_weighted_share - expected_weighted_share)
                    <= 1e-12,
                    f"Trøndelag roads_large R7 at {road_distance:.0f} m "
                    "uses manifest-weighted model area.",
                    f"Trøndelag roads_large R7 area drifted at "
                    f"{road_distance:.0f} m: domain={actual_domain_area:.12f}, "
                    f"potential={actual_area:.12f}, "
                    f"weighted={actual_weighted_share:.12f}.",
                )

    for layer_ids, resolution_expectations in (
        ROAD_MEDIUM_AND_COMBINED_EXPECTATIONS.items()
    ):
        road_selection = {
            group_id: []
            for group_id in app.public_wind_group_ids("trondelag")
        }
        road_selection["roads"] = list(layer_ids)
        for resolution, expectations in resolution_expectations.items():
            display_geometry_path = app._h3_display_geometry_path(
                trondelag_region,
                resolution,
            )
            target_cell_ids = set(
                app.load_h3_display_geometries(display_geometry_path)
            )
            for road_distance, (
                expected_share,
                expected_blocked,
                expected_area,
            ) in expectations.items():
                params = app._reference_default_wind_params()
                params["road_distance_m"] = road_distance
                result = app._wind_fast_distance_runtime_result(
                    trondelag_region,
                    params,
                    road_selection,
                    resolution,
                )
                frame = (
                    (result or {}).get("fast_distance_frame")
                    if isinstance(result, dict)
                    else None
                )
                actual_share = float(
                    ((result or {}).get("combined") or {}).get(
                        "land_share_pct",
                        -1.0,
                    )
                )
                actual_area = (
                    float(frame["potential_area_km2"].sum())
                    if frame is not None
                    else -1.0
                )
                actual_blocked = (
                    int(frame["potential_area_share_pct"].eq(0.0).sum())
                    if frame is not None
                    else -1
                )
                oracle = _roads_acceptance_oracle(
                    trondelag_registry,
                    layer_ids,
                    road_distance,
                    resolution,
                    target_cell_ids,
                )
                actual_by_hex = (
                    {
                        str(row.hex_id):
                        float(row.potential_area_share_pct) / 100.0
                        for row in frame.itertuples(index=False)
                    }
                    if frame is not None
                    else {}
                )
                max_cell_error = (
                    max(
                        abs(actual_by_hex[cell_id] - oracle[cell_id])
                        for cell_id in actual_by_hex
                    )
                    if actual_by_hex
                    and actual_by_hex.keys() == oracle.keys()
                    else float("inf")
                )
                expected_canonical_ids = sorted(layer_ids)
                selection_label = "+".join(layer_ids)
                report.check(
                    result is not None
                    and result.get("canonical_layer_ids")
                    == expected_canonical_ids
                    and frame is not None
                    and len(frame) == DISPLAY_COUNTS[resolution]
                    and set(frame["hex_id"].astype(str)) == target_cell_ids
                    and actual_blocked == expected_blocked
                    and abs(actual_share - expected_share) <= 1e-12
                    and abs(actual_area - expected_area) <= 1e-9
                    and max_cell_error <= 1e-12,
                    f"Trøndelag {selection_label} R{resolution} uses one "
                    f"canonical SpeedLocal result at {road_distance:.0f} m "
                    f"({expected_share:.12f}%, {expected_blocked} blocked).",
                    f"Trøndelag {selection_label} R{resolution} drifted at "
                    f"{road_distance:.0f} m: share={actual_share:.12f}, "
                    f"blocked={actual_blocked}, area={actual_area:.12f}, "
                    f"max_cell_error={max_cell_error}, canonical="
                    f"{((result or {}).get('canonical_layer_ids') or [])}.",
                )

    invalid_road_request_errors: list[str] = []
    for invalid_layer_ids, expected_message in (
        ((), "at least one layer"),
        (("roads_medium", "roads_medium"), "duplicate layer ids"),
        (("roads_unknown",), "no canonical road layers"),
    ):
        try:
            app.roads_acceptance_frame(
                "trondelag",
                invalid_layer_ids,
                300.0,
                ("placeholder",),
                7,
            )
        except ValueError as exc:
            if expected_message not in str(exc):
                invalid_road_request_errors.append(str(exc))
        else:
            invalid_road_request_errors.append(
                f"{invalid_layer_ids!r} did not fail closed"
            )
    report.check(
        not invalid_road_request_errors,
        "Canonical road requests fail closed on empty, duplicate, and "
        "undeclared layer selections.",
        "Canonical road request validation drifted: "
        f"{invalid_road_request_errors}",
    )

    invalid_app_selection_errors: list[str] = []
    for invalid_layer_ids, expected_message in (
        (("roads_medium", "roads_medium"), "duplicate layer ids"),
        (("roads_unknown",), "undeclared road layers"),
        (("",), "blank layer id"),
    ):
        invalid_selection = {
            group_id: []
            for group_id in app.public_wind_group_ids("trondelag")
        }
        invalid_selection["roads"] = list(invalid_layer_ids)
        try:
            app._wind_fast_distance_runtime_result(
                trondelag_region,
                app._reference_default_wind_params(),
                invalid_selection,
                7,
            )
        except ValueError as exc:
            if expected_message not in str(exc):
                invalid_app_selection_errors.append(str(exc))
        else:
            invalid_app_selection_errors.append(
                f"{invalid_layer_ids!r} did not fail closed"
            )
    report.check(
        not invalid_app_selection_errors,
        "The V2 Final runtime rejects duplicate, blank, and undeclared raw "
        "road selections before legacy normalization.",
        "The V2 Final road-selection boundary validation drifted: "
        f"{invalid_app_selection_errors}",
    )

    invalid_population_selection_errors: list[str] = []
    for invalid_layer_ids, expected_message in (
        (("population_points", "population_points"), "duplicate layer ids"),
        (("population_unknown",), "undeclared population layers"),
        (("",), "blank layer id"),
    ):
        invalid_selection = {
            group_id: []
            for group_id in app.public_wind_group_ids("trondelag")
        }
        invalid_selection[app.WIND_POPULATION_GROUP_ID] = list(
            invalid_layer_ids
        )
        try:
            app._wind_fast_distance_runtime_result(
                trondelag_region,
                app._reference_default_wind_params(),
                invalid_selection,
                7,
            )
        except ValueError as exc:
            if expected_message not in str(exc):
                invalid_population_selection_errors.append(str(exc))
        else:
            invalid_population_selection_errors.append(
                f"{invalid_layer_ids!r} did not fail closed"
            )
    try:
        app.normalize_group_layer_map(
            {"settlement": [app.WIND_POPULATION_SOURCE_LAYER_ID]},
            "trondelag",
        )
    except ValueError as exc:
        if "Legacy settlement population selections" not in str(exc):
            invalid_population_selection_errors.append(str(exc))
    else:
        invalid_population_selection_errors.append(
            "the legacy settlement population alias did not fail closed"
        )
    report.check(
        not invalid_population_selection_errors,
        "The V2 Final runtime rejects duplicate, blank, and undeclared raw "
        "population selections and the removed settlement alias.",
        "The V2 Final population-selection boundary validation drifted: "
        f"{invalid_population_selection_errors}",
    )

    invalid_nature_selection_errors: list[str] = []
    for invalid_layer_ids, expected_message in (
        (("protected_areas", "protected_areas"), "duplicate layer ids"),
        (("nature_unknown",), "undeclared nature layers"),
        (("",), "blank layer id"),
    ):
        invalid_selection = {
            group_id: []
            for group_id in app.public_wind_group_ids("trondelag")
        }
        invalid_selection[app.WIND_NATURE_GROUP_ID] = list(
            invalid_layer_ids
        )
        try:
            app._wind_fast_distance_runtime_result(
                trondelag_region,
                app._reference_default_wind_params(),
                invalid_selection,
                7,
            )
        except ValueError as exc:
            if expected_message not in str(exc):
                invalid_nature_selection_errors.append(str(exc))
        else:
            invalid_nature_selection_errors.append(
                f"{invalid_layer_ids!r} did not fail closed"
            )
    try:
        app.normalize_group_layer_map(
            {"protected": ["protected_areas"]},
            "trondelag",
        )
    except ValueError as exc:
        if "Legacy protected nature selections" not in str(exc):
            invalid_nature_selection_errors.append(str(exc))
    else:
        invalid_nature_selection_errors.append(
            "the legacy protected nature alias did not fail closed"
        )
    report.check(
        not invalid_nature_selection_errors,
        "The V2 Final runtime rejects duplicate, blank, and undeclared raw "
        "nature selections and the removed protected alias.",
        "The V2 Final nature-selection boundary validation drifted: "
        f"{invalid_nature_selection_errors}",
    )

    original_population_distance_loader = app.distance_table_for_layer
    population_loader_calls: list[str] = []
    population_loader_results: list[dict[str, object] | None] = []
    canonical_population_ids = list(
        app.canonical_population_layer_ids("trondelag")
    )
    combined_population_result: dict[str, object] | None = None
    combined_population_error = ""
    combined_population_oracle_error = float("inf")
    try:
        def _reject_legacy_population(registry_meta, layer_id):
            normalized_layer_id = str(layer_id)
            population_loader_calls.append(normalized_layer_id)
            if normalized_layer_id in canonical_population_ids:
                raise AssertionError(
                    f"{normalized_layer_id} reached legacy distance loading"
                )
            return original_population_distance_loader(
                registry_meta,
                normalized_layer_id,
            )

        app.distance_table_for_layer = _reject_legacy_population
        for resolution in (7, 6, 5):
            population_loader_results.append(
                app._wind_fast_distance_runtime_result(
                    trondelag_region,
                    {
                        **app._reference_default_wind_params(),
                        "settlement_distance_m": 500.0,
                    },
                    population_only,
                    resolution,
                )
            )
        combined_selection = {
            group_id: []
            for group_id in app.public_wind_group_ids("trondelag")
        }
        combined_selection[app.WIND_POPULATION_GROUP_ID] = list(
            canonical_population_ids
        )
        combined_population_result = app._wind_fast_distance_runtime_result(
            trondelag_region,
            {
                **app._reference_default_wind_params(),
                "settlement_distance_m": 500.0,
            },
            combined_selection,
            7,
        )
        combined_frame = (
            combined_population_result.get("fast_distance_frame")
            if isinstance(combined_population_result, dict)
            else None
        )
        combined_target_ids = set(
            app.load_h3_display_geometries(
                app._h3_display_geometry_path(trondelag_region, 7)
            )
        )
        combined_oracle = _population_acceptance_oracle(
            trondelag_registry,
            tuple(canonical_population_ids),
            500.0,
            7,
            combined_target_ids,
        )
        combined_actual = (
            {
                str(row.hex_id): float(row.potential_area_share_pct) / 100.0
                for row in combined_frame.itertuples(index=False)
            }
            if isinstance(combined_frame, pd.DataFrame)
            else {}
        )
        if combined_actual.keys() == combined_oracle.keys():
            combined_population_oracle_error = max(
                abs(combined_actual[cell_id] - combined_oracle[cell_id])
                for cell_id in combined_actual
            )
    except Exception as exc:
        combined_population_error = str(exc)
    finally:
        app.distance_table_for_layer = original_population_distance_loader

    report.check(
        not combined_population_error
        and len(population_loader_results) == 3
        and all(
            result is not None
            and result.get("canonical_layer_ids")
            == [app.WIND_POPULATION_SOURCE_LAYER_ID]
            for result in population_loader_results
        )
        and app.WIND_POPULATION_SOURCE_LAYER_ID
        not in population_loader_calls,
        "The primary wind population filter never reaches the legacy "
        "distance loader at R7/R6/R5.",
        "The primary population filter still depends on legacy distance "
        f"loading: {combined_population_error or population_loader_calls}",
    )
    report.check(
        canonical_population_ids
        == ["population_points", "built_centre", "built_low_selection"]
        and combined_population_result is not None
        and not set(canonical_population_ids).intersection(population_loader_calls)
        and combined_population_oracle_error <= 1e-12,
        "All three manifest population sources combine canonically without "
        "losing accepted cell behavior.",
        "Combined canonical population behavior drifted: "
        f"error={combined_population_error}, "
        f"max_cell_error={combined_population_oracle_error}, "
        f"loader_calls={population_loader_calls}.",
    )

    original_nature_distance_loader = app.distance_table_for_layer
    nature_loader_calls: list[str] = []
    nature_loader_errors: list[str] = []
    nature_loader_results: list[dict[str, object] | None] = []
    try:
        def _reject_legacy_nature(registry_meta, layer_id):
            normalized_layer_id = str(layer_id)
            nature_loader_calls.append(normalized_layer_id)
            if normalized_layer_id == "protected_areas":
                raise AssertionError(
                    "protected_areas reached legacy distance loading"
                )
            return original_nature_distance_loader(
                registry_meta,
                normalized_layer_id,
            )

        app.distance_table_for_layer = _reject_legacy_nature
        for resolution in (7, 6, 5):
            nature_loader_results.append(
                app._wind_fast_distance_runtime_result(
                    trondelag_region,
                    {
                        **app._reference_default_wind_params(),
                        app.WIND_NATURE_PARAM_KEY: 1000.0,
                    },
                    nature_only,
                    resolution,
                )
            )
    except Exception as exc:
        nature_loader_errors.append(str(exc))
    finally:
        app.distance_table_for_layer = original_nature_distance_loader
    report.check(
        not nature_loader_errors
        and len(nature_loader_results) == 3
        and all(
            result is not None
            and result.get("canonical_layer_ids") == ["protected_areas"]
            for result in nature_loader_results
        )
        and "protected_areas" not in nature_loader_calls,
        "The wind nature filter never reaches the legacy distance loader at "
        "R7/R6/R5.",
        "The nature filter still depends on legacy distance loading: "
        f"{nature_loader_errors or nature_loader_calls}",
    )

    original_priority_groups = app._allocation_priority_layer_groups
    original_priority_loader = app.distance_table_for_layer
    priority_loader_calls: list[str] = []
    priority_errors: list[str] = []
    priority_max_errors: dict[int, float] = {}
    priority_specs = original_priority_groups("trondelag", "wind")
    population_priority_specs = [
        spec
        for spec in priority_specs
        if spec.get("canonical_group_id")
        == app.CANONICAL_POPULATION_GROUP_ID
    ]
    try:
        if len(population_priority_specs) != 1:
            raise AssertionError(
                "wind allocation ranking does not expose one canonical "
                "population specification"
            )
        canonical_spec = population_priority_specs[0]
        canonical_ids = [
            str(layer_id)
            for layer_id in canonical_spec.get("canonical_layer_ids", [])
        ]
        legacy_spec = dict(canonical_spec)
        legacy_spec["layer_ids"] = canonical_ids + [
            str(layer_id)
            for layer_id in canonical_spec.get("layer_ids", [])
        ]
        legacy_spec["canonical_group_id"] = None
        legacy_spec["canonical_layer_ids"] = []

        def _priority_population_guard(registry_meta, layer_id):
            normalized_layer_id = str(layer_id)
            priority_loader_calls.append(normalized_layer_id)
            if normalized_layer_id in canonical_ids:
                raise AssertionError(
                    f"{normalized_layer_id} reached legacy allocation-ranking loading"
                )
            return original_priority_loader(registry_meta, normalized_layer_id)

        for resolution in (7, 6, 5):
            domain_ids = list(
                app.wind_analysis_domain_cell_areas_km2(
                    "trondelag",
                    resolution,
                )
            )
            priority_source = pd.DataFrame(
                {
                    "hex_id": domain_ids,
                    "potential_area_share_pct": 50.0,
                    "core_score": 0.5,
                }
            )
            app._allocation_priority_layer_groups = (
                lambda _region_id, _technology, spec=legacy_spec: [spec]
            )
            legacy_priority = app._apply_landscape_priority_to_allocation_frame(
                priority_source,
                trondelag_region,
                "wind",
                resolution,
            ).sort_values("hex_id")

            app._allocation_priority_layer_groups = (
                lambda _region_id, _technology, spec=canonical_spec: [spec]
            )
            app.distance_table_for_layer = _priority_population_guard
            canonical_priority = app._apply_landscape_priority_to_allocation_frame(
                priority_source,
                trondelag_region,
                "wind",
                resolution,
            ).sort_values("hex_id")
            error_columns = (
                "landscape_priority_score",
                "allocation_priority_score",
                "technical_priority_score",
                "core_score",
            )
            priority_max_errors[resolution] = max(
                float(
                    (
                        pd.to_numeric(canonical_priority[column], errors="coerce")
                        - pd.to_numeric(legacy_priority[column], errors="coerce")
                    )
                    .abs()
                    .max()
                )
                for column in error_columns
            )
            app.distance_table_for_layer = original_priority_loader
    except Exception as exc:
        priority_errors.append(str(exc))
    finally:
        app._allocation_priority_layer_groups = original_priority_groups
        app.distance_table_for_layer = original_priority_loader

    report.check(
        not priority_errors
        and len(population_priority_specs) == 1
        and population_priority_specs[0].get("canonical_layer_ids")
        == ["population_points", "built_centre", "built_low_selection"]
        and not {
            "population_points",
            "built_centre",
            "built_low_selection",
        }.intersection(priority_loader_calls)
        and priority_max_errors.keys() == {7, 6, 5}
        and max(priority_max_errors.values(), default=float("inf")) <= 1e-12,
        "Wind allocation ranking uses canonical population distances at "
        "R7/R6/R5 without changing the accepted legacy ranking values.",
        "Population allocation ranking still depends on a legacy population "
        "loader or changed values: "
        f"errors={priority_errors}, loader_calls={priority_loader_calls}, "
        f"max_errors={priority_max_errors}.",
    )
    nature_priority_specs = [
        spec
        for spec in priority_specs
        if spec.get("canonical_group_id")
        == app.CANONICAL_NATURE_GROUP_ID
    ]
    report.check(
        len(nature_priority_specs) == 1
        and nature_priority_specs[0].get("canonical_layer_ids")
        == ["protected_areas"]
        and nature_priority_specs[0].get("layer_ids") == [],
        "Wind allocation ranking exposes protected_areas only through the "
        "canonical nature contract.",
        "Wind allocation ranking still exposes a legacy protected-nature "
        f"path: {nature_priority_specs}.",
    )

    original_population_contract = app.population_control_contract
    original_population_ids = app.canonical_population_layer_ids
    original_population_loader = app.distance_table_for_layer
    broken_contract_loader_calls: list[str] = []
    broken_contract_errors: list[str] = []
    try:
        def _missing_population_contract(_region_id):
            raise ValueError("wind has no population ui descriptor")

        def _record_broken_contract_loader(registry_meta, layer_id):
            broken_contract_loader_calls.append(str(layer_id))
            return original_population_loader(registry_meta, layer_id)

        app.population_control_contract = _missing_population_contract
        app.distance_table_for_layer = _record_broken_contract_loader
        try:
            app._wind_fast_distance_runtime_result(
                trondelag_region,
                app._reference_default_wind_params(),
                population_only,
                7,
            )
        except ValueError as exc:
            broken_contract_errors.append(str(exc))
        else:
            broken_contract_errors.append(
                "broken population contract did not fail"
            )
        try:
            app._wind_control_groups("trondelag")
        except ValueError as exc:
            broken_contract_errors.append(str(exc))
        else:
            broken_contract_errors.append(
                "broken population controls did not fail"
            )
        try:
            app._allocation_priority_layer_groups("trondelag", "wind")
        except ValueError as exc:
            broken_contract_errors.append(str(exc))
        else:
            broken_contract_errors.append(
                "broken population allocation ranking did not fail"
            )
    finally:
        app.population_control_contract = original_population_contract
        app.distance_table_for_layer = original_population_loader
    report.check(
        len(broken_contract_errors) == 3
        and all(
            "no population ui descriptor" in message
            for message in broken_contract_errors
        )
        and not broken_contract_loader_calls,
        "A broken migrated population UI contract fails closed before any "
        "legacy distance loading.",
        "A broken population UI contract reopened the legacy path: "
        f"errors={broken_contract_errors}, "
        f"loader_calls={broken_contract_loader_calls}.",
    )

    try:
        def _missing_population_layers(_region_id):
            raise ValueError(
                "wind declares no canonical population layers"
            )

        app.canonical_population_layer_ids = _missing_population_layers
        try:
            app.normalize_group_layer_map(
                population_only,
                "trondelag",
            )
        except ValueError as exc:
            missing_layer_error = str(exc)
        else:
            missing_layer_error = ""
    finally:
        app.canonical_population_layer_ids = original_population_ids
    report.check(
        "declares no canonical population layers" in missing_layer_error,
        "A missing migrated population layer contract fails during selection "
        "normalization.",
        "A missing canonical population layer was reclassified as legacy.",
    )

    legacy_distance_loader = app.distance_table_for_layer
    canonical_coverage_results: dict[
        tuple[tuple[str, ...], int],
        dict | None,
    ] = {}
    try:
        def _reject_legacy_road_distance(*_args, **_kwargs):
            raise AssertionError("Road selection reached legacy distance loading")

        app.distance_table_for_layer = _reject_legacy_road_distance
        for selected_road_layers in (
            ("roads_medium",),
            ("roads_medium", "roads_large"),
        ):
            for resolution in (7, 6, 5):
                canonical_coverage_results[
                    (selected_road_layers, resolution)
                ] = app._wind_fast_distance_runtime_result(
                    trondelag_region,
                    {
                        **app._reference_default_wind_params(),
                        "road_distance_m": 300.0,
                    },
                    {
                        **{
                            group_id: []
                            for group_id in app.public_wind_group_ids("trondelag")
                        },
                        "roads": list(selected_road_layers),
                    },
                    resolution,
                )
        canonical_only_result = canonical_coverage_results[
            (("roads_medium", "roads_large"), 7)
        ]
        reversed_result = app._wind_fast_distance_runtime_result(
            trondelag_region,
            {**app._reference_default_wind_params(), "road_distance_m": 300.0},
            {
                **{
                    group_id: []
                    for group_id in app.public_wind_group_ids("trondelag")
                },
                "roads": ["roads_large", "roads_medium"],
            },
            7,
        )
    except Exception as exc:
        canonical_only_result = None
        reversed_result = None
        canonical_coverage_results = {}
        canonical_only_error = str(exc)
    else:
        canonical_only_error = ""
    finally:
        app.distance_table_for_layer = legacy_distance_loader
    canonical_frame = (
        canonical_only_result.get("fast_distance_frame")
        if isinstance(canonical_only_result, dict)
        else None
    )
    reversed_frame = (
        reversed_result.get("fast_distance_frame")
        if isinstance(reversed_result, dict)
        else None
    )
    complete_canonical_coverage = all(
        result is not None
        and result.get("canonical_layer_ids") == sorted(layer_ids)
        for (layer_ids, _resolution), result
        in canonical_coverage_results.items()
    ) and len(canonical_coverage_results) == 6
    report.check(
        complete_canonical_coverage,
        "Trøndelag road selections do not fall through to the legacy "
        "distance loader at R7/R6/R5.",
        "Trøndelag roads still depend on the legacy distance loader: "
        f"{canonical_only_error}",
    )
    report.check(
        reversed_result is not None
        and reversed_result.get("canonical_layer_ids")
        == ["roads_large", "roads_medium"]
        and isinstance(canonical_frame, pd.DataFrame)
        and isinstance(reversed_frame, pd.DataFrame)
        and canonical_frame[["hex_id", "potential_area_share_pct"]].equals(
            reversed_frame[["hex_id", "potential_area_share_pct"]]
        ),
        "Canonical combined roads are invariant to selected-layer order.",
        "Canonical combined roads changed with selected-layer order.",
    )

    for road_distance, source_frame in roads_large_r7_frames.items():
        expected_area = ROADS_LARGE_R7_AREA_EXPECTATIONS[road_distance][0]
        for resolution, (
            expected_score,
            expected_wind_only,
            expected_not_suitable,
        ) in ROADS_LARGE_APP_ROLLUP_EXPECTATIONS[road_distance].items():
            downstream = app._combined_potential_establishment_frame(
                trondelag_region,
                source_frame,
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
                resolution,
                7,
            )
            score = float(downstream["wind_potential_score"].mean())
            area = float(downstream["wind_potential_area_km2"].sum())
            domain_area = float(downstream["wind_model_area_km2"].sum())
            classes = downstream["establishment_class"].value_counts()
            report.check(
                len(downstream) == DISPLAY_COUNTS[resolution]
                and abs(area - expected_area) <= 1e-9
                and abs(domain_area - TRONDELAG_MODEL_DOMAIN_AREA_KM2) <= 1e-9
                and abs(score - expected_score) <= 1e-12
                and int(classes.get("wind_only", 0)) == expected_wind_only
                and int(classes.get("not_suitable", 0))
                == expected_not_suitable,
                f"Trøndelag roads_large R7 at {road_distance:.0f} m "
                f"rolls to R{resolution} with manifest-area scoring and "
                "area-weighted class dominance.",
                f"Trøndelag roads_large R7→R{resolution} establishment "
                f"drifted at {road_distance:.0f} m: area={area:.12f}, "
                f"domain={domain_area:.12f}, score={score:.12f}, "
                f"classes={classes.to_dict()}.",
            )

    r7_model_areas = app.wind_analysis_domain_cell_areas_km2(
        "trondelag",
        7,
    )
    unfiltered_wind = pd.DataFrame(
        {
            "hex_id": list(r7_model_areas),
            "potential_area_share_pct": 100.0,
            "potential_area_km2": list(r7_model_areas.values()),
            "wind_hard_exclusion_intersects": False,
        }
    )
    unfiltered_rollups_valid = True
    unfiltered_rollup_details: list[str] = []
    for resolution in DISPLAY_COUNTS:
        downstream = app._combined_potential_establishment_frame(
            trondelag_region,
            unfiltered_wind,
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            resolution,
            7,
        )
        area = float(downstream["wind_potential_area_km2"].sum())
        scores = pd.to_numeric(
            downstream["wind_potential_score"],
            errors="coerce",
        )
        suitable = downstream["wind_suitable"].fillna(False).astype(bool)
        valid = (
            len(downstream) == DISPLAY_COUNTS[resolution]
            and abs(area - TRONDELAG_MODEL_DOMAIN_AREA_KM2) <= 1e-9
            and bool(scores.eq(100.0).all())
            and bool(suitable.all())
        )
        unfiltered_rollups_valid = unfiltered_rollups_valid and valid
        unfiltered_rollup_details.append(
            f"R{resolution}: cells={len(downstream)}, area={area:.12f}, "
            f"score_min={float(scores.min()):.1f}, "
            f"score_max={float(scores.max()):.1f}"
        )
    report.check(
        unfiltered_rollups_valid,
        "Unfiltered R7 wind remains 100% through the actual R7/R6/R5 "
        "establishment rollup path.",
        "Unfiltered downstream wind lost manifest-area semantics: "
        + "; ".join(unfiltered_rollup_details),
    )

    tooltip_hex_ids = list(r7_model_areas)[:3]
    tooltip_frame = pd.DataFrame(
        {
            "hex_id": tooltip_hex_ids,
            "establishment_class": [
                "solar_only",
                "wind_and_solar",
                "wind_only",
            ],
            "establishment_label": [
                "Endast sol",
                "Vind och sol",
                "Endast vind",
            ],
            "wind_suitable": [False, True, True],
            "solar_suitable": [True, True, False],
            "wind_potential_score": [0.0, 17.4, 100.0],
            "solar_potential_score": [100.0, 82.6, 0.0],
        }
    )
    tooltip_features = app._combined_establishment_feature_collection(
        tooltip_frame,
        app._h3_display_geometry_path(trondelag_region, 7),
        7,
    ).get("features", [])
    tooltip_bodies = [
        str((feature.get("properties") or {}).get("tooltip_body") or "")
        for feature in tooltip_features
    ]
    tooltip_properties = [
        feature.get("properties") or {}
        for feature in tooltip_features
    ]
    report.check(
        tooltip_bodies
        == [
            "Vindpotential: 0 % · Solpotential: 100 %",
            "Vindpotential: 17 % · Solpotential: 83 %",
            "Vindpotential: 100 % · Solpotential: 0 %",
        ]
        and all(
            "wind_potential_score" not in properties
            and "solar_potential_score" not in properties
            for properties in tooltip_properties
        ),
        "Combined-potential hover reuses the client-side tooltip with compact "
        "integer wind/solar percentages and no duplicate numeric properties.",
        "Combined-potential hover or payload drifted: "
        f"bodies={tooltip_bodies}, keys="
        f"{[sorted(properties) for properties in tooltip_properties]}.",
    )

    allocation_source = pd.DataFrame(
        {
            "hex_id": ["cell-small", "cell-large"],
            "potential_area_share_pct": [100.0, 100.0],
            "potential_area_km2": [1.0, 3.0],
            "display_area_km2": [1.0, 3.0],
            "core_score": [1.0, 0.9],
            "zone_size": [2, 2],
        }
    )
    allocated, allocation_stats = app.allocate_wind_area_from_core_hexes(
        allocation_source,
        4.0,
        999.0,
        cell_area_column="display_area_km2",
    )
    report.check(
        len(allocated) == 2
        and bool(allocated["allocated_hex_share_pct"].eq(100.0).all())
        and abs(float(allocated["allocated_area_km2"].sum()) - 4.0) <= 1e-12
        and abs(
            float(allocation_stats["selected_hex_footprint_km2"]) - 4.0
        ) <= 1e-12
        and int(allocation_stats["needed_hex"]) == 2,
        "Wind allocation uses each manifest model-cell area for percentage, "
        "footprint, and cell-count statistics.",
        "Wind allocation fell back to the supplied global H3 sentinel: "
        f"shares={allocated.get('allocated_hex_share_pct', pd.Series()).tolist()}, "
        f"stats={allocation_stats}.",
    )

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
