from __future__ import annotations

import os
import sys
from pathlib import Path

import h3


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


def _roads_large_acceptance_oracle(
    registry: dict,
    threshold_m: float,
    target_resolution: int,
    target_cell_ids: set[str],
) -> dict[str, float]:
    distance = distance_table_for_layer(registry, "roads_large")
    if distance["hex_id"].astype(str).duplicated().any():
        raise ValueError("Frozen roads_large distance table has duplicate hex ids")
    ramp_end = max(threshold_m * 2.0, threshold_m + 1.0)
    rolled: dict[str, tuple[float, bool]] = {}
    for row in distance.itertuples(index=False):
        cell_id = str(row.hex_id)
        if int(h3.get_resolution(cell_id)) != 7:
            raise ValueError(f"Frozen roads_large row is not R7: {cell_id}")
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
                f"Frozen roads_large rollup is missing target cell: {cell_id}"
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

    selection = app._reference_default_wind_layer_selection()
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
                and result.get("canonical_layer_ids") == ["roads_large"]
                and abs(actual_share - expected_share) <= 1e-12,
                f"Trøndelag R{resolution} at {road_distance:.0f} m preserves "
                f"frozen full-flow output ({expected_share:.12f}%).",
                f"Trøndelag R{resolution} at {road_distance:.0f} m drifted: "
                f"expected {expected_share:.12f}%, got {actual_share:.12f}%, "
                f"canonical={((result or {}).get('canonical_layer_ids') or [])}.",
            )

    roads_large_only = {
        group_id: []
        for group_id in app.WIND_GROUP_LAYER_DEFAULTS
    }
    roads_large_only["transport"] = ["roads_large"]
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
            oracle = _roads_large_acceptance_oracle(
                trondelag_registry,
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

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
