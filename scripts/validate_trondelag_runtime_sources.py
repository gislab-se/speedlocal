from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V2_SOURCE_ROOT = Path(r"C:\tmp\landskapsanalys-v2-multiregion")
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
EXPECTED_REGION_ID = "trondelag"
EXPECTED_NATIVE_CRS = "EPSG:25832"
EXPECTED_DISPLAY_COUNTS = {7: 13735, 6: 2163, 5: 365}
EXPECTED_LANDSCAPE_COUNT = 13735
EXPECTED_LANDSCAPE_TYPES = {f"LT{idx:02d}" for idx in range(1, 10)}
EXPECTED_LT09_COUNT = 359


@dataclass(frozen=True)
class FeatureSummary:
    count: int
    unique_hex_count: int
    duplicate_hex_count: int
    hex_ids: set[str]
    landscape_type_counts: Counter[str]


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
        print("SpeedLocal Trondelag runtime sources")
        print("=" * 37)
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


def source_root() -> Path:
    return Path(os.environ.get(V2_SOURCE_ROOT_ENV, str(DEFAULT_V2_SOURCE_ROOT)))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def repo_path(root: Path, path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return root / path


def as_int_list(values: Any) -> list[int]:
    result: list[int] = []
    for value in values or []:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


def int_keyed_counts(values: dict[str, Any]) -> dict[int, int]:
    result: dict[int, int] = {}
    for key, value in values.items():
        try:
            result[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return result


def hex_id(properties: dict[str, Any]) -> str:
    for key in ["hex_id", "h3_address", "h3_id", "cell_id"]:
        value = str(properties.get(key) or "").strip()
        if value:
            return value
    return ""


def landscape_type_id(properties: dict[str, Any]) -> str:
    for key in ["landscape_type_id", "landscape_type", "lt_id", "landskapstyp_id"]:
        value = str(properties.get(key) or "").strip()
        if value.startswith("LT"):
            return value
    class_value = str(properties.get("class_km") or "").strip()
    if class_value.isdigit():
        return f"LT{int(class_value):02d}"
    return ""


def feature_summary(path: Path, collect_hex_ids: bool = False) -> FeatureSummary:
    data = load_json(path)
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError(f"GeoJSON has no feature list: {path}")

    seen: set[str] = set()
    duplicate_count = 0
    type_counts: Counter[str] = Counter()
    stored_ids: set[str] = set()

    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        cell_id = hex_id(properties)
        if cell_id:
            if cell_id in seen:
                duplicate_count += 1
            seen.add(cell_id)
            if collect_hex_ids:
                stored_ids.add(cell_id)
        type_id = landscape_type_id(properties)
        if type_id:
            type_counts[type_id] += 1

    return FeatureSummary(
        count=len(features),
        unique_hex_count=len(seen),
        duplicate_hex_count=duplicate_count,
        hex_ids=stored_ids,
        landscape_type_counts=type_counts,
    )


def check_speedlocal_catalog(report: Report) -> None:
    region = load_json(ROOT / "regions" / "trondelag" / "region.json")
    runtime = region.get("runtime") or {}
    fallback_ids = {
        str(item.get("id") or "")
        for item in runtime.get("file_fallbacks") or []
        if isinstance(item, dict)
    }
    report.check(
        region.get("region_id") == EXPECTED_REGION_ID,
        "SpeedLocal Trondelag catalog id is trondelag.",
        f"SpeedLocal Trondelag catalog id is {region.get('region_id')!r}.",
    )
    report.check(
        region.get("native_crs") == EXPECTED_NATIVE_CRS,
        "SpeedLocal Trondelag catalog uses EPSG:25832.",
        f"SpeedLocal Trondelag native CRS is {region.get('native_crs')!r}.",
    )
    report.check(
        as_int_list(region.get("available_h3_resolutions")) == [7, 6, 5],
        "SpeedLocal Trondelag catalog exposes R7/R6/R5 only.",
        f"SpeedLocal Trondelag resolutions are {region.get('available_h3_resolutions')!r}.",
    )
    report.check(
        {"trondelag_region_package", "trondelag_h3_display_r7", "trondelag_lablab_landscape_r7"}.issubset(fallback_ids),
        "SpeedLocal Trondelag file fallback placeholders exist.",
        f"SpeedLocal Trondelag fallback ids are incomplete: {sorted(fallback_ids)}.",
    )


def check_v2_region(report: Report, root: Path) -> dict[str, Any] | None:
    path = root / "regions" / "trondelag" / "region.json"
    if not path.exists():
        report.check(False, "", f"Missing V2 Trondelag region package: {path}")
        return None
    region = load_json(path)
    counts = int_keyed_counts(region.get("h3_display_geometry_counts") or {})
    resolutions = as_int_list(region.get("available_h3_resolutions"))
    report.check(region.get("region_id") == EXPECTED_REGION_ID, "V2 region id is trondelag.", f"V2 region id is {region.get('region_id')!r}.")
    report.check(region.get("native_crs") == EXPECTED_NATIVE_CRS, "V2 Trondelag native CRS is EPSG:25832.", f"V2 Trondelag native CRS is {region.get('native_crs')!r}.")
    report.check(resolutions == [7, 6, 5], "V2 Trondelag exposes R7/R6/R5.", f"V2 Trondelag resolutions are {resolutions}.")
    report.check(8 not in resolutions and 9 not in resolutions, "V2 Trondelag does not expose R8/R9.", f"V2 Trondelag exposes forbidden R8/R9: {resolutions}.")
    report.check(counts == EXPECTED_DISPLAY_COUNTS, "V2 Trondelag display counts match expected R7/R6/R5.", f"V2 display counts are {counts}.")
    return region


def check_landscape_manifest(report: Report, root: Path, region: dict[str, Any]) -> dict[str, Any] | None:
    manifest_path = repo_path(root, str(region.get("landscape_manifest") or ""))
    if manifest_path is None or not manifest_path.exists():
        report.check(False, "", f"Missing V2 Trondelag landscape manifest: {manifest_path}")
        return None
    manifest = load_json(manifest_path)
    review = manifest.get("review") or {}
    counts = int_keyed_counts(manifest.get("expected_feature_counts") or {})
    report.check(manifest.get("region_id") == EXPECTED_REGION_ID, "Landscape manifest region id is trondelag.", f"Landscape manifest region id is {manifest.get('region_id')!r}.")
    report.check(manifest.get("status") == "app_ready_after_qgis_review", "Landscape manifest is app-ready after QGIS review.", f"Landscape manifest status is {manifest.get('status')!r}.")
    report.check(bool(manifest.get("is_lablab_landscape")), "Landscape manifest is LABLAB-first.", "Landscape manifest is not marked is_lablab_landscape.")
    report.check(manifest.get("native_crs") == EXPECTED_NATIVE_CRS, "Landscape manifest uses EPSG:25832.", f"Landscape manifest native CRS is {manifest.get('native_crs')!r}.")
    report.check(counts == EXPECTED_DISPLAY_COUNTS, "Landscape manifest expected counts match R7/R6/R5.", f"Landscape manifest counts are {counts}.")
    report.check(bool(review.get("qgis_reviewed")), "Landscape manifest is QGIS-reviewed.", "Landscape manifest is not QGIS-reviewed.")
    report.check(
        int(review.get("current_app_extent_feature_count") or -1) == EXPECTED_LANDSCAPE_COUNT,
        "Landscape manifest app extent count is 13,735.",
        f"Landscape manifest app extent count is {review.get('current_app_extent_feature_count')!r}.",
    )
    report.check(
        int(review.get("lt09_current_app_extent_feature_count") or -1) == EXPECTED_LT09_COUNT,
        "Landscape manifest records LT09 count as 359.",
        f"Landscape manifest LT09 count is {review.get('lt09_current_app_extent_feature_count')!r}.",
    )
    return manifest


def check_display_sources(report: Report, root: Path, region: dict[str, Any]) -> dict[int, FeatureSummary]:
    display_paths = region.get("h3_display_geometries") or {}
    summaries: dict[int, FeatureSummary] = {}
    for resolution, expected_count in EXPECTED_DISPLAY_COUNTS.items():
        path = repo_path(root, str(display_paths.get(str(resolution)) or ""))
        if path is None or not path.exists():
            report.check(False, "", f"Missing R{resolution} display source: {path}")
            continue
        summary = feature_summary(path, collect_hex_ids=(resolution == 7))
        summaries[resolution] = summary
        report.check(
            summary.count == expected_count,
            f"R{resolution} display source has {expected_count} features.",
            f"R{resolution} display source has {summary.count} features, expected {expected_count}.",
        )
        report.check(
            summary.unique_hex_count == expected_count and summary.duplicate_hex_count == 0,
            f"R{resolution} display source has unique hex ids.",
            f"R{resolution} display unique={summary.unique_hex_count}, duplicates={summary.duplicate_hex_count}.",
        )
    return summaries


def check_landscape_source(
    report: Report,
    root: Path,
    manifest: dict[str, Any],
    display_summaries: dict[int, FeatureSummary],
) -> None:
    path = repo_path(root, str(manifest.get("landscape_geojson") or ""))
    if path is None or not path.exists():
        report.check(False, "", f"Missing Trondelag LABLAB R7 landscape source: {path}")
        return
    summary = feature_summary(path, collect_hex_ids=True)
    report.check(
        summary.count == EXPECTED_LANDSCAPE_COUNT,
        "LABLAB R7 landscape source has 13,735 features.",
        f"LABLAB R7 landscape source has {summary.count} features.",
    )
    report.check(
        summary.unique_hex_count == EXPECTED_LANDSCAPE_COUNT and summary.duplicate_hex_count == 0,
        "LABLAB R7 landscape source has unique hex ids.",
        f"LABLAB R7 landscape unique={summary.unique_hex_count}, duplicates={summary.duplicate_hex_count}.",
    )
    observed_types = set(summary.landscape_type_counts)
    report.check(
        observed_types == EXPECTED_LANDSCAPE_TYPES,
        "LABLAB R7 landscape source contains LT01-LT09 exactly.",
        f"LABLAB R7 landscape types are {sorted(observed_types)}.",
    )
    report.check(
        summary.landscape_type_counts.get("LT09", 0) == EXPECTED_LT09_COUNT,
        "LABLAB R7 landscape source contains 359 LT09 cells.",
        f"LABLAB R7 LT09 count is {summary.landscape_type_counts.get('LT09', 0)}.",
    )
    display_r7 = display_summaries.get(7)
    if display_r7 is not None:
        missing_from_display = summary.hex_ids - display_r7.hex_ids
        missing_from_landscape = display_r7.hex_ids - summary.hex_ids
        report.check(
            not missing_from_display and not missing_from_landscape,
            "LABLAB R7 landscape hex ids match R7 display ids.",
            (
                "LABLAB/display R7 mismatch: "
                f"landscape-only={len(missing_from_display)}, display-only={len(missing_from_landscape)}."
            ),
        )


def check_placeholder_manifests(report: Report, root: Path, region: dict[str, Any]) -> None:
    for key, label in [
        ("scenario_manifest", "scenario"),
        ("potential_manifest", "potential"),
        ("social_acceptance_manifest", "social acceptance"),
    ]:
        path = repo_path(root, str(region.get(key) or ""))
        if path is None or not path.exists():
            report.check(False, "", f"Missing V2 Trondelag {label} manifest: {path}")
            continue
        manifest = load_json(path)
        status = str(manifest.get("status") or "")
        if key == "social_acceptance_manifest":
            report.check(
                status == "synthetic_test_data" and bool(manifest.get("synthetic")),
                "Trondelag social acceptance is marked synthetic test data.",
                f"Trondelag social acceptance status/synthetic is {status!r}/{manifest.get('synthetic')!r}.",
            )
        else:
            report.check(
                status == "placeholder",
                f"Trondelag {label} manifest is explicitly placeholder.",
                f"Trondelag {label} status is {status!r}.",
            )


def main() -> int:
    report = Report()
    root = source_root()
    report.note(f"V2 source root: {root}")
    report.check(root.exists(), "V2 source root exists.", f"V2 source root does not exist: {root}")
    if not root.exists():
        return report.emit()

    check_speedlocal_catalog(report)
    region = check_v2_region(report, root)
    if not region:
        return report.emit()
    manifest = check_landscape_manifest(report, root, region)
    display_summaries = check_display_sources(report, root, region)
    if manifest:
        check_landscape_source(report, root, manifest, display_summaries)
    check_placeholder_manifests(report, root, region)

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
