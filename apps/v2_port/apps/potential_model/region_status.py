from __future__ import annotations

from typing import Any

from .manifests import load_linked_manifest, read_manifest, resolve_repo_path


def repo_path_exists(path_value: object) -> tuple[str, bool]:
    path = resolve_repo_path(str(path_value)) if path_value else None
    return (str(path) if path is not None else "", bool(path and path.exists()))


def read_optional_manifest(path_value: object) -> dict[str, Any] | None:
    path = resolve_repo_path(str(path_value)) if path_value else None
    if path is None or not path.exists():
        return None
    return read_manifest(str(path)).copy()


def status_row(label: str, path_value: object) -> dict[str, Any]:
    path, exists = repo_path_exists(path_value)
    return {
        "del": label,
        "status": "klar" if exists else "saknas",
        "path": path or str(path_value or ""),
    }


def available_h3_resolutions(region: dict[str, Any]) -> list[int]:
    values: list[int] = []
    for value in region.get("available_h3_resolutions", []) or []:
        try:
            values.append(int(value))
        except Exception:
            continue
    if values:
        return sorted(set(values), reverse=True)
    try:
        default_resolution = int(region.get("default_h3_resolution") or 9)
    except Exception:
        default_resolution = 9
    return [default_resolution]


def runtime_blockers(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any] | None,
    potential_manifest: dict[str, Any] | None,
    scenario_manifest: dict[str, Any] | None,
    solar_rules: dict[str, Any] | None,
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []

    def require(label: str, path_value: object, kind: str) -> None:
        path, exists = repo_path_exists(path_value)
        if not exists:
            blockers.append({"del": label, "typ": kind, "path": path or str(path_value or "")})

    require("Landskapsanalys", region.get("landscape_manifest"), "manifest")
    require("Potential", region.get("potential_manifest"), "manifest")
    require("Scenarier/energimodell", region.get("scenario_manifest"), "manifest")

    if not isinstance(landscape_manifest, dict):
        blockers.append({"del": "Landskapsdata", "typ": "data", "path": ""})
    else:
        require("Landskapshex", landscape_manifest.get("landscape_geojson"), "data")
        require("Faktorpoäng", landscape_manifest.get("factor_scores"), "data")

    if not isinstance(potential_manifest, dict):
        blockers.append({"del": "Potentialregler", "typ": "manifest", "path": ""})

    if not isinstance(solar_rules, dict):
        rules = (potential_manifest or {}).get("rules") if isinstance(potential_manifest, dict) else {}
        require("Solregler", (rules or {}).get("solar"), "regelmanifest")

    geometry_paths = region.get("h3_display_geometries") or {}
    default_resolution = region.get("default_h3_resolution")
    if default_resolution in {None, ""}:
        blockers.append({"del": "H3 default", "typ": "regionmanifest", "path": ""})
    else:
        require(f"H3 R{default_resolution}", geometry_paths.get(str(default_resolution)), "data")

    if not isinstance(scenario_manifest, dict):
        blockers.append({"del": "Energimodell", "typ": "manifest", "path": ""})

    return blockers


def load_region_context(region: dict[str, Any]) -> dict[str, Any]:
    landscape_manifest = load_linked_manifest(region, "landscape_manifest")
    potential_manifest = load_linked_manifest(region, "potential_manifest")
    rules = (potential_manifest or {}).get("rules") or {}
    solar_rules = read_optional_manifest(rules.get("solar"))
    wind_rules = read_optional_manifest(rules.get("wind"))
    scenario_manifest = load_linked_manifest(region, "scenario_manifest")
    missing = runtime_blockers(region, landscape_manifest, potential_manifest, scenario_manifest, solar_rules)
    return {
        "landscape_manifest": landscape_manifest,
        "potential_manifest": potential_manifest,
        "scenario_manifest": scenario_manifest,
        "solar_rules": solar_rules,
        "wind_rules": wind_rules,
        "missing_data": missing,
        "runtime_ready": not missing,
    }


def region_data_status_rows(region: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label in [
        ("landscape_manifest", "Landskapsanalys"),
        ("potential_manifest", "Potential"),
        ("scenario_manifest", "Scenarier/energimodell"),
    ]:
        rows.append(status_row(label, region.get(key)))

    landscape_manifest = context.get("landscape_manifest") if isinstance(context.get("landscape_manifest"), dict) else {}
    for key, label in [
        ("landscape_geojson", "Landskapshex"),
        ("factor_scores", "Faktorpoäng"),
        ("cluster_profile", "Strukturprofil"),
        ("cluster_sizes", "Strukturstorlekar"),
        ("run_summary", "Körningssammanfattning"),
    ]:
        if key in landscape_manifest:
            rows.append(status_row(label, landscape_manifest.get(key)))

    potential_manifest = context.get("potential_manifest") if isinstance(context.get("potential_manifest"), dict) else {}
    rules = (potential_manifest or {}).get("rules") or {}
    for key, label in [("solar", "Solregler"), ("wind", "Vindregler")]:
        rows.append(status_row(label, rules.get(key)))

    scenario_manifest = context.get("scenario_manifest") if isinstance(context.get("scenario_manifest"), dict) else {}
    energy_model = (scenario_manifest or {}).get("energy_model") or {}
    duckdb_path = ((energy_model.get("duckdb") or {}).get("path")) if isinstance(energy_model, dict) else None
    area_demand_path = ((energy_model.get("area_demand") or {}).get("path")) if isinstance(energy_model, dict) else None
    if duckdb_path:
        rows.append(status_row("DuckDB energimodell", duckdb_path))
    if area_demand_path:
        rows.append(status_row("AreaDemand", area_demand_path))

    geometry_paths = region.get("h3_display_geometries") or {}
    for resolution in available_h3_resolutions(region):
        rows.append(status_row(f"H3 R{resolution}", geometry_paths.get(str(resolution))))
    return rows
