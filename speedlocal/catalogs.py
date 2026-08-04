from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import AnalysisContract, analysis_contract
from .paths import repo_root


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_region(region_id: str) -> dict[str, Any]:
    index = _read_json(repo_root() / "regions" / "index.json")
    indexed = [str(item) for item in index.get("regions") or []]
    if region_id not in indexed:
        raise KeyError(f"Region is not in the public catalog: {region_id}")
    region = _read_json(repo_root() / "regions" / region_id / "region.json")
    if str(region.get("region_id")) != region_id:
        raise ValueError(f"Region manifest id mismatch: {region_id}")
    return region


def list_regions() -> list[dict[str, Any]]:
    index = _read_json(repo_root() / "regions" / "index.json")
    return [load_region(str(region_id)) for region_id in index.get("regions") or []]


def _load_analysis_raw(path: Path, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    resolved = path.resolve()
    root = repo_root().resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Analysis manifest escapes repository: {path}")
    if resolved in seen:
        chain = " -> ".join(item.as_posix() for item in (*seen, resolved))
        raise ValueError(f"Analysis manifest inheritance cycle: {chain}")
    raw = _read_json(resolved)
    base_rel = raw.get("extends")
    if base_rel is None:
        return raw
    if not isinstance(base_rel, str) or not base_rel.strip():
        raise ValueError("Analysis manifest extends must be a repository path")
    base_path = (root / base_rel).resolve()
    base = _load_analysis_raw(base_path, (*seen, resolved))
    merged = dict(base)
    merged.update({key: value for key, value in raw.items() if key != "extends"})
    return merged


def load_analysis(region_id: str, analysis_id: str) -> AnalysisContract:
    region = load_region(region_id)
    manifest_rel = (region.get("analysis_manifests") or {}).get(analysis_id)
    if not manifest_rel:
        raise KeyError(f"Analysis {analysis_id} is not configured for {region_id}")
    path = (repo_root() / str(manifest_rel)).resolve()
    if repo_root().resolve() not in path.parents:
        raise ValueError(f"Analysis manifest escapes repository: {manifest_rel}")
    contract = analysis_contract(_load_analysis_raw(path))
    if contract.region_id != region_id or contract.id != analysis_id:
        raise ValueError(f"Analysis manifest identity mismatch: {path}")
    return contract
