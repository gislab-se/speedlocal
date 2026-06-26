from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REGIONS_ROOT = ROOT / "regions"


class CatalogError(RuntimeError):
    """Raised when the delivery catalog is incomplete or invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise CatalogError(f"Expected JSON object: {path}")
    return data


@lru_cache(maxsize=1)
def load_region_index() -> dict[str, Any]:
    path = REGIONS_ROOT / "index.json"
    if not path.exists():
        raise CatalogError(f"Missing region index: {path}")
    return _read_json(path)


def indexed_region_ids() -> list[str]:
    index = load_region_index()
    values = index.get("regions") or []
    if not isinstance(values, list):
        raise CatalogError("regions/index.json field 'regions' must be a list.")
    result: list[str] = []
    for item in values:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict) and item.get("region_id"):
            result.append(str(item["region_id"]))
        else:
            raise CatalogError(f"Invalid region index entry: {item!r}")
    return [value.strip().lower() for value in result if value]


def default_region_id() -> str:
    index = load_region_index()
    value = str(index.get("default_region_id") or "").strip().lower()
    if value:
        return value
    ids = indexed_region_ids()
    return ids[0] if ids else "trondelag"


@lru_cache(maxsize=32)
def load_region(region_id: str) -> dict[str, Any]:
    wanted = str(region_id).strip().lower()
    if wanted not in indexed_region_ids():
        raise CatalogError(f"Region is not indexed: {wanted}")
    path = REGIONS_ROOT / wanted / "region.json"
    if not path.exists():
        raise CatalogError(f"Missing region manifest: {path}")
    data = _read_json(path)
    if str(data.get("region_id") or "").strip().lower() != wanted:
        raise CatalogError(f"Region manifest id mismatch: {path}")
    data["_manifest_path"] = str(path)
    return data


def list_regions() -> list[dict[str, Any]]:
    return [load_region(region_id) for region_id in indexed_region_ids()]


def resolve_repo_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return ROOT / path
