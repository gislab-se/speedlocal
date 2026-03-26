from __future__ import annotations

import json
import math
import os
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

try:
    from apps.solochvind.area_demand_scenarios import (
        SCENARIO_LABELS as AREA_SCENARIO_LABELS,
        SCENARIO_ORDER as AREA_SCENARIO_ORDER,
        build_area_demand_scenario_bundle,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from area_demand_scenarios import (
        SCENARIO_LABELS as AREA_SCENARIO_LABELS,
        SCENARIO_ORDER as AREA_SCENARIO_ORDER,
        build_area_demand_scenario_bundle,
    )

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None


UNIT_TO_TWH = {
    "twh": 1.0,
    "gwh": 1e-3,
    "mwh": 1e-6,
    "pj": 1.0 / 3.6,
    "tj": 1.0 / 3600.0,
}

LANDSCAPE_COLORS = {
    0: [166, 219, 210, 90],
    1: [253, 174, 97, 90],
    2: [255, 255, 191, 90],
    3: [231, 212, 232, 90],
    4: [215, 25, 28, 90],
    5: [255, 237, 111, 90],
    6: [171, 217, 233, 90],
    7: [197, 176, 213, 90],
}

ENERGY_LABELS = {"wind": "Vind", "solar": "Sol"}
TIMES_TO_ENERGY = {"NRG_WIN": "wind", "NRG_SOL": "solar"}
WIND_OPTION_ORDER = ("high_acceptance", "medium_acceptance", "low_acceptance")
SOLAR_OPTION_ORDER = ("high_acceptance", "medium_acceptance", "low_acceptance")
ACCEPTANCE_LABELS = {
    "high_acceptance": "Hög",
    "medium_acceptance": "Mellan",
    "low_acceptance": "Låg",
}
SELECTION_MODE_LABELS = {"auto": "Auto", "adjust": "Auto + justera"}
MAP_VIEW_LABELS = {
    "selection": "Urval",
    "wind": "Vindacceptans",
    "solar": "Solacceptans",
    "landscape": "Landskapsklass",
}
CLUSTER_INFO = {
    1: ("1 - Tätorts- och verksamhetskärnor", "#6F7F8F"),
    2: ("2 - Vardagslandskap med blandad bakgrundskaraktär", "#D8C36A"),
    3: ("3 - Flygsands- och låglänta kuststråk", "#D99A7A"),
    4: ("4 - Brant relief och dalpräglat inland", "#A7B88A"),
    5: ("5 - Skogligt inland och habitatkärnor", "#58724C"),
}
FACTOR_LABELS = {
    "F1": "Flygsands- och låglänta kustmiljöer",
    "F2": "Brant relief och sprickdalspräglad terräng",
    "F3": "Skogligt skyddsinland och habitatkärnor",
    "F4": "Bosättning och byggd struktur",
    "F5": "Marina sand- och gruskluster",
}


def _get_config_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        secret_value = st.secrets.get(name, "")
    except Exception:
        secret_value = ""
    return str(secret_value).strip()


def _config_path(name: str) -> Path | None:
    value = _get_config_value(name)
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def _resolve_hex_path(project_root: Path) -> Path | None:
    configured = _config_path("HEX_POINTS_PATH")
    if configured is not None:
        return configured
    candidate = project_root / "data" / "gc4" / "bornholm_vindacceptans_stage1_v4_res9_hex.geojson"
    return candidate if candidate.exists() else None


def _resolve_area_demand_path(project_root: Path) -> Path | None:
    candidates = [
        project_root / "data" / "raw" / "AreaDemand.xlsx",
        project_root.parent / "eml" / "data" / "raw" / "AreaDemand.xlsx",
    ]
    return next((path for path in candidates if path.exists()), None)


def _resolve_duckdb(project_root: Path) -> tuple[Path | None, str]:
    configured = _get_config_value("DUCKDB_PATH")
    if configured:
        path = Path(configured)
        if path.exists():
            return path, f"loaded duckdb: {path}"
    candidate = project_root / "data" / "processed" / "speedlocal_times.duckdb"
    if candidate.exists():
        return candidate, f"loaded duckdb: {candidate}"
    return None, "duckdb-fil saknas"


def _rgba_css(color: list[int] | tuple[int, ...]) -> str:
    r, g, b, a = [int(v) for v in color]
    return f"rgba({r}, {g}, {b}, {a / 255.0:.3f})"


def _render_map_legend(items: list[tuple[str, list[int] | tuple[int, ...]]]) -> None:
    blocks = []
    for label, color in items:
        blocks.append(
            (
                "<div style='display:flex;align-items:center;gap:0.45rem;margin:0.12rem 0;'>"
                f"<span style='display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid rgba(0,0,0,0.18);background:{_rgba_css(color)};'></span>"
                f"<span style='font-size:0.9rem;'>{label}</span>"
                "</div>"
            )
        )
    st.markdown(
        (
            "<div style='padding:0.55rem 0.7rem;border:1px solid rgba(49,51,63,0.14);"
            "border-radius:0.6rem;background:rgba(255,255,255,0.82);margin-bottom:0.75rem;'>"
            "<div style='font-size:0.82rem;font-weight:600;margin-bottom:0.2rem;'>Teckenförklaring</div>"
            + "".join(blocks)
            + "</div>"
        ),
        unsafe_allow_html=True,
    )


def _coerce_candidate_series(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip().str.lower()
    truthy = {"true", "1", "yes", "ja", "y", "t"}
    falsy = {"false", "0", "no", "nej", "n", "f"}
    result = pd.Series(pd.NA, index=series.index, dtype="boolean")
    result[text.isin(truthy)] = True
    result[text.isin(falsy)] = False
    if series.dropna().isin([True, False]).any():
        result = result.fillna(series.astype("boolean"))
    return result


def _read_geojson(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or str(payload.get("type")) != "FeatureCollection":
        raise ValueError(f"GeoJSON-filen är inte en FeatureCollection: {path}")
    rows: list[dict[str, object]] = []
    for feature in payload.get("features", []):
        geometry = dict(feature.get("geometry") or {})
        props = dict(feature.get("properties") or {})
        polygon = None
        if geometry.get("type") == "Polygon":
            coords = geometry.get("coordinates") or []
            polygon = coords[0] if len(coords) == 1 else coords
        props["polygon"] = polygon
        rows.append(props)
    return pd.DataFrame(rows)


def _outer_ring(polygon: object) -> list[list[float]]:
    if not isinstance(polygon, list) or not polygon:
        return []
    first = polygon[0]
    if isinstance(first, list) and first and isinstance(first[0], list):
        return first
    return polygon


def _polygon_centroid(polygon: object) -> tuple[float, float]:
    ring = _outer_ring(polygon)
    if not ring:
        return math.nan, math.nan
    lons = [float(coord[0]) for coord in ring if isinstance(coord, list) and len(coord) >= 2]
    lats = [float(coord[1]) for coord in ring if isinstance(coord, list) and len(coord) >= 2]
    if not lons or not lats:
        return math.nan, math.nan
    return float(sum(lats) / len(lats)), float(sum(lons) / len(lons))


def _map_bounds(frame: pd.DataFrame) -> list[list[float]] | None:
    min_lat = math.inf
    min_lon = math.inf
    max_lat = -math.inf
    max_lon = -math.inf
    found = False
    for polygon in frame["polygon"].tolist():
        rings = _polygon_coordinates(polygon)
        if not rings:
            continue
        for ring in rings:
            for coord in ring:
                if not isinstance(coord, list) or len(coord) < 2:
                    continue
                lon = float(coord[0])
                lat = float(coord[1])
                min_lat = min(min_lat, lat)
                min_lon = min(min_lon, lon)
                max_lat = max(max_lat, lat)
                max_lon = max(max_lon, lon)
                found = True
    if not found:
        return None
    return [[min_lat, min_lon], [max_lat, max_lon]]


@st.cache_data(show_spinner=False)
def load_hex_context(hex_path_str: str) -> pd.DataFrame:
    path = Path(hex_path_str)
    if path.suffix.lower() not in {".geojson", ".json"}:
        raise ValueError("Den nya solochvind-appen stöder just nu bara GeoJSON som hexkälla.")
    df = _read_geojson(path)
    if "hex_id" not in df.columns:
        raise ValueError("Hexfilen saknar kolumnen hex_id.")
    for col in ["F1", "F2", "F3", "F4", "F5"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "class_km" not in df.columns:
        df["class_km"] = 0
    df["class_km"] = pd.to_numeric(df["class_km"], errors="coerce").fillna(0).astype(int)
    if "hex_area_km2" not in df.columns:
        df["hex_area_km2"] = np.nan
    df["hex_area_km2"] = pd.to_numeric(df["hex_area_km2"], errors="coerce")
    for option in WIND_OPTION_ORDER:
        allowed_col = f"allowed_for_wind_{option}"
        score_col = f"acceptance_score_{option}"
        class_col = f"acceptance_class_{option}"
        reason_col = f"exclusion_reason_{option}"
        if allowed_col not in df.columns:
            df[allowed_col] = True
        df[allowed_col] = _coerce_candidate_series(df[allowed_col]).fillna(False).astype(bool)
        if score_col not in df.columns:
            df[score_col] = np.where(df[allowed_col], 100.0, 0.0)
        df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0.0)
        if class_col not in df.columns:
            df[class_col] = np.where(df[allowed_col], "allowed", "blocked")
        df[class_col] = df[class_col].fillna("").astype(str)
        if reason_col not in df.columns:
            df[reason_col] = np.where(df[allowed_col], "", "blocked")
        df[reason_col] = df[reason_col].fillna("").astype(str)
    return df


@st.cache_data(show_spinner=False)
def build_map_frame(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    lats: list[float] = []
    lons: list[float] = []
    for polygon in work["polygon"].tolist():
        lat, lon = _polygon_centroid(polygon)
        lats.append(lat)
        lons.append(lon)
    work["lat"] = lats
    work["lon"] = lons
    return work


def _norm(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    lo = values.min()
    hi = values.max()
    if pd.isna(lo) or pd.isna(hi) or hi <= lo:
        return pd.Series(np.zeros(len(values)), index=values.index)
    return (values - lo) / (hi - lo)


def _build_suitability(df: pd.DataFrame) -> pd.DataFrame:
    work = df[["hex_id", "F1", "F2", "F3", "F4", "F5"]].copy()
    f1 = _norm(work["F1"])
    f2 = _norm(work["F2"])
    f3 = _norm(work["F3"])
    f4 = _norm(work["F4"])
    work["s_wind"] = 0.45 * f1 + 0.35 * f3 + 0.20 * (1.0 - f2)
    work["s_solar"] = 0.55 * f4 + 0.25 * f1 + 0.20 * (1.0 - f2)
    return work


def _describe_quantile(value: float, q25: float, q50: float, q75: float) -> str:
    if value >= q75:
        return "Övre kvartil"
    if value >= q50:
        return "Övre medianhalva"
    if value >= q25:
        return "Mittenband"
    return "Nedre kvartil"


def _add_solar_acceptance(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    solar_scores = pd.to_numeric(work["s_solar"], errors="coerce").fillna(0.0)
    q25 = float(solar_scores.quantile(0.25))
    q50 = float(solar_scores.quantile(0.50))
    q75 = float(solar_scores.quantile(0.75))
    work["solar_acceptance_score"] = solar_scores * 100.0
    work["solar_acceptance_class"] = [
        _describe_quantile(float(value), q25, q50, q75) for value in solar_scores
    ]
    work["allowed_for_solar_high_acceptance"] = solar_scores >= q25
    work["allowed_for_solar_medium_acceptance"] = solar_scores >= q50
    work["allowed_for_solar_low_acceptance"] = solar_scores >= q75
    work["solar_acceptance_note"] = (
        "Härledd från landskapsmodellens solar-suitability. "
        "Hög = övre 75 %, Mellan = övre 50 %, Låg = övre 25 %."
    )
    return work


def _as_twh(value: pd.Series, unit: pd.Series) -> pd.Series:
    factor = unit.astype(str).str.strip().str.lower().map(UNIT_TO_TWH).fillna(1.0)
    return pd.to_numeric(value, errors="coerce") * factor


def _duckdb_has_object(con, name: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
          AND lower(table_name) = lower(?)
        LIMIT 1
        """,
        [name],
    ).fetchone()
    return row is not None


def _duckdb_columns(con, name: str) -> list[str]:
    rows = con.execute(
        """
        SELECT lower(column_name)
        FROM information_schema.columns
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
          AND lower(table_name) = lower(?)
        ORDER BY ordinal_position
        """,
        [name],
    ).fetchall()
    return [str(row[0]) for row in rows]


@st.cache_data(show_spinner=False)
def load_times_inputs(project_root_str: str) -> tuple[pd.DataFrame, dict[str, str], str]:
    if duckdb is None:
        raise RuntimeError("Paketet duckdb saknas.")
    project_root = Path(project_root_str)
    db_path, db_status = _resolve_duckdb(project_root)
    if db_path is None:
        raise FileNotFoundError(db_status)
    con = duckdb.connect(str(db_path), read_only=True)
    source_table = next((name for name in ["timesreport_raw", "timesreport"] if _duckdb_has_object(con, name)), None)
    if source_table is None:
        raise RuntimeError("DuckDB saknar timesreport_raw/timesreport.")
    cols = set(_duckdb_columns(con, source_table))
    unit_col = "units" if "units" in cols else ("unit" if "unit" in cols else None)
    ts_col = "timeslice" if "timeslice" in cols else ("all_ts" if "all_ts" in cols else None)
    if unit_col is None or ts_col is None:
        raise RuntimeError("DuckDB-tabellen saknar unit-/timeslice-kolumner.")
    raw = con.execute(
        f"""
        SELECT
            scen,
            CAST(year AS INTEGER) AS year,
            UPPER(COALESCE(comgroup, '')) AS comgroup,
            COALESCE(prc, '') AS prc,
            value,
            {unit_col} AS unit
        FROM {source_table}
        WHERE lower(topic) = 'energy'
          AND lower(attr) = 'f_out'
          AND upper(coalesce({ts_col}, '')) = 'ANNUAL'
          AND TRY_CAST(year AS INTEGER) IS NOT NULL
          AND upper(COALESCE(comgroup, '')) IN ('NRG_WIN', 'NRG_SOL')
        """
    ).df()
    if raw.empty:
        raise RuntimeError("Inga vind- eller solrader hittades i DuckDB:n.")
    raw["value_twh"] = _as_twh(raw["value"], raw["unit"])
    raw["energy_key"] = raw["comgroup"].map(TIMES_TO_ENERGY).fillna("")
    raw = raw.dropna(subset=["year", "value_twh"])
    raw["year"] = raw["year"].astype(int)
    raw["scen"] = raw["scen"].astype(str)
    descriptions: dict[str, str] = {}
    if _duckdb_has_object(con, "scen_desc"):
        desc_cols = _duckdb_columns(con, "scen_desc")
        id_col = "id" if "id" in desc_cols else ("scen" if "scen" in desc_cols else None)
        if id_col is not None and "description" in desc_cols:
            for scen_id, description in con.execute(
                f"SELECT DISTINCT {id_col} AS scen_id, description FROM scen_desc"
            ).fetchall():
                if scen_id is not None and description is not None:
                    descriptions[str(scen_id)] = str(description)
    con.close()
    return raw, descriptions, f"{db_status}; source_table={source_table}"


def _scenario_display_label(scenario_id: str, descriptions: dict[str, str]) -> str:
    description = str(descriptions.get(scenario_id, "")).strip()
    if not description or description == scenario_id:
        return scenario_id
    return f"{description} [{scenario_id}]"


def _build_times_summary(rows: pd.DataFrame) -> tuple[dict[str, dict[int, float]], dict[str, dict[int, dict[str, float]]], pd.DataFrame]:
    mix = (
        rows.groupby(["scen", "year", "energy_key"], as_index=False)["value_twh"]
        .sum()
        .sort_values(["scen", "year", "energy_key"])
        .reset_index(drop=True)
    )
    totals_frame = mix.groupby(["scen", "year"], as_index=False)["value_twh"].sum()
    totals: dict[str, dict[int, float]] = {}
    base_mix: dict[str, dict[int, dict[str, float]]] = {}
    for _, row in totals_frame.iterrows():
        totals.setdefault(str(row["scen"]), {})[int(row["year"])] = float(row["value_twh"])
    for (scenario_id, year), block in mix.groupby(["scen", "year"]):
        values = {
            "wind": float(block.loc[block["energy_key"] == "wind", "value_twh"].sum()),
            "solar": float(block.loc[block["energy_key"] == "solar", "value_twh"].sum()),
        }
        total = sum(values.values())
        if total <= 0:
            pct = {"wind": 50.0, "solar": 50.0}
        else:
            pct = {key: values[key] * 100.0 / total for key in values}
        base_mix.setdefault(str(scenario_id), {})[int(year)] = pct
    return totals, base_mix, mix


def _area_scenario_label(scenario_id: str) -> str:
    return AREA_SCENARIO_LABELS.get(str(scenario_id), str(scenario_id))


def _normalize_mix_100(values: dict[str, float]) -> dict[str, float]:
    clean = {key: max(0.0, float(value)) for key, value in values.items()}
    total = sum(clean.values())
    if total <= 0:
        return {"wind": 50.0, "solar": 50.0}
    return {key: clean[key] * 100.0 / total for key in clean}


def _set_mix_state(values: dict[str, float]) -> None:
    normalized = _normalize_mix_100(values)
    for key, value in normalized.items():
        st.session_state[f"mix_{key}"] = float(value)


def _sync_mix_state(base_mix: dict[str, float]) -> None:
    ctx = "wind|solar"
    previous = str(st.session_state.get("_mix_ctx", ""))
    if previous != ctx:
        _set_mix_state(base_mix)
        st.session_state["_mix_ctx"] = ctx


def _rebalance_slider(changed_key: str, slider_keys: list[str]) -> None:
    values = {key: float(st.session_state.get(key, 0.0)) for key in slider_keys}
    target = 100.0
    delta = target - sum(values.values())
    if abs(delta) < 1e-9:
        return
    others = [key for key in slider_keys if key != changed_key]
    if not others:
        st.session_state[changed_key] = target
        return
    other_sum = sum(max(0.0, values[key]) for key in others)
    if other_sum <= 1e-12:
        share = delta / len(others)
        for key in others:
            st.session_state[key] = max(0.0, values[key] + share)
    else:
        for key in others:
            weight = max(0.0, values[key]) / other_sum
            st.session_state[key] = max(0.0, values[key] + delta * weight)
    total_after = sum(float(st.session_state.get(key, 0.0)) for key in slider_keys)
    if abs(total_after - target) > 1e-6:
        st.session_state[changed_key] = max(
            0.0, float(st.session_state.get(changed_key, 0.0)) + (target - total_after)
        )


def _parse_hex_input(text: str, valid_hexes: set[str]) -> tuple[list[str], list[str]]:
    tokens = [token.strip() for token in text.replace(",", "\n").splitlines() if token.strip()]
    valid = []
    invalid = []
    for token in tokens:
        if token in valid_hexes:
            valid.append(token)
        else:
            invalid.append(token)
    return sorted(set(valid)), sorted(set(invalid))


def _build_selection_candidates(
    frame: pd.DataFrame,
    mix_share_pct: dict[str, float],
    wind_allowed_col: str,
    solar_allowed_col: str,
) -> pd.DataFrame:
    candidates = frame.copy()
    candidates["wind_rank"] = np.where(
        candidates[wind_allowed_col],
        pd.to_numeric(candidates["wind_acceptance_score_selected"], errors="coerce").fillna(0.0) / 100.0,
        0.0,
    )
    candidates["solar_rank"] = np.where(
        candidates[solar_allowed_col],
        pd.to_numeric(candidates["s_solar"], errors="coerce").fillna(0.0),
        0.0,
    )
    candidates["combined_rank"] = (
        candidates["wind_rank"] * (float(mix_share_pct["wind"]) / 100.0)
        + candidates["solar_rank"] * (float(mix_share_pct["solar"]) / 100.0)
    )
    return candidates.sort_values("combined_rank", ascending=False).reset_index(drop=True)


def _build_auto_allocation(
    candidates: pd.DataFrame,
    mix_rows: pd.DataFrame,
    hex_area_km2: float,
    wind_allowed_col: str,
    solar_allowed_col: str,
) -> pd.DataFrame:
    available = candidates.copy()
    selected_parts: list[pd.DataFrame] = []
    order = mix_rows.sort_values("area_need_km2", ascending=False)
    for _, row in order.iterrows():
        area_need = float(row["area_need_km2"])
        if area_need <= 0:
            continue
        tech = str(row["energy_key"])
        if tech == "wind":
            tech_candidates = available[available[wind_allowed_col] == True].copy()
            tech_candidates = tech_candidates.sort_values("wind_rank", ascending=False)
        else:
            tech_candidates = available[available[solar_allowed_col] == True].copy()
            tech_candidates = tech_candidates.sort_values("solar_rank", ascending=False)
        n_hex = int(math.ceil(area_need / max(hex_area_km2, 1e-9)))
        if n_hex <= 0 or tech_candidates.empty:
            continue
        chosen = tech_candidates.head(min(n_hex, len(tech_candidates))).copy()
        if chosen.empty:
            continue
        chosen["selected_for"] = ENERGY_LABELS[tech]
        selected_parts.append(chosen[["hex_id", "selected_for"]])
        available = available[~available["hex_id"].isin(chosen["hex_id"])].copy()
    if not selected_parts:
        return pd.DataFrame(columns=["hex_id", "selected_for"])
    selected = pd.concat(selected_parts, ignore_index=True)
    selected = (
        selected.groupby("hex_id", as_index=False)["selected_for"]
        .agg(lambda values: ", ".join(sorted(set(values))))
        .reset_index(drop=True)
    )
    return selected


def _selection_mode_label(mode_id: str) -> str:
    return SELECTION_MODE_LABELS.get(str(mode_id), str(mode_id))


def _acceptance_label(option_id: str) -> str:
    return ACCEPTANCE_LABELS.get(str(option_id), str(option_id))


def _map_view_label(view_id: str) -> str:
    return MAP_VIEW_LABELS.get(str(view_id), str(view_id))


def _fmt_num(value: object, digits: int = 3) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "-"
    return f"{float(numeric):.{digits}f}"


def _cluster_label(class_id: object) -> str:
    try:
        class_int = int(class_id)
    except Exception:
        return f"Kluster {class_id}"
    return CLUSTER_INFO.get(class_int, (f"Kluster {class_int}", "#999999"))[0]


def _cluster_color(class_id: object) -> str:
    try:
        class_int = int(class_id)
    except Exception:
        return "#999999"
    return CLUSTER_INFO.get(class_int, (f"Kluster {class_int}", "#999999"))[1]


def _popup_html(row: pd.Series, solar_mode_label: str, wind_mode_label: str) -> str:
    strongest = sorted(
        ((label, float(pd.to_numeric(row.get(code), errors="coerce"))) for code, label in FACTOR_LABELS.items()),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    factor_lines = "".join(
        f"<li>{label}: {_fmt_num(value, 3)}</li>"
        for label, value in [(label, row.get(code)) for code, label in FACTOR_LABELS.items()]
    )
    strongest_lines = "".join(
        f"<li>{label}: {_fmt_num(value, 3)}</li>" for label, value in strongest[:3]
    )
    selected_for = str(row.get("selected_for", "")).strip() or "Ej vald i nuvarande urval"
    wind_reason = str(row.get(f"exclusion_reason_{wind_mode_label}", "")).strip() or "-"
    wind_class = str(row.get(f"acceptance_class_{wind_mode_label}", "")).strip() or "-"
    return f"""
    <div style="font-size:13px; line-height:1.35; max-width:420px;">
      <div style="font-weight:700; margin-bottom:6px;">{_cluster_label(row.get('class_km'))}</div>
      <div><b>Hex:</b> {row.get('hex_id', '-')}</div>
      <div><b>Urval:</b> {selected_for}</div>
      <div><b>Hexarea:</b> {_fmt_num(row.get('hex_area_km2'), 3)} km²</div>
      <div style="margin-top:8px;"><b>Faktorprofil</b></div>
      <ul style="margin:4px 0 6px 18px; padding:0;">{factor_lines}</ul>
      <div><b>Starkaste faktorer</b></div>
      <ul style="margin:4px 0 6px 18px; padding:0;">{strongest_lines}</ul>
      <div style="margin-top:8px;"><b>Topologi i detta hex</b></div>
      <ul style="margin:4px 0 6px 18px; padding:0;">
        <li>Distans till bosättning: {_fmt_num(row.get('dist_to_settlement_m'), 0)} m</li>
        <li>Distans till medelväg: {_fmt_num(row.get('dist_to_road_medium_m'), 0)} m</li>
        <li>Distans till större väg: {_fmt_num(row.get('dist_to_road_large_m'), 0)} m</li>
      </ul>
      <div style="margin-top:8px;"><b>Vindacceptans ({_acceptance_label(wind_mode_label)})</b></div>
      <ul style="margin:4px 0 6px 18px; padding:0;">
        <li>Klass: {wind_class}</li>
        <li>Score: {_fmt_num(row.get('wind_acceptance_score_selected'), 1)}</li>
        <li>Skäl: {wind_reason}</li>
      </ul>
      <div style="margin-top:8px;"><b>Solacceptans ({solar_mode_label})</b></div>
      <ul style="margin:4px 0 0 18px; padding:0;">
        <li>Klass: {row.get('solar_acceptance_class', '-')}</li>
        <li>Score: {_fmt_num(row.get('solar_acceptance_score'), 1)}</li>
        <li>Status: Provisoriskt lager tills separat solacceptans finns</li>
      </ul>
    </div>
    """


def _polygon_coordinates(polygon: object) -> list[list[list[float]]] | None:
    if not isinstance(polygon, list) or not polygon:
        return None
    first = polygon[0]
    if isinstance(first, list) and first and isinstance(first[0], list):
        # Ignore inner rings when rendering; a handful of clipped hexes in the
        # source GeoJSON contain tiny holes that show up as distracting white
        # polygons in the map.
        return [first]
    return [polygon]


def _feature_collection(frame: pd.DataFrame, popup_field: str) -> dict[str, object]:
    features: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        coords = _polygon_coordinates(row.get("polygon"))
        if not coords:
            continue
        props = {key: row.get(key) for key in frame.columns if key != "polygon"}
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": coords},
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features, "popup_field": popup_field}


def _geojson_popup() -> folium.GeoJsonPopup:
    return folium.GeoJsonPopup(
        fields=["popup_html"],
        aliases=[""],
        labels=False,
        localize=False,
        style="background-color: white;",
        parse_html=False,
        sticky=False,
        max_width=420,
    )


def _add_geojson_layer(
    target_map: folium.Map,
    name: str,
    frame: pd.DataFrame,
    style_function,
    *,
    show: bool,
) -> None:
    if frame.empty:
        return
    folium.GeoJson(
        data=_feature_collection(frame, "popup_html"),
        name=name,
        style_function=style_function,
        highlight_function=lambda _: {
            "weight": 1.6,
            "color": "#111111",
            "fillOpacity": 0.72,
            "opacity": 0.95,
        },
        popup=_geojson_popup(),
        control=True,
        show=show,
        zoom_on_click=False,
    ).add_to(target_map)


def _render_leaflet_map(view: pd.DataFrame, wind_mode_label: str, solar_mode_label: str) -> folium.Map:
    center_lat = float(view["lat"].median())
    center_lon = float(view["lon"].median())
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="Ljus baskarta", control=True).add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellit",
        control=True,
        show=False,
    ).add_to(fmap)

    work = view.copy()
    work["cluster_label"] = work["class_km"].map(_cluster_label)
    work["cluster_color"] = work["class_km"].map(_cluster_color)
    work["popup_html"] = work.apply(lambda row: _popup_html(row, solar_mode_label, wind_mode_label), axis=1)

    _add_geojson_layer(
        fmap,
        "1. Landskapsanalys",
        work,
        lambda feature: {
            "fillColor": feature["properties"].get("cluster_color", "#999999"),
            "color": "transparent",
            "weight": 0.0,
            "opacity": 0.0,
            "fillOpacity": 0.62,
        },
        show=True,
    )

    wind_allowed = work[work["wind_allowed_selected"] == True].copy()
    _add_geojson_layer(
        fmap,
        f"2. Vindacceptans ({_acceptance_label(wind_mode_label)})",
        wind_allowed,
        lambda feature: {
            "fillColor": "#3A8E41",
            "color": "transparent",
            "weight": 0.0,
            "opacity": 0.0,
            "fillOpacity": 0.42,
        },
        show=True,
    )

    solar_allowed = work[work["solar_allowed_selected"] == True].copy()
    _add_geojson_layer(
        fmap,
        f"3. Solacceptans ({solar_mode_label}, provisorisk)",
        solar_allowed,
        lambda feature: {
            "fillColor": "#E0B22D",
            "color": "transparent",
            "weight": 0.0,
            "opacity": 0.0,
            "fillOpacity": 0.34,
        },
        show=False,
    )

    selected = work[work["selected"] == 1].copy()
    _add_geojson_layer(
        fmap,
        "4. Valda hex",
        selected,
        lambda feature: {
            "fillColor": "#D62839",
            "color": "#8F1021",
            "weight": 1.5,
            "fillOpacity": 0.25,
        },
        show=True,
    )

    removed = work[work["removed_by_user"] == True].copy()
    _add_geojson_layer(
        fmap,
        "5. Manuellt borttagna hex",
        removed,
        lambda feature: {
            "fillColor": "#2F2F2F",
            "color": "#111111",
            "weight": 1.1,
            "fillOpacity": 0.20,
        },
        show=False,
    )

    bounds = _map_bounds(work)
    if bounds is not None:
        fmap.fit_bounds(bounds, padding=(8, 8))

    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


st.set_page_config(page_title="Sol och Vind Prototype", layout="wide")
st.title("Sol och Vind Prototype (Bornholm)")
st.caption("Förenklad app för scenarier, markintensitet och landskapsacceptans för vind och sol.")

app_base = Path(__file__).resolve().parent
project_root = app_base.parents[1]

hex_path = _resolve_hex_path(project_root)
if hex_path is None:
    st.error("Saknar res9-hexagondata. Förväntad fil är `data/gc4/bornholm_vindacceptans_stage1_v4_res9_hex.geojson`.")
    st.stop()
area_demand_path = _resolve_area_demand_path(project_root)
if area_demand_path is None:
    st.error("Saknar `AreaDemand.xlsx` i `data/raw`.")
    st.stop()

try:
    hex_df = load_hex_context(str(hex_path))
except Exception as exc:
    st.error(f"Kunde inte läsa hexagondata ({exc})")
    st.stop()

map_df = build_map_frame(hex_df).dropna(subset=["polygon", "lat", "lon"]).copy()
if map_df.empty:
    st.error("Hexkartan blev tom efter inläsning.")
    st.stop()

suitability_df = _build_suitability(hex_df)
analysis_df = map_df.merge(suitability_df, on="hex_id", how="left")
analysis_df = _add_solar_acceptance(analysis_df)

for option in WIND_OPTION_ORDER:
    analysis_df[f"wind_allowed_selected__{option}"] = analysis_df[f"allowed_for_wind_{option}"].fillna(False).astype(bool)
    analysis_df[f"wind_score_selected__{option}"] = pd.to_numeric(
        analysis_df[f"acceptance_score_{option}"], errors="coerce"
    ).fillna(0.0)
for option in SOLAR_OPTION_ORDER:
    analysis_df[f"solar_allowed_selected__{option}"] = analysis_df[f"allowed_for_solar_{option}"].fillna(False).astype(bool)

try:
    times_rows, scenario_desc, times_status = load_times_inputs(str(project_root))
except Exception as exc:
    st.error(f"Kunde inte läsa vind- och solrader från DuckDB ({exc})")
    st.stop()

scenario_totals, base_mix_map, raw_mix_df = _build_times_summary(times_rows)
if not scenario_totals:
    st.error("DuckDB:n gav inga scenarier för vind och sol.")
    st.stop()

area_bundle = build_area_demand_scenario_bundle(area_demand_path, times_techs=["NRG_WIN", "NRG_SOL"])
area_table = pd.DataFrame(area_bundle.get("scenario_table", pd.DataFrame())).copy()
observation_table = pd.DataFrame(area_bundle.get("observation_table", pd.DataFrame())).copy()
references = list(area_bundle.get("references", []))

scenario_options = sorted(scenario_totals.keys())
default_scenario_index = scenario_options.index("ENERGYISLAND2050") if "ENERGYISLAND2050" in scenario_options else 0

st.sidebar.markdown("### 3.1 Scenario")
scenario = st.sidebar.selectbox(
    "Välj scenario",
    scenario_options,
    index=default_scenario_index,
    format_func=lambda scenario_id: _scenario_display_label(str(scenario_id), scenario_desc),
)
scenario_label = _scenario_display_label(str(scenario), scenario_desc)
scenario_years = sorted(int(year) for year in scenario_totals.get(str(scenario), {}).keys())
default_year = 2050 if 2050 in scenario_years else scenario_years[-1]
year = st.sidebar.segmented_control(
    "Scenarioår (TIMES)",
    options=scenario_years,
    default=default_year,
    selection_mode="single",
)
if year is None:
    year = default_year
st.sidebar.caption(
    "Appen läser bara `NRG_WIN` och `NRG_SOL` från DuckDB i den här förenklade versionen. "
    "Scenarier och år hämtas direkt från DuckDB-strukturen, så om EML levererar en ny fil följer appen den. "
    "[Öppna EML-modellen](https://energymodellinglab.up.railway.app/)."
)

st.sidebar.markdown("### 3.2 Markintensitet")
area_scenario_id = st.sidebar.select_slider(
    "Markintensitetsscenario",
    options=list(AREA_SCENARIO_ORDER),
    value="mid",
    format_func=_area_scenario_label,
)
st.sidebar.caption("Lågt, Mellan och Högt byggs direkt från litteraturspann i `AreaDemand.xlsx`.")

st.sidebar.markdown("### 3.3.1 Landskaps-acceptans-vind")
wind_acceptance_id = st.sidebar.segmented_control(
    "Ny vindkraft",
    options=list(WIND_OPTION_ORDER),
    default="medium_acceptance",
    selection_mode="single",
    format_func=_acceptance_label,
)
if wind_acceptance_id is None:
    wind_acceptance_id = "medium_acceptance"

st.sidebar.markdown("### 3.3.2 Landskaps-acceptans-sol")
solar_acceptance_id = st.sidebar.segmented_control(
    "Ny solkraft",
    options=list(SOLAR_OPTION_ORDER),
    default="medium_acceptance",
    selection_mode="single",
    format_func=_acceptance_label,
)
if solar_acceptance_id is None:
    solar_acceptance_id = "medium_acceptance"
st.sidebar.caption(
    "Solacceptans är härledd från landskapsmodellens solar-suitability: "
    "Hög = övre 75 %, Mellan = övre 50 %, Låg = övre 25 %."
)
st.sidebar.caption("Separat solacceptanslager finns ännu inte, så 3.3.2 är tills vidare ett provisoriskt lager.")

base_total_twh = float(scenario_totals.get(str(scenario), {}).get(int(year), 0.0))
base_mix = base_mix_map.get(str(scenario), {}).get(int(year), {"wind": 50.0, "solar": 50.0})
base_mix = _normalize_mix_100({"wind": float(base_mix.get("wind", 0.0)), "solar": float(base_mix.get("solar", 0.0))})
_sync_mix_state(base_mix)

st.sidebar.markdown("### 3.4 Elmix")
if st.sidebar.button("Återställ till TIMES-mix", use_container_width=True):
    _set_mix_state(base_mix)
slider_keys = ["mix_wind", "mix_solar"]
st.sidebar.slider("Vind", min_value=0.0, max_value=100.0, step=0.1, key="mix_wind", on_change=_rebalance_slider, args=("mix_wind", slider_keys))
st.sidebar.slider("Sol", min_value=0.0, max_value=100.0, step=0.1, key="mix_solar", on_change=_rebalance_slider, args=("mix_solar", slider_keys))
mix_pct = _normalize_mix_100(
    {
        "wind": float(st.session_state.get("mix_wind", 0.0)),
        "solar": float(st.session_state.get("mix_solar", 0.0)),
    }
)
st.sidebar.caption(f"Summa elmix: {mix_pct['wind'] + mix_pct['solar']:.1f}%")

mix_rows = pd.DataFrame(
    [
        {"times_tech": "NRG_WIN", "energy_key": "wind", "TWh": base_total_twh * mix_pct["wind"] / 100.0},
        {"times_tech": "NRG_SOL", "energy_key": "solar", "TWh": base_total_twh * mix_pct["solar"] / 100.0},
    ]
)
factor_map = dict(area_bundle.get("factors_by_scenario", {}).get(str(area_scenario_id), {}))
mix_rows["km2_per_twh"] = mix_rows["times_tech"].map(factor_map)
mix_rows["area_need_km2"] = mix_rows["TWh"] * mix_rows["km2_per_twh"]
mix_rows["Teknik"] = mix_rows["energy_key"].map(ENERGY_LABELS)
total_area_need = float(mix_rows["area_need_km2"].sum())

wind_allowed_col = f"wind_allowed_selected__{wind_acceptance_id}"
solar_allowed_col = f"solar_allowed_selected__{solar_acceptance_id}"
analysis_df["wind_allowed_selected"] = analysis_df[wind_allowed_col].fillna(False).astype(bool)
analysis_df["wind_acceptance_score_selected"] = analysis_df[f"wind_score_selected__{wind_acceptance_id}"].fillna(0.0)
analysis_df["solar_allowed_selected"] = analysis_df[solar_allowed_col].fillna(False).astype(bool)

build = analysis_df.copy()
hex_area_km2 = float(pd.to_numeric(build["hex_area_km2"], errors="coerce").dropna().median())
if not math.isfinite(hex_area_km2) or hex_area_km2 <= 0:
    hex_area_km2 = 0.1
hex_need_total = int(math.ceil(total_area_need / max(hex_area_km2, 1e-9))) if total_area_need > 0 else 0

if "hex_selection_mode" not in st.session_state:
    st.session_state["hex_selection_mode"] = "auto"
if "hex_add_text" not in st.session_state:
    st.session_state["hex_add_text"] = ""
if "hex_remove_text" not in st.session_state:
    st.session_state["hex_remove_text"] = ""

selection_mode = str(st.session_state.get("hex_selection_mode", "auto"))
add_text = str(st.session_state.get("hex_add_text", ""))
remove_text = str(st.session_state.get("hex_remove_text", ""))

candidates = _build_selection_candidates(build, mix_pct, wind_allowed_col, solar_allowed_col)
auto_selected = _build_auto_allocation(candidates, mix_rows, hex_area_km2, wind_allowed_col, solar_allowed_col)
auto_selected_hexes = set(auto_selected["hex_id"].astype(str).tolist())

editor_selected_hexes: set[str] = set(auto_selected_hexes)
added_hexes: list[str] = []
removed_hexes: list[str] = []
invalid_add_hexes: list[str] = []
invalid_remove_hexes: list[str] = []

if selection_mode == "adjust":
    valid_hexes = set(candidates["hex_id"].astype(str).tolist())
    added_hexes, invalid_add_hexes = _parse_hex_input(add_text, valid_hexes)
    removed_hexes, invalid_remove_hexes = _parse_hex_input(remove_text, valid_hexes)

top_candidates = candidates.head(min(250, len(candidates))).copy()
top_candidates["vald"] = top_candidates["hex_id"].astype(str).isin(auto_selected_hexes)

final_selected_hexes = set(auto_selected_hexes)
if selection_mode == "adjust":
    top_hexes = set(top_candidates["hex_id"].astype(str).tolist())
    final_selected_hexes = (auto_selected_hexes - top_hexes) | editor_selected_hexes
    final_selected_hexes |= set(added_hexes)
    final_selected_hexes -= set(removed_hexes)

final_selected = pd.DataFrame({"hex_id": sorted(final_selected_hexes)})
final_selected["selected"] = 1
final_selected = final_selected.merge(auto_selected, on="hex_id", how="left")
final_selected["selected_for"] = final_selected["selected_for"].fillna("Manuellt tillagd")

view = build.merge(final_selected, on="hex_id", how="left")
view["selected"] = view["selected"].fillna(0).astype(int)
view["selected_for"] = view["selected_for"].fillna("")
view["removed_by_user"] = view["hex_id"].astype(str).isin(removed_hexes)
view["added_by_user"] = view["hex_id"].astype(str).isin(added_hexes)

if invalid_add_hexes:
    st.warning("Kunde inte lägga till följande hex_id eftersom de inte finns i kartlagret: " + ", ".join(invalid_add_hexes))
if invalid_remove_hexes:
    st.warning("Kunde inte ta bort följande hex_id eftersom de inte finns i kartlagret: " + ", ".join(invalid_remove_hexes))

wind_allowed_count = int(view["wind_allowed_selected"].sum())
solar_allowed_count = int(view["solar_allowed_selected"].sum())

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Scenario", scenario_label)
m2.metric("År", str(year))
m3.metric("Vind + sol från DuckDB (TWh)", f"{base_total_twh:.3f}")
m4.metric("Markanspråk (km²)", f"{total_area_need:.2f}")
m5.metric("Hexbehov", str(hex_need_total))

if base_total_twh <= 0.01:
    st.warning("Valt scenarioår innehåller mycket lite vind och sol i DuckDB:n. Kartan blir därför nästan tom.")

map_col, side_col = st.columns([1.8, 1.1], gap="large")

with map_col:
    st.subheader("Karta")
    legend_items = [
        ("1 - Tätorts- och verksamhetskärnor", [111, 127, 143, 175]),
        ("2 - Vardagslandskap med blandad bakgrundskaraktär", [216, 195, 106, 180]),
        ("3 - Flygsands- och låglänta kuststråk", [217, 154, 122, 180]),
        ("4 - Brant relief och dalpräglat inland", [167, 184, 138, 180]),
        ("5 - Skogligt inland och habitatkärnor", [88, 114, 76, 185]),
        ("Vindacceptans", [58, 142, 65, 150]),
        ("Solacceptans, provisorisk", [224, 178, 45, 150]),
        ("Valda hex", [214, 40, 57, 185]),
        ("Borttagna hex", [45, 45, 45, 180]),
    ]
    folium_map = _render_leaflet_map(view, wind_acceptance_id, _acceptance_label(solar_acceptance_id))
    st_folium(folium_map, use_container_width=True, height=760, returned_objects=[])
    st.caption(
        f"Lager i kartan: landskapsanalys, vindacceptans för `{_acceptance_label(wind_acceptance_id)}`, "
        f"solacceptans `{_acceptance_label(solar_acceptance_id)}` som provisoriskt lager, "
        f"samt valda hex. Klicka på ett hex för detaljinformation."
    )
    st.caption(
        f"Vindacceptans `{_acceptance_label(wind_acceptance_id)}`: {wind_allowed_count} av {len(view)} hex tillåtna. "
        f"Solacceptans `{_acceptance_label(solar_acceptance_id)}`: {solar_allowed_count} av {len(view)} hex tillåtna."
    )

with side_col:
    st.subheader("Beräkning")
    _render_map_legend(legend_items)
    calc_df = mix_rows[["Teknik", "TWh", "km2_per_twh", "area_need_km2"]].rename(
        columns={"km2_per_twh": "km²/TWh", "area_need_km2": "km²"}
    )
    st.dataframe(calc_df.round(3), use_container_width=True, hide_index=True)
    st.caption(
        f"Markintensitet: `{_area_scenario_label(area_scenario_id)}`. "
        f"Hexarea (median): `{hex_area_km2:.3f} km²`. "
        f"TIMES-status: `{times_status}`."
    )
    if len(final_selected_hexes) < hex_need_total:
        st.warning("Valda hex täcker inte hela beräknat markanspråk.")
    else:
        st.success("Valda hex täcker minst det beräknade markanspråket.")

    raw_breakdown = raw_mix_df[
        (raw_mix_df["scen"].astype(str) == str(scenario))
        & (pd.to_numeric(raw_mix_df["year"], errors="coerce") == int(year))
    ].copy()
    raw_breakdown["Teknik"] = raw_breakdown["energy_key"].map(ENERGY_LABELS)
    raw_breakdown = raw_breakdown[["Teknik", "value_twh"]].rename(columns={"value_twh": "TIMES TWh"})
    st.markdown("#### Vind + sol från TIMES")
    st.dataframe(raw_breakdown.round(6), use_container_width=True, hide_index=True)

with st.expander("Markintensitet: definitioner, Excel-värden och referenser", expanded=False):
    st.write("Scenarierna byggs direkt från `AreaDemand.xlsx` för `NRG_WIN` och `NRG_SOL`.")
    st.write(str(area_bundle.get("rules_text", "")))
    if not area_table.empty:
        st.dataframe(area_table.round(3), use_container_width=True, hide_index=True)
    if not observation_table.empty:
        st.markdown("##### Excel-observationer som används")
        st.dataframe(observation_table.round(3), use_container_width=True, hide_index=True, height=280)
    if references:
        st.markdown("##### Referenser från workbooken")
        for reference in references:
            st.write(f"- {reference}")

with st.expander("Urval och justeringar", expanded=False):
    st.write(
        "Auto-urvalet rankar vind och sol separat mot sina respektive acceptansfilter. "
        "I läget `Auto + justera` kan du både lägga till och ta bort specifika hexagoner."
    )
    st.radio(
        "Urvalsmetod för hex",
        options=list(SELECTION_MODE_LABELS),
        horizontal=True,
        format_func=_selection_mode_label,
        key="hex_selection_mode",
    )
    if st.session_state.get("hex_selection_mode") == "adjust":
        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            st.text_area(
                "Lägg till hex_id (ett per rad eller kommaseparerat)",
                key="hex_add_text",
                height=110,
                placeholder="891f2a75053ffff",
            )
        with exp_col2:
            st.text_area(
                "Ta bort hex_id (ett per rad eller kommaseparerat)",
                key="hex_remove_text",
                height=110,
                placeholder="891f2a75197ffff",
            )
        st.caption(
            "Det här är en tillfällig lösning. Nästa steg är ett riktigt klick-urval direkt i kartan."
        )
    if selection_mode == "adjust":
        if added_hexes:
            st.write("Manuellt tillagda hex:")
            st.write(", ".join(added_hexes))
        if removed_hexes:
            st.write("Manuellt borttagna hex:")
            st.write(", ".join(removed_hexes))
