from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
V2_PORT = ROOT / "apps" / "v2_port"
V2_APPS = V2_PORT / "apps"
for path in (ROOT, V2_PORT, V2_APPS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import potential_app as app
from potential_model.energy_modeling import allocate_wind_area_from_core_hexes


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        (self.passes if condition else self.failures).append(
            ok if condition else fail
        )

    def emit(self) -> int:
        print("SpeedLocal allocation-adapter validation")
        print("=" * 40)
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


def _selected_signature(frame: pd.DataFrame) -> list[tuple[object, ...]]:
    return [
        (
            str(row.hex_id),
            int(row.selected_rank),
            round(float(row.potential_area_km2), 12),
            round(float(row.allocated_area_km2), 12),
            round(float(row.allocated_hex_share_pct), 12),
            round(float(row.remaining_area_after_km2), 12),
        )
        for row in frame.itertuples(index=False)
    ]


def _stats_signature(stats: dict[str, object]) -> tuple[float, float, int, float]:
    return (
        round(float(stats["selected_area_km2"]), 12),
        round(float(stats["unmet_area_km2"]), 12),
        int(stats["selected_hex_count"]),
        round(float(stats["available_candidate_area_km2"]), 12),
    )


def main() -> int:
    report = Report()
    wind_source = pd.DataFrame(
        {
            "hex_id": ["b", "a", "c"],
            "potential_area_share_pct": [80.0, 100.0, 80.0],
            "potential_area_km2": [0.6, 0.4, 0.5],
            "display_area_km2": [0.6, 0.4, 0.5],
            "core_score": [0.8, 1.0, 0.8],
            "zone_size": [2, 2, 2],
        }
    )
    wind, wind_stats = allocate_wind_area_from_core_hexes(
        wind_source,
        0.9,
        999.0,
        cell_area_column="display_area_km2",
    )
    expected = [
        ("a", 1, 0.4, 0.4, 100.0, 0.5),
        ("b", 2, 0.6, 0.5, 83.333333333333, 0.0),
    ]
    report.check(
        _selected_signature(wind) == expected
        and _stats_signature(wind_stats) == (0.9, 0.0, 2, 1.5)
        and math.isclose(
            float(wind_stats["selected_potential_area_km2"]),
            1.0,
            abs_tol=1e-12,
        )
        and math.isclose(
            float(wind_stats["selected_hex_footprint_km2"]),
            1.0,
            abs_tol=1e-12,
        ),
        "Wind adapter preserves ordered rows, partial final cell, and legacy statistics.",
        f"Wind inside-potential adapter drifted: rows={_selected_signature(wind)}, stats={wind_stats}.",
    )

    reversed_wind, reversed_wind_stats = allocate_wind_area_from_core_hexes(
        wind_source.iloc[::-1].reset_index(drop=True),
        0.9,
        999.0,
        cell_area_column="display_area_km2",
    )
    report.check(
        _selected_signature(reversed_wind) == expected
        and _stats_signature(reversed_wind_stats)
        == _stats_signature(wind_stats),
        "Wind adapter is independent of source row order.",
        "Wind adapter changed under reversed source rows.",
    )

    reserved_source = pd.DataFrame(
        {
            "hex_id": ["reserved-high", "separate", "reserved-tie"],
            "potential_area_share_pct": [100.0, 100.0, 100.0],
            "potential_area_km2": [0.5, 0.5, 0.5],
            "display_area_km2": [0.5, 0.5, 0.5],
            "core_score": [1.0, 0.9, 0.9],
            "zone_size": [1, 1, 1],
        }
    )
    reserved, _ = allocate_wind_area_from_core_hexes(
        reserved_source,
        1.0,
        999.0,
        avoid_hex_ids={"reserved-high", "reserved-tie"},
        cell_area_column="display_area_km2",
    )
    report.check(
        reserved["hex_id"].astype(str).tolist()
        == ["reserved-high", "separate"],
        "Wind adapter preserves higher-ranked co-use and separate-cell tie preference.",
        f"Wind overlap order drifted: {reserved['hex_id'].tolist()}.",
    )

    solar_source = pd.DataFrame(
        {
            "hex_id": ["b", "a", "c"],
            "solar_score": [80.0, 100.0, 80.0],
            "potential_area_km2": [0.6, 0.4, 0.5],
            "display_area_km2": [0.6, 0.4, 0.5],
        }
    )
    solar, solar_stats = app._solar_establishment_frame(
        {},
        solar_source,
        0.9,
        0.09,
        10.0,
        999.0,
        None,
    )
    report.check(
        _selected_signature(solar) == expected
        and _stats_signature(solar_stats) == (0.9, 0.0, 2, 1.5)
        and math.isclose(
            float(solar["allocated_twh"].sum()),
            0.09,
            abs_tol=1e-12,
        ),
        "Solar adapter preserves ordered rows and statistics while using per-cell eligible shares.",
        f"Solar inside-potential adapter drifted: rows={_selected_signature(solar)}, stats={solar_stats}.",
    )

    reversed_solar, reversed_solar_stats = app._solar_establishment_frame(
        {},
        solar_source.iloc[::-1].reset_index(drop=True),
        0.9,
        0.09,
        10.0,
        999.0,
        None,
    )
    report.check(
        _selected_signature(reversed_solar) == expected
        and _stats_signature(reversed_solar_stats)
        == _stats_signature(solar_stats),
        "Solar adapter is independent of source row order.",
        "Solar adapter changed under reversed source rows.",
    )

    zero_solar, zero_solar_stats = app._solar_establishment_frame(
        {},
        solar_source,
        0.0,
        0.0,
        10.0,
        999.0,
        None,
    )
    report.check(
        zero_solar.empty
        and float(zero_solar_stats["selected_area_km2"]) == 0.0
        and float(zero_solar_stats["unmet_area_km2"]) == 0.0,
        "Solar zero demand creates no phantom allocation or shortage.",
        f"Solar zero demand drifted: rows={len(zero_solar)}, stats={zero_solar_stats}.",
    )

    try:
        app._solar_establishment_frame(
            {},
            solar_source.drop(columns=["display_area_km2"]),
            0.9,
            0.09,
            10.0,
            999.0,
            None,
        )
    except ValueError as exc:
        missing_eligible_closed = "eligible" in str(exc)
    else:
        missing_eligible_closed = False
    report.check(
        missing_eligible_closed,
        "Solar allocation fails closed without per-cell eligible area.",
        "Solar allocation accepted a theoretical-H3 fallback.",
    )
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
