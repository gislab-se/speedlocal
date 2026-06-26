from __future__ import annotations

import json
from io import StringIO
from typing import Any

import h3
import pandas as pd
import streamlit as st

from .geometry import geometry_for_hex, load_h3_display_geometries
from .landscape import cluster_label, load_factor_scores
from .manifests import resolve_repo_path


def _closed_ring(hex_id: str) -> list[list[float]] | None:
    try:
        boundary = h3.cell_to_boundary(str(hex_id))
    except Exception:
        return None
    ring = [[float(lng), float(lat)] for lat, lng in boundary]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring or None


def _factor_refs_for_role(landscape_manifest: dict[str, Any], role: str) -> list[str]:
    semantic_roles = landscape_manifest.get("semantic_roles") or {}
    refs = semantic_roles.get(role) or []
    return [str(ref) for ref in refs if str(ref).startswith("F")]


def _positive_mean(frame: pd.DataFrame, columns: list[str], cap: float) -> pd.Series:
    if not columns:
        return pd.Series(0.0, index=frame.index)
    usable = [col for col in columns if col in frame.columns]
    if not usable:
        return pd.Series(0.0, index=frame.index)
    values = frame[usable].clip(lower=0.0, upper=cap) / float(cap)
    return values.mean(axis=1).fillna(0.0)


def _cluster_term(frame: pd.DataFrame, cluster_ref: str, weight: float) -> pd.Series:
    prefix = "class_km:"
    if not cluster_ref.startswith(prefix) or "class_km" not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    cluster_value = cluster_ref.removeprefix(prefix)
    return (frame["class_km"].astype(str) == cluster_value).astype(float) * float(weight)


def _cluster_role_term(
    frame: pd.DataFrame,
    landscape_manifest: dict[str, Any],
    role: str,
    weight: float,
    fallback_ref: str,
) -> pd.Series:
    semantic_roles = landscape_manifest.get("semantic_roles") or {}
    refs = [str(ref) for ref in semantic_roles.get(role, []) if str(ref).startswith("class_km:")]
    if not refs:
        refs = [fallback_ref]
    terms = [_cluster_term(frame, ref, 1.0) for ref in refs]
    if not terms:
        return pd.Series(0.0, index=frame.index)
    return pd.concat(terms, axis=1).max(axis=1).fillna(0.0) * float(weight)


def _class_for_score(score: float, breaks: list[dict[str, Any]]) -> dict[str, Any]:
    for item in breaks:
        lower = float(item.get("min", 0))
        upper = float(item.get("max", 100))
        if lower <= score < upper or (score == 100 and upper == 100):
            return item
    return breaks[-1] if breaks else {"id": "unknown", "label": "Okänd", "color": "#999999"}


def class_for_score(score: float, breaks: list[dict[str, Any]]) -> dict[str, Any]:
    return _class_for_score(score, breaks)


def _mode_or_first(values: pd.Series) -> Any:
    mode = values.mode(dropna=True)
    if not mode.empty:
        return mode.iloc[0]
    non_null = values.dropna()
    return non_null.iloc[0] if not non_null.empty else None


def _potential_columns(technology: str) -> dict[str, str]:
    return {
        "score": f"{technology}_score",
        "class": f"{technology}_class",
        "label": f"{technology}_class_label",
        "color": f"{technology}_color",
    }


def apply_potential_classes(
    frame: pd.DataFrame,
    technology: str,
    breaks: list[dict[str, Any]],
) -> pd.DataFrame:
    cols = _potential_columns(technology)
    out = frame.copy()
    out[cols["score"]] = out[cols["score"]].clip(lower=0.0, upper=100.0).round(1)
    class_rows = [_class_for_score(float(score), breaks) for score in out[cols["score"]]]
    out[cols["class"]] = [str(item.get("id", "unknown")) for item in class_rows]
    out[cols["label"]] = [str(item.get("label", item.get("id", "unknown"))) for item in class_rows]
    out[cols["color"]] = [str(item.get("color", "#999999")) for item in class_rows]
    return out


