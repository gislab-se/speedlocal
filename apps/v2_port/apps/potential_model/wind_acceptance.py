from __future__ import annotations

import json
from io import StringIO
from typing import Any

import h3
import pandas as pd
import streamlit as st

from acceptance_model.layers import distance_table_for_layer, load_registry

from .geometry import geometry_for_hex, load_h3_display_geometries
from .potential import apply_potential_classes, rollup_potential_frame, wind_potential_frame


SOURCE_RESOLUTION = 10
POTENTIAL_MIN_SCORE = 45.0

WIND_GROUP_LAYER_DEFAULTS: dict[str, list[str]] = {
    "settlement": [
        "population_points",
        "buildings_low",
        "buildings_high",
        "built_centre",
        "built_low_selection",
    ],
    "transport": ["roads_medium", "roads_large"],
    "electrical": [
        "high_voltage_lines",
        "underground_cables",
        "power_substations",
        "existing_wind_turbines",
    ],
    "protected": [
        "protected_areas",
        "natura_designated_land",
        "natura_bird_protection",
        "natura_habitat_areas",
        "natura_ramsar",
        "nature_wildlife_reserve",
        "nature_area_forest",
    ],
    "coastal": ["coastal_zone_3km", "strand_protection"],
    "culture": [
        "cultural_preservation",
        "valuable_cultural_environment",
        "cultural_conservation_values",
    ],
    "reindeer": [
        "reindeer_grazing_merged",
        "reindeer_migration_routes",
    ],
    "aviation_approach": ["aviation_approach_zones"],
    "aviation_bird": ["aviation_bird_collision"],
    "military": ["military_areas"],
}

GROUP_PARAM_MAP = {
    "settlement": "settlement_distance_m",
    "transport": "road_distance_m",
    "electrical": "grid_max_distance_m",
    "protected": "protected_buffer_m",
    "coastal": "coastal_buffer_m",
    "culture": "culture_buffer_m",
    "reindeer": "reindeer_buffer_m",
    "aviation_approach": "aviation_approach_buffer_m",
    "aviation_bird": "aviation_bird_distance_m",
    "military": "military_buffer_m",
}

GROUP_LABELS = {
    "settlement": "Boende och bebyggelse",
    "transport": "Vagar och transport",
    "electrical": "Elinfrastruktur",
    "protected": "Skyddad natur",
    "coastal": "Kust och strand",
    "culture": "Kulturmiljo",
    "reindeer": "Rennaring / reindrift",
    "aviation_approach": "Inflygning",
    "aviation_bird": "Fagelkollision",
    "military": "Militara omraden",
}

HARD_EXCLUSION_GROUPS = {"protected", "coastal", "culture", "reindeer", "aviation_approach", "military"}
ALWAYS_ACTIVE_GROUPS = {"settlement", "transport", "electrical"}


