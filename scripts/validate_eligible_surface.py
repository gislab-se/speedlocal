from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal.area_result import run_area_analysis
from speedlocal.catalogs import load_analysis
from speedlocal.sources import (
    eligible_surface_contract_for_analysis,
    resolve_analysis_domain_cell_areas_km2,
    resolve_eligible_surface_cell_areas_km2,
    resolve_eligible_surface_path,
)
from speedlocal.validation import validate_contract


ELIGIBLE_AREA_KM2 = 41_826.93063562673
FULL_DOMAIN_AREA_KM2 = 45_213.18864360976
COASTAL_CELL = "870833c35ffffff"
COASTAL_ELIGIBLE_AREA_KM2 = 0.001293899509


def _artifact_feature(path: Path, cell_id: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise AssertionError(f"Eligible-surface artifact is invalid: {path}")
    matches = [
        feature
        for feature in features
        if str((feature.get("properties") or {}).get("hex_id")) == cell_id
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected exactly one feature for {cell_id}, got {len(matches)}"
        )
    return matches[0]


def main() -> int:
    wind = load_analysis("trondelag", "wind")
    solar = load_analysis("trondelag", "solar")
    validate_contract(wind)
    validate_contract(solar)

    wind_surface = eligible_surface_contract_for_analysis(wind)
    solar_surface = eligible_surface_contract_for_analysis(solar)
    assert wind.area_result is not None
    assert solar.area_result is not None
    assert wind.area_result.denominator == "eligible_surface"
    assert solar.area_result.denominator == "eligible_surface"
    assert wind.area_result.eligible_surface_id == "onshore_land"
    assert solar.area_result.eligible_surface_id == "onshore_land"
    assert wind_surface == solar_surface
    assert wind_surface.surface_scope == "onshore_land"
    assert wind_surface.water_policy == "exclude_sea_retain_inland_water"
    assert wind_surface.outside_region_policy == "exclude"

    full_areas = resolve_analysis_domain_cell_areas_km2(wind, 7)
    eligible_by_resolution = {
        resolution: resolve_eligible_surface_cell_areas_km2(wind, resolution)
        for resolution in (7, 6, 5)
    }
    assert len(full_areas) == 13_735
    assert math.isclose(
        math.fsum(full_areas.values()),
        FULL_DOMAIN_AREA_KM2,
        rel_tol=0.0,
        abs_tol=1e-9,
    )
    assert {resolution: len(areas) for resolution, areas in eligible_by_resolution.items()} == {
        7: 13_735,
        6: 2_163,
        5: 365,
    }
    assert all(
        math.isclose(
            math.fsum(areas.values()),
            ELIGIBLE_AREA_KM2,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for areas in eligible_by_resolution.values()
    )
    assert math.isclose(
        math.fsum(full_areas.values())
        - math.fsum(eligible_by_resolution[7].values()),
        3_386.2580079830805,
        rel_tol=0.0,
        abs_tol=1e-9,
    )

    eligible_r7 = eligible_by_resolution[7]
    shares = {
        cell_id: eligible_r7[cell_id] / full_area
        for cell_id, full_area in full_areas.items()
    }
    assert sum(value < 0.5 for value in shares.values()) == 970
    assert sum(value < 0.1 for value in shares.values()) == 283
    assert min(shares, key=shares.get) == COASTAL_CELL
    assert math.isclose(
        eligible_r7[COASTAL_CELL],
        COASTAL_ELIGIBLE_AREA_KM2,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    r7_path = resolve_eligible_surface_path(wind, 7)
    coastal_feature = _artifact_feature(r7_path, COASTAL_CELL)
    properties = coastal_feature["properties"]
    assert isinstance(properties, dict)
    assert properties["surface_id"] == "onshore_land"
    assert properties["geometry_status"] == "eligible_surface_intersection"
    assert math.isclose(
        float(properties["eligible_area_m2"]),
        COASTAL_ELIGIBLE_AREA_KM2 * 1_000_000.0,
        rel_tol=0.0,
        abs_tol=1e-6,
    )

    for technology in ("wind", "solar"):
        unfiltered = run_area_analysis(
            "trondelag",
            technology,
            (),
            {},
            target_resolution=7,
        )
        population = run_area_analysis(
            "trondelag",
            technology,
            ("population_points",),
            {"population_points": {"buffer_m": 100.0}},
            target_resolution=7,
        )
        assert math.isclose(
            unfiltered.model_area_km2,
            ELIGIBLE_AREA_KM2,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        assert unfiltered.potential_pct == 100.0
        assert math.isclose(
            population.remaining_area_km2,
            38_872.46616699324,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        assert math.isclose(
            population.potential_pct,
            92.93645404112695,
            rel_tol=0.0,
            abs_tol=1e-9,
        )

    tampered_surface = replace(wind_surface, sha256="0" * 64)
    tampered = replace(
        wind,
        eligible_surfaces={"onshore_land": tampered_surface},
    )
    try:
        resolve_eligible_surface_path(tampered, 7)
    except ValueError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("A checksum-drifted eligible surface did not fail closed")

    print(
        "Eligible-surface validation passed: onshore wind/solar use "
        "41,826.930636 km2 at R7/R6/R5; 3,386.258008 km2 of full coastal "
        "cells are excluded while canonical group metrics remain separate."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
