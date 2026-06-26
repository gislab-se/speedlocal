from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path
from typing import Any

import h3
import pandas as pd

from .geometry import geometry_for_hex, load_h3_display_geometries
from .manifests import resolve_repo_path


SCENARIO_IDS = ("low", "medium", "high")
DEFAULT_SCENARIO_ID = "medium"
SCENARIO_VALUE_COLUMNS = {
    "low": "acceptance_low",
    "medium": "acceptance_medium",
    "high": "acceptance_high",
}


def acceptance_scenarios(manifest: dict[str, Any] | None) -> list[dict[str, str]]:
    configured = (manifest or {}).get("scenarios") or []
    scenarios: list[dict[str, str]] = []
    for scenario in configured:
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get("id", "")).strip()
        if scenario_id in SCENARIO_IDS:
            scenarios.append(
                {
                    "id": scenario_id,
                    "label": str(scenario.get("label") or scenario_id),
                    "column": str(scenario.get("value_column") or SCENARIO_VALUE_COLUMNS[scenario_id]),
                }
            )
    if scenarios:
        return scenarios
    return [
        {"id": "low", "label": "Låg acceptans", "column": SCENARIO_VALUE_COLUMNS["low"]},
        {"id": "medium", "label": "Mellanacceptans", "column": SCENARIO_VALUE_COLUMNS["medium"]},
        {"id": "high", "label": "Hög acceptans", "column": SCENARIO_VALUE_COLUMNS["high"]},
    ]


def acceptance_scenario_label(manifest: dict[str, Any] | None, scenario_id: str) -> str:
    for scenario in acceptance_scenarios(manifest):
        if scenario["id"] == scenario_id:
            return scenario["label"]
    return str(scenario_id)


def acceptance_value_column(manifest: dict[str, Any] | None, scenario_id: str) -> str:
    for scenario in acceptance_scenarios(manifest):
        if scenario["id"] == scenario_id:
            return scenario["column"]
    return SCENARIO_VALUE_COLUMNS.get(str(scenario_id), SCENARIO_VALUE_COLUMNS[DEFAULT_SCENARIO_ID])


def _manifest_path(manifest: dict[str, Any], key: str) -> Path | None:
    value = manifest.get(key)
    return resolve_repo_path(str(value)) if value else None


@lru_cache(maxsize=8)
def _load_acceptance_csv(csv_path: str) -> pd.DataFrame:
    frame = pd.read_csv(csv_path, dtype={"hex_id": str})
    for column in SCENARIO_VALUE_COLUMNS.values():
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").clip(lower=0.0, upper=1.0).round(3)
    return frame


def load_acceptance_frame(manifest: dict[str, Any]) -> pd.DataFrame:
    csv_path = _manifest_path(manifest, "acceptance_csv")
    if csv_path is None or not csv_path.exists():
        return pd.DataFrame()
    return _load_acceptance_csv(str(csv_path)).copy()


def acceptance_legend_items() -> list[dict[str, str]]:
    return [
        {"label": "0.00-0.20", "color": "#b91c1c"},
        {"label": "0.20-0.40", "color": "#f97316"},
        {"label": "0.40-0.60", "color": "#facc15"},
        {"label": "0.60-0.80", "color": "#65a30d"},
        {"label": "0.80-1.00", "color": "#166534"},
    ]


def acceptance_color(value: float) -> str:
    if value < 0.2:
        return "#b91c1c"
    if value < 0.4:
        return "#f97316"
    if value < 0.6:
        return "#facc15"
    if value < 0.8:
        return "#65a30d"
    return "#166534"


