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


def load_analysis(region_id: str, analysis_id: str) -> AnalysisContract:
    region = load_region(region_id)
    manifest_rel = (region.get("analysis_manifests") or {}).get(analysis_id)
    if not manifest_rel:
        raise KeyError(f"Analysis {analysis_id} is not configured for {region_id}")
    path = (repo_root() / str(manifest_rel)).resolve()
    if repo_root().resolve() not in path.parents:
        raise ValueError(f"Analysis manifest escapes repository: {manifest_rel}")
    contract = analysis_contract(_read_json(path))
    if contract.region_id != region_id or contract.id != analysis_id:
        raise ValueError(f"Analysis manifest identity mismatch: {path}")
    return contract
