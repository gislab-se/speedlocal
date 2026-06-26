from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REGIONS = ["bornholm", "trondelag", "skaraborg"]
FORBIDDEN_PATHS = [
    "R",
    "script",
    "apps/gc4",
    "apps/solochvind",
    "MIGRATION_PLAN.md",
]
REQUIRED_PATHS = [
    "README.md",
    ".github/workflows/pages.yml",
    "app.py",
    "requirements.txt",
    "site/landskapspotential/index.html",
    "apps/landskapspotential/app.py",
    "apps/landskapspotential/catalog.py",
    "apps/landskapspotential/file_runtime.py",
    "regions/index.json",
    "db/init/001_runtime_base.sql",
    "db/init/002_runtime_catalog_contract.sql",
    "scripts/validate_static_site.py",
    "scripts/validate_region_readiness.py",
    "scripts/validate_trondelag_runtime_sources.py",
    "scripts/validate_file_runtime_summary.py",
    "scripts/prepare_trondelag_runtime_metadata.py",
    "docs/SPEEDLOCAL_SLIMDOWN_5_DAY_PLAN.md",
    "docs/SPEEDLOCAL_COPY_LIST.md",
    "docs/SPEEDLOCAL_RUNTIME_IMPORT_PLAN.md",
]


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
        print("SpeedLocal delivery repo validation")
        print("=" * 36)
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


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def region_ids(index: dict) -> list[str]:
    values = index.get("regions") or []
    ids: list[str] = []
    for item in values:
        ids.append(str(item.get("region_id") if isinstance(item, dict) else item).lower())
    return ids


def main() -> int:
    report = Report()

    for path in REQUIRED_PATHS:
        report.check((ROOT / path).exists(), f"Required path exists: {path}", f"Missing required path: {path}")

    for path in FORBIDDEN_PATHS:
        report.check(not (ROOT / path).exists(), f"Legacy path removed: {path}", f"Legacy path remains: {path}")

    index = load_json(ROOT / "regions" / "index.json")
    ids = region_ids(index)
    report.check(ids == EXPECTED_REGIONS, f"Region index is exactly {EXPECTED_REGIONS}.", f"Unexpected region index: {ids}")
    report.check("vara" not in ids, "Legacy Vara region is not exposed.", "Legacy Vara region is exposed.")

    for region_id in EXPECTED_REGIONS:
        region = load_json(ROOT / "regions" / region_id / "region.json")
        report.check(region.get("region_id") == region_id, f"{region_id}: manifest id matches.", f"{region_id}: manifest id mismatch.")
        runtime = region.get("runtime") or {}
        report.check(
            runtime.get("backend_preference") == "postgres_then_file",
            f"{region_id}: backend preference is postgres_then_file.",
            f"{region_id}: backend preference is not postgres_then_file.",
        )
        report.check("file_fallbacks" in runtime, f"{region_id}: file fallback contract exists.", f"{region_id}: file fallback contract missing.")

    trondelag = load_json(ROOT / "regions" / "trondelag" / "region.json")
    trondelag_res = [int(value) for value in trondelag.get("available_h3_resolutions") or []]
    report.check(trondelag_res == [7, 6, 5], "Trondelag exposes only R7/R6/R5.", f"Trondelag resolutions are {trondelag_res}.")
    report.check(8 not in trondelag_res and 9 not in trondelag_res, "Trondelag R8/R9 are not exposed.", "Trondelag exposes R8/R9.")

    skaraborg = load_json(ROOT / "regions" / "skaraborg" / "region.json")
    report.check(skaraborg.get("status") == "planned", "Skaraborg is planned/disabled.", "Skaraborg is not marked planned.")

    large_files = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and path.stat().st_size > 1_500_000
    ]
    report.check(not large_files, "No large runtime artifacts are checked into the delivery skeleton.", f"Large files remain: {large_files[:5]}")

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
