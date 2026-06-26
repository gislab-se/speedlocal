from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import h3
import pandas as pd
import streamlit as st

from .geometry import geometry_for_hex, load_h3_display_geometries
from .manifests import resolve_repo_path


CLUSTER_COLORS = {
    "1": "#6E7C91",
    "2": "#C58B43",
    "3": "#B7C97A",
    "4": "#E8C49A",
    "5": "#7A5D72",
    "6": "#8FA7A5",
    "7": "#4E7A45",
    "8": "#C89A5A",
}


V10_TYPE_COLORS = {
    "LT01": "#627A93",
    "LT02": "#D7B882",
    "LT03": "#A35A3C",
    "LT04": "#2E6B3E",
    "LT05": "#C7D84C",
}


FACTOR_STOPS = [
    (-2.0, "#355c7d"),
    (-1.0, "#6c8fb1"),
    (0.0, "#f1efe7"),
    (1.0, "#d99048"),
    (2.0, "#8f3f2f"),
]


def _manifest_path(manifest: dict[str, Any], key: str) -> Path:
    path = resolve_repo_path(str(manifest[key]))
    if path is None:
        raise ValueError(f"Missing path for manifest key: {key}")
    return path


def _optional_manifest_path(manifest: dict[str, Any], *keys: str) -> Path | None:
    for key in keys:
        value = manifest.get(key)
        if not value:
            continue
        path = resolve_repo_path(str(value))
        if path is not None and path.exists():
            return path
    return None


@st.cache_data(show_spinner=False)
def _read_csv(path_str: str) -> pd.DataFrame:
    return pd.read_csv(path_str)


@st.cache_data(show_spinner=False)
def _read_landscape_geojson_frame(path_str: str) -> pd.DataFrame:
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for feature in data.get("features") or []:
        props = dict(feature.get("properties") or {})
        if not props.get("hex_id"):
            continue
        if "class_km" not in props and "class_k8" in props:
            props["class_km"] = props["class_k8"]
        if "v10_type_id" not in props and props.get("landscape_type_id"):
            props["v10_type_id"] = props.get("landscape_type_id")
        if "v10_type_name" not in props and props.get("landscape_type_name"):
            props["v10_type_name"] = props.get("landscape_type_name")
        if "landscape_type" not in props:
            props["landscape_type"] = (
                props.get("landscape_type_name")
                or props.get("landscape_type_id")
                or props.get("v10_type_name")
                or props.get("v10_type_id")
                or props.get("class_km")
            )
        rows.append(props)

    frame = pd.DataFrame(rows)
    for column in ["class_km", "class_k8", "F1", "F2", "F3", "F4", "F5"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_factor_scores(manifest: dict[str, Any]) -> pd.DataFrame:
    path = _optional_manifest_path(manifest, "factor_scores", "landscape_geojson", "factor_scores_geojson")
    if path is None:
        raise ValueError("Landscape manifest is missing factor_scores or landscape_geojson.")
    if path.suffix.lower() in {".geojson", ".json"}:
        return _read_landscape_geojson_frame(str(path))
    return _read_csv(str(path))


def load_cluster_profile(manifest: dict[str, Any]) -> pd.DataFrame:
    return _read_csv(str(_manifest_path(manifest, "cluster_profile")))


def load_cluster_sizes(manifest: dict[str, Any]) -> pd.DataFrame:
    return _read_csv(str(_manifest_path(manifest, "cluster_sizes")))


def load_run_summary(manifest: dict[str, Any]) -> pd.DataFrame:
    path = resolve_repo_path(manifest.get("run_summary"))
    if path is None or not path.exists():
        return pd.DataFrame(columns=["metric", "value"])
    return _read_csv(str(path))


def factor_columns(manifest: dict[str, Any], frame: pd.DataFrame | None = None) -> list[str]:
    labels = manifest.get("factor_labels") or {}
    if labels:
        return list(labels.keys())
    if frame is None:
        frame = load_factor_scores(manifest)
    return [col for col in frame.columns if col.startswith("F") and col[1:].isdigit()]


def landscape_source_resolution(manifest: dict[str, Any]) -> int:
    return int(manifest.get("source_h3_resolution", manifest.get("default_h3_resolution", 9)))


def _mode_or_first(values: pd.Series) -> Any:
    mode = values.mode(dropna=True)
    if not mode.empty:
        return mode.iloc[0]
    non_null = values.dropna()
    return non_null.iloc[0] if not non_null.empty else None


@st.cache_data(show_spinner=False)
def landscape_frame_for_resolution(manifest: dict[str, Any], resolution: int) -> pd.DataFrame:
    source_resolution = landscape_source_resolution(manifest)
    frame = load_factor_scores(manifest).copy()
    if int(resolution) >= source_resolution:
        return frame

    factors = factor_columns(manifest, frame)
    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str).map(lambda value: h3.cell_to_parent(value, int(resolution)))
    aggregations: dict[str, tuple[str, str | Any]] = {
        factor: (factor, "mean")
        for factor in factors
        if factor in work.columns
    }
    aggregations["class_km"] = ("class_km", _mode_or_first)
    for column in [
        "class_k8",
        "v10_type_id",
        "v10_type_name",
        "v10_type_name_en",
        "v10_confidence",
        "v10_rule",
        "v10_rule_en",
        "landscape_type",
    ]:
        if column in work.columns:
            aggregations[column] = (column, _mode_or_first)
    return (
        work.groupby("hex_id", as_index=False)
        .agg(**aggregations)
        .sort_values("hex_id")
    )


