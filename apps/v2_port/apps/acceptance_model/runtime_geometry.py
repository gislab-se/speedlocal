from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from speedlocal.paths import resolve_source_path

from .layers import active_region_id, load_registry, registry_source


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_confined_artifact_path(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved_candidate = candidate.resolve(strict=True)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"Artifact path escapes its declared root: {candidate}"
        ) from exc
    return resolved_candidate


def _validated_fixture(
    config_json: str,
    region_id: str,
) -> tuple[Path, Path, dict[str, Any]]:
    try:
        requested_config = json.loads(config_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Acceptance runtime configuration is invalid JSON"
        ) from exc
    if not isinstance(requested_config, dict):
        raise ValueError("Acceptance runtime configuration must be an object")

    source = registry_source(region_id)
    if source["runtime_strategy"] != "precomputed_polygon":
        raise RuntimeError(
            f"Region {region_id} does not declare a precomputed polygon runtime"
        )
    artifact_root = resolve_source_path(
        source["provider"],
        source["artifact_root"],
    )
    if not artifact_root.is_dir():
        raise FileNotFoundError(
            f"Precomputed polygon artifact root does not exist: {artifact_root}"
        )
    artifact_root = artifact_root.resolve(strict=True)

    contracts: dict[str, dict[str, Any]] = {}
    for fixture in source["validated_fixtures"]:
        if not isinstance(fixture, dict):
            raise ValueError(
                f"Invalid validated fixture contract for region: {region_id}"
            )
        files_sha256 = fixture.get("files_sha256")
        if not isinstance(files_sha256, dict):
            raise ValueError(
                f"Fixture {fixture.get('id')} has no checksum inventory"
            )
        config_sha256 = str(files_sha256.get("config.json") or "").lower()
        if not config_sha256 or config_sha256 in contracts:
            raise ValueError(
                "Fixture configuration checksum is missing or duplicated: "
                f"{fixture.get('id')}"
            )
        contracts[config_sha256] = fixture

    supported_group_ids = set(load_registry(region_id)[0])
    requested_groups = requested_config.get("groups")
    if not isinstance(requested_groups, dict):
        raise ValueError("Acceptance runtime configuration has no groups")
    requested_effective = {
        "groups": {
            str(group_id): value
            for group_id, value in requested_groups.items()
            if str(group_id) in supported_group_ids
        }
    }

    matches: list[tuple[Path, dict[str, Any]]] = []
    for unresolved_config_path in sorted(artifact_root.glob("*/config.json")):
        try:
            config_path = _resolve_confined_artifact_path(
                artifact_root,
                unresolved_config_path,
            )
            candidate_config = _load_json(config_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        candidate_groups = candidate_config.get("groups")
        if not isinstance(candidate_groups, dict):
            continue
        candidate_effective = {
            "groups": {
                str(group_id): value
                for group_id, value in candidate_groups.items()
                if str(group_id) in supported_group_ids
            }
        }
        if candidate_effective != requested_effective:
            continue
        fixture = contracts.get(_sha256(config_path))
        if fixture is not None:
            matches.append((config_path.parent, fixture))

    if not matches:
        raise RuntimeError(
            "Det saknas ett validerat fryst polygonresultat för denna "
            "kombination. Återgå till ett validerat baseline-läge eller "
            "porta polygonmotorn innan kombinationen används."
        )
    if len(matches) != 1:
        raise RuntimeError(
            "More than one validated polygon result matches this control "
            "combination; refusing an ambiguous baseline."
        )
    directory, fixture = matches[0]
    return artifact_root, directory, fixture


def _load_validated_result(
    artifact_root: Path,
    directory: Path,
    fixture: dict[str, Any],
) -> dict[str, Any]:
    directory = _resolve_confined_artifact_path(artifact_root, directory)
    files_sha256 = fixture["files_sha256"]
    required_contract_files = {
        "combined.geojson",
        "config.json",
        "metadata.json",
    }
    if not required_contract_files.issubset(files_sha256):
        raise ValueError(
            f"Fixture {fixture.get('id')} has an incomplete checksum inventory"
        )

    for name, expected_sha256 in files_sha256.items():
        if Path(str(name)).name != str(name):
            raise ValueError(
                f"Fixture file must be a direct artifact child: {name}"
            )
        path = _resolve_confined_artifact_path(
            directory,
            directory / str(name),
        )
        if not path.is_file():
            raise FileNotFoundError(f"Validated fixture file is missing: {path}")
        actual_sha256 = _sha256(path)
        if actual_sha256 != str(expected_sha256).lower():
            raise RuntimeError(
                f"Validated fixture checksum mismatch: {path.name}"
            )

    metadata_path = _resolve_confined_artifact_path(
        directory,
        directory / "metadata.json",
    )
    result = _load_json(metadata_path)
    groups = result.get("groups")
    combined = result.get("combined")
    if not isinstance(groups, dict) or not isinstance(combined, dict):
        raise ValueError(
            f"Fixture {fixture.get('id')} has invalid runtime metadata"
        )

    referenced_files: set[str] = set()
    for item in [*groups.values(), combined]:
        if not isinstance(item, dict):
            raise ValueError(
                f"Fixture {fixture.get('id')} has invalid layer metadata"
            )
        geojson_file = str(item.get("geojson_file") or "")
        if not geojson_file:
            raise ValueError(
                f"Fixture {fixture.get('id')} has a layer without GeoJSON"
            )
        referenced_files.add(geojson_file)
        if geojson_file not in files_sha256:
            raise ValueError(
                f"Fixture GeoJSON is not checksum-declared: {geojson_file}"
            )
        geojson_path = _resolve_confined_artifact_path(
            directory,
            directory / geojson_file,
        )
        item["geojson"] = _load_json(geojson_path)

    result["cache_key"] = (
        f"precomputed_polygon:{files_sha256['config.json']}"
    )
    result["runtime_strategy"] = "precomputed_polygon"
    result["validated_fixture_id"] = str(fixture.get("id") or "")
    result["validated_artifact_files"] = sorted(referenced_files)
    return result


def run_geometry_runtime(
    config_json: str,
    region_id: str | None = None,
) -> dict[str, Any]:
    normalized_region_id = active_region_id(region_id)
    artifact_root, directory, fixture = _validated_fixture(
        config_json,
        normalized_region_id,
    )
    return _load_validated_result(artifact_root, directory, fixture)
