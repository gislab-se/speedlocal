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
                == ["roads_large", "roads_medium"]
                and abs(actual_share - expected_share) <= 1e-12,
                f"Trøndelag R{resolution} at {road_distance:.0f} m preserves "
                f"frozen full-flow output ({expected_share:.12f}%).",
                f"Trøndelag R{resolution} at {road_distance:.0f} m drifted: "
                f"expected {expected_share:.12f}%, got {actual_share:.12f}%, "
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