def rollup_potential_frame(
    frame: pd.DataFrame,
    target_resolution: int,
    breaks: list[dict[str, Any]],
    technology: str,
    source_resolution: int = 9,
) -> pd.DataFrame:
    cols = _potential_columns(technology)
    if target_resolution == source_resolution:
        out = frame.copy()
        out["h3_resolution"] = source_resolution
        out["source_resolution"] = source_resolution
        out["source_child_count"] = 1
        out["high_potential_share"] = out[cols["class"]].isin(["high", "very_high"]).astype(float)
        return out

    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str).map(lambda value: h3.cell_to_parent(value, target_resolution))
    work["is_high_potential"] = work[cols["class"]].isin(["high", "very_high"]).astype(float)
    aggregations: dict[str, tuple[str, str | Any]] = {
        "source_child_count": (cols["score"], "count"),
        "potential_score": (cols["score"], "mean"),
        "high_potential_share": ("is_high_potential", "mean"),
        "class_km": ("class_km", _mode_or_first),
        "landscape_type": ("landscape_type", _mode_or_first),
    }
    optional_mean_columns = [
        "wind_acceptance",
        "wind_landscape_score",
        "wind_potential_area",
        "wind_rule_blocked",
        "wind_hard_blocked",
    ]
    for column in optional_mean_columns:
        if column in work.columns:
            aggregations[column] = (column, "mean")
    for column in ["wind_active_rule_groups", "wind_blocking_groups"]:
        if column in work.columns:
            aggregations[column] = (column, _mode_or_first)

    grouped = work.groupby("hex_id", as_index=False).agg(**aggregations).sort_values("hex_id")
    grouped[cols["score"]] = grouped.pop("potential_score").round(1)
    grouped["high_potential_share"] = grouped["high_potential_share"].round(3)
    grouped["h3_resolution"] = target_resolution
    grouped["source_resolution"] = source_resolution
    return apply_potential_classes(grouped, technology, breaks)


@st.cache_data(show_spinner=False)
def build_solar_capacity_frame(
    landscape_source_path: str,
    landscape_manifest_json: str,
    solar_rules_json: str,
) -> pd.DataFrame:
    landscape_manifest = json.loads(landscape_manifest_json)
    solar_rules = json.loads(solar_rules_json)
    score_model = solar_rules.get("score_model") or {}
    frame = load_factor_scores(landscape_manifest).copy()

    frame["solar_score_raw"] = float(score_model.get("base_score", 50))
    for term in score_model.get("cluster_terms") or []:
        col = f"cluster_term__{str(term.get('cluster_ref', '')).replace(':', '_')}"
        frame[col] = _cluster_term(frame, str(term.get("cluster_ref", "")), float(term.get("weight", 0)))
        frame["solar_score_raw"] += frame[col]

    cap = float(score_model.get("factor_positive_cap", 2.0))
    for term in score_model.get("role_terms") or []:
        role = str(term.get("role", ""))
        transform = str(term.get("transform", "positive_mean"))
        columns = _factor_refs_for_role(landscape_manifest, role)
        col = f"role_term__{role}"
        if transform == "positive_mean":
            transformed = _positive_mean(frame, columns, cap)
        else:
            transformed = pd.Series(0.0, index=frame.index)
        frame[col] = transformed * float(term.get("weight", 0))
        frame["solar_score_raw"] += frame[col]

    frame["solar_score"] = frame["solar_score_raw"].clip(lower=0.0, upper=100.0).round(1)
    breaks = score_model.get("class_breaks") or []
    class_rows = [_class_for_score(float(score), breaks) for score in frame["solar_score"]]
    frame["solar_class"] = [str(item.get("id", "unknown")) for item in class_rows]
    frame["solar_class_label"] = [str(item.get("label", item.get("id", "unknown"))) for item in class_rows]
    frame["solar_color"] = [str(item.get("color", "#999999")) for item in class_rows]
    if "v10_type_name" in frame.columns:
        frame["landscape_type"] = frame["v10_type_name"].fillna("").astype(str)
    else:
        frame["landscape_type"] = frame["class_km"].apply(lambda value: cluster_label(landscape_manifest, value))
    return frame


