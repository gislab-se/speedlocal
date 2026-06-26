from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PORT_ROOT = ROOT / "apps" / "v2_port"
PLAN_DOC = ROOT / "docs" / "V2_QUARANTINE_PORT_INVENTORY_2026-06-26.md"
FORBIDDEN_REGION_IDS = {"vara", "skara"}
REQUIRED_DOC_PHRASES = [
    "## Required Now",
    "## Required Later",
    "## Leave Behind",
    "## Guardrail Patches Required Before Run",
    "## First Standard Layer Groups",
]
FORBIDDEN_PORT_PATHS = [
    "apps/v2_port/apps/potential_model/manifests/regions",
    "apps/v2_port/regions/skara",
    "apps/v2_port/regions/vara",
    "apps/v2_port/data",
    "apps/v2_port/exports",
    "apps/v2_port/artifacts",
    "apps/v2_port/tmp",
    "apps/v2_port/apps/acceptance_model/registry.json",
]
FORBIDDEN_PY_PATTERNS = [
    "_legacy_region_manifest_paths",
    'manifests_root() / "regions"',
    "manifests_root() / 'regions'",
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
        print("SpeedLocal V2 port guardrails")
        print("=" * 30)
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


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _find_forbidden_region_ids(value: Any, path: Path) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        region_id = value.get("region_id")
        if str(region_id).lower() in FORBIDDEN_REGION_IDS:
            found.append(f"{path.relative_to(ROOT).as_posix()}: region_id={region_id}")
        for nested in value.values():
            found.extend(_find_forbidden_region_ids(nested, path))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_find_forbidden_region_ids(nested, path))
    return found


def _forbidden_json_region_ids() -> list[str]:
    findings: list[str] = []
    if not PORT_ROOT.exists():
        return findings
    for path in PORT_ROOT.rglob("*.json"):
        try:
            payload = _load_json(path)
        except Exception as exc:
            findings.append(f"{path.relative_to(ROOT).as_posix()}: invalid JSON ({exc})")
            continue
        findings.extend(_find_forbidden_region_ids(payload, path))
    return findings


def _forbidden_python_patterns() -> list[str]:
    findings: list[str] = []
    if not PORT_ROOT.exists():
        return findings
    for path in PORT_ROOT.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_PY_PATTERNS:
            if pattern in text:
                findings.append(f"{path.relative_to(ROOT).as_posix()}: {pattern}")
    return findings


def main() -> int:
    report = Report()
    report.check(PLAN_DOC.exists(), "V2 quarantine port inventory exists.", f"Missing plan doc: {PLAN_DOC.relative_to(ROOT)}")
    if PLAN_DOC.exists():
        doc_text = PLAN_DOC.read_text(encoding="utf-8")
        for phrase in REQUIRED_DOC_PHRASES:
            report.check(phrase in doc_text, f"Plan doc contains {phrase}.", f"Plan doc missing {phrase}.")

    if not PORT_ROOT.exists():
        report.check(True, "No V2 quarantine port has been copied yet.", "Unexpected V2 quarantine port state.")
        return report.emit()

    for path_value in FORBIDDEN_PORT_PATHS:
        path = ROOT / path_value
        report.check(not path.exists(), f"Forbidden port path absent: {path_value}", f"Forbidden port path exists: {path_value}")

    large_files = [
        path.relative_to(ROOT).as_posix()
        for path in PORT_ROOT.rglob("*")
        if path.is_file() and path.stat().st_size > 1_500_000
    ]
    report.check(not large_files, "No large files are checked into apps/v2_port.", f"Large files in apps/v2_port: {large_files[:8]}")

    forbidden_regions = _forbidden_json_region_ids()
    report.check(not forbidden_regions, "No forbidden legacy region ids in V2 port JSON.", f"Forbidden region ids found: {forbidden_regions[:8]}")

    forbidden_patterns = _forbidden_python_patterns()
    report.check(not forbidden_patterns, "No legacy region discovery patterns in V2 port Python.", f"Forbidden Python patterns found: {forbidden_patterns[:8]}")

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())

