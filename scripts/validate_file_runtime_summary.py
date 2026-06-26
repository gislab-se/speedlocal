from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.landskapspotential.file_runtime import (
    EXPECTED_BORNHOLM_DISPLAY_COUNTS,
    EXPECTED_BORNHOLM_LANDSCAPE_APP_COUNT,
    EXPECTED_BORNHOLM_LANDSCAPE_CSV_ROWS,
    EXPECTED_BORNHOLM_LANDSCAPE_TYPES,
    EXPECTED_BORNHOLM_SCORE_ROWS,
    EXPECTED_BORNHOLM_SOCIAL_ROWS,
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
    bornholm = runtime_source_summary("bornholm")
    bornholm_rows = dataset_rows(bornholm)
    bornholm_by_id = {row["dataset_id"]: row for row in bornholm_rows}

    report.check(bornholm.available, "Bornholm file runtime summary is available.", bornholm.message)
    report.check(len(bornholm_rows) == 12, "Bornholm file runtime summary has twelve datasets.", f"Expected 12 datasets, got {len(bornholm_rows)}.")
    for resolution, expected_count in EXPECTED_BORNHOLM_DISPLAY_COUNTS.items():
        row = bornholm_by_id.get(f"bornholm_h3_display_r{resolution}") or {}
        report.check(
            row.get("valid") is True and row.get("actual_count") == expected_count,
            f"Bornholm R{resolution} display dataset validates with {expected_count} features.",
            f"Bornholm R{resolution} display dataset row is {row!r}.",
        )
    report.check(
        (bornholm_by_id.get("bornholm_dagi_landsdel_runtime_summary") or {}).get("valid") is True,
        "Bornholm DAGI Landsdel runtime summary validates.",
        f"Runtime summary row is {bornholm_by_id.get('bornholm_dagi_landsdel_runtime_summary')!r}.",
    )
    bornholm_landscape = bornholm_by_id.get("bornholm_lablab_landscape_r9_app_extent") or {}
    report.check(
        bornholm_landscape.get("valid") is True and bornholm_landscape.get("actual_count") == EXPECTED_BORNHOLM_LANDSCAPE_APP_COUNT,
        "Bornholm LABLAB R9 landscape app extent validates with 6,852 features.",
        f"Bornholm landscape app row is {bornholm_landscape!r}.",
    )
    report.check(
        set(bornholm.metadata.get("landscape_types") or []) == EXPECTED_BORNHOLM_LANDSCAPE_TYPES,
        "Bornholm landscape summary contains LT01-LT05 exactly.",
        f"Bornholm landscape types are {bornholm.metadata.get('landscape_types')!r}.",
    )
    bornholm_landscape_csv = bornholm_by_id.get("bornholm_lablab_landscape_r9_csv") or {}
    report.check(
        bornholm_landscape_csv.get("valid") is True and bornholm_landscape_csv.get("actual_count") == EXPECTED_BORNHOLM_LANDSCAPE_CSV_ROWS,
        "Bornholm landscape CSV validates with 6,877 rows.",
        f"Bornholm landscape CSV row is {bornholm_landscape_csv!r}.",
    )
    report.check(
        (bornholm_by_id.get("bornholm_potential_r10_derived_r9_pey_manifest") or {}).get("valid") is True
        and bornholm.metadata.get("runtime_mode") == "r10_derived_r9_pey"
        and bornholm.metadata.get("true_r9_native_pey") is False,
        "Bornholm R10-derived R9 PEY labelling is preserved.",
        f"Bornholm PEY metadata is {bornholm.metadata!r}.",
    )
    score = bornholm_by_id.get("bornholm_establishment_placement_score_r9") or {}
    report.check(
        score.get("valid") is True and score.get("actual_count") == EXPECTED_BORNHOLM_SCORE_ROWS,
        "Bornholm establishment placement score validates with 6,878 rows.",
        f"Bornholm score row is {score!r}.",
    )
    social = bornholm_by_id.get("bornholm_synthetic_social_acceptance_r9") or {}
    report.check(
        social.get("valid") is True and social.get("actual_count") == EXPECTED_BORNHOLM_SOCIAL_ROWS,
        "Bornholm synthetic social acceptance validates with 6,878 rows.",
        f"Bornholm social row is {social!r}.",
    )
    report.check(
        (bornholm_by_id.get("bornholm_synthetic_social_acceptance_manifest") or {}).get("valid") is True,
        "Bornholm social acceptance remains labelled synthetic test data.",
        f"Bornholm social manifest row is {bornholm_by_id.get('bornholm_synthetic_social_acceptance_manifest')!r}.",
    )

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
