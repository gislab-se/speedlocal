from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGIONS_ROOT = ROOT / "regions"
EXPECTED_REGION_IDS = ["bornholm", "trondelag", "skaraborg"]


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        if condition:
            self.passes.append(ok)
        else:
            self.failures.append(fail)

    def emit(self) -> int:
        print("SpeedLocal region readiness")
        print("=" * 27)
        print("\nBLOCKERS")
        if self.failures:
            for idx, failure in enumerate(self.failures, start=1):
                print(f"{idx}. FAIL {failure}")
        else:
            print("None")

        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")

        status = "FAIL" if self.failures else "PASS"
        print(f"\nRESULT: {status} ({len(self.passes)} passed, {len(self.failures)} blocker(s))")
        return 1 if self.failures else 0


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def region_ids(index: dict[str, Any]) -> list[str]:
    values = index.get("regions") or []
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            result.append(value.strip().lower())
        elif isinstance(value, dict):
            result.append(str(value.get("region_id") or "").strip().lower())
    return [value for value in result if value]


def file_fallbacks(region: dict[str, Any]) -> list[dict[str, Any]]:
    values = ((region.get("runtime") or {}).get("file_fallbacks") or [])
    return [value for value in values if isinstance(value, dict)]


def fallback_ids(region: dict[str, Any]) -> set[str]:
    return {str(value.get("id") or "") for value in file_fallbacks(region)}


def text_values(values: Any) -> str:
    if isinstance(values, list):
        return " ".join(str(value) for value in values)
    return str(values or "")


def check_shared(report: Report, region: dict[str, Any], region_id: str) -> None:
    runtime = region.get("runtime") or {}
    report.check(
        region.get("region_id") == region_id,
        f"{region_id}: region id matches package path.",
        f"{region_id}: region id mismatch: {region.get('region_id')!r}.",
    )
    report.check(
        runtime.get("backend_preference") == "postgres_then_file",
        f"{region_id}: Postgres is preferred before file fallback.",
        f"{region_id}: backend preference is not postgres_then_file.",
    )
    report.check(
        isinstance(runtime.get("database"), dict),
        f"{region_id}: database contract exists.",
        f"{region_id}: database contract is missing.",
    )
    report.check(
        isinstance(runtime.get("file_fallbacks"), list),
        f"{region_id}: file fallback list exists.",
        f"{region_id}: file fallback list is missing.",
    )


def check_bornholm(report: Report, region: dict[str, Any]) -> None:
    resolutions = [int(value) for value in region.get("available_h3_resolutions") or []]
    readiness = text_values(region.get("readiness_requirements"))
    report.check(region.get("status") == "active", "Bornholm is active.", "Bornholm is not active.")
    report.check(
        region.get("native_crs") == "EPSG:25833",
        "Bornholm uses EPSG:25833.",
        f"Bornholm native CRS is {region.get('native_crs')!r}.",
    )
    report.check(
        resolutions == [6, 7, 8, 9],
        "Bornholm exposes R6/R7/R8/R9.",
        f"Bornholm resolutions are {resolutions}, expected [6, 7, 8, 9].",
    )
    report.check(
        int(region.get("default_h3_resolution") or -1) == 9,
        "Bornholm defaults to R9 analysis.",
        f"Bornholm default H3 is {region.get('default_h3_resolution')!r}.",
    )
    ids = fallback_ids(region)
    report.check(
        {"bornholm_region_package", "bornholm_h3_display_r9", "bornholm_potential_r9"}.issubset(ids),
        "Bornholm has required file fallback placeholders.",
        f"Bornholm fallback ids are incomplete: {sorted(ids)}.",
    )
    report.check(
        "R10-derived R9 PEY" in readiness,
        "Bornholm readiness preserves R10-derived R9 PEY labelling.",
        "Bornholm readiness does not mention R10-derived R9 PEY.",
    )


def check_trondelag(report: Report, region: dict[str, Any]) -> None:
    resolutions = [int(value) for value in region.get("available_h3_resolutions") or []]
    constraints = text_values(region.get("constraints"))
    readiness = text_values(region.get("readiness_requirements"))
    report.check(region.get("status") == "active", "Trondelag is active.", "Trondelag is not active.")
    report.check(
        region.get("native_crs") == "EPSG:25832",
        "Trondelag uses EPSG:25832.",
        f"Trondelag native CRS is {region.get('native_crs')!r}.",
    )
    report.check(
        resolutions == [7, 6, 5],
        "Trondelag exposes only R7/R6/R5.",
        f"Trondelag resolutions are {resolutions}, expected [7, 6, 5].",
    )
    report.check(
        8 not in resolutions and 9 not in resolutions,
        "Trondelag R8/R9 are not exposed.",
        f"Trondelag exposes forbidden R8/R9: {resolutions}.",
    )
    report.check(
        int(region.get("default_h3_resolution") or -1) == 7,
        "Trondelag defaults to R7 analysis.",
        f"Trondelag default H3 is {region.get('default_h3_resolution')!r}.",
    )
    ids = fallback_ids(region)
    report.check(
        {"trondelag_region_package", "trondelag_h3_display_r7", "trondelag_lablab_landscape_r7"}.issubset(ids),
        "Trondelag has required file fallback placeholders.",
        f"Trondelag fallback ids are incomplete: {sorted(ids)}.",
    )
    report.check(
        "250 m" in constraints,
        "Trondelag constraints preserve 250 m population-grid proxy labelling.",
        "Trondelag constraints do not mention the 250 m population-grid proxy.",
    )
    report.check(
        "LT01-LT09" in readiness,
        "Trondelag readiness requires LT01-LT09 validation.",
        "Trondelag readiness does not require LT01-LT09 validation.",
    )


def check_skaraborg(report: Report, region: dict[str, Any]) -> None:
    card = region.get("landing_card") or {}
    report.check(region.get("status") == "planned", "Skaraborg is planned.", "Skaraborg is not planned.")
    report.check(
        card.get("enabled") is False,
        "Skaraborg landing card is disabled.",
        f"Skaraborg landing card enabled is {card.get('enabled')!r}.",
    )
    report.check(
        region.get("native_crs") == "EPSG:3006",
        "Skaraborg uses EPSG:3006 as planned Swedish CRS.",
        f"Skaraborg native CRS is {region.get('native_crs')!r}.",
    )
    report.check(
        not region.get("available_h3_resolutions"),
        "Skaraborg has no active H3 resolutions yet.",
        f"Skaraborg unexpectedly exposes H3 resolutions: {region.get('available_h3_resolutions')!r}.",
    )
    report.check(
        file_fallbacks(region) == [],
        "Skaraborg has no file fallbacks until data exists.",
        "Skaraborg has file fallbacks before data readiness.",
    )


def main() -> int:
    report = Report()
    index = load_json(REGIONS_ROOT / "index.json")
    ids = region_ids(index)
    report.check(
        ids == EXPECTED_REGION_IDS,
        f"Region index is exactly {EXPECTED_REGION_IDS}.",
        f"Unexpected region index: {ids}.",
    )
    report.check("skara" not in ids, "Legacy skara id is not indexed.", "Legacy skara id is indexed.")
    report.check("vara" not in ids, "Legacy Vara id is not indexed.", "Legacy Vara id is indexed.")

    for region_id in EXPECTED_REGION_IDS:
        region = load_json(REGIONS_ROOT / region_id / "region.json")
        check_shared(report, region, region_id)
        if region_id == "bornholm":
            check_bornholm(report, region)
        elif region_id == "trondelag":
            check_trondelag(report, region)
        elif region_id == "skaraborg":
            check_skaraborg(report, region)

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
