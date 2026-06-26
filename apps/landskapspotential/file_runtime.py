from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
DEFAULT_V2_SOURCE_ROOT = Path(r"C:\tmp\landskapsanalys-v2-multiregion")
EXPECTED_TRONDELAG_DISPLAY_COUNTS = {7: 13735, 6: 2163, 5: 365}
EXPECTED_TRONDELAG_LANDSCAPE_COUNT = 13735
EXPECTED_TRONDELAG_LANDSCAPE_TYPES = {f"LT{idx:02d}" for idx in range(1, 10)}
EXPECTED_TRONDELAG_LT09_COUNT = 359
EXPECTED_BORNHOLM_DISPLAY_COUNTS = {6: 32, 7: 166, 8: 1035, 9: 6852}
EXPECTED_BORNHOLM_LANDSCAPE_APP_COUNT = 6852
EXPECTED_BORNHOLM_LANDSCAPE_CSV_ROWS = 6877
EXPECTED_BORNHOLM_SCORE_ROWS = 6878
EXPECTED_BORNHOLM_SOCIAL_ROWS = 6878
EXPECTED_BORNHOLM_LANDSCAPE_TYPES = {f"LT{idx:02d}" for idx in range(1, 6)}


@dataclass(frozen=True)
class DatasetSummary:
    dataset_id: str
    kind: str
    source_path: str
    expected_count: int | None
    actual_count: int | None
    valid: bool
    message: str


@dataclass(frozen=True)
class FileRuntimeSummary:
    region_id: str
    available: bool
    source_root: str
    message: str
    datasets: tuple[DatasetSummary, ...]
    metadata: dict[str, Any]