def solar_capacity_frame(landscape_manifest: dict[str, Any], solar_rules: dict[str, Any]) -> pd.DataFrame:
    source_value = landscape_manifest.get("factor_scores") or landscape_manifest.get("landscape_geojson") or landscape_manifest.get("factor_scores_geojson")
    if not source_value:
        raise ValueError("Landscape manifest is missing factor_scores or landscape_geojson.")
    source_path = resolve_repo_path(str(source_value))
    if source_path is None:
        raise ValueError("Landscape source path could not be resolved.")
    return build_solar_capacity_frame(
        str(source_path),
        json.dumps(landscape_manifest, sort_keys=True, ensure_ascii=False),
        json.dumps(solar_rules, sort_keys=True, ensure_ascii=False),
    )


@st.cache_data(show_spinner=False)
def load_potential_rollup(path_str: str) -> pd.DataFrame:
    return pd.read_csv(path_str)


def rollup_frame_for_entry(entry: dict[str, Any]) -> pd.DataFrame:
    path = resolve_repo_path(str(entry["path"]))
    if path is None:
        raise ValueError("Rollup entry is missing path.")
    return load_potential_rollup(str(path))


def solar_capacity_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["solar_class", "solar_class_label"], as_index=False)
        .agg(hexagoner=("hex_id", "count"), medelpoang=("solar_score", "mean"))
        .sort_values("medelpoang")
        .assign(medelpoang=lambda data: data["medelpoang"].round(1))
    )


def solar_capacity_by_landscape(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["class_km", "landscape_type"], as_index=False)
        .agg(
            hexagoner=("hex_id", "count"),
            medelpoang=("solar_score", "mean"),
            hog_potential=("solar_class", lambda values: int(values.isin(["high", "very_high"]).sum())),
        )
        .sort_values("class_km")
        .assign(medelpoang=lambda data: data["medelpoang"].round(1))
    )


def potential_summary(frame: pd.DataFrame, technology: str) -> pd.DataFrame:
    cols = _potential_columns(technology)
    return (
        frame.groupby([cols["class"], cols["label"]], as_index=False)
        .agg(hexagoner=("hex_id", "count"), medelpoang=(cols["score"], "mean"))
        .sort_values("medelpoang")
        .assign(medelpoang=lambda data: data["medelpoang"].round(1))
        .rename(columns={cols["class"]: "klass", cols["label"]: "klass_label"})
    )


def potential_by_landscape(frame: pd.DataFrame, technology: str) -> pd.DataFrame:
    cols = _potential_columns(technology)
    return (
        frame.groupby(["class_km", "landscape_type"], as_index=False)
        .agg(
            hexagoner=("hex_id", "count"),
            medelpoang=(cols["score"], "mean"),
            hog_potential=(cols["class"], lambda values: int(values.isin(["high", "very_high"]).sum())),
        )
        .sort_values("class_km")
        .assign(medelpoang=lambda data: data["medelpoang"].round(1))
    )


