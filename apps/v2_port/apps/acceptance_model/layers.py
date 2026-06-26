from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from .i18n import acceptance_class_label, cluster_label, reference_layer_name, ui_text

try:
    import h3
except Exception:  # pragma: no cover
    h3 = None


@dataclass(frozen=True)
class GroupSpec:
    id: str
    label: str
    analysis_kind: str
    analysis_label: str
    analysis_min_m: int
    analysis_max_m: int
    analysis_step_m: int
    analysis_default_m: int
    blend_default: int
    group_color: tuple[int, int, int]
    interpretation: str


@dataclass(frozen=True)
class SourceLayerSpec:
    id: str
    group_id: str
    layer_key: str
    label: str
    note: str
    source_color: tuple[int, int, int]
    point_radius: int


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def port_root() -> Path:
    return Path(__file__).resolve().parents[2]


def registry_path() -> Path:
    region_id = str(st.session_state.get("potential_selected_region_id", "trondelag") or "trondelag").lower()
    if region_id == "trondelag":
        trondelag_path = Path(__file__).resolve().with_name("registry_trondelag.json")
        if trondelag_path.exists():
            return trondelag_path
    if region_id == "bornholm":
        bornholm_path = Path(__file__).resolve().with_name("registry_bornholm.json")
        if bornholm_path.exists():
            return bornholm_path
    raise FileNotFoundError(f"No SpeedLocal acceptance registry is enabled for region: {region_id}")


@st.cache_data(show_spinner=False)
def _read_json(path_str: str) -> dict[str, Any]:
    with Path(path_str).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_repo_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path
    repo_path = repo_root() / path
    if repo_path.exists():
        return repo_path
    port_path = port_root() / path
    if port_path.exists():
        return port_path
    return repo_path


def load_registry() -> tuple[dict[str, GroupSpec], dict[str, SourceLayerSpec], dict[str, Any]]:
    raw = _read_json(str(registry_path()))
    groups = {
        item["id"]: GroupSpec(
            id=item["id"],
            label=item["label"],
            analysis_kind=item["analysis_kind"],
            analysis_label=item["analysis_label"],
            analysis_min_m=int(item["analysis_min_m"]),
            analysis_max_m=int(item["analysis_max_m"]),
            analysis_step_m=int(item["analysis_step_m"]),
            analysis_default_m=int(item["analysis_default_m"]),
            blend_default=int(item["blend_default"]),
            group_color=tuple(int(v) for v in item["group_color"]),
            interpretation=item["interpretation"],
        )
        for item in raw["groups"]
    }
    layers = {
        item["id"]: SourceLayerSpec(
            id=item["id"],
            group_id=item["group_id"],
            layer_key=item["layer_key"],
            label=item["label"],
            note=item["note"],
            source_color=tuple(int(v) for v in item["source_color"]),
            point_radius=int(item["point_radius"]),
        )
        for item in raw["layers"]
    }
    return groups, layers, raw


def ordered_groups() -> list[GroupSpec]:
    groups, _, raw = load_registry()
    return [groups[item["id"]] for item in raw["groups"]]


def ordered_layers() -> list[SourceLayerSpec]:
    _, layers, raw = load_registry()
    return [layers[item["id"]] for item in raw["layers"]]


@st.cache_data(show_spinner=False)
def load_acceptance_hex_table(gpkg_path: str, layer_name: str) -> pd.DataFrame:
    con = sqlite3.connect(gpkg_path)
    try:
        df = pd.read_sql_query(f'SELECT * FROM "{layer_name}"', con)
    finally:
        con.close()
    if "geom" in df.columns:
        df = df.drop(columns=["geom"])
    return df


def _hex_polygon(hex_id: str) -> list[list[float]] | None:
    if h3 is None:
        return None
    try:
        boundary = h3.cell_to_boundary(hex_id)
    except Exception:
        return None
    return [[lng, lat] for lat, lng in boundary]


@st.cache_data(show_spinner=False)
def build_hex_map_frame(gpkg_path: str, layer_name: str) -> pd.DataFrame:
    base_df = load_acceptance_hex_table(gpkg_path, layer_name)
    if h3 is None:
        return pd.DataFrame()

    out = base_df.copy()
    latitudes: list[float] = []
    longitudes: list[float] = []
    polygons: list[list[list[float]] | None] = []
    for hex_id in out["hex_id"].astype(str):
        try:
            lat, lon = h3.cell_to_latlng(hex_id)
            latitudes.append(lat)
            longitudes.append(lon)
            polygons.append(_hex_polygon(hex_id))
        except Exception:
            latitudes.append(np.nan)
            longitudes.append(np.nan)
            polygons.append(None)

    out["lat"] = latitudes
    out["lon"] = longitudes
    out["polygon"] = polygons
    return out.dropna(subset=["lat", "lon", "polygon"]).copy()


