from __future__ import annotations

import json
import subprocess
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
    "tmp",
    "artifacts",
    "data/runtime/generated",
    "data/runtime/mounted",
]
REQUIRED_PATHS = [
    "README.md",
    ".github/workflows/pages.yml",
    "app.py",
    "status_app.py",
    "requirements.txt",
    "speedlocal/runtime_bundle.py",
    "data/runtime/manifests/trondelag/v2-final-runtime-r7-2026-07-30.1.json",
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
    "scripts/validate_v2_port_guardrails.py",
    "scripts/validate_v2_source_adapter.py",
    "scripts/validate_v2_port_app.py",
    "scripts/validate_v2_final_baseline_parity.py",
    "scripts/validate_bornholm_v2_diagnostics.py",
    "scripts/validate_generic_engine.py",
    "scripts/validate_frozen_v2_reference.py",
    "scripts/validate_runtime_bundle.py",
    "scripts/build_v2_runtime_bundle.py",
    "scripts/prepare_trondelag_runtime_metadata.py",
    "AGENTS.md",
    "docs/README.md",
    "docs/GENERAL_PROGRAM_PLAN.md",
    "docs/DELIVERY_PLAN.md",
    "docs/DAILY_WORKFLOW.md",
    "docs/daily/2026-07-29.md",
    "docs/daily/2026-07-30.md",
    "docs/slices/roads.md",
    "docs/REPO_HYGIENE.md",
    "docs/FROZEN_V2_REFERENCE.md",
    "docs/frozen_v2_reference.json",
]
RELEASE_CRITICAL_TRACKED_PATHS = [
    "app.py",
    "speedlocal/runtime_bundle.py",
    "data/runtime/manifests/trondelag/v2-final-runtime-r7-2026-07-30.1.json",
    "scripts/build_v2_runtime_bundle.py",
    "scripts/validate_runtime_bundle.py",
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

    tracked_result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    tracked_paths = {
        value.decode("utf-8")
        for value in tracked_result.stdout.split(b"\0")
        if value
    }
    for path in RELEASE_CRITICAL_TRACKED_PATHS:
        report.check(
            path in tracked_paths,
            f"Release-critical path is tracked: {path}",
            f"Release-critical path is not tracked: {path}",
        )

    root_entrypoint = (ROOT / "app.py").read_text(encoding="utf-8")
    report.check(
        'V2_FINAL_ENTRYPOINT = ROOT / "apps" / "v2_port" / "app.py"' in root_entrypoint,
        "Root Streamlit entrypoint launches the V2 Final monolith.",
        "Root Streamlit entrypoint does not launch the V2 Final monolith.",
    )
    bootstrap_call = "ensure_v2_source_root()"
    runpy_call = "runpy.run_path(str(V2_FINAL_ENTRYPOINT)"
    report.check(
        bootstrap_call in root_entrypoint
        and runpy_call in root_entrypoint
        and root_entrypoint.index(bootstrap_call) < root_entrypoint.index(runpy_call),
        "Root entrypoint verifies the V2 runtime bundle before launching V2 Final.",
        "Root entrypoint does not verify the V2 runtime bundle before launch.",
    )
    status_entrypoint = (ROOT / "status_app.py").read_text(encoding="utf-8")
    report.check(
        "from apps.landskapspotential.app import main" in status_entrypoint,
        "Technical runtime status entrypoint remains available.",
        "Technical runtime status entrypoint is not wired.",
    )

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
    trondelag_reference = trondelag.get("behavior_reference") or {}
    report.check(
        trondelag.get("status") == "active"
        and trondelag_reference.get("status") == "authoritative"
        and trondelag_reference.get("scope") == "trondelag_only"
        and trondelag_reference.get("frozen_v2_parity") is True,
        "Trondelag alone is active and authoritative for frozen-V2 parity.",
        "Trondelag is not configured as the sole frozen-V2 parity authority.",
    )

    bornholm = load_json(ROOT / "regions" / "bornholm" / "region.json")
    bornholm_reference = bornholm.get("behavior_reference") or {}
    report.check(
        bornholm.get("status") == "onboarding"
        and (bornholm.get("landing_card") or {}).get("enabled") is False
        and bornholm_reference.get("status") == "diagnostic_only"
        and bornholm_reference.get("frozen_v2_parity") is False,
        "Bornholm remains cataloged but disabled, with V2 evidence diagnostic only.",
        "Bornholm is active or incorrectly classified as a V2 parity baseline.",
    )

    skaraborg = load_json(ROOT / "regions" / "skaraborg" / "region.json")
    report.check(skaraborg.get("status") == "planned", "Skaraborg is planned/disabled.", "Skaraborg is not marked planned.")

    large_files = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and ".venv" not in path.parts
        and path.stat().st_size > 1_500_000
    ]
    report.check(not large_files, "No large runtime artifacts are checked into the delivery skeleton.", f"Large files remain: {large_files[:5]}")

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