def wind_potential_frame(
    landscape_manifest: dict[str, Any],
    breaks: list[dict[str, Any]],
    params: dict[str, float],
) -> pd.DataFrame:
    frame = load_factor_scores(landscape_manifest).copy()
    cap = float(params.get("factor_positive_cap", 2.0))
    sensitivity = float(params.get("landscape_sensitivity", 1.0))
    f_settlement = _positive_mean(frame, _factor_refs_for_role(landscape_manifest, "settlement_built_structure"), cap)
    f_coastal = _positive_mean(frame, _factor_refs_for_role(landscape_manifest, "coastal_lowland"), cap)
    f_terrain = _positive_mean(frame, _factor_refs_for_role(landscape_manifest, "steep_valley_relief"), cap)
    f_protected = _positive_mean(frame, _factor_refs_for_role(landscape_manifest, "protected_forest_habitat"), cap)

    frame["wind_score_raw"] = float(params.get("base_score", 54.0))
    frame["wind_score_raw"] += _cluster_role_term(
        frame,
        landscape_manifest,
        "mixed_everyday_matrix",
        float(params.get("everyday_matrix_bonus", 12.0)),
        "class_km:2",
    )
    frame["wind_score_raw"] += f_settlement * float(params.get("infrastructure_bonus", 6.0))
    frame["wind_score_raw"] -= f_settlement * float(params.get("settlement_penalty", 22.0))
    frame["wind_score_raw"] -= f_settlement * float(params.get("road_penalty", 6.0))
    frame["wind_score_raw"] -= f_coastal * float(params.get("coastal_penalty", 14.0)) * sensitivity
    frame["wind_score_raw"] -= f_terrain * float(params.get("terrain_penalty", 10.0)) * sensitivity
    frame["wind_score_raw"] -= f_protected * float(params.get("protected_penalty", 18.0)) * sensitivity
    frame["wind_score"] = frame["wind_score_raw"]
    if "v10_type_name" in frame.columns:
        frame["landscape_type"] = frame["v10_type_name"].fillna("").astype(str)
    else:
        frame["landscape_type"] = frame["class_km"].apply(lambda value: cluster_label(landscape_manifest, value))
    return apply_potential_classes(frame, "wind", breaks)


@st.cache_data(show_spinner=False)
def build_potential_feature_collection_with_geometries(
    frame_json: str,
    technology: str,
    display_geometry_path: str | None,
) -> dict[str, Any]:
    frame = pd.read_json(StringIO(frame_json), orient="records")
    cols = _potential_columns(technology)
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else None
    features: list[dict[str, Any]] = []
    technology_label = {"solar": "Landskapspotential Sol", "wind": "Landskapspotential Vind"}.get(technology, "Potential")
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

        score = float(getattr(row, cols["score"]))
        class_label = str(getattr(row, cols["label"]))
        popup = (
            f"<strong>{hex_id}</strong><br>"
            f"{technology_label}: {class_label} ({score:.1f})<br>"
            f"Landskapstyp: {int(row.class_km)} - {row.landscape_type}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "score": score,
                    "class": str(getattr(row, cols["class"])),
                    "class_label": class_label,
                    "fill": str(getattr(row, cols["color"])),
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def potential_feature_collection(
    frame: pd.DataFrame,
    technology: str,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    cols = _potential_columns(technology)
    map_frame = frame[["hex_id", "class_km", "landscape_type", cols["score"], cols["class"], cols["label"], cols["color"]]]
    return build_potential_feature_collection_with_geometries(
        map_frame.to_json(orient="records", force_ascii=False),
        technology,
        display_geometry_path,
    )


@st.cache_data(show_spinner=False)
def build_solar_capacity_feature_collection(frame_json: str) -> dict[str, Any]:
    return build_solar_capacity_feature_collection_with_geometries(frame_json, None)


@st.cache_data(show_spinner=False)
def build_solar_capacity_feature_collection_with_geometries(
    frame_json: str,
    display_geometry_path: str | None,
) -> dict[str, Any]:
    frame = pd.read_json(StringIO(frame_json), orient="records")
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else None
    features: list[dict[str, Any]] = []
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
        popup = (
            f"<strong>{hex_id}</strong><br>"
            f"Landskapspotential Sol: {row.solar_class_label} ({float(row.solar_score):.1f})<br>"
            f"Landskapstyp: {int(row.class_km)} - {row.landscape_type}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "score": float(row.solar_score),
                    "class": str(row.solar_class),
                    "class_label": str(row.solar_class_label),
                    "fill": str(row.solar_color),
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def solar_capacity_feature_collection(frame: pd.DataFrame, display_geometry_path: str | None = None) -> dict[str, Any]:
    map_frame = frame[["hex_id", "class_km", "landscape_type", "solar_score", "solar_class", "solar_class_label", "solar_color"]]
    return build_solar_capacity_feature_collection_with_geometries(
        map_frame.to_json(orient="records", force_ascii=False),
        display_geometry_path,
    )
