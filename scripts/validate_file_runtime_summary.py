from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.landskapspotential.file_runtime import (
    EXPECTED_TRONDELAG_DISPLAY_COUNTS,
    EXPECTED_TRONDELAG_LANDSCAPE_COUNT,
    EXPECTED_TRONDELAG_LANDSCAPE_TYPES,
    EXPECTED_TRONDELAG_LT09_COUNT,
    dataset_rows,
    runtime_source_summary,
)


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
        print("SpeedLocal file runtime summary")
        print("=" * 31)
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


def main() -> int:
    report = Report()
    summary = runtime_source_summary("trondelag")
    rows = dataset_rows(summary)
    by_id = {row["dataset_id"]: row for row in rows}

    report.check(summary.available, "Trondelag file runtime summary is available.", summary.message)
    report.check(len(rows) == 4, "Trondelag file runtime summary has four datasets.", f"Expected 4 datasets, got {len(rows)}.")
    for resolution, expected_count in EXPECTED_TRONDELAG_DISPLAY_COUNTS.items():
        row = by_id.get(f"trondelag_h3_display_r{resolution}") or {}
        report.check(
            row.get("valid") is True and row.get("actual_count") == expected_count,
            f"R{resolution} display dataset validates with {expected_count} features.",
            f"R{resolution} display dataset row is {row!r}.",
        )

    landscape = by_id.get("trondelag_lablab_landscape_r7_app_extent") or {}
    report.check(
        landscape.get("valid") is True and landscape.get("actual_count") == EXPECTED_TRONDELAG_LANDSCAPE_COUNT,
        "LABLAB R7 landscape dataset validates with 13,735 features.",
        f"Landscape dataset row is {landscape!r}.",
    )
    report.check(
        set(summary.metadata.get("landscape_types") or []) == EXPECTED_TRONDELAG_LANDSCAPE_TYPES,
        "LABLAB R7 landscape summary contains LT01-LT09 exactly.",
        f"Landscape types are {summary.metadata.get('landscape_types')!r}.",
    )
    report.check(
        summary.metadata.get("lt09_count") == EXPECTED_TRONDELAG_LT09_COUNT,
        "LABLAB R7 landscape summary contains 359 LT09 cells.",
        f"LT09 count is {summary.metadata.get('lt09_count')!r}.",
    )
    planned = runtime_source_summary("skaraborg")
    report.check(
        planned.available is False and not dataset_rows(planned),
        "Planned regions without readers fail closed.",
        f"Unexpected planned-region source summary: {planned!r}.",
    )
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