def configured_source_root() -> Path:
    return Path(os.environ.get(V2_SOURCE_ROOT_ENV, str(DEFAULT_V2_SOURCE_ROOT)))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _repo_path(root: Path, path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return root / path


def _rel_path(root: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _hex_id(properties: dict[str, Any]) -> str:
    for key in ["hex_id", "h3_address", "h3_id", "cell_id"]:
        value = str(properties.get(key) or "").strip()
        if value:
            return value
    return ""


def _landscape_type_id(properties: dict[str, Any]) -> str:
    for key in ["landscape_type_id", "landscape_type", "lt_id", "landskapstyp_id"]:
        value = str(properties.get(key) or "").strip()
        if value.startswith("LT"):
            return value
    class_value = str(properties.get("class_km") or "").strip()
    if class_value.isdigit():
        return f"LT{int(class_value):02d}"
    return ""


def _feature_summary(path: Path) -> tuple[int, int, int, Counter[str]]:
    data = _load_json(path)
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError(f"GeoJSON has no feature list: {path}")

    seen: set[str] = set()
    duplicate_count = 0
    landscape_types: Counter[str] = Counter()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        cell_id = _hex_id(properties)
        if cell_id:
            if cell_id in seen:
                duplicate_count += 1
            seen.add(cell_id)
        type_id = _landscape_type_id(properties)
        if type_id:
            landscape_types[type_id] += 1

    return len(features), len(seen), duplicate_count, landscape_types


def _display_dataset(root: Path, region_id: str, resolution: int, expected_count: int, source_path: Path | None) -> DatasetSummary:
    dataset_id = f"{region_id}_h3_display_r{resolution}"
    if source_path is None or not source_path.exists():
        return DatasetSummary(
            dataset_id=dataset_id,
            kind="h3_display_geometry",
            source_path=_rel_path(root, source_path),
            expected_count=expected_count,
            actual_count=None,
            valid=False,
            message="Missing display GeoJSON source.",
        )

    count, unique_hex_count, duplicate_count, _ = _feature_summary(source_path)
    valid = count == expected_count and unique_hex_count == expected_count and duplicate_count == 0
    return DatasetSummary(
        dataset_id=dataset_id,
        kind="h3_display_geometry",
        source_path=_rel_path(root, source_path),
        expected_count=expected_count,
        actual_count=count,
        valid=valid,
        message="Feature count and hex ids match." if valid else f"count={count}, unique={unique_hex_count}, duplicates={duplicate_count}",
    )


def _landscape_dataset(
    root: Path,
    dataset_id: str,
    source_path: Path | None,
    expected_count: int,
    expected_types: set[str],
    expected_lt09_count: int | None = None,
) -> tuple[DatasetSummary, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "landscape_types": [],
        "lt09_count": 0,
    }
    if source_path is None or not source_path.exists():
        return (
            DatasetSummary(
                dataset_id=dataset_id,
                kind="landscape_cells",
                source_path=_rel_path(root, source_path),
                expected_count=expected_count,
                actual_count=None,
                valid=False,
                message="Missing landscape GeoJSON source.",
            ),
            metadata,
        )

    count, unique_hex_count, duplicate_count, landscape_types = _feature_summary(source_path)
    observed_types = set(landscape_types)
    lt09_count = landscape_types.get("LT09", 0)
    valid = (
        count == expected_count
        and unique_hex_count == expected_count
        and duplicate_count == 0
        and observed_types == expected_types
        and (expected_lt09_count is None or lt09_count == expected_lt09_count)
    )
    metadata = {
        "landscape_types": sorted(observed_types),
        "lt09_count": lt09_count,
    }
    return (
        DatasetSummary(
            dataset_id=dataset_id,
            kind="landscape_cells",
            source_path=_rel_path(root, source_path),
            expected_count=expected_count,
            actual_count=count,
            valid=valid,
            message="Feature count, hex ids and landscape types match." if valid else f"count={count}, unique={unique_hex_count}, duplicates={duplicate_count}, lt09={lt09_count}",
        ),
        metadata,
    )


def _csv_dataset(root: Path, dataset_id: str, kind: str, source_path: Path | None, expected_count: int, required_columns: set[str]) -> DatasetSummary:
    if source_path is None or not source_path.exists():
        return DatasetSummary(
            dataset_id=dataset_id,
            kind=kind,
            source_path=_rel_path(root, source_path),
            expected_count=expected_count,
            actual_count=None,
            valid=False,
            message="Missing CSV source.",
        )

    import csv

    row_count = 0
    seen: set[str] = set()
    duplicate_count = 0
    fieldnames: set[str] = set()
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        for row in reader:
            row_count += 1
            cell_id = str(row.get("hex_id") or "").strip()
            if cell_id:
                if cell_id in seen:
                    duplicate_count += 1
                seen.add(cell_id)

    missing_columns = required_columns.difference(fieldnames)
    valid = row_count == expected_count and len(seen) == expected_count and duplicate_count == 0 and not missing_columns
    return DatasetSummary(
        dataset_id=dataset_id,
        kind=kind,
        source_path=_rel_path(root, source_path),
        expected_count=expected_count,
        actual_count=row_count,
        valid=valid,
        message="Row count, hex ids and required columns match." if valid else f"rows={row_count}, unique={len(seen)}, duplicates={duplicate_count}, missing_columns={sorted(missing_columns)}",
    )


def _manifest_summary(dataset_id: str, kind: str, root: Path, source_path: Path | None, valid: bool, message: str) -> DatasetSummary:
    return DatasetSummary(
        dataset_id=dataset_id,
        kind=kind,
        source_path=_rel_path(root, source_path),
        expected_count=None,
        actual_count=None,
        valid=valid,
        message=message,
    )


def _int_value(value: Any, default: int = -1) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=8)
def _trondelag_runtime_summary(source_root_value: str) -> FileRuntimeSummary:
    root = Path(source_root_value)
    if not root.exists():
        return FileRuntimeSummary(
            region_id="trondelag",
            available=False,
            source_root=str(root),
            message=f"Source root does not exist. Set {V2_SOURCE_ROOT_ENV}.",
            datasets=(),
            metadata={},
        )

    region_path = root / "regions" / "trondelag" / "region.json"
    if not region_path.exists():
        return FileRuntimeSummary(
            region_id="trondelag",
            available=False,
            source_root=str(root),
            message=f"Missing V2 region manifest: {region_path}",
            datasets=(),
            metadata={},
        )

    region = _load_json(region_path)
    display_paths = region.get("h3_display_geometries") or {}
    datasets: list[DatasetSummary] = []
    for resolution, expected_count in EXPECTED_TRONDELAG_DISPLAY_COUNTS.items():
        source_path = _repo_path(root, str(display_paths.get(str(resolution)) or ""))
        datasets.append(_display_dataset(root, "trondelag", resolution, expected_count, source_path))

    landscape_manifest_path = _repo_path(root, str(region.get("landscape_manifest") or ""))
    if landscape_manifest_path is None or not landscape_manifest_path.exists():
        landscape_source = None
        landscape_metadata = {"landscape_types": [], "lt09_count": 0}
        datasets.append(
            DatasetSummary(
                dataset_id="trondelag_lablab_landscape_r7_app_extent",
                kind="landscape_cells",
                source_path="",
                expected_count=EXPECTED_TRONDELAG_LANDSCAPE_COUNT,
                actual_count=None,
                valid=False,
                message=f"Missing landscape manifest: {landscape_manifest_path}",
            )
        )
    else:
        landscape_manifest = _load_json(landscape_manifest_path)
        landscape_source = _repo_path(root, str(landscape_manifest.get("landscape_geojson") or ""))
        landscape_dataset, landscape_metadata = _landscape_dataset(
            root,
            "trondelag_lablab_landscape_r7_app_extent",
            landscape_source,
            EXPECTED_TRONDELAG_LANDSCAPE_COUNT,
            EXPECTED_TRONDELAG_LANDSCAPE_TYPES,
            EXPECTED_TRONDELAG_LT09_COUNT,
        )
        datasets.append(landscape_dataset)

    valid = bool(datasets) and all(dataset.valid for dataset in datasets)
    metadata = {
        "native_crs": region.get("native_crs"),
        "available_h3_resolutions": region.get("available_h3_resolutions"),
        "default_h3_resolution": region.get("default_h3_resolution"),
        "landscape_types": landscape_metadata.get("landscape_types", []),
        "lt09_count": landscape_metadata.get("lt09_count", 0),
        "source_root_env": V2_SOURCE_ROOT_ENV,
    }
    return FileRuntimeSummary(
        region_id="trondelag",
        available=valid,
        source_root=str(root),
        message="Trondelag file runtime source archive is validated." if valid else "Trondelag file runtime source archive has blockers.",
        datasets=tuple(datasets),
        metadata=metadata,
    )


@lru_cache(maxsize=8)
def _bornholm_runtime_summary(source_root_value: str) -> FileRuntimeSummary:
    root = Path(source_root_value)
    if not root.exists():
        return FileRuntimeSummary(
            region_id="bornholm",
            available=False,
            source_root=str(root),
            message=f"Source root does not exist. Set {V2_SOURCE_ROOT_ENV}.",
            datasets=(),
            metadata={},
        )

    region_path = root / "regions" / "bornholm" / "region.json"
    if not region_path.exists():
        return FileRuntimeSummary(
            region_id="bornholm",
            available=False,
            source_root=str(root),
            message=f"Missing V2 region manifest: {region_path}",
            datasets=(),
            metadata={},
        )

    region = _load_json(region_path)
    datasets: list[DatasetSummary] = []

    display_paths = region.get("h3_display_geometries") or {}
    display_counts = {int(key): int(value) for key, value in (region.get("h3_display_geometry_counts") or {}).items()}
    display_counts_match = display_counts == EXPECTED_BORNHOLM_DISPLAY_COUNTS
    for resolution, expected_count in EXPECTED_BORNHOLM_DISPLAY_COUNTS.items():
        source_path = _repo_path(root, str(display_paths.get(str(resolution)) or ""))
        datasets.append(_display_dataset(root, "bornholm", resolution, expected_count, source_path))

    runtime_summary_path = root / "exports" / "v2_multiregion" / "bornholm" / "bornholm_dagi_landsdel_runtime_summary.json"
    runtime_summary = _load_json(runtime_summary_path) if runtime_summary_path.exists() else {}
    runtime_counts = runtime_summary.get("counts") if isinstance(runtime_summary, dict) else {}
    source_universe = runtime_summary.get("source_universe") if isinstance(runtime_summary, dict) else {}
    runtime_display_counts = {int(key): int(value) for key, value in ((runtime_counts or {}).get("display_geometries") or {}).items()}
    runtime_summary_valid = (
        bool(runtime_summary)
        and runtime_summary.get("selected_landmask") == "dagi_landsdel_bornholm"
        and runtime_display_counts == EXPECTED_BORNHOLM_DISPLAY_COUNTS
        and _int_value((runtime_counts or {}).get("landscape_app_features")) == EXPECTED_BORNHOLM_LANDSCAPE_APP_COUNT
        and _int_value((runtime_counts or {}).get("display_without_landscape_csv")) == 0
        and _int_value((runtime_counts or {}).get("display_without_score_csv")) == 0
        and _int_value((runtime_counts or {}).get("display_without_social_csv")) == 0
    )
    datasets.append(
        _manifest_summary(
            "bornholm_dagi_landsdel_runtime_summary",
            "manifest",
            root,
            runtime_summary_path,
            runtime_summary_valid,
            "DAGI Landsdel runtime summary matches display/source counts." if runtime_summary_valid else "DAGI Landsdel runtime summary has blockers.",
        )
    )

    landscape_manifest_path = _repo_path(root, str(region.get("landscape_manifest") or ""))
    landscape_metadata = {"landscape_types": [], "lt09_count": 0}
    if landscape_manifest_path is None or not landscape_manifest_path.exists():
        datasets.append(
            DatasetSummary(
                dataset_id="bornholm_lablab_landscape_r9_app_extent",
                kind="landscape_cells",
                source_path="",
                expected_count=EXPECTED_BORNHOLM_LANDSCAPE_APP_COUNT,
                actual_count=None,
                valid=False,
                message=f"Missing landscape manifest: {landscape_manifest_path}",
            )
        )
        landscape_manifest = {}
    else:
        landscape_manifest = _load_json(landscape_manifest_path)
        landscape_source = _repo_path(root, str(landscape_manifest.get("landscape_geojson") or ""))
        landscape_dataset, landscape_metadata = _landscape_dataset(
            root,
            "bornholm_lablab_landscape_r9_app_extent",
            landscape_source,
            EXPECTED_BORNHOLM_LANDSCAPE_APP_COUNT,
            EXPECTED_BORNHOLM_LANDSCAPE_TYPES,
        )
        datasets.append(landscape_dataset)

        landscape_csv = _repo_path(root, str(landscape_manifest.get("landscape_csv") or ""))
        datasets.append(
            _csv_dataset(
                root,
                "bornholm_lablab_landscape_r9_csv",
                "landscape_csv",
                landscape_csv,
                EXPECTED_BORNHOLM_LANDSCAPE_CSV_ROWS,
                {"hex_id", "h3_resolution", "source_h3_resolution", "landscape_type_id", "legacy_v10_type_id"},
            )
        )

    potential_manifest_path = _repo_path(root, str(region.get("potential_manifest") or ""))
    potential_manifest = _load_json(potential_manifest_path) if potential_manifest_path and potential_manifest_path.exists() else {}
    runtime_contract = potential_manifest.get("runtime_contract") if isinstance(potential_manifest, dict) else {}
    potential_manifest_valid = (
        potential_manifest.get("status") == "r10_derived_r9_pey"
        and (runtime_contract or {}).get("mode") == "r10_derived_r9_pey"
        and int((runtime_contract or {}).get("analysis_h3_resolution") or -1) == 9
        and int((runtime_contract or {}).get("runtime_base_h3_resolution") or -1) == 10
        and (runtime_contract or {}).get("true_r9_native_pey") is False
        and (runtime_contract or {}).get("requires_rebuild_for_true_r9_native") is True
    )
    datasets.append(
        _manifest_summary(
            "bornholm_potential_r10_derived_r9_pey_manifest",
            "manifest",
            root,
            potential_manifest_path,
            potential_manifest_valid,
            "R10-derived R9 PEY runtime contract is explicitly labelled." if potential_manifest_valid else "Potential manifest does not preserve the R10-derived R9 PEY contract.",
        )
    )

    score_config = region.get("establishment_placement_score") or {}
    score_manifest_path = _repo_path(root, str(score_config.get("manifest") or ""))
    score_manifest = _load_json(score_manifest_path) if score_manifest_path and score_manifest_path.exists() else {}
    score_manifest_valid = (
        score_config.get("runtime_mode") == "r10_derived_r9_pey"
        and int(score_manifest.get("h3_resolution") or -1) == 9
        and int(score_manifest.get("source_h3_resolution") or -1) == 10
        and int(score_manifest.get("rows") or -1) == EXPECTED_BORNHOLM_SCORE_ROWS
    )
    datasets.append(
        _manifest_summary(
            "bornholm_establishment_score_r9_manifest",
            "manifest",
            root,
            score_manifest_path,
            score_manifest_valid,
            "Establishment score manifest preserves R10-source/R9-runtime semantics." if score_manifest_valid else "Establishment score manifest has blockers.",
        )
    )
    score_csv = _repo_path(root, str(score_manifest.get("path") or score_config.get("path") or ""))
    datasets.append(
        _csv_dataset(
            root,
            "bornholm_establishment_placement_score_r9",
            "establishment_score_csv",
            score_csv,
            EXPECTED_BORNHOLM_SCORE_ROWS,
            {"hex_id", "h3_resolution", "source_h3_resolution", "wind_establishment_placement_score", "solar_establishment_placement_score"},
        )
    )

    social_manifest_path = _repo_path(root, str(region.get("social_acceptance_manifest") or ""))
    social_manifest = _load_json(social_manifest_path) if social_manifest_path and social_manifest_path.exists() else {}
    social_manifest_valid = (
        social_manifest.get("status") == "synthetic_test_data"
        and social_manifest.get("synthetic") is True
        and int(social_manifest.get("hex_resolution") or -1) == 9
        and int(social_manifest.get("source_hex_resolution") or -1) == 10
    )
    datasets.append(
        _manifest_summary(
            "bornholm_synthetic_social_acceptance_manifest",
            "manifest",
            root,
            social_manifest_path,
            social_manifest_valid,
            "Synthetic social acceptance is clearly labelled as test data." if social_manifest_valid else "Social acceptance manifest has blockers.",
        )
    )
    social_csv = _repo_path(root, str(social_manifest.get("acceptance_csv") or ""))
    datasets.append(
        _csv_dataset(
            root,
            "bornholm_synthetic_social_acceptance_r9",
            "social_acceptance_csv",
            social_csv,
            EXPECTED_BORNHOLM_SOCIAL_ROWS,
            {"hex_id", "h3_resolution", "source_h3_resolution", "acceptance_low", "acceptance_medium", "acceptance_high"},
        )
    )

    valid = bool(datasets) and display_counts_match and all(dataset.valid for dataset in datasets)
    metadata = {
        "native_crs": region.get("native_crs"),
        "available_h3_resolutions": region.get("available_h3_resolutions"),
        "default_h3_resolution": region.get("default_h3_resolution"),
        "display_counts": display_counts,
        "landscape_types": landscape_metadata.get("landscape_types", []),
        "runtime_mode": score_config.get("runtime_mode"),
        "true_r9_native_pey": (runtime_contract or {}).get("true_r9_native_pey"),
        "requires_rebuild_for_true_r9_native": (runtime_contract or {}).get("requires_rebuild_for_true_r9_native"),
        "landmask": runtime_summary.get("selected_landmask") if isinstance(runtime_summary, dict) else None,
        "source_universe": source_universe or {},
        "source_root_env": V2_SOURCE_ROOT_ENV,
    }
    return FileRuntimeSummary(
        region_id="bornholm",
        available=valid,
        source_root=str(root),
        message="Bornholm file runtime source archive is validated." if valid else "Bornholm file runtime source archive has blockers.",
        datasets=tuple(datasets),
        metadata=metadata,
    )


def runtime_source_summary(region_id: str, source_root: Path | None = None) -> FileRuntimeSummary:
    wanted = str(region_id).strip().lower()
    root = source_root or configured_source_root()
    if wanted == "bornholm":
        return _bornholm_runtime_summary(str(root))
    if wanted == "trondelag":
        return _trondelag_runtime_summary(str(root))
    return FileRuntimeSummary(
        region_id=wanted,
        available=False,
        source_root=str(root),
        message="No file-backed runtime reader exists for this region yet.",
        datasets=(),
        metadata={},
    )


def dataset_rows(summary: FileRuntimeSummary) -> list[dict[str, Any]]:
    return [
        {
            "dataset_id": dataset.dataset_id,
            "kind": dataset.kind,
            "expected_count": dataset.expected_count,
            "actual_count": dataset.actual_count,
            "valid": dataset.valid,
            "source_path": dataset.source_path,
            "message": dataset.message,
        }
        for dataset in summary.datasets
    ]