@lru_cache(maxsize=24)
def _rolled_acceptance_frame(
    csv_path: str,
    value_column: str,
    source_resolution: int,
    target_resolution: int,
) -> pd.DataFrame:
    frame = _load_acceptance_csv(csv_path)
    if frame.empty or value_column not in frame.columns:
        return pd.DataFrame(columns=["hex_id", "acceptance_value", "source_hex_count"])

    work = frame[["hex_id", value_column]].copy()
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce").clip(lower=0.0, upper=1.0)
    if int(target_resolution) < int(source_resolution):
        work["target_hex_id"] = work["hex_id"].map(lambda cell: h3.cell_to_parent(str(cell), int(target_resolution)))
    else:
        work["target_hex_id"] = work["hex_id"].astype(str)

    rolled = (
        work.groupby("target_hex_id", as_index=False)
        .agg(acceptance_value=(value_column, "mean"), source_hex_count=("hex_id", "count"))
        .rename(columns={"target_hex_id": "hex_id"})
    )
    rolled["acceptance_value"] = rolled["acceptance_value"].clip(lower=0.0, upper=1.0).round(3)
    return rolled.sort_values("hex_id").reset_index(drop=True)


@lru_cache(maxsize=12)
def _acceptance_feature_collection_cached(
    csv_path: str,
    geometry_path: str,
    scenario_id: str,
    value_column: str,
    scenario_label: str,
    source_resolution: int,
    target_resolution: int,
) -> dict[str, Any]:
    frame = _rolled_acceptance_frame(csv_path, value_column, int(source_resolution), int(target_resolution))
    if frame.empty:
        return {"type": "FeatureCollection", "features": []}

    geometries = load_h3_display_geometries(geometry_path)
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        hex_id = str(row.hex_id)
        geometry = geometry_for_hex(hex_id, geometries)
        if geometry is None:
            continue
        value = round(float(row.acceptance_value), 3)
        source_count = int(row.source_hex_count)
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "acceptance_scenario": str(scenario_id),
                    "acceptance_value": value,
                    "source_hex_count": source_count,
                    "source_h3_resolution": int(source_resolution),
                    "target_h3_resolution": int(target_resolution),
                    "fill": acceptance_color(value),
                    "tooltip_title": "Syntetisk social acceptans",
                    "tooltip_body": (
                        f"{html.escape(str(scenario_label))}<br>"
                        f"Värde: {value:.3f}<br>"
                        f"H3 R{int(target_resolution)}<br>"
                        f"Källhex: {source_count}<br>"
                        "Testdata, inte forskningsresultat"
                    ),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def acceptance_feature_collection(
    manifest: dict[str, Any],
    scenario_id: str,
    target_resolution: int | None = None,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    csv_path = _manifest_path(manifest, "acceptance_csv")
    geometry_path = (
        Path(display_geometry_path)
        if display_geometry_path
        else _manifest_path(manifest, "hex_geometry_path") or _manifest_path(manifest, "source_hex_geojson")
    )
    if csv_path is None or geometry_path is None or not csv_path.exists() or not geometry_path.exists():
        return {"type": "FeatureCollection", "features": []}

    scenario_id = str(scenario_id) if str(scenario_id) in SCENARIO_IDS else DEFAULT_SCENARIO_ID
    source_resolution = int(manifest.get("hex_resolution") or 0)
    target_resolution = int(target_resolution or source_resolution)
    return _acceptance_feature_collection_cached(
        str(csv_path),
        str(geometry_path),
        scenario_id,
        acceptance_value_column(manifest, scenario_id),
        acceptance_scenario_label(manifest, scenario_id),
        source_resolution,
        target_resolution,
    )


def acceptance_layer(
    manifest: dict[str, Any],
    scenario_id: str,
    target_resolution: int | None = None,
    display_geometry_path: str | None = None,
) -> dict[str, Any]:
    scenario_label = acceptance_scenario_label(manifest, scenario_id)
    resolution = int(target_resolution or manifest.get("hex_resolution") or 0)
    return {
        "name": f"Social acceptans: {scenario_label} R{resolution}",
        "feature_collection": acceptance_feature_collection(manifest, scenario_id, resolution, display_geometry_path),
        "fill_property": "fill",
        "legend_items": acceptance_legend_items(),
        "legend_id": "synthetic_social_acceptance",
        "legend_title": "Syntetisk social acceptans",
        "default_visible": True,
        "stroke": False,
        "weight": 0.0,
        "fill_opacity": 0.72,
        "layer_kind": "hex",
        "opacity_family": "synthetic_social_acceptance",
        "opacity_label": "Social acceptans",
    }
