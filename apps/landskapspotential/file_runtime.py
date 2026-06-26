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


def _display_dataset(root: Path, resolution: int, expected_count: int, source_path: Path | None) -> DatasetSummary:
    dataset_id = f"trondelag_h3_display_r{resolution}"
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


def _landscape_dataset(root: Path, source_path: Path | None) -> tuple[DatasetSummary, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "landscape_types": [],
        "lt09_count": 0,
    }
    if source_path is None or not source_path.exists():
        return (
            DatasetSummary(
                dataset_id="trondelag_lablab_landscape_r7_app_extent",
                kind="landscape_cells",
                source_path=_rel_path(root, source_path),
                expected_count=EXPECTED_TRONDELAG_LANDSCAPE_COUNT,
                actual_count=None,
                valid=False,
                message="Missing LABLAB R7 landscape GeoJSON source.",
            ),
            metadata,
        )

    count, unique_hex_count, duplicate_count, landscape_types = _feature_summary(source_path)
    observed_types = set(landscape_types)
    lt09_count = landscape_types.get("LT09", 0)
    valid = (
        count == EXPECTED_TRONDELAG_LANDSCAPE_COUNT
        and unique_hex_count == EXPECTED_TRONDELAG_LANDSCAPE_COUNT
        and duplicate_count == 0
        and observed_types == EXPECTED_TRONDELAG_LANDSCAPE_TYPES
        and lt09_count == EXPECTED_TRONDELAG_LT09_COUNT
    )
    metadata = {
        "landscape_types": sorted(observed_types),
        "lt09_count": lt09_count,
    }
    return (
        DatasetSummary(
            dataset_id="trondelag_lablab_landscape_r7_app_extent",
            kind="landscape_cells",
            source_path=_rel_path(root, source_path),
            expected_count=EXPECTED_TRONDELAG_LANDSCAPE_COUNT,
            actual_count=count,
            valid=valid,
            message="Feature count, landscape types and LT09 match." if valid else f"count={count}, unique={unique_hex_count}, duplicates={duplicate_count}, lt09={lt09_count}",
        ),
        metadata,
    )


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
        datasets.append(_display_dataset(root, resolution, expected_count, source_path))

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
        landscape_dataset, landscape_metadata = _landscape_dataset(root, landscape_source)
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


def runtime_source_summary(region_id: str, source_root: Path | None = None) -> FileRuntimeSummary:
    wanted = str(region_id).strip().lower()
    root = source_root or configured_source_root()
    if wanted != "trondelag":
        return FileRuntimeSummary(
            region_id=wanted,
            available=False,
            source_root=str(root),
            message="No file-backed runtime reader exists for this region yet.",
            datasets=(),
            metadata={},
        )
    return _trondelag_runtime_summary(str(root))


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