def asset_dir(registry_meta: dict[str, Any]) -> Path:
    return resolve_repo_path(registry_meta["asset_dir"])


@st.cache_data(show_spinner=False)
def load_asset_manifest(manifest_path: str) -> pd.DataFrame:
    path = Path(manifest_path)
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "layer_id",
                "layer_key",
                "label",
                "group_id",
                "geometry_family",
                "source_exists",
                "feature_count",
                "geojson_path",
                "distance_path",
                "status",
                "message",
            ]
        )
    return pd.read_csv(path)


def layer_status_table(registry_meta: dict[str, Any]) -> pd.DataFrame:
    groups, _, _ = load_registry()
    manifest = load_asset_manifest(str(asset_dir(registry_meta) / "asset_manifest.csv"))
    manifest_map = {}
    if not manifest.empty:
        manifest_map = {row["layer_id"]: row for _, row in manifest.iterrows()}

    rows: list[dict[str, Any]] = []
    for spec in ordered_layers():
        manifest_row = manifest_map.get(spec.id)
        group_label = groups[spec.group_id].label
        if manifest_row is None:
            rows.append(
                {
                    "group": group_label,
                    "layer_id": spec.id,
                    "label": spec.label,
                    "geometry_family": "unknown",
                    "source_exists": False,
                    "feature_count": 0,
                    "status": "missing_assets",
                    "message": "Asset manifest not generated yet.",
                    "geojson_ready": False,
                    "distance_ready": False,
                }
            )
            continue

        geojson_rel = str(manifest_row.get("geojson_path", ""))
        distance_rel = str(manifest_row.get("distance_path", ""))
        geojson_ready = bool(geojson_rel) and resolve_repo_path(geojson_rel).exists()
        distance_ready = bool(distance_rel) and resolve_repo_path(distance_rel).exists()
        rows.append(
            {
                "group": group_label,
                "layer_id": spec.id,
                "label": spec.label,
                "geometry_family": str(manifest_row.get("geometry_family", "unknown")),
                "source_exists": bool(manifest_row.get("source_exists", False)),
                "feature_count": int(manifest_row.get("feature_count", 0) or 0),
                "status": str(manifest_row.get("status", "unknown")),
                "message": str(manifest_row.get("message", "")),
                "geojson_ready": geojson_ready,
                "distance_ready": distance_ready,
            }
        )

    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def load_source_geojson(geojson_path: str) -> dict[str, Any] | None:
    path = Path(geojson_path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def source_geojson_for_layer(registry_meta: dict[str, Any], layer_id: str) -> dict[str, Any] | None:
    manifest = load_asset_manifest(str(asset_dir(registry_meta) / "asset_manifest.csv"))
    if manifest.empty:
        return None
    rows = manifest.loc[manifest["layer_id"] == layer_id]
    if rows.empty:
        return None
    geojson_rel = str(rows.iloc[0].get("geojson_path", ""))
    if not geojson_rel:
        return None
    return load_source_geojson(str(resolve_repo_path(geojson_rel)))


@st.cache_data(show_spinner=False)
def load_distance_table(distance_path: str) -> pd.DataFrame:
    path = Path(distance_path)
    if not path.exists():
        return pd.DataFrame(columns=["hex_id", "distance_m", "intersects"])
    df = pd.read_csv(path)
    if "intersects" not in df.columns:
        df["intersects"] = False
    return df[["hex_id", "distance_m", "intersects"]].copy()


def distance_table_for_layer(registry_meta: dict[str, Any], layer_id: str) -> pd.DataFrame:
    manifest = load_asset_manifest(str(asset_dir(registry_meta) / "asset_manifest.csv"))
    if manifest.empty:
        return pd.DataFrame(columns=["hex_id", "distance_m", "intersects"])
    rows = manifest.loc[manifest["layer_id"] == layer_id]
    if rows.empty:
        return pd.DataFrame(columns=["hex_id", "distance_m", "intersects"])
    distance_rel = str(rows.iloc[0].get("distance_path", ""))
    if not distance_rel:
        return pd.DataFrame(columns=["hex_id", "distance_m", "intersects"])
    return load_distance_table(str(resolve_repo_path(distance_rel)))



_CLASS_PALETTE = {
    "Exkluderad": "#d7dde2",
    "Lag": "#f1e8a6",
    "Medel": "#f0b35b",
    "Hog": "#7dbb7d",
    "Mycket hog": "#2c7a4b",
}

_CLUSTER_PALETTE = {
    "1": "#d8893a",
    "2": "#d8c35a",
    "3": "#bcc6b7",
    "4": "#72889a",
    "5": "#355843",
}

_SCORE_STOPS = [
    (0.0, (239, 232, 216)),
    (20.0, (224, 199, 130)),
    (40.0, (217, 144, 72)),
    (60.0, (155, 184, 108)),
    (80.0, (44, 122, 75)),
]


def _rgb_to_hex_local(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def _interpolate_color(value: float, stops: list[tuple[float, tuple[int, int, int]]]) -> str:
    if value <= stops[0][0]:
        return _rgb_to_hex_local(stops[0][1])
    if value >= stops[-1][0]:
        return _rgb_to_hex_local(stops[-1][1])
    for idx in range(1, len(stops)):
        left_val, left_rgb = stops[idx - 1]
        right_val, right_rgb = stops[idx]
        if value <= right_val:
            share = (value - left_val) / (right_val - left_val)
            rgb = tuple(int(round(left_rgb[channel] + (right_rgb[channel] - left_rgb[channel]) * share)) for channel in range(3))
            return _rgb_to_hex_local(rgb)
    return _rgb_to_hex_local(stops[-1][1])


def _score_fill_hex(score: Any, allowed: bool) -> str:
    if not allowed or pd.isna(score):
        return _CLASS_PALETTE["Exkluderad"]
    return _interpolate_color(float(score), _SCORE_STOPS)


def _closed_hex_ring(coords: Any) -> list[list[float]] | None:
    if not isinstance(coords, list) or len(coords) < 3:
        return None
    ring = [[float(point[0]), float(point[1])] for point in coords]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _format_score(value: Any) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):.1f}"


