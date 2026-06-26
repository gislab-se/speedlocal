from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV = "REGIONAL_LANDSCAPE_PIPELINE_ROOT"
DEFAULT_REGIONAL_LANDSCAPE_PIPELINE_ROOT = Path(r"C:\gislab\regional-landscape-pipeline")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def port_root() -> Path:
    return Path(__file__).resolve().parents[2]


def package_root() -> Path:
    return Path(__file__).resolve().parent


def manifests_root() -> Path:
    return package_root() / "manifests"


def regions_root() -> Path:
    return repo_root() / "regions"


def region_index_path() -> Path:
    return regions_root() / "index.json"


def _regional_landscape_pipeline_root() -> Path:
    return Path(
        os.environ.get(
            REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV,
            str(DEFAULT_REGIONAL_LANDSCAPE_PIPELINE_ROOT),
        )
    )


def _expand_path_tokens(path_value: str) -> str:
    value = str(path_value).strip()
    token_values = [
        f"${{{REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV}}}",
        f"%{REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV}%",
    ]
    for token in token_values:
        if value == token or value.startswith(f"{token}/") or value.startswith(f"{token}\\"):
            suffix = value[len(token) :].lstrip("/\\")
            root = _regional_landscape_pipeline_root()
            return str(root / suffix) if suffix else str(root)
    return os.path.expandvars(value)


def resolve_repo_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path_value = _expand_path_tokens(path_value)
    path = Path(path_value)
    if path.is_absolute():
        return path
    repo_path = repo_root() / path
    if repo_path.exists():
        return repo_path
    port_path = port_root() / path
    if port_path.exists():
        return port_path
    return repo_path


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=64)
def read_manifest(path_str: str) -> dict[str, Any]:
    return _read_json(Path(path_str))


def _region_id_from_manifest_path(path: Path) -> str:
    if path.name == "region.json":
        return path.parent.name
    return path.stem


def _region_manifest_path_from_index(region_id: str) -> Path:
    return regions_root() / region_id / "region.json"


@lru_cache(maxsize=8)
def load_region_index() -> dict[str, Any]:
    index_path = region_index_path()
    if not index_path.exists():
        return {"regions": []}
    return _read_json(index_path).copy()


def default_region_id() -> str:
    index = load_region_index()
    value = str(index.get("default_region_id") or "").strip()
    if value:
        return value.lower()
    regions = index.get("regions") or []
    if regions:
        return str(regions[0]).strip().lower()
    return "trondelag"


def _indexed_region_manifest_paths() -> list[Path]:
    index = load_region_index()
    region_ids = index.get("regions") or []
    paths: list[Path] = []
    for region_id in region_ids:
        path = _region_manifest_path_from_index(str(region_id))
        if path.exists():
            paths.append(path)
    return paths


def list_region_manifest_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for path in _indexed_region_manifest_paths():
        region_id = _region_id_from_manifest_path(path).lower()
        if region_id in seen:
            continue
        seen.add(region_id)
        paths.append(path)
    return paths


def _with_legacy_region_aliases(manifest: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "native_crs": ("crs", "native"),
        "web_crs": ("crs", "web"),
        "default_map_center": ("map", "default_center"),
        "default_zoom": ("map", "default_zoom"),
        "available_h3_resolutions": ("h3", "available_display_resolutions"),
        "default_h3_resolution": ("h3", "default_analysis_resolution"),
        "default_display_h3_resolution": ("h3", "default_display_resolution"),
        "h3_display_geometries": ("h3", "display_geometries"),
        "h3_display_geometry_counts": ("h3", "display_geometry_counts"),
    }
    for alias, (section_key, nested_key) in aliases.items():
        section = manifest.get(section_key)
        if alias not in manifest and isinstance(section, dict) and nested_key in section:
            manifest[alias] = section.get(nested_key)

    linked = manifest.get("manifests")
    if isinstance(linked, dict):
        linked_aliases = {
            "landscape_manifest": "landscape",
            "potential_manifest": "potential",
            "scenario_manifest": "scenarios",
            "social_acceptance_manifest": "social_acceptance",
            "acceptance_registry": "acceptance_registry",
            "layer_catalog": "layer_catalog",
        }
        for alias, linked_key in linked_aliases.items():
            if alias not in manifest and linked_key in linked:
                manifest[alias] = linked.get(linked_key)
    return manifest


def _load_region_manifest(path: Path) -> dict[str, Any]:
    manifest = read_manifest(str(path)).copy()
    manifest["_manifest_path"] = str(path)
    manifest["_region_package_dir"] = str(path.parent) if path.name == "region.json" else ""
    return _with_legacy_region_aliases(manifest)


def list_regions() -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for path in list_region_manifest_paths():
        regions.append(_load_region_manifest(path))
    return regions


def load_region(region_id: str) -> dict[str, Any]:
    wanted = str(region_id).lower()
    for path in list_region_manifest_paths():
        if _region_id_from_manifest_path(path).lower() == wanted:
            return _load_region_manifest(path)
    package_path = _region_manifest_path_from_index(str(region_id))
    raise FileNotFoundError(f"Region manifest not found in SpeedLocal index: {package_path}")


def resolve_region_path(region: dict[str, Any], path_value: str | None) -> Path | None:
    if not path_value:
        return None
    expanded = _expand_path_tokens(path_value)
    path = Path(expanded)
    if path.is_absolute():
        return path
    package_dir = region.get("_region_package_dir")
    if package_dir:
        package_path = Path(str(package_dir)) / path
        if package_path.exists():
            return package_path
    repo_path = repo_root() / path
    if repo_path.exists():
        return repo_path
    port_path = port_root() / path
    if port_path.exists():
        return port_path
    return repo_path


def load_linked_manifest(region: dict[str, Any], key: str) -> dict[str, Any] | None:
    path = resolve_region_path(region, region.get(key))
    if path is None or not path.exists():
        return None
    manifest = read_manifest(str(path)).copy()
    manifest["_manifest_path"] = str(path)
    return manifest