def cluster_label(manifest: dict[str, Any], class_value: object) -> str:
    labels = manifest.get("cluster_labels") or {}
    key = str(int(class_value)) if pd.notna(class_value) else "?"
    return labels.get(key, f"Cluster {key}")


def factor_label(manifest: dict[str, Any], factor: str) -> str:
    labels = manifest.get("factor_labels") or {}
    return labels.get(factor, factor)


def landscape_type_display_colors(manifest: dict[str, Any] | None = None) -> dict[str, str]:
    colors = dict(V10_TYPE_COLORS)
    if not manifest:
        return colors
    manifest_colors = manifest.get("landscape_type_colors") or {}
    manifest_labels = manifest.get("landscape_type_labels") or {}
    for key, value in manifest_colors.items():
        colors.setdefault(str(key), str(value))
    for key in manifest_labels:
        colors.setdefault(str(key), "#999999")
    return colors


def cluster_summary(manifest: dict[str, Any]) -> pd.DataFrame:
    profile = load_cluster_profile(manifest)
    sizes = load_cluster_sizes(manifest)
    merged = profile.merge(sizes, on="class_km", how="left", suffixes=("", "_size"))
    merged["landskapstyp"] = merged["class_km"].apply(lambda value: cluster_label(manifest, value))
    labels = manifest.get("factor_labels") or {}
    rename = {factor: f"{factor} - {label}" for factor, label in labels.items() if factor in merged.columns}
    ordered = ["class_km", "landskapstyp", "n_hex_size", "share", *[col for col in labels if col in merged.columns]]
    ordered = [col for col in ordered if col in merged.columns]
    return merged[ordered].rename(columns={"class_km": "kluster", "n_hex_size": "hexagoner", **rename})


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    stripped = value.lstrip("#")
    return tuple(int(stripped[idx : idx + 2], 16) for idx in (0, 2, 4))


def _interpolate_color(value: float, stops: list[tuple[float, str]]) -> str:
    if pd.isna(value):
        return "#d9d9d9"
    if value <= stops[0][0]:
        return stops[0][1]
    if value >= stops[-1][0]:
        return stops[-1][1]
    for idx in range(1, len(stops)):
        left_value, left_hex = stops[idx - 1]
        right_value, right_hex = stops[idx]
        if value <= right_value:
            share = (float(value) - left_value) / (right_value - left_value)
            left_rgb = _hex_to_rgb(left_hex)
            right_rgb = _hex_to_rgb(right_hex)
            rgb = tuple(int(round(left_rgb[channel] + (right_rgb[channel] - left_rgb[channel]) * share)) for channel in range(3))
            return _rgb_to_hex(rgb)
    return stops[-1][1]


def _closed_ring(hex_id: str) -> list[list[float]] | None:
    try:
        boundary = h3.cell_to_boundary(str(hex_id))
    except Exception:
        return None
    ring = [[float(lng), float(lat)] for lat, lng in boundary]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring or None