def _format_distance(value: Any) -> str:
    if pd.isna(value):
        return "NA"
    return f"{int(round(float(value)))} m"


@st.cache_data(show_spinner=False)
def build_acceptance_reference_payload(gpkg_path: str, layer_name: str, language: str = "sv") -> dict[str, Any] | None:
    frame = build_hex_map_frame(gpkg_path, layer_name)
    if frame.empty:
        return None

    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        ring = _closed_hex_ring(getattr(row, "polygon", None))
        if ring is None:
            continue

        cluster_raw = getattr(row, "class_km", None)
        cluster_key = str(int(cluster_raw)) if not pd.isna(cluster_raw) else "?"
        cluster_label_local = cluster_label(cluster_key, language)
        allowed_medium = bool(getattr(row, "allowed_for_wind_medium_acceptance", False))

        popup_body = (
            f"{ui_text('hex', language)}: {getattr(row, 'hex_id', '')}<br>"
            f"{ui_text('high_acceptance', language)}: {acceptance_class_label(getattr(row, 'acceptance_class_high_acceptance', 'Exkluderad'), language)} ({_format_score(getattr(row, 'acceptance_score_high_acceptance', None))})<br>"
            f"{ui_text('medium_acceptance', language)}: {acceptance_class_label(getattr(row, 'acceptance_class_medium_acceptance', 'Exkluderad'), language)} ({_format_score(getattr(row, 'acceptance_score_medium_acceptance', None))})<br>"
            f"{ui_text('low_acceptance', language)}: {acceptance_class_label(getattr(row, 'acceptance_class_low_acceptance', 'Exkluderad'), language)} ({_format_score(getattr(row, 'acceptance_score_low_acceptance', None))})<br>"
            f"{ui_text('settlement_distance', language)}: {_format_distance(getattr(row, 'dist_to_settlement_m', None))}<br>"
            f"{ui_text('large_road_distance', language)}: {_format_distance(getattr(row, 'dist_to_road_large_m', None))}<br>"
            f"{ui_text('medium_road_distance', language)}: {_format_distance(getattr(row, 'dist_to_road_medium_m', None))}<br>"
            f"{ui_text('nearest_electrical', language)}: {_format_distance(getattr(row, 'dist_to_electrical_m', None))}<br>"
            f"{ui_text('landscape_cluster', language)}: {cluster_key} - {cluster_label_local}"
        )

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "fill_high": _CLASS_PALETTE.get(str(getattr(row, "acceptance_class_high_acceptance", "Exkluderad")), _CLASS_PALETTE["Exkluderad"]),
                    "fill_medium": _CLASS_PALETTE.get(str(getattr(row, "acceptance_class_medium_acceptance", "Exkluderad")), _CLASS_PALETTE["Exkluderad"]),
                    "fill_low": _CLASS_PALETTE.get(str(getattr(row, "acceptance_class_low_acceptance", "Exkluderad")), _CLASS_PALETTE["Exkluderad"]),
                    "fill_score_medium": _score_fill_hex(getattr(row, "acceptance_score_medium_acceptance", None), allowed_medium),
                    "fill_cluster": _CLUSTER_PALETTE.get(cluster_key, "#777777"),
                    "fill_opacity_high": 0.96 if bool(getattr(row, "allowed_for_wind_high_acceptance", False)) else 0.012,
                    "fill_opacity_medium": 0.96 if bool(getattr(row, "allowed_for_wind_medium_acceptance", False)) else 0.012,
                    "fill_opacity_low": 0.96 if bool(getattr(row, "allowed_for_wind_low_acceptance", False)) else 0.012,
                    "fill_opacity_score_medium": 0.92 if allowed_medium else 0.0,
                    "fill_opacity_cluster": 0.74,
                    "popup_body_reference": popup_body,
                },
            }
        )

    layers = [
        {
            "name": reference_layer_name("scenario_medium", language),
            "stroke": False,
            "strokeColor": "#ffffff",
            "fillColor": "#8c8c8c",
            "fillColorProperty": "fill_medium",
            "fillOpacityProperty": "fill_opacity_medium",
            "strokeOpacity": 0.0,
            "fillOpacity": 0.72,
            "weight": 0.0,
            "pointRadius": 2,
            "defaultVisible": False,
            "fillPattern": None,
            "popupTitle": reference_layer_name("scenario_medium", language),
            "popupBodyProperty": "popup_body_reference",
            "overlayFamily": "reference",
        },
        {
            "name": reference_layer_name("scenario_low", language),
            "stroke": False,
            "strokeColor": "#ffffff",
            "fillColor": "#8c8c8c",
            "fillColorProperty": "fill_low",
            "fillOpacityProperty": "fill_opacity_low",
            "strokeOpacity": 0.0,
            "fillOpacity": 0.72,
            "weight": 0.0,
            "pointRadius": 2,
            "defaultVisible": False,
            "fillPattern": None,
            "popupTitle": reference_layer_name("scenario_low", language),
            "popupBodyProperty": "popup_body_reference",
            "overlayFamily": "reference",
        },
        {
            "name": reference_layer_name("scenario_high", language),
            "stroke": False,
            "strokeColor": "#ffffff",
            "fillColor": "#8c8c8c",
            "fillColorProperty": "fill_high",
            "fillOpacityProperty": "fill_opacity_high",
            "strokeOpacity": 0.0,
            "fillOpacity": 0.72,
            "weight": 0.0,
            "pointRadius": 2,
            "defaultVisible": False,
            "fillPattern": None,
            "popupTitle": reference_layer_name("scenario_high", language),
            "popupBodyProperty": "popup_body_reference",
            "overlayFamily": "reference",
        },
        {
            "name": reference_layer_name("scenario_score_medium", language),
            "stroke": False,
            "strokeColor": "#ffffff",
            "fillColor": "#8c8c8c",
            "fillColorProperty": "fill_score_medium",
            "fillOpacityProperty": "fill_opacity_score_medium",
            "strokeOpacity": 0.0,
            "fillOpacity": 0.72,
            "weight": 0.0,
            "pointRadius": 2,
            "defaultVisible": False,
            "fillPattern": None,
            "popupTitle": reference_layer_name("scenario_score_medium", language),
            "popupBodyProperty": "popup_body_reference",
            "overlayFamily": "reference",
        },
        {
            "name": reference_layer_name("clusters", language),
            "stroke": False,
            "strokeColor": "#ffffff",
            "fillColor": "#777777",
            "fillColorProperty": "fill_cluster",
            "fillOpacityProperty": "fill_opacity_cluster",
            "strokeOpacity": 0.0,
            "fillOpacity": 0.72,
            "weight": 0.0,
            "pointRadius": 2,
            "defaultVisible": False,
            "fillPattern": None,
            "popupTitle": reference_layer_name("clusters", language),
            "popupBodyProperty": "popup_body_reference",
            "overlayFamily": "reference",
        },
    ]

    return {"featureCollection": {"type": "FeatureCollection", "features": features}, "layers": layers}


def acceptance_reference_payload(registry_meta: dict[str, Any], language: str = "sv") -> dict[str, Any] | None:
    gpkg_path = resolve_repo_path(registry_meta["acceptance_hex_gpkg"])
    if not gpkg_path.exists():
        return None
    return build_acceptance_reference_payload(str(gpkg_path), str(registry_meta["acceptance_hex_layer"]), language)