def _iter_geojson_geometries(geojson: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(geojson, dict):
        return []

    geojson_type = str(geojson.get("type") or "")
    if geojson_type == "FeatureCollection":
        geometries: list[dict[str, Any]] = []
        for feature in geojson.get("features") or []:
            geometry = feature.get("geometry") if isinstance(feature, dict) else None
            if isinstance(geometry, dict) and geometry.get("coordinates"):
                geometries.append(geometry)
        return geometries

    if geojson_type == "Feature":
        geometry = geojson.get("geometry")
        if isinstance(geometry, dict) and geometry.get("coordinates"):
            return [geometry]
        return []

    if geojson.get("coordinates"):
        return [geojson]
    return []


def normalize_group_layer_map(
    group_layer_map: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for group_id, default_layer_ids in WIND_GROUP_LAYER_DEFAULTS.items():
        requested = (group_layer_map or {}).get(group_id, default_layer_ids)
        requested_ids = [str(layer_id) for layer_id in (requested or [])]
        normalized[group_id] = [layer_id for layer_id in requested_ids if layer_id in default_layer_ids]
    return normalized


def _closed_ring(hex_id: str) -> list[list[float]] | None:
    try:
        boundary = h3.cell_to_boundary(str(hex_id))
    except Exception:
        return None
    ring = [[float(lng), float(lat)] for lat, lng in boundary]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring or None


def _h3_resolution_for_series(hex_ids: pd.Series) -> int | None:
    resolutions: list[int] = []
    for value in hex_ids.dropna().astype(str).head(250):
        try:
            resolutions.append(int(h3.get_resolution(value)))
        except Exception:
            continue
    if not resolutions:
        return None
    return int(pd.Series(resolutions).mode().iloc[0])


def _group_distance_frame(
    hex_ids: pd.Series,
    registry_meta: dict[str, Any],
    layer_ids: list[str],
) -> pd.DataFrame:
    work = pd.DataFrame({"hex_id": hex_ids.astype(str).unique()})
    source_resolution = _h3_resolution_for_series(work["hex_id"])
    distance_cols: list[str] = []
    overlap_cols: list[str] = []

    for layer_id in layer_ids:
        layer_frame = distance_table_for_layer(registry_meta, layer_id)
        if layer_frame.empty:
            continue
        layer_frame = layer_frame.copy()
        distance_resolution = _h3_resolution_for_series(layer_frame["hex_id"])
        join_col = "hex_id"
        if source_resolution is not None and distance_resolution is not None and source_resolution != distance_resolution:
            join_col = "distance_hex_id"
            if source_resolution > distance_resolution:
                work[join_col] = work["hex_id"].map(lambda value: h3.cell_to_parent(str(value), distance_resolution))
            else:
                work[join_col] = work["hex_id"]
                layer_frame[join_col] = layer_frame["hex_id"].map(lambda value: h3.cell_to_parent(str(value), source_resolution))
                layer_frame = (
                    layer_frame.groupby(join_col, as_index=False)
                    .agg(distance_m=("distance_m", "min"), intersects=("intersects", "max"))
                )
            if join_col not in layer_frame.columns:
                layer_frame[join_col] = layer_frame["hex_id"]

        distance_col = f"{layer_id}__distance_m"
        overlap_col = f"{layer_id}__intersects"
        renamed = layer_frame.rename(columns={"distance_m": distance_col, "intersects": overlap_col})
        work = work.merge(renamed[[join_col, distance_col, overlap_col]], on=join_col, how="left")
        distance_cols.append(distance_col)
        overlap_cols.append(overlap_col)

    if not distance_cols:
        return pd.DataFrame(columns=["hex_id", "min_distance_m", "any_intersection"])

    out = work[["hex_id"]].copy()
    out["min_distance_m"] = work[distance_cols].min(axis=1, skipna=True)
    out["any_intersection"] = work[overlap_cols].fillna(False).astype(bool).any(axis=1)
    return out


def _distance_conflict_acceptance(
    min_distance_m: pd.Series,
    threshold_m: float,
    any_intersection: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    distance = pd.to_numeric(min_distance_m, errors="coerce")
    if threshold_m <= 0:
        blocked = any_intersection.astype(bool)
        return (~blocked).astype(float), blocked
    ramp_end = max(float(threshold_m * 2), float(threshold_m + 1))
    acceptance = ((distance - threshold_m) / (ramp_end - threshold_m)).clip(lower=0.0, upper=1.0).fillna(0.0)
    acceptance.loc[any_intersection.astype(bool)] = 0.0
    blocked = any_intersection.astype(bool) | (distance <= float(threshold_m))
    return acceptance, blocked


def _proximity_acceptance(
    min_distance_m: pd.Series,
    threshold_m: float,
    any_intersection: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    threshold = max(float(threshold_m), 1.0)
    distance = pd.to_numeric(min_distance_m, errors="coerce")
    acceptance = (1.0 - (distance / threshold)).clip(lower=0.0, upper=1.0).fillna(0.0)
    acceptance.loc[any_intersection.astype(bool)] = 1.0
    blocked = ~any_intersection.astype(bool) & (distance > threshold)
    return acceptance, blocked


def _hard_exclusion_acceptance(
    min_distance_m: pd.Series,
    threshold_m: float,
    any_intersection: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    distance = pd.to_numeric(min_distance_m, errors="coerce")
    if threshold_m <= 0:
        blocked = any_intersection.astype(bool)
    else:
        blocked = any_intersection.astype(bool) | (distance <= float(threshold_m))
    return (~blocked).astype(float), blocked


def _acceptance_for_kind(
    analysis_kind: str,
    min_distance_m: pd.Series,
    threshold_m: float,
    any_intersection: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    if analysis_kind == "proximity_feasibility":
        return _proximity_acceptance(min_distance_m, threshold_m, any_intersection)
    if analysis_kind == "distance_conflict":
        return _distance_conflict_acceptance(min_distance_m, threshold_m, any_intersection)
    return _hard_exclusion_acceptance(min_distance_m, threshold_m, any_intersection)


def wind_acceptance_group_summary() -> pd.DataFrame:
    groups, layers, _ = load_registry()
    rows: list[dict[str, Any]] = []
    for group_id, layer_ids in WIND_GROUP_LAYER_DEFAULTS.items():
        group = groups.get(group_id)
        if group is None:
            continue
        rows.append(
            {
                "regelgrupp": GROUP_LABELS.get(group_id, group.label),
                "typ": group.analysis_kind,
                "lager": len([layer_id for layer_id in layer_ids if layer_id in layers]),
                "kallager": ", ".join(layers[layer_id].label for layer_id in layer_ids if layer_id in layers),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _build_wind_acceptance_frame_cached(
    factor_scores_path: str,
    landscape_manifest_json: str,
    score_params_json: str,
    ui_params_json: str,
    breaks_json: str,
    group_layer_map_json: str,
) -> pd.DataFrame:
    import json

    landscape_manifest = json.loads(landscape_manifest_json)
    score_params = json.loads(score_params_json)
    ui_params = json.loads(ui_params_json)
    breaks = json.loads(breaks_json)
    group_layer_map = normalize_group_layer_map(json.loads(group_layer_map_json))

    base = wind_potential_frame(landscape_manifest, breaks, score_params).copy()
    groups, _, registry_meta = load_registry()
    acceptance_cols: list[str] = []
    blocked_cols: list[str] = []
    hard_blocked_cols: list[str] = []
    active_labels: list[str] = []

    for group_id, layer_ids in group_layer_map.items():
        group = groups.get(group_id)
        param_key = GROUP_PARAM_MAP.get(group_id)
        if group is None or param_key is None:
            continue
        if not layer_ids:
            continue

        threshold_m = float(ui_params.get(param_key, group.analysis_default_m))
        distance_frame = _group_distance_frame(base["hex_id"], registry_meta, layer_ids)
        if distance_frame.empty:
            continue

        acceptance, blocked = _acceptance_for_kind(
            group.analysis_kind,
            distance_frame["min_distance_m"],
            threshold_m,
            distance_frame["any_intersection"],
        )

        group_label = GROUP_LABELS.get(group_id, group.label)
        active_labels.append(group_label)
        group_acceptance_col = f"{group_id}_acceptance"
        group_blocked_col = f"{group_id}_blocked"
        group_distance_col = f"{group_id}_distance_m"

        group_result = distance_frame[["hex_id", "min_distance_m"]].copy()
        group_result[group_acceptance_col] = acceptance.astype(float)
        group_result[group_blocked_col] = blocked.astype(bool)
        group_result = group_result.rename(columns={"min_distance_m": group_distance_col})
        base = base.merge(group_result, on="hex_id", how="left")

        base[group_acceptance_col] = base[group_acceptance_col].fillna(0.0)
        base[group_blocked_col] = base[group_blocked_col].fillna(False).astype(bool)
        acceptance_cols.append(group_acceptance_col)
        blocked_cols.append(group_blocked_col)
        if group_id in HARD_EXCLUSION_GROUPS:
            hard_blocked_cols.append(group_blocked_col)

    if acceptance_cols:
        base["wind_acceptance"] = base[acceptance_cols].min(axis=1, skipna=True).fillna(0.0)
    else:
        base["wind_acceptance"] = 1.0

    if blocked_cols:
        base["wind_rule_blocked"] = base[blocked_cols].any(axis=1)
    else:
        base["wind_rule_blocked"] = False

    if hard_blocked_cols:
        base["wind_hard_blocked"] = base[hard_blocked_cols].any(axis=1)
    else:
        base["wind_hard_blocked"] = False

    base["wind_landscape_score"] = base["wind_score"].astype(float)
    base["wind_score"] = (base["wind_landscape_score"] * base["wind_acceptance"]).clip(lower=0.0, upper=100.0)
    base.loc[base["wind_hard_blocked"], "wind_score"] = 0.0
    base["wind_potential_area"] = (base["wind_score"] >= POTENTIAL_MIN_SCORE) & (~base["wind_hard_blocked"])
    base["wind_active_rule_groups"] = ", ".join(active_labels)
    base["wind_blocking_groups"] = base.apply(
        lambda row: ", ".join(
            GROUP_LABELS.get(col.removesuffix("_blocked"), col.removesuffix("_blocked"))
            for col in blocked_cols
            if bool(row.get(col, False))
        ),
        axis=1,
    )
    return apply_potential_classes(base, "wind", breaks)


def wind_acceptance_potential_frame(
    landscape_manifest: dict[str, Any],
    breaks: list[dict[str, Any]],
    score_params: dict[str, float],
    ui_params: dict[str, float],
    group_layer_map: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    import json

    source_value = landscape_manifest.get("factor_scores") or landscape_manifest.get("landscape_geojson") or landscape_manifest.get("factor_scores_geojson")
    if not source_value:
        raise ValueError("Landscape manifest is missing factor_scores or landscape_geojson.")
    from .manifests import resolve_repo_path

    path = resolve_repo_path(str(source_value))
    if path is None:
        raise ValueError("Landscape source path could not be resolved.")
    return _build_wind_acceptance_frame_cached(
        str(path),
        json.dumps(landscape_manifest, sort_keys=True, ensure_ascii=False),
        json.dumps(score_params, sort_keys=True, ensure_ascii=False),
        json.dumps(ui_params, sort_keys=True, ensure_ascii=False),
        json.dumps(breaks, sort_keys=True, ensure_ascii=False),
        json.dumps(normalize_group_layer_map(group_layer_map), sort_keys=True, ensure_ascii=False),
    )


def wind_acceptance_rollup_frame(
    source_frame: pd.DataFrame,
    target_resolution: int,
    breaks: list[dict[str, Any]],
) -> pd.DataFrame:
    source_resolution = _h3_resolution_for_series(source_frame["hex_id"]) or SOURCE_RESOLUTION
    return rollup_potential_frame(source_frame, target_resolution, breaks, "wind", source_resolution)


@st.cache_data(show_spinner=False)
def _build_wind_vector_feature_collection(
    frame_json: str,
    display_geometry_path: str | None,
    only_potential_area: bool,
) -> dict[str, Any]:
    frame = pd.read_json(StringIO(frame_json), orient="records")
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else None
    features: list[dict[str, Any]] = []
    if only_potential_area and "wind_potential_area" in frame.columns:
        frame = frame.loc[frame["wind_potential_area"].astype(bool)].copy()

    for row in frame.itertuples(index=False):
        hex_id = str(row.hex_id)
        geometry = geometry_for_hex(hex_id, display_geometries)
        if geometry is None and display_geometry_path:
            continue
        if geometry is None:
            ring = _closed_ring(hex_id)
            if ring is None:
                continue
            geometry = {"type": "Polygon", "coordinates": [ring]}
        if not geometry.get("coordinates"):
            continue

        blocking = str(getattr(row, "wind_blocking_groups", "") or "Inga")
        score = float(getattr(row, "wind_score", 0.0))
        acceptance = float(getattr(row, "wind_acceptance", 0.0))
        popup = (
            f"<strong>Vindpotentialyta</strong><br>"
            f"H3-kalla: {hex_id}<br>"
            f"Potential: {getattr(row, 'wind_class_label', '')} ({score:.1f})<br>"
            f"Regelacceptans: {acceptance:.2f}<br>"
            f"Blockerande grupper: {blocking}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "score": score,
                    "class": str(getattr(row, "wind_class", "")),
                    "class_label": str(getattr(row, "wind_class_label", "")),
                    "fill": str(getattr(row, "wind_color", "#999999")),
                    "popup": popup,
                    "vector_role": "wind_candidate_area",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def wind_vector_feature_collection(
    source_frame: pd.DataFrame,
    display_geometry_path: str | None,
    only_potential_area: bool = True,
) -> dict[str, Any]:
    map_columns = [
        "hex_id",
        "wind_score",
        "wind_class",
        "wind_class_label",
        "wind_color",
        "wind_acceptance",
        "wind_potential_area",
        "wind_blocking_groups",
    ]
    available = [column for column in map_columns if column in source_frame.columns]
    return _build_wind_vector_feature_collection(
        source_frame[available].to_json(orient="records", force_ascii=False),
        display_geometry_path,
        only_potential_area,
    )


@st.cache_data(show_spinner=False)
def _build_runtime_combined_hex_frame(
    combined_geojson_json: str,
    target_resolution: int,
    breaks_json: str,
) -> pd.DataFrame:
    combined_geojson = json.loads(combined_geojson_json)
    breaks = json.loads(breaks_json)
    sample_resolution = max(int(target_resolution), min(int(target_resolution) + 2, SOURCE_RESOLUTION + 1))
    covered_children_by_parent: dict[str, set[str]] = {}

    for geometry in _iter_geojson_geometries(combined_geojson):
        try:
            child_hexes = h3.geo_to_cells(geometry, sample_resolution)
        except Exception:
            continue
        for child_hex in child_hexes:
            child_hex_id = str(child_hex)
            parent_hex = child_hex_id if sample_resolution == int(target_resolution) else str(h3.cell_to_parent(child_hex_id, int(target_resolution)))
            covered_children_by_parent.setdefault(parent_hex, set()).add(child_hex_id)

    rows: list[dict[str, Any]] = []
    for hex_id, child_hexes in sorted(covered_children_by_parent.items()):
        total_children = max(1, int(h3.cell_to_children_size(hex_id, sample_resolution)))
        share = min(1.0, len(child_hexes) / float(total_children))
        rows.append(
            {
                "hex_id": hex_id,
                "wind_score": round(share * 100.0, 1),
                "wind_acceptance": round(share, 3),
                "wind_potential_area": bool(share > 0.0),
                "wind_rule_blocked": False,
                "wind_hard_blocked": False,
                "wind_blocking_groups": "",
                "wind_active_rule_groups": "runtime_combined",
                "source_child_count": len(child_hexes),
                "source_resolution": int(sample_resolution),
                "h3_resolution": int(target_resolution),
            }
        )

    frame = pd.DataFrame(
        rows,
        columns=[
            "hex_id",
            "wind_score",
            "wind_acceptance",
            "wind_potential_area",
            "wind_rule_blocked",
            "wind_hard_blocked",
            "wind_blocking_groups",
            "wind_active_rule_groups",
            "source_child_count",
            "source_resolution",
            "h3_resolution",
        ],
    )
    if frame.empty:
        return apply_potential_classes(frame, "wind", breaks)

    frame["high_potential_share"] = frame["wind_score"].div(100.0).round(3)
    return apply_potential_classes(frame.sort_values("hex_id").reset_index(drop=True), "wind", breaks)


def runtime_combined_hex_frame(
    combined_geojson: dict[str, Any],
    target_resolution: int,
    breaks: list[dict[str, Any]],
) -> pd.DataFrame:
    return _build_runtime_combined_hex_frame(
        json.dumps(combined_geojson, sort_keys=True, ensure_ascii=False),
        int(target_resolution),
        json.dumps(breaks, sort_keys=True, ensure_ascii=False),
    )


def wind_candidate_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"candidate_cells": 0, "candidate_share": 0.0, "mean_acceptance": 0.0}
    candidate = frame.get("wind_potential_area", pd.Series(False, index=frame.index)).astype(bool)
    return {
        "candidate_cells": int(candidate.sum()),
        "candidate_share": float(candidate.mean() * 100.0),
        "mean_acceptance": float(frame.get("wind_acceptance", pd.Series(0.0, index=frame.index)).mean()),
    }
