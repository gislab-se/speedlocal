from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import validate_trondelag_runtime_sources as sources


DATASET_VERSION = "2026_06_23"


@dataclass(frozen=True)
class DatasetSeed:
    dataset_id: str
    region_id: str
    dataset_kind: str
    dataset_version: str
    source_status: str
    validation_status: str
    source_path: str
    source_manifest: str
    expected_feature_count: int | None
    actual_feature_count: int | None
    metadata: dict[str, Any]


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        if condition:
            self.passes.append(ok)
        else:
            self.failures.append(fail)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def emit(self) -> int:
        print("SpeedLocal Trondelag runtime metadata")
        print("=" * 39)
        print("\nBLOCKERS")
        if self.failures:
            for idx, failure in enumerate(self.failures, start=1):
                print(f"{idx}. FAIL {failure}")
        else:
            print("None")

        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")

        if self.notes:
            print("\nNOTES")
            for item in self.notes:
                print(f"- {item}")

        status = "FAIL" if self.failures else "PASS"
        print(f"\nRESULT: {status} ({len(self.passes)} passed, {len(self.failures)} blocker(s))")
        return 1 if self.failures else 0


def rel_path(root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def jsonb_literal(value: dict[str, Any]) -> str:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"'{text.replace(chr(39), chr(39) + chr(39))}'::jsonb"


def insert_region_sql(region: dict[str, Any]) -> str:
    return "\n".join(
        [
            "INSERT INTO runtime.regions (",
            "    region_id, display_name, native_crs, app_status, data_status, notes",
            ") VALUES (",
            "    'trondelag',",
            f"    {sql_literal(region.get('display_name') or 'Trondelag')},",
            f"    {sql_literal(sources.EXPECTED_NATIVE_CRS)},",
            "    'active',",
            "    'file_fallback_until_speedlocal_runtime_import',",
            f"    {sql_literal(region.get('runtime_note') or '')}",
            ")",
            "ON CONFLICT (region_id) DO UPDATE SET",
            "    display_name = EXCLUDED.display_name,",
            "    native_crs = EXCLUDED.native_crs,",
            "    app_status = EXCLUDED.app_status,",
            "    data_status = EXCLUDED.data_status,",
            "    notes = EXCLUDED.notes,",
            "    updated_at = now();",
        ]
    )


def insert_dataset_sql(dataset: DatasetSeed) -> str:
    return "\n".join(
        [
            "INSERT INTO meta.runtime_datasets (",
            "    dataset_id, region_id, dataset_kind, dataset_version,",
            "    source_status, validation_status, source_path, source_manifest,",
            "    expected_feature_count, actual_feature_count, metadata",
            ") VALUES (",
            f"    {sql_literal(dataset.dataset_id)}, {sql_literal(dataset.region_id)},",
            f"    {sql_literal(dataset.dataset_kind)}, {sql_literal(dataset.dataset_version)},",
            f"    {sql_literal(dataset.source_status)}, {sql_literal(dataset.validation_status)},",
            f"    {sql_literal(dataset.source_path)}, {sql_literal(dataset.source_manifest)},",
            f"    {sql_literal(dataset.expected_feature_count)}, {sql_literal(dataset.actual_feature_count)},",
            f"    {jsonb_literal(dataset.metadata)}",
            ")",
            "ON CONFLICT (dataset_id) DO UPDATE SET",
            "    region_id = EXCLUDED.region_id,",
            "    dataset_kind = EXCLUDED.dataset_kind,",
            "    dataset_version = EXCLUDED.dataset_version,",
            "    source_status = EXCLUDED.source_status,",
            "    validation_status = EXCLUDED.validation_status,",
            "    source_path = EXCLUDED.source_path,",
            "    source_manifest = EXCLUDED.source_manifest,",
            "    expected_feature_count = EXCLUDED.expected_feature_count,",
            "    actual_feature_count = EXCLUDED.actual_feature_count,",
            "    metadata = EXCLUDED.metadata,",
            "    updated_at = now();",
        ]
    )


def emit_sql(region: dict[str, Any], datasets: list[DatasetSeed]) -> str:
    statements = [
        "\\set ON_ERROR_STOP on",
        "",
        "BEGIN;",
        "",
        insert_region_sql(region),
    ]
    for dataset in datasets:
        statements.extend(["", insert_dataset_sql(dataset)])
    statements.extend(
        [
            "",
            "COMMIT;",
            "",
        ]
    )
    return "\n".join(statements)


def prepare(root: Path, report: Report) -> tuple[dict[str, Any] | None, list[DatasetSeed]]:
    report.note(f"V2 source root: {root}")
    report.check(root.exists(), "V2 source root exists.", f"V2 source root does not exist: {root}")
    if not root.exists():
        return None, []

    region_path = root / "regions" / "trondelag" / "region.json"
    region = sources.load_json(region_path)
    manifest_path = sources.repo_path(root, str(region.get("landscape_manifest") or ""))
    manifest = sources.load_json(manifest_path) if manifest_path and manifest_path.exists() else None

    report.check(region.get("region_id") == "trondelag", "Region manifest id is trondelag.", f"Region manifest id is {region.get('region_id')!r}.")
    report.check(region.get("native_crs") == sources.EXPECTED_NATIVE_CRS, "Region manifest uses EPSG:25832.", f"Region manifest native CRS is {region.get('native_crs')!r}.")
    report.check(
        sources.as_int_list(region.get("available_h3_resolutions")) == [7, 6, 5],
        "Region manifest exposes R7/R6/R5.",
        f"Region manifest resolutions are {region.get('available_h3_resolutions')!r}.",
    )
    if manifest is None:
        report.check(False, "", f"Missing landscape manifest: {manifest_path}")
        return region, []

    report.check(
        manifest.get("status") == "app_ready_after_qgis_review",
        "Landscape manifest is app-ready after QGIS review.",
        f"Landscape manifest status is {manifest.get('status')!r}.",
    )
    report.check(
        bool((manifest.get("review") or {}).get("qgis_reviewed")),
        "Landscape manifest is QGIS-reviewed.",
        "Landscape manifest is not QGIS-reviewed.",
    )

    display_paths = region.get("h3_display_geometries") or {}
    display_datasets: list[DatasetSeed] = []
    for resolution, expected_count in sources.EXPECTED_DISPLAY_COUNTS.items():
        source_path = sources.repo_path(root, str(display_paths.get(str(resolution)) or ""))
        if source_path is None or not source_path.exists():
            report.check(False, "", f"Missing R{resolution} display source: {source_path}")
            continue
        summary = sources.feature_summary(source_path)
        report.check(
            summary.count == expected_count,
            f"R{resolution} display source validates with {expected_count} features.",
            f"R{resolution} display source has {summary.count} features, expected {expected_count}.",
        )
        display_datasets.append(
            DatasetSeed(
                dataset_id=f"trondelag_h3_display_r{resolution}",
                region_id="trondelag",
                dataset_kind="h3_display_geometry",
                dataset_version=DATASET_VERSION,
                source_status="app_ready_after_qgis_review",
                validation_status="validated",
                source_path=rel_path(root, source_path),
                source_manifest=rel_path(root, region_path),
                expected_feature_count=expected_count,
                actual_feature_count=summary.count,
                metadata={
                    "h3_resolution": resolution,
                    "native_crs": sources.EXPECTED_NATIVE_CRS,
                    "web_crs": "EPSG:4326",
                    "import_scope": "metadata_seed_only",
                },
            )
        )

    landscape_path = sources.repo_path(root, str(manifest.get("landscape_geojson") or ""))
    landscape_dataset: list[DatasetSeed] = []
    if landscape_path is None or not landscape_path.exists():
        report.check(False, "", f"Missing LABLAB R7 landscape source: {landscape_path}")
    else:
        summary = sources.feature_summary(landscape_path)
        observed_types = set(summary.landscape_type_counts)
        report.check(
            summary.count == sources.EXPECTED_LANDSCAPE_COUNT,
            "LABLAB R7 landscape source validates with 13,735 features.",
            f"LABLAB R7 landscape source has {summary.count} features.",
        )
        report.check(
            observed_types == sources.EXPECTED_LANDSCAPE_TYPES,
            "LABLAB R7 landscape source contains LT01-LT09 exactly.",
            f"LABLAB R7 landscape types are {sorted(observed_types)}.",
        )
        report.check(
            summary.landscape_type_counts.get("LT09", 0) == sources.EXPECTED_LT09_COUNT,
            "LABLAB R7 landscape source contains 359 LT09 cells.",
            f"LABLAB R7 LT09 count is {summary.landscape_type_counts.get('LT09', 0)}.",
        )
        landscape_dataset.append(
            DatasetSeed(
                dataset_id="trondelag_lablab_landscape_r7_app_extent",
                region_id="trondelag",
                dataset_kind="landscape_cells",
                dataset_version=DATASET_VERSION,
                source_status="app_ready_after_qgis_review",
                validation_status="validated",
                source_path=rel_path(root, landscape_path),
                source_manifest=rel_path(root, manifest_path),
                expected_feature_count=sources.EXPECTED_LANDSCAPE_COUNT,
                actual_feature_count=summary.count,
                metadata={
                    "h3_resolution": 7,
                    "native_crs": sources.EXPECTED_NATIVE_CRS,
                    "web_crs": "EPSG:4326",
                    "landscape_types": sorted(observed_types),
                    "lt09_count": summary.landscape_type_counts.get("LT09", 0),
                    "review_date": (manifest.get("review") or {}).get("review_date"),
                    "import_scope": "metadata_seed_only",
                },
            )
        )

    datasets = [
        DatasetSeed(
            dataset_id="trondelag_region_manifest",
            region_id="trondelag",
            dataset_kind="region_manifest",
            dataset_version=DATASET_VERSION,
            source_status="app_ready_after_qgis_review",
            validation_status="validated",
            source_path=rel_path(root, region_path),
            source_manifest=rel_path(root, region_path),
            expected_feature_count=None,
            actual_feature_count=None,
            metadata={
                "native_crs": sources.EXPECTED_NATIVE_CRS,
                "available_h3_resolutions": [7, 6, 5],
                "default_h3_resolution": 7,
                "import_scope": "metadata_seed_only",
            },
        ),
        *display_datasets,
        *landscape_dataset,
    ]
    report.check(
        len(datasets) == 5,
        "Prepared five Trondelag metadata seeds.",
        f"Prepared {len(datasets)} metadata seeds, expected 5.",
    )
    report.note("Prepared metadata only; geometry rows are not emitted by this script.")
    return region, datasets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Trondelag runtime metadata SQL.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=sources.source_root(),
        help=f"V2 source archive root. Defaults to {sources.V2_SOURCE_ROOT_ENV} or {sources.DEFAULT_V2_SOURCE_ROOT}.",
    )
    parser.add_argument(
        "--emit-sql",
        action="store_true",
        help="Print idempotent metadata seed SQL instead of a human validation report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = Report()
    region, datasets = prepare(args.source_root, report)
    if args.emit_sql:
        if report.failures or region is None:
            return report.emit()
        print(emit_sql(region, datasets))
        return 0
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
