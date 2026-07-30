from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORT_ROOT = ROOT / "apps" / "v2_port"
PORT_APPS = PORT_ROOT / "apps"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"

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
) -> dict[str, float]:
    distance = distance_table_for_layer(registry, "roads_large")
    if distance["hex_id"].astype(str).duplicated().any():
        raise ValueError("Frozen roads_large distance table has duplicate hex ids")
    ramp_end = max(threshold_m * 2.0, threshold_m + 1.0)
    oracle: dict[str, float] = {}
    for row in distance.itertuples(index=False):
        cell_id = str(row.hex_id)
        intersects = str(row.intersects).strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if intersects:
            acceptance = 0.0
        else:
            acceptance = max(
                0.0,
                min(
                    1.0,
                    (float(row.distance_m) - threshold_m)
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
    for road_distance, expected_share in (
        (300.0, 6.734336366945759),
        (1000.0, 6.235573178012377),
    ):
        params = app._reference_default_wind_params()
        params["road_distance_m"] = road_distance
        result = app._wind_fast_distance_runtime_result(
            trondelag_region,
            params,
            selection,
            7,
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
            and abs(actual_share - expected_share) <= 1e-12,
            f"Trøndelag {road_distance:.0f} m preserves frozen fast-distance "
            f"output ({expected_share:.12f}%).",
            f"Trøndelag {road_distance:.0f} m drifted: "
            f"expected {expected_share:.12f}%, got {actual_share:.12f}%.",
        )

    roads_large_only = {
        group_id: []
        for group_id in app.WIND_GROUP_LAYER_DEFAULTS
    }
    roads_large_only["transport"] = ["roads_large"]
    for road_distance, expected_share, expected_blocked in (
        (300.0, 96.8838733163451, 428),
        (1000.0, 95.54751146705496, 434),
    ):
        params = app._reference_default_wind_params()
        params["road_distance_m"] = road_distance
        result = app._wind_fast_distance_runtime_result(
            trondelag_region,
            params,
            roads_large_only,
            7,
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
        )
        actual_by_hex = (
            {
                str(row.hex_id): float(row.potential_area_share_pct) / 100.0
                for row in frame.itertuples(index=False)
            }
            if frame is not None
            else {}
        )
        expected_by_hex = {
            cell_id: oracle[cell_id]
            for cell_id in actual_by_hex
            if cell_id in oracle
        }
        max_cell_error = (
            max(
                abs(actual_by_hex[cell_id] - expected_by_hex[cell_id])
                for cell_id in actual_by_hex
            )
            if actual_by_hex
            and actual_by_hex.keys() == expected_by_hex.keys()
            else float("inf")
        )
        report.check(
            result is not None
            and result.get("canonical_layer_ids") == ["roads_large"]
            and frame is not None
            and len(frame) == 13735
            and not frame["hex_id"].astype(str).duplicated().any()
            and actual_blocked == expected_blocked
            and abs(actual_share - expected_share) <= 1e-12
            and max_cell_error <= 1e-12,
            f"TrÃ¸ndelag roads_large R7 uses SpeedLocal on 13,735 cells "
            f"at {road_distance:.0f} m ({expected_share:.12f}%, "
            f"{expected_blocked} blocked).",
            f"TrÃ¸ndelag roads_large R7 drifted at {road_distance:.0f} m: "
            f"share={actual_share:.12f}, blocked={actual_blocked}, "
            f"max_cell_error={max_cell_error}, "
            f"canonical={((result or {}).get('canonical_layer_ids') or [])}.",
        )

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