@st.cache_data(show_spinner=False)
def build_landscape_feature_collection_from_frame(
    frame_json: str,
    factor_labels_json: str,
    cluster_labels_json: str,
    factor: str,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    frame = pd.read_json(StringIO(frame_json), orient="records")
    factor_labels = json.loads(factor_labels_json)
    cluster_labels = json.loads(cluster_labels_json)
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else None
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        hex_id = str(getattr(row, "hex_id"))
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
        class_raw = getattr(row, "class_km")
        cluster_key = str(int(class_raw)) if pd.notna(class_raw) else "?"
        factor_value = float(getattr(row, factor)) if factor in frame.columns and pd.notna(getattr(row, factor)) else None
        cluster_name = cluster_labels.get(cluster_key, f"Cluster {cluster_key}")
        factor_name = factor_labels.get(factor, factor)
        popup = (
            f"<strong>{hex_id}</strong><br>"
            f"Landskapstyp: {cluster_key} - {cluster_name}<br>"
            f"{factor_name}: {factor_value:.2f}" if factor_value is not None else f"<strong>{hex_id}</strong><br>Landskapstyp: {cluster_key} - {cluster_name}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "cluster": cluster_key,
                    "cluster_label": cluster_name,
                    "cluster_fill": CLUSTER_COLORS.get(cluster_key, "#999999"),
                    "factor": factor,
                    "factor_label": factor_name,
                    "factor_value": factor_value,
                    "factor_fill": _interpolate_color(float(factor_value), FACTOR_STOPS) if factor_value is not None else "#d9d9d9",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@st.cache_data(show_spinner=False)
def build_landscape_feature_collection(
    factor_scores_path: str,
    factor_labels_json: str,
    cluster_labels_json: str,
    factor: str,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    frame = _read_csv(factor_scores_path)
    factor_labels = json.loads(factor_labels_json)
    cluster_labels = json.loads(cluster_labels_json)
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else None
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        hex_id = str(getattr(row, "hex_id"))
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
        class_raw = getattr(row, "class_km")
        cluster_key = str(int(class_raw)) if pd.notna(class_raw) else "?"
        factor_value = float(getattr(row, factor)) if factor in frame.columns and pd.notna(getattr(row, factor)) else None
        cluster_name = cluster_labels.get(cluster_key, f"Cluster {cluster_key}")
        factor_name = factor_labels.get(factor, factor)
        popup = (
            f"<strong>{hex_id}</strong><br>"
            f"Landskapstyp: {cluster_key} - {cluster_name}<br>"
            f"{factor_name}: {factor_value:.2f}" if factor_value is not None else f"<strong>{hex_id}</strong><br>Landskapstyp: {cluster_key} - {cluster_name}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "cluster": cluster_key,
                    "cluster_label": cluster_name,
                    "cluster_fill": CLUSTER_COLORS.get(cluster_key, "#999999"),
                    "factor": factor,
                    "factor_label": factor_name,
                    "factor_value": factor_value,
                    "factor_fill": _interpolate_color(float(factor_value), FACTOR_STOPS) if factor_value is not None else "#d9d9d9",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def feature_collection_for_manifest(
    manifest: dict[str, Any],
    factor: str,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    return feature_collection_for_frame(manifest, load_factor_scores(manifest), factor, display_geometry_path)


def feature_collection_for_frame(
    manifest: dict[str, Any],
    frame: pd.DataFrame,
    factor: str,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    return build_landscape_feature_collection_from_frame(
        frame.to_json(orient="records", force_ascii=False),
        json.dumps(manifest.get("factor_labels") or {}, sort_keys=True, ensure_ascii=False),
        json.dumps(manifest.get("cluster_labels") or {}, sort_keys=True, ensure_ascii=False),
        factor,
        display_geometry_path,
    )


@st.cache_data(show_spinner=False)
def build_landscape_type_feature_collection_from_frame(
    frame_json: str,
    type_labels_json: str,
    type_colors_json: str,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    frame = pd.read_json(StringIO(frame_json), orient="records")
    type_labels = json.loads(type_labels_json)
    type_colors = json.loads(type_colors_json)
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else None
    features: list[dict[str, Any]] = []

    for row in frame.itertuples(index=False):
        hex_id = str(getattr(row, "hex_id"))
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

        type_id = str(getattr(row, "v10_type_id", "") or "LT?")
        type_name = str(getattr(row, "v10_type_name", "") or type_labels.get(type_id, type_id))
        class_raw = getattr(row, "class_km", None)
        cluster_key = str(int(class_raw)) if pd.notna(class_raw) else "?"
        confidence = str(getattr(row, "v10_confidence", "") or "")
        rule = str(getattr(row, "v10_rule", "") or "")
        popup = (
            f"<strong>{hex_id}</strong><br>"
            f"Landskapstyp: {type_name}<br>"
            f"Landskapsstruktur: {cluster_key}<br>"
            f"Säkerhet: {confidence}"
        )
        if rule:
            popup = f"{popup}<br>{rule}"

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "v10_type_id": type_id,
                    "v10_type_name": type_name,
                    "v9_cluster": cluster_key,
                    "confidence": confidence,
                    "landscape_type_fill": type_colors.get(type_id, "#999999"),
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def landscape_type_feature_collection_for_frame(
    manifest: dict[str, Any],
    frame: pd.DataFrame,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    return build_landscape_type_feature_collection_from_frame(
        frame.to_json(orient="records", force_ascii=False),
        json.dumps(manifest.get("landscape_type_labels") or {}, sort_keys=True, ensure_ascii=False),
        json.dumps(landscape_type_display_colors(manifest), sort_keys=True, ensure_ascii=False),
        display_geometry_path,
    )
