import hashlib
import math
import os
import re
import shutil
import struct
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path

try:
    import altair as alt
except Exception:  # pragma: no cover
    alt = None

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

try:
    from apps.gc4.area_demand_scenarios import (
        SCENARIO_LABELS as AREA_SCENARIO_LABELS,
        SCENARIO_ORDER as AREA_SCENARIO_ORDER,
        TIMES_TECH_RULES as AREA_SCENARIO_TIMES_RULES,
        build_area_demand_scenario_bundle,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from area_demand_scenarios import (
        SCENARIO_LABELS as AREA_SCENARIO_LABELS,
        SCENARIO_ORDER as AREA_SCENARIO_ORDER,
        TIMES_TECH_RULES as AREA_SCENARIO_TIMES_RULES,
        build_area_demand_scenario_bundle,
    )

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

try:
    import h3
except Exception:  # pragma: no cover
    h3 = None


DEFAULT_AREA_FACTORS = {"wind": 1.20, "solar": 2.10, "nuclear": 0.12}  # km2/TWh
DEFAULT_AREA_FACTOR_GENERIC = 1.00
ENERGY_LABELS = {
    "sv": {
        "wind": "Vind",
        "solar": "Sol",
        "nuclear": "Kärnkraft",
        "hydro": "Vattenkraft",
        "bio": "Bioenergi",
        "coal": "Kol",
        "gas": "Gas",
        "oil": "Olja",
        "renewables": "Förnybart",
        "electricity": "El",
        "demand": "Efterfrågan",
        "other": "Övrigt",
    },
    "en": {
        "wind": "Wind",
        "solar": "Solar",
        "nuclear": "Nuclear",
        "hydro": "Hydropower",
        "bio": "Bioenergy",
        "coal": "Coal",
        "gas": "Gas",
        "oil": "Oil",
        "renewables": "Renewables",
        "electricity": "Electricity",
        "demand": "Demand",
        "other": "Other",
    },
}
AREA_SCENARIO_UI_LABELS = {
    "low": {"sv": "Lågt markanspråk", "en": "Low land demand"},
    "mid": {"sv": "Mellan", "en": "Medium"},
    "high": {"sv": "Högt", "en": "High"},
}
SELECTION_MODE_UI_LABELS = {
    "auto": {"sv": "Auto", "en": "Auto"},
    "manual": {"sv": "Manuellt", "en": "Manual"},
}
WIND_PLACEMENT_ORDER = ("high_acceptance", "medium_acceptance", "low_acceptance")
WIND_PLACEMENT_UI_LABELS = {
    "high_acceptance": {"sv": "Hög", "en": "High"},
    "medium_acceptance": {"sv": "Mellan", "en": "Medium"},
    "low_acceptance": {"sv": "Låg", "en": "Low"},
}
ENERGY_COMGROUP_MAP = {
    "nrg_win": "wind",
    "nrg_sol": "solar",
    "nrg_hyd": "hydro",
    "nrg_nuk": "nuclear",
    "nrg_nuc": "nuclear",
    "nrg_sbio": "bio",
    "nrg_bio": "bio",
    "nrg_bga": "bio",
    "nrg_bfu": "bio",
    "nrg_man": "bio",
    "nrg_gas": "gas",
    "nrg_coal": "coal",
    "nrg_coa": "coal",
    "nrg_foil": "oil",
    "nrg_oil": "oil",
    "nrg_elc": "electricity",
    "nrg_elec": "electricity",
    "nrg_rnw": "renewables",
    "nrg_rew": "renewables",
    "nrg_amb": "other",
    "nrg_dhea": "other",
    "nrg_wst": "other",
}
ENERGY_TECHGROUP_MAP = {
    "tg_bio": "bio",
    "tg_elc": "electricity",
    "tg_gas": "gas",
    "tg_nuc": "nuclear",
    "tg_rew": "renewables",
    "tg_coa": "coal",
    "tg_oil": "oil",
    "tg_dmd": "demand",
}
ENERGY_EXACT_TOKEN_MAP = {
    "wind": "wind",
    "win": "wind",
    "solar": "solar",
    "sol": "solar",
    "hydro": "hydro",
    "water": "hydro",
    "nuclear": "nuclear",
    "nuc": "nuclear",
    "biomass": "bio",
    "bio": "bio",
    "coal": "coal",
    "coa": "coal",
    "gas": "gas",
    "oil": "oil",
    "electricity": "electricity",
    "elc": "electricity",
    "demand": "demand",
    "dem": "demand",
    "dsl": "oil",
    "gsl": "oil",
    "hfo": "oil",
    "lpg": "oil",
    "nap": "oil",
    "ker": "oil",
}
ENERGY_PREFIX_RULES = (
    ("elcwin", "wind"),
    ("minwin", "wind"),
    ("elcsol", "solar"),
    ("minsol", "solar"),
    ("elehyd", "hydro"),
    ("elenuc", "nuclear"),
    ("elegas", "gas"),
    ("eleoil", "oil"),
    ("elebio", "bio"),
)
ENERGY_SUFFIX_RULES = (
    ("dsl", "oil"),
    ("gsl", "oil"),
    ("lpg", "oil"),
    ("hfo", "oil"),
    ("nap", "oil"),
)
UNIT_TO_TWH = {
    "twh": 1.0,
    "gwh": 1e-3,
    "mwh": 1e-6,
    "pj": 1.0 / 3.6,
    "tj": 1.0 / 3600.0,
}
HOURS_PER_YEAR = 8760.0
SUITABILITY_TECHS = (
    "wind",
    "solar",
    "nuclear",
    "hydro",
    "bio",
    "coal",
    "gas",
    "oil",
    "renewables",
    "electricity",
    "demand",
    "other",
)

CLUSTER_COLORS = {
    0: [166, 219, 210, 90],
    1: [253, 174, 97, 90],
    2: [255, 255, 191, 90],
    3: [231, 212, 232, 90],
    4: [215, 25, 28, 90],
    5: [255, 237, 111, 90],
    6: [171, 217, 233, 90],
    7: [197, 176, 213, 90],
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


def _current_language() -> str:
    language = str(st.session_state.get("ui_language", "sv")).strip().lower()
    if language not in {"sv", "en"}:
        language = "sv"
    st.session_state["ui_language"] = language
    return language


def _tr(sv: str, en: str) -> str:
    return sv if _current_language() == "sv" else en


def _toggle_language() -> None:
    st.session_state["ui_language"] = "en" if _current_language() == "sv" else "sv"


def _language_switch_label() -> str:
    return "Switch to English" if _current_language() == "sv" else "Byt till svenska"


def _language_status_label() -> str:
    return "Svenska" if _current_language() == "sv" else "English"


def _area_scenario_label(scenario_id: str) -> str:
    labels = AREA_SCENARIO_UI_LABELS.get(str(scenario_id), {})
    fallback = AREA_SCENARIO_LABELS.get(str(scenario_id), str(scenario_id))
    return labels.get(_current_language(), fallback)


def _selection_mode_label(selection_mode: str) -> str:
    labels = SELECTION_MODE_UI_LABELS.get(str(selection_mode), {})
    fallback = str(selection_mode)
    return labels.get(_current_language(), fallback)


def _wind_placement_label(scenario_id: str) -> str:
    labels = WIND_PLACEMENT_UI_LABELS.get(str(scenario_id), {})
    fallback = str(scenario_id)
    return labels.get(_current_language(), fallback)


def _wind_allowed_column(scenario_id: str) -> str:
    return f"allowed_for_wind_{scenario_id}"


def _wind_score_column(scenario_id: str) -> str:
    return f"acceptance_score_{scenario_id}"


def _wind_class_column(scenario_id: str) -> str:
    return f"acceptance_class_{scenario_id}"


def _wind_reason_column(scenario_id: str) -> str:
    return f"exclusion_reason_{scenario_id}"


def _translate_columns(rename_map: dict[str, tuple[str, str]]) -> dict[str, str]:
    return {column: _tr(sv, en) for column, (sv, en) in rename_map.items()}


def _translate_app_category_column(df: pd.DataFrame, column: str = "Appkategori") -> pd.DataFrame:
    if column not in df.columns:
        return df
    display_df = df.copy()
    display_df[column] = display_df[column].map(
        lambda value: _human_tech_name(str(value)) if str(value).strip() else ""
    )
    return display_df


def _rgba_css(color: list[int] | tuple[int, ...]) -> str:
    if not isinstance(color, (list, tuple)) or len(color) < 4:
        return "rgba(180, 180, 180, 0.5)"
    r, g, b, a = color[:4]
    alpha = max(0.0, min(1.0, float(a) / 255.0))
    return f"rgba({int(r)}, {int(g)}, {int(b)}, {alpha:.3f})"


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
            f"<div style='font-size:0.82rem;font-weight:600;margin-bottom:0.2rem;'>{_tr('Teckenförklaring', 'Legend')}</div>"
            + "".join(blocks)
            + "</div>"
        ),
        unsafe_allow_html=True,
    )


def _utm33n_to_lonlat(easting: float, northing: float) -> tuple[float, float]:
    # EPSG:32633 -> EPSG:4326 using the standard WGS84 UTM inverse transform.
    a = 6378137.0
    ecc_sq = 0.0066943799901413165
    ecc_prime_sq = ecc_sq / (1.0 - ecc_sq)
    k0 = 0.9996
    x = float(easting) - 500000.0
    y = float(northing)
    m = y / k0
    mu = m / (
        a
        * (
            1.0
            - ecc_sq / 4.0
            - 3.0 * ecc_sq**2 / 64.0
            - 5.0 * ecc_sq**3 / 256.0
        )
    )
    e1 = (1.0 - math.sqrt(1.0 - ecc_sq)) / (1.0 + math.sqrt(1.0 - ecc_sq))
    j1 = 3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0
    j2 = 21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0
    j3 = 151.0 * e1**3 / 96.0
    j4 = 1097.0 * e1**4 / 512.0
    fp = mu + j1 * math.sin(2.0 * mu) + j2 * math.sin(4.0 * mu) + j3 * math.sin(6.0 * mu) + j4 * math.sin(8.0 * mu)
    sin_fp = math.sin(fp)
    cos_fp = math.cos(fp)
    tan_fp = math.tan(fp)
    c1 = ecc_prime_sq * cos_fp**2
    t1 = tan_fp**2
    n1 = a / math.sqrt(1.0 - ecc_sq * sin_fp**2)
    r1 = a * (1.0 - ecc_sq) / (1.0 - ecc_sq * sin_fp**2) ** 1.5
    d = x / (n1 * k0)
    q1 = n1 * tan_fp / r1
    q2 = d**2 / 2.0
    q3 = (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1**2 - 9.0 * ecc_prime_sq) * d**4 / 24.0
    q4 = (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1**2 - 252.0 * ecc_prime_sq - 3.0 * c1**2) * d**6 / 720.0
    lat = fp - q1 * (q2 - q3 + q4)
    q5 = d
    q6 = (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
    q7 = (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1**2 + 8.0 * ecc_prime_sq + 24.0 * t1**2) * d**5 / 120.0
    lon_origin = math.radians(15.0)
    lon = lon_origin + (q5 - q6 + q7) / cos_fp
    return math.degrees(lat), math.degrees(lon)


def _signed_ring_area_xy(ring: list[tuple[float, float]]) -> float:
    if len(ring) < 3:
        return 0.0
    area = 0.0
    for idx, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(idx + 1) % len(ring)]
        area += x1 * y2 - x2 * y1
    return 0.5 * area


def _polygon_area_xy(rings: list[list[tuple[float, float]]]) -> float:
    if not rings:
        return 0.0
    outer = abs(_signed_ring_area_xy(rings[0]))
    holes = sum(abs(_signed_ring_area_xy(ring)) for ring in rings[1:])
    return max(0.0, outer - holes)


def _read_wkb_polygon(data: bytes, offset: int = 0) -> tuple[list[list[tuple[float, float]]], int]:
    byte_order = data[offset]
    endian = "<" if byte_order == 1 else ">"
    offset += 1
    geom_type = struct.unpack_from(f"{endian}I", data, offset)[0]
    offset += 4
    if geom_type % 1000 != 3:
        raise ValueError(f"Unsupported polygon geometry type: {geom_type}")
    ring_count = struct.unpack_from(f"{endian}I", data, offset)[0]
    offset += 4
    rings: list[list[tuple[float, float]]] = []
    for _ in range(ring_count):
        point_count = struct.unpack_from(f"{endian}I", data, offset)[0]
        offset += 4
        ring: list[tuple[float, float]] = []
        for _ in range(point_count):
            x, y = struct.unpack_from(f"{endian}dd", data, offset)
            offset += 16
            ring.append((float(x), float(y)))
        rings.append(ring)
    return rings, offset


def _read_wkb_geometry_collection(data: bytes, offset: int = 0) -> tuple[list[list[list[tuple[float, float]]]], int]:
    byte_order = data[offset]
    endian = "<" if byte_order == 1 else ">"
    offset += 1
    geom_type = struct.unpack_from(f"{endian}I", data, offset)[0]
    offset += 4
    base_type = geom_type % 1000
    if base_type == 3:
        offset -= 5
        polygon, offset = _read_wkb_polygon(data, offset)
        return [polygon], offset
    if base_type != 6:
        raise ValueError(f"Unsupported geometry collection type: {geom_type}")
    polygon_count = struct.unpack_from(f"{endian}I", data, offset)[0]
    offset += 4
    polygons: list[list[list[tuple[float, float]]]] = []
    for _ in range(polygon_count):
        polygon, offset = _read_wkb_polygon(data, offset)
        polygons.append(polygon)
    return polygons, offset


@lru_cache(maxsize=16384)
def _decode_gpkg_polygon(blob: bytes | None) -> tuple[object | None, float | None]:
    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 8 or bytes(blob[:2]) != b"GP":
        return None, None
    flags = int(blob[3])
    envelope_code = (flags >> 1) & 0b111
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    wkb_offset = 8 + envelope_sizes.get(envelope_code, 0)
    try:
        polygons_xy, _ = _read_wkb_geometry_collection(bytes(blob), wkb_offset)
    except Exception:
        return None, None
    if not polygons_xy:
        return None, None
    total_area_km2 = sum(_polygon_area_xy(rings) for rings in polygons_xy) / 1_000_000.0
    display_rings_xy = max(polygons_xy, key=_polygon_area_xy)
    display_rings = []
    for ring_xy in display_rings_xy:
        if len(ring_xy) < 4:
            continue
        lonlat_ring = []
        for x, y in ring_xy:
            lat, lon = _utm33n_to_lonlat(x, y)
            lonlat_ring.append([lon, lat])
        display_rings.append(lonlat_ring)
    if not display_rings:
        return None, total_area_km2 if total_area_km2 > 0 else None
    polygon = display_rings[0] if len(display_rings) == 1 else display_rings
    return polygon, total_area_km2 if total_area_km2 > 0 else None


def _find_first_col(columns: list[str], tokens: list[str]) -> str | None:
    for c in columns:
        low = c.lower()
        if any(t in low for t in tokens):
            return c
    return None


def _read_table_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".gpkg":
        import sqlite3

        with sqlite3.connect(path) as con:
            layer_df = pd.read_sql_query(
                "SELECT table_name FROM gpkg_contents WHERE data_type = 'features' ORDER BY table_name LIMIT 1",
                con,
            )
            if layer_df.empty:
                raise ValueError(f"Inget feature-lager hittades i geopackage: {path}")
            layer_name = str(layer_df.iloc[0]["table_name"])
            geom_df = pd.read_sql_query(
                "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?",
                con,
                params=[layer_name],
            )
            geom_col = str(geom_df.iloc[0]["column_name"]) if not geom_df.empty else None
            col_df = pd.read_sql_query(f'PRAGMA table_info("{layer_name}")', con)
            selected_cols = []
            for name in col_df["name"].astype(str).tolist():
                if str(name) == str(geom_col):
                    selected_cols.append(f'"{name}" AS "__gpkg_geom__"')
                else:
                    selected_cols.append(f'"{name}"')
            if not selected_cols:
                raise ValueError(f"Inga attributkolumner hittades i geopackage-lagret: {path}")
            return pd.read_sql_query(f'SELECT {", ".join(selected_cols)} FROM "{layer_name}"', con)
    raise ValueError(f"Filformat stods inte: {path}")


def _default_area_factors() -> dict[str, float]:
    return {
        "wind": DEFAULT_AREA_FACTORS["wind"],
        "solar": DEFAULT_AREA_FACTORS["solar"],
        "nuclear": DEFAULT_AREA_FACTORS["nuclear"],
        "hydro": 1.20,
        "bio": 1.40,
        "coal": 0.90,
        "gas": 0.60,
        "oil": 0.70,
        "renewables": 1.30,
        "electricity": 1.00,
        "demand": 1.00,
        "other": DEFAULT_AREA_FACTOR_GENERIC,
    }


def _human_tech_name(tech: str) -> str:
    labels = ENERGY_LABELS.get(_current_language(), ENERGY_LABELS["sv"])
    return labels.get(tech, tech.replace("_", " ").title())


def _scenario_display_label(scen: str, descriptions: dict[str, str]) -> str:
    desc = str(descriptions.get(scen, "")).strip()
    if not desc or desc == scen:
        return scen
    return f"{desc} [{scen}]"


def _times_tech_code(comgroup: object = "", techgroup: object = "") -> str:
    comgroup_text = str(comgroup).strip().upper()
    if comgroup_text and comgroup_text not in {"NA", "NAN"}:
        return comgroup_text
    techgroup_text = str(techgroup).strip().upper()
    if techgroup_text and techgroup_text not in {"NA", "NAN"}:
        return techgroup_text
    return "UNKNOWN"


def _times_tech_display(times_tech: str, energy_key: str) -> str:
    human = _human_tech_name(energy_key)
    if not human:
        return times_tech
    return f"{times_tech} ({human})"


def _build_baseline_line_chart(
    data: pd.DataFrame,
    y_field: str,
    y_title: str,
    year_order: list[str],
    scenario_order: list[str],
    *,
    zero: bool = True,
    value_format: str = ".2f",
):
    if alt is None:
        return None
    return (
        alt.Chart(data)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=72), strokeWidth=2.5)
        .encode(
            x=alt.X("year_label:N", title=_tr("År", "Year"), sort=year_order),
            y=alt.Y(f"{y_field}:Q", title=y_title, scale=alt.Scale(zero=zero)),
            color=alt.Color("scenario_label:N", title=_tr("Scenario", "Scenario"), sort=scenario_order),
            tooltip=[
                alt.Tooltip("scenario_label:N", title=_tr("Scenario", "Scenario")),
                alt.Tooltip("year_label:N", title=_tr("År", "Year")),
                alt.Tooltip(f"{y_field}:Q", title=y_title, format=value_format),
            ],
        )
        .properties(height=320)
        .interactive()
    )


def _energy_tokens(*values: object) -> list[str]:
    tokens: list[str] = []
    for value in values:
        low = str(value).lower().strip()
        if not low or low == "nan":
            continue
        tokens.extend(re.findall(r"[a-z0-9]+", low))
    return tokens


def _tech_from_fields(
    techgroup: object = "",
    comgroup: object = "",
    prc: object = "",
    com: object = "",
) -> tuple[str, str]:
    comgroup_key = str(comgroup).lower().strip()
    if comgroup_key in ENERGY_COMGROUP_MAP:
        return ENERGY_COMGROUP_MAP[comgroup_key], "comgroup"

    techgroup_key = str(techgroup).lower().strip()
    if techgroup_key in ENERGY_TECHGROUP_MAP:
        return ENERGY_TECHGROUP_MAP[techgroup_key], "techgroup"

    tokens = _energy_tokens(prc, com, techgroup, comgroup)
    for token in tokens:
        if token in ENERGY_EXACT_TOKEN_MAP:
            return ENERGY_EXACT_TOKEN_MAP[token], "token"

    for token in tokens:
        for prefix, tech in ENERGY_PREFIX_RULES:
            if token.startswith(prefix):
                return tech, "token"

    for token in tokens:
        for suffix, tech in ENERGY_SUFFIX_RULES:
            if token.endswith(suffix):
                return tech, "token"

    return "other", "unmapped"


def _classify_energy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    if work.empty:
        work["energy_key"] = pd.Series(dtype="object")
        work["mapping_source"] = pd.Series(dtype="object")
        work["raw_mapping"] = pd.Series(dtype="object")
        return work

    energy_keys: list[str] = []
    mapping_sources: list[str] = []
    raw_mappings: list[str] = []
    raw_fields = ["techgroup", "comgroup", "prc", "com"]

    for row in work.to_dict("records"):
        tech, source = _tech_from_fields(
            techgroup=row.get("techgroup", ""),
            comgroup=row.get("comgroup", ""),
            prc=row.get("prc", ""),
            com=row.get("com", ""),
        )
        energy_keys.append(str(tech))
        mapping_sources.append(str(source))
        raw_mappings.append(
            " | ".join(
                [
                    str(row.get(name, "")).strip() if str(row.get(name, "")).strip() else "NA"
                    for name in raw_fields
                ]
            )
        )

    work["energy_key"] = energy_keys
    work["mapping_source"] = mapping_sources
    work["raw_mapping"] = raw_mappings
    return work


def _normalize_mix_100(values: dict[str, float]) -> dict[str, float]:
    keys = list(values.keys())
    if not keys:
        return {}
    clean = {k: max(0.0, float(values.get(k, 0.0))) for k in keys}
    s = sum(clean.values())
    if s <= 0:
        eq = 100.0 / len(keys)
        return {k: eq for k in keys}
    return {k: clean[k] * 100.0 / s for k in keys}


def _set_mix_state(tech_keys: list[str], values: dict[str, float]) -> None:
    normalized = _normalize_mix_100({tech: float(values.get(tech, 0.0)) for tech in tech_keys})
    for tech in tech_keys:
        st.session_state[f"mix_{tech}"] = float(normalized.get(tech, 0.0))


def _sync_mix_state(tech_keys: list[str], base_mix: dict[str, float]) -> None:
    ctx_key = "_mix_tech_ctx"
    current_ctx = "|".join(tech_keys)
    previous_ctx = str(st.session_state.get(ctx_key, ""))

    if not tech_keys:
        st.session_state[ctx_key] = current_ctx
        return

    if not previous_ctx:
        _set_mix_state(tech_keys, base_mix)
        st.session_state[ctx_key] = current_ctx
        return

    if previous_ctx == current_ctx:
        st.session_state[ctx_key] = current_ctx
        return

    preserved: dict[str, float] = {}
    for tech in tech_keys:
        state_key = f"mix_{tech}"
        if state_key in st.session_state:
            preserved[tech] = float(st.session_state.get(state_key, 0.0))
        else:
            preserved[tech] = float(base_mix.get(tech, 0.0))
    _set_mix_state(tech_keys, preserved)
    st.session_state[ctx_key] = current_ctx


def _build_base_mix_by_year(
    mix_rows: pd.DataFrame, scenario_totals: dict[str, dict[int, float]]
) -> dict[str, dict[int, dict[str, float]]]:
    if mix_rows.empty:
        return {}

    work = mix_rows.copy()
    work["scen"] = work["scen"].astype(str)
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work["energy_key"] = work["energy_key"].astype(str)
    work["value_twh"] = pd.to_numeric(work["value_twh"], errors="coerce")
    work = work.dropna(subset=["year", "value_twh"])
    if work.empty:
        return {}
    work["year"] = work["year"].astype(int)

    all_techs = sorted({str(v) for v in work["energy_key"].dropna().tolist() if str(v).strip()})
    if not all_techs:
        all_techs = ["other"]

    available_mix_lookup: dict[str, dict[int, dict[str, float]]] = {}
    for (scen, year), y_block in work.groupby(["scen", "year"]):
        by_tech = (
            y_block.groupby("energy_key", as_index=False)["value_twh"]
            .sum()
            .set_index("energy_key")["value_twh"]
            .to_dict()
        )
        available_mix_lookup.setdefault(str(scen), {})[int(year)] = _normalize_mix_100(
            {k: float(by_tech.get(k, 0.0)) for k in all_techs}
        )

    base_mix: dict[str, dict[int, dict[str, float]]] = {}
    for scen, year_totals in scenario_totals.items():
        yearly_mix: dict[int, dict[str, float]] = {}
        available_years = sorted(available_mix_lookup.get(str(scen), {}).keys())
        for year in sorted(int(y) for y in year_totals.keys()):
            if int(year) in available_mix_lookup.get(str(scen), {}):
                yearly_mix[int(year)] = dict(available_mix_lookup[str(scen)][int(year)])
                continue
            if available_years:
                fallback_year = min(available_years, key=lambda available: abs(available - int(year)))
                yearly_mix[int(year)] = dict(available_mix_lookup[str(scen)][fallback_year])
                continue
            yearly_mix[int(year)] = {"other": 100.0}
        if yearly_mix:
            base_mix[str(scen)] = yearly_mix
    return base_mix


def _resolve_base_mix_for_year(
    base_mix_map: dict[str, object], scenario: str, year: int
) -> dict[str, float]:
    scenario_mix = base_mix_map.get(str(scenario), {"other": 100.0})
    if not isinstance(scenario_mix, dict) or not scenario_mix:
        return {"other": 100.0}

    sample_value = next(iter(scenario_mix.values()))
    if isinstance(sample_value, dict):
        year_mix = scenario_mix.get(int(year))
        if isinstance(year_mix, dict) and year_mix:
            return dict(year_mix)
        available_years = sorted(int(y) for y in scenario_mix.keys())
        if available_years:
            fallback_year = min(available_years, key=lambda available: abs(available - int(year)))
            fallback_mix = scenario_mix.get(fallback_year, {})
            if isinstance(fallback_mix, dict) and fallback_mix:
                return dict(fallback_mix)
        return {"other": 100.0}

    return {str(k): float(v) for k, v in scenario_mix.items()}


def _rebalance_slider(changed_key: str, slider_keys: list[str]) -> None:
    vals = {k: float(st.session_state.get(k, 0.0)) for k in slider_keys}
    target = 100.0
    total = sum(vals.values())
    delta = target - total
    if abs(delta) < 1e-9:
        return

    others = [k for k in slider_keys if k != changed_key]
    if not others:
        st.session_state[changed_key] = target
        return

    other_sum = sum(max(0.0, vals[k]) for k in others)
    if other_sum <= 1e-12:
        share = delta / len(others)
        for k in others:
            st.session_state[k] = max(0.0, vals[k] + share)
    else:
        for k in others:
            weight = max(0.0, vals[k]) / other_sum
            st.session_state[k] = max(0.0, vals[k] + delta * weight)

    total2 = float(sum(float(st.session_state.get(k, 0.0)) for k in slider_keys))
    if abs(total2 - target) > 1e-6:
        st.session_state[changed_key] = max(
            0.0, float(st.session_state.get(changed_key, 0.0)) + (target - total2)
        )


def _normalize_text(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.strip()


def _as_twh(value: pd.Series, units: pd.Series) -> pd.Series:
    unit_norm = _normalize_text(units)
    factor = unit_norm.map(UNIT_TO_TWH).fillna(1.0)
    return pd.to_numeric(value, errors="coerce") * factor


def _find_timesreport_csv(project_root: Path) -> Path | None:
    candidates = [
        project_root / "external" / "DemoS_012_timesreport" / "TIMESreport" / "compare_timesreport.csv",
        project_root / "external" / "DemoS_012_timesreport" / "compare_timesreport.csv",
        project_root / "data" / "external" / "timesreport" / "compare_timesreport.csv",
    ]
    return next((p for p in candidates if p.exists()), None)


def _find_duckdb(project_root: Path) -> Path | None:
    candidates = [
        project_root / "data" / "processed" / "speedlocal_times.duckdb",
        project_root / "duckdb" / "speedlocal_times.duckdb",
    ]
    return next((p for p in candidates if p.exists()), None)


def _find_area_demand_xlsx(project_root: Path) -> Path | None:
    candidates = [
        project_root.parent / "eml" / "data" / "raw" / "AreaDemand.xlsx",
        project_root / "data" / "raw" / "AreaDemand.xlsx",
        Path.cwd() / "data" / "raw" / "AreaDemand.xlsx",
    ]
    return next((p for p in candidates if p.exists()), None)


def _find_area_profile_duckdb(project_root: Path) -> Path | None:
    candidates = [
        project_root / "data" / "processed" / "area_demand_profiles.duckdb",
        project_root / "data" / "processed" / "speedlocal_area_profiles.duckdb",
    ]
    return next((p for p in candidates if p.exists()), None)


def _config_path(name: str) -> Path | None:
    value = _get_config_value(name)
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def _find_res9_hex_gpkg(project_root: Path) -> Path | None:
    candidates = [
        project_root.parent
        / "landskapsanalys"
        / "docs"
        / "geocontext"
        / "acceptance_framework"
        / "data"
        / "bornholm_vindacceptans_stage1_v4_res9"
        / "bornholm_vindacceptans_stage1_v4_res9_hex.gpkg",
        project_root
        / "data"
        / "gc4"
        / "bornholm_vindacceptans_stage1_v4_res9_hex.gpkg",
    ]
    return next((p for p in candidates if p.exists()), None)


def _find_hex_points(project_root: Path) -> Path | None:
    configured = _config_path("HEX_POINTS_PATH")
    if configured is not None:
        return configured
    candidates = [
        _find_res9_hex_gpkg(project_root),
        project_root / "jyp_note_book_geocontext" / "bornholm_points_with_context_gc4.csv",
        project_root / "data" / "gc4" / "bornholm_points_with_context_gc4.csv",
    ]
    return next((p for p in candidates if p is not None and p.exists()), None)


def _find_hex_scores(project_root: Path) -> Path | None:
    configured = _config_path("HEX_SCORES_PATH")
    if configured is not None:
        return configured
    candidates = [
        project_root / "jyp_note_book_geocontext" / "bornholm_r8_factor_scores_gc4.csv",
        project_root / "data" / "gc4" / "bornholm_r8_factor_scores_gc4.csv",
    ]
    return next((p for p in candidates if p.exists()), None)


def _find_acceptance_layer(project_root: Path) -> Path | None:
    configured = _config_path("ACCEPTANCE_LAYER_PATH")
    if configured is not None:
        return configured
    candidates = [
        project_root / "data" / "processed" / "acceptance_layer.csv",
        project_root / "data" / "processed" / "acceptance_layer.parquet",
    ]
    return next((p for p in candidates if p.exists()), None)


def _resolve_hex_sources(project_root: Path) -> tuple[Path | None, Path | None, Path | None, str]:
    points_path = _find_hex_points(project_root)
    scores_path = _find_hex_scores(project_root)
    acceptance_path = _find_acceptance_layer(project_root)
    scores_configured = _config_path("HEX_SCORES_PATH") is not None
    acceptance_configured = _config_path("ACCEPTANCE_LAYER_PATH") is not None

    if points_path is not None and points_path.suffix.lower() == ".gpkg":
        if not scores_configured:
            scores_path = None
        if not acceptance_configured:
            acceptance_path = None

    parts: list[str] = []
    parts.append(f"points: {points_path}" if points_path is not None else "points: saknas")
    if points_path is not None and points_path.suffix.lower() == ".gpkg" and scores_path is None:
        parts.append("scores: inbyggt i points-gpkg")
    else:
        parts.append(f"scores: {scores_path}" if scores_path is not None else "scores: saknas")
    if acceptance_path is not None:
        parts.append(f"acceptance: {acceptance_path}")
    elif points_path is not None and points_path.suffix.lower() == ".gpkg":
        parts.append("acceptance: inbyggt i points-gpkg")
    return points_path, scores_path, acceptance_path, "; ".join(parts)


@st.cache_data(show_spinner=False, ttl=3600)
def _download_duckdb_share(share_url: str) -> tuple[str | None, str]:
    url = str(share_url).strip()
    if not url:
        return None, "duckdb share-url saknas"

    target_dir = Path(tempfile.gettempdir()) / "speedlocal_duckdb"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]}.duckdb"

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "speedlocal-streamlit"})
        with urllib.request.urlopen(request, timeout=120) as response, target_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:
        return None, f"duckdb share-download misslyckades ({exc})"

    return str(target_path), f"downloaded duckdb share: {target_path}"


def _resolve_duckdb(project_root: Path) -> tuple[Path | None, str]:
    env_path = _get_config_value("DUCKDB_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p, f"loaded duckdb env path: {p}"

    local_path = _find_duckdb(project_root)
    if local_path is not None:
        return local_path, f"loaded duckdb: {local_path}"

    share_url = _get_config_value("DUCKDB_SHARE_URL")
    if share_url:
        downloaded_path, status = _download_duckdb_share(share_url)
        if downloaded_path:
            return Path(downloaded_path), status
        return None, status

    return None, "duckdb-fil saknas"


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
    return [str(r[0]) for r in rows]


def _aggregate_energy_mix_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["scen", "year", "energy_key", "value_twh"])
    return (
        raw.groupby(["scen", "year", "energy_key"], as_index=False)["value_twh"]
        .sum()
        .sort_values(["scen", "year", "energy_key"])
    )


def _build_times_mapping_audit(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    empty_mix = pd.DataFrame(columns=["scen", "year", "energy_key", "value_twh", "share_pct", "row_count"])
    empty_coverage = pd.DataFrame(
        columns=[
            "scen",
            "year",
            "total_twh",
            "named_twh",
            "other_bucket_twh",
            "unmapped_twh",
            "named_share_pct",
            "other_bucket_share_pct",
            "unmapped_share_pct",
        ]
    )
    empty_mapping = pd.DataFrame(
        columns=["scen", "year", "energy_key", "mapping_source", "raw_mapping", "value_twh", "row_count"]
    )
    if raw.empty:
        return {"coverage": empty_coverage, "mix": empty_mix, "mapping": empty_mapping}

    mix = (
        raw.groupby(["scen", "year", "energy_key"], as_index=False)
        .agg(value_twh=("value_twh", "sum"), row_count=("energy_key", "size"))
        .sort_values(["scen", "year", "value_twh"], ascending=[True, True, False])
    )
    totals = (
        mix.groupby(["scen", "year"], as_index=False)["value_twh"]
        .sum()
        .rename(columns={"value_twh": "total_twh"})
    )
    mix = mix.merge(totals, on=["scen", "year"], how="left")
    mix["share_pct"] = np.where(mix["total_twh"] > 0, 100.0 * mix["value_twh"] / mix["total_twh"], 0.0)

    named = (
        mix[mix["energy_key"] != "other"]
        .groupby(["scen", "year"], as_index=False)["value_twh"]
        .sum()
        .rename(columns={"value_twh": "named_twh"})
    )
    other_bucket = (
        mix[mix["energy_key"] == "other"]
        .groupby(["scen", "year"], as_index=False)["value_twh"]
        .sum()
        .rename(columns={"value_twh": "other_bucket_twh"})
    )
    unmapped = (
        raw[raw["mapping_source"] == "unmapped"]
        .groupby(["scen", "year"], as_index=False)["value_twh"]
        .sum()
        .rename(columns={"value_twh": "unmapped_twh"})
    )

    coverage = totals.merge(named, on=["scen", "year"], how="left").merge(
        other_bucket, on=["scen", "year"], how="left"
    ).merge(unmapped, on=["scen", "year"], how="left")
    for column in ["named_twh", "other_bucket_twh", "unmapped_twh"]:
        coverage[column] = coverage[column].fillna(0.0)
    coverage["named_share_pct"] = np.where(
        coverage["total_twh"] > 0, 100.0 * coverage["named_twh"] / coverage["total_twh"], 0.0
    )
    coverage["other_bucket_share_pct"] = np.where(
        coverage["total_twh"] > 0, 100.0 * coverage["other_bucket_twh"] / coverage["total_twh"], 0.0
    )
    coverage["unmapped_share_pct"] = np.where(
        coverage["total_twh"] > 0, 100.0 * coverage["unmapped_twh"] / coverage["total_twh"], 0.0
    )
    coverage = coverage.sort_values(["scen", "year"]).reset_index(drop=True)

    mapping = (
        raw.groupby(["scen", "year", "energy_key", "mapping_source", "raw_mapping"], as_index=False)
        .agg(value_twh=("value_twh", "sum"), row_count=("energy_key", "size"))
        .sort_values(["scen", "year", "value_twh"], ascending=[True, True, False])
    )
    return {"coverage": coverage, "mix": mix, "mapping": mapping}


def _load_energy_rows_duckdb(con) -> tuple[pd.DataFrame | None, str]:
    source_table = next((name for name in ["timesreport_raw", "timesreport"] if _duckdb_has_object(con, name)), None)
    if source_table is None:
        return None, "duckdb saknar timesreport_raw/timesreport"

    cols = set(_duckdb_columns(con, source_table))
    required = {"scen", "year", "value", "topic", "attr"}
    missing = sorted(required - cols)
    if missing:
        return None, f"duckdb-tabell {source_table} saknar kolumner: {', '.join(missing)}"

    unit_col = "units" if "units" in cols else ("unit" if "unit" in cols else None)
    if unit_col is None:
        return None, f"duckdb-tabell {source_table} saknar units/unit"

    ts_col = "timeslice" if "timeslice" in cols else ("all_ts" if "all_ts" in cols else None)
    select_cols = ["scen", "year", "value", f"{unit_col} AS units"]
    for name in ["techgroup", "comgroup", "prc", "com"]:
        if name in cols:
            select_cols.append(name)

    where_clauses = [
        "lower(topic) = 'energy'",
        "lower(attr) IN ('f_out', 'comnet')",
        "TRY_CAST(year AS INTEGER) IS NOT NULL",
    ]
    if ts_col is not None:
        where_clauses.append(f"upper(coalesce({ts_col}, '')) = 'ANNUAL'")

    raw = con.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM {source_table}
        WHERE {" AND ".join(where_clauses)}
        """
    ).df()
    if raw.empty:
        return raw, f"duckdb-tabell {source_table} gav tomt resultat"

    raw = _classify_energy_frame(raw)
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce")
    raw["value_twh"] = _as_twh(raw["value"], raw["units"])
    raw = raw.dropna(subset=["year", "value_twh"])
    if raw.empty:
        return None, f"duckdb-tabell {source_table} saknar giltiga year/value"

    raw["year"] = raw["year"].astype(int)
    raw["scen"] = raw["scen"].astype(str)
    return raw, f"loaded duckdb raw: {source_table}"


def _load_energy_mix_frame_duckdb(con) -> tuple[pd.DataFrame | None, str]:
    if _duckdb_has_object(con, "v_energy_mix"):
        mix = con.execute(
            """
            SELECT
                scen,
                CAST(year AS INTEGER) AS year,
                COALESCE(energy_key, 'other') AS energy_key,
                value_twh
            FROM v_energy_mix
            WHERE TRY_CAST(year AS INTEGER) IS NOT NULL
            """
        ).df()
        return mix, "loaded duckdb view: v_energy_mix"

    raw, status = _load_energy_rows_duckdb(con)
    if raw is None:
        return None, status
    return _aggregate_energy_mix_frame(raw), status


def _load_preview_frame_duckdb(con) -> tuple[pd.DataFrame | None, dict[str, list[str]] | None, str]:
    source_table = next((name for name in ["timesreport_raw", "timesreport"] if _duckdb_has_object(con, name)), None)
    if source_table is None:
        return None, None, "duckdb preview: timesreport_raw/timesreport saknas"

    cols = _duckdb_columns(con, source_table)
    summary: dict[str, list[str]] = {}
    for key in ["scen", "techgroup", "comgroup", "topic", "attr"]:
        if key in cols:
            vals = con.execute(
                f"SELECT DISTINCT {key} AS value FROM {source_table} WHERE {key} IS NOT NULL ORDER BY 1 LIMIT 80"
            ).df()["value"].astype(str).tolist()
            summary[key] = vals

    unit_col = "units" if "units" in cols else ("unit" if "unit" in cols else None)
    if unit_col is not None:
        vals = con.execute(
            f"SELECT DISTINCT {unit_col} AS value FROM {source_table} WHERE {unit_col} IS NOT NULL ORDER BY 1 LIMIT 80"
        ).df()["value"].astype(str).tolist()
        summary["units"] = vals

    if "year" in cols:
        vals = con.execute(
            f"SELECT DISTINCT year AS value FROM {source_table} WHERE year IS NOT NULL ORDER BY 1 LIMIT 80"
        ).df()["value"].astype(str).tolist()
        summary["year"] = vals

    preview = con.execute(f"SELECT * FROM {source_table} LIMIT 25").df()
    return preview, summary, f"loaded duckdb preview: {source_table}"


def _load_energy_rows_csv(project_root: Path) -> tuple[pd.DataFrame | None, str]:
    csv_path = _find_timesreport_csv(project_root)
    if csv_path is None:
        return None, "fallback: compare_timesreport.csv saknas"

    try:
        raw = pd.read_csv(csv_path)
    except Exception as exc:
        return None, f"fallback: kunde inte lasa TIMESreport csv ({exc})"
    if raw.empty:
        return None, "fallback: TIMESreport csv tom"

    raw.columns = [str(c).strip().lower() for c in raw.columns]
    need = {"scen", "year", "value", "units"}
    if not need.issubset(set(raw.columns)):
        return None, "fallback: TIMESreport csv saknar nodvandiga kolumner (scen/year/value/units)"

    df = raw.copy()
    if "topic" in df.columns:
        df = df[_normalize_text(df["topic"]).isin(["energy"])]
    if "attr" in df.columns:
        attr_norm = _normalize_text(df["attr"])
        keep = attr_norm.isin(["f_out", "comnet"])
        if keep.any():
            df = df[keep]
    if "timeslice" in df.columns:
        ts_norm = _normalize_text(df["timeslice"])
        annual = ts_norm.eq("annual")
        if annual.any():
            df = df[annual]

    if df.empty:
        return None, "fallback: inga rader kvar efter TIMESreport-filtrering"

    df = _classify_energy_frame(df)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year"])
    if df.empty:
        return None, "fallback: inga giltiga ar hittades i TIMESreport csv"
    df["year"] = df["year"].astype(int)
    df["value_twh"] = _as_twh(df["value"], df["units"])
    df = df.dropna(subset=["value_twh"])
    if df.empty:
        return None, "fallback: alla values blev ogiltiga efter enhetskonvertering"

    df["scen"] = df["scen"].astype(str)
    return df, f"loaded: {csv_path}"


def load_timesreport_scenarios(
    project_root: Path,
) -> tuple[dict[str, dict[int, float]] | None, dict[str, dict[int, dict[str, float]]] | None, str]:
    df, load_status = _load_energy_rows_csv(project_root)
    if df is None:
        return None, None, load_status
    if df.empty:
        return None, None, load_status

    mix = _aggregate_energy_mix_frame(df)
    totals = mix.groupby(["scen", "year"], as_index=False)["value_twh"].sum()

    scenario_totals: dict[str, dict[int, float]] = {}
    for _, r in totals.iterrows():
        scenario_totals.setdefault(str(r["scen"]), {})[int(r["year"])] = float(r["value_twh"])

    if not scenario_totals:
        return None, None, "fallback: kunde inte bygga scenarios fran TIMESreport csv"

    base_mix = _build_base_mix_by_year(mix, scenario_totals)
    for scen, year_totals in scenario_totals.items():
        if scen not in base_mix:
            base_mix[scen] = {}
        for year in year_totals.keys():
            if int(year) not in base_mix[scen]:
                base_mix[scen][int(year)] = {"other": 100.0}

    return scenario_totals, base_mix, load_status


def load_timesreport_scenarios_duckdb(
    project_root: Path,
) -> tuple[dict[str, dict[int, float]] | None, dict[str, dict[int, dict[str, float]]] | None, str]:
    if duckdb is None:
        return None, None, "duckdb package saknas"
    db_path, db_status = _resolve_duckdb(project_root)
    if db_path is None:
        return None, None, db_status

    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        return None, None, f"duckdb kunde inte oppnas ({exc})"

    try:
        mix, mix_status = _load_energy_mix_frame_duckdb(con)
    except Exception as exc:
        con.close()
        return None, None, f"duckdb-fraga misslyckades ({exc})"
    finally:
        try:
            con.close()
        except Exception:
            pass

    if mix is None:
        return None, None, mix_status
    if mix.empty:
        return None, None, mix_status

    mix["scen"] = mix["scen"].astype(str)
    mix["year"] = pd.to_numeric(mix["year"], errors="coerce").astype("Int64")
    mix["value_twh"] = pd.to_numeric(mix["value_twh"], errors="coerce")
    mix = mix.dropna(subset=["year", "value_twh"])
    if mix.empty:
        return None, None, "duckdb-resultat saknar giltiga year/value_twh"
    mix["year"] = mix["year"].astype(int)

    totals = mix.groupby(["scen", "year"], as_index=False)["value_twh"].sum()
    scenario_totals: dict[str, dict[int, float]] = {}
    for _, r in totals.iterrows():
        scenario_totals.setdefault(str(r["scen"]), {})[int(r["year"])] = float(r["value_twh"])

    if not scenario_totals:
        return None, None, "duckdb innehaller inga scenariototaler"

    base_mix = _build_base_mix_by_year(mix, scenario_totals)
    for scen, year_totals in scenario_totals.items():
        if scen not in base_mix:
            base_mix[scen] = {}
        for year in year_totals.keys():
            if int(year) not in base_mix[scen]:
                base_mix[scen][int(year)] = {"other": 100.0}

    return scenario_totals, base_mix, f"{db_status}; {mix_status}"


def load_area_factors_duckdb(project_root: Path) -> tuple[dict[str, float] | None, str]:
    if duckdb is None:
        return None, "duckdb package saknas"
    db_path, db_status = _resolve_duckdb(project_root)
    if db_path is None:
        return None, db_status
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        if not _duckdb_has_object(con, "area_factors"):
            con.close()
            return None, f"{db_status}; area_factors saknas i duckdb"
        rows = con.execute("SELECT energy_key, km2_per_twh FROM area_factors").df()
        con.close()
    except Exception as exc:
        return None, f"kunde inte lasa area_factors i duckdb ({exc})"
    if rows.empty:
        return None, "area_factors tom i duckdb"
    out = {
        str(r["energy_key"]): float(r["km2_per_twh"])
        for _, r in rows.iterrows()
        if pd.notna(r["energy_key"]) and pd.notna(r["km2_per_twh"])
    }
    return (out if out else None), f"{db_status}; loaded area_factors"


def _area_metric_kind(metric: str) -> str | None:
    metric_low = str(metric).lower()
    if "gwh/km2" in metric_low:
        return "gwh_per_km2"
    if "w/m2" in metric_low:
        return "w_per_m2"
    return None


def _area_metric_label(metric: str) -> str:
    kind = _area_metric_kind(metric)
    if kind == "gwh_per_km2":
        return "Production density"
    if kind == "w_per_m2":
        return "Power density"
    return str(metric).strip()


def _area_profile_source_name(header: str, previous_header: str) -> str:
    clean = str(header).strip()
    if clean and not clean.lower().startswith("unnamed:"):
        return clean
    return previous_header.strip()


def _area_tech_from_text(text: str) -> str | None:
    low = str(text).lower().strip()
    if not low or low.startswith("sources:"):
        return None
    if any(token in low for token in ["hydro", "hyrdo", "hyrd", "run-of-river", "reservoir"]):
        return "hydro"
    if "wind" in low:
        return "wind"
    if "solar" in low:
        return "solar"
    if "smr" in low or "nuclear" in low:
        return "nuclear"
    if "biomass" in low or low.startswith("bio"):
        return "bio"
    if "gas" in low:
        return "gas"
    if "coal" in low:
        return "coal"
    if "oil" in low:
        return "oil"
    return None


def _extract_area_numbers(text: str) -> list[float]:
    cleaned = str(text).replace(",", ".")
    return [float(token) for token in re.findall(r"\d+(?:\.\d+)?", cleaned)]


def _representative_area_value(value: object) -> float | None:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    nums = _extract_area_numbers(text)
    if not nums:
        return None
    if "±" in text:
        return nums[0]
    if ("-" in text or "–" in text) and len(nums) >= 2:
        lo = min(nums[0], nums[1])
        hi = max(nums[0], nums[1])
        if lo > 0 and hi > 0:
            return math.sqrt(lo * hi)
        return (lo + hi) / 2.0
    return nums[0]


def _area_value_to_km2_per_twh(value: object, metric: str) -> float | None:
    rep = _representative_area_value(value)
    if rep is None or rep <= 0:
        return None
    kind = _area_metric_kind(metric)
    if kind == "gwh_per_km2":
        return 1000.0 / rep
    if kind == "w_per_m2":
        return 1000.0 / (rep * (HOURS_PER_YEAR / 1000.0))
    return None


def _recommended_area_profile_id(area_profiles: dict[str, dict[str, object]]) -> str | None:
    for profile_id, profile in area_profiles.items():
        if "norway specific" in str(profile.get("label", "")).lower():
            return profile_id
    return next(iter(area_profiles.keys()), None)


def _area_factor_source_label(source_key: str, profile_label: str) -> str:
    if source_key == "profile":
        return profile_label
    if source_key == "duckdb":
        return "DuckDB area_factors"
    if source_key == "fallback_default":
        return "Intern standard-fallback"
    if source_key == "missing_generic":
        return "Generisk fallback (1.0 km2/TWh)"
    return "Okand proveniens"


@st.cache_data(show_spinner=False)
def load_area_factor_profiles_xlsx(project_root: Path) -> tuple[dict[str, dict[str, object]], str]:
    xlsx_path = _find_area_demand_xlsx(project_root)
    if xlsx_path is None:
        return {}, "AreaDemand.xlsx saknas"

    try:
        raw = pd.read_excel(xlsx_path, sheet_name=0)
    except Exception as exc:
        return {}, f"kunde inte lasa AreaDemand.xlsx ({exc})"
    if raw.empty or raw.shape[0] < 2 or raw.shape[1] < 3:
        return {}, "AreaDemand.xlsx saknar profiler"

    columns = [str(c).strip() for c in raw.columns]
    metric_row = raw.iloc[0]
    data = raw.iloc[1:].copy()
    profiles: dict[str, dict[str, object]] = {}
    previous_source = ""

    for idx in range(2, len(columns)):
        metric = str(metric_row.iloc[idx]).strip()
        kind = _area_metric_kind(metric)
        if kind is None:
            continue

        source_name = _area_profile_source_name(columns[idx], previous_source)
        if source_name:
            previous_source = source_name
        label = source_name or f"AreaDemand kolumn {idx + 1}"
        label = f"{label} [{_area_metric_label(metric)}]"

        factors = _default_area_factors()
        factor_sources = {energy_key: "fallback_default" for energy_key in factors}
        coverage: list[str] = []
        for _, row in data.iterrows():
            tech = _area_tech_from_text(row.iloc[0])
            if tech is None:
                first_cell = str(row.iloc[0]).strip().lower()
                if first_cell.startswith("sources:"):
                    break
                continue
            if tech in coverage:
                continue
            km2_per_twh = _area_value_to_km2_per_twh(row.iloc[idx], metric)
            if km2_per_twh is None:
                continue
            factors[tech] = float(km2_per_twh)
            factor_sources[tech] = "profile"
            coverage.append(tech)

        if coverage:
            profiles[f"xlsx_{idx}"] = {
                "label": label,
                "source_name": source_name or f"AreaDemand kolumn {idx + 1}",
                "metric": metric,
                "factors": factors,
                "factor_sources": factor_sources,
                "coverage": coverage,
                "path": str(xlsx_path),
            }

    if not profiles:
        return {}, "AreaDemand.xlsx kunde inte tolkas till profiler"
    return profiles, f"loaded AreaDemand-profiler: {len(profiles)} från {xlsx_path}"


@st.cache_data(show_spinner=False)
def load_area_factor_profiles_sidecar(project_root: Path) -> tuple[dict[str, dict[str, object]], str]:
    if duckdb is None:
        return {}, "duckdb package saknas"
    db_path = _find_area_profile_duckdb(project_root)
    if db_path is None:
        return {}, "area profile duckdb saknas"

    try:
        con = duckdb.connect(str(db_path), read_only=True)
        if not _duckdb_has_object(con, "area_profiles") or not _duckdb_has_object(con, "area_factor_profiles"):
            con.close()
            return {}, f"area profile duckdb saknar tabeller ({db_path})"

        factor_cols = set(_duckdb_columns(con, "area_factor_profiles"))
        value_source_sql = "value_source" if "value_source" in factor_cols else "'profile_unknown' AS value_source"

        profiles_df = con.execute(
            """
            SELECT profile_id, label, source_name, metric, source_path
            FROM area_profiles
            ORDER BY sort_order, profile_id
            """
        ).df()
        factors_df = con.execute(
            f"""
            SELECT profile_id, energy_key, km2_per_twh, {value_source_sql}
            FROM area_factor_profiles
            ORDER BY profile_id, energy_key
            """
        ).df()
        con.close()
    except Exception as exc:
        return {}, f"kunde inte lasa area profile duckdb ({exc})"

    profiles: dict[str, dict[str, object]] = {}
    for _, row in profiles_df.iterrows():
        profile_id = str(row["profile_id"]).strip()
        if not profile_id:
            continue
        profiles[profile_id] = {
            "label": str(row["label"]).strip(),
            "source_name": str(row["source_name"]).strip(),
            "metric": str(row["metric"]).strip(),
            "factors": _default_area_factors(),
            "factor_sources": {},
            "coverage": [],
            "path": str(row["source_path"]).strip(),
        }
    for _, row in factors_df.iterrows():
        profile_id = str(row["profile_id"]).strip()
        energy_key = str(row["energy_key"]).strip()
        if profile_id not in profiles or not energy_key:
            continue
        profiles[profile_id]["factors"][energy_key] = float(row["km2_per_twh"])
        source_key = str(row["value_source"]).strip() or "profile_unknown"
        profiles[profile_id]["factor_sources"][energy_key] = source_key
        if source_key == "profile":
            profiles[profile_id]["coverage"].append(energy_key)

    if not profiles:
        return {}, f"area profile duckdb tom ({db_path})"
    return profiles, f"loaded area profile duckdb: {db_path}"


@st.cache_data(show_spinner=False)
def load_timesreport_energy_rows(project_root: Path) -> tuple[pd.DataFrame | None, str]:
    if duckdb is not None:
        db_path, db_status = _resolve_duckdb(project_root)
        if db_path is not None:
            try:
                con = duckdb.connect(str(db_path), read_only=True)
                raw, raw_status = _load_energy_rows_duckdb(con)
                con.close()
                if raw is not None:
                    return raw, f"{db_status}; {raw_status}"
            except Exception:
                pass
    raw, raw_status = _load_energy_rows_csv(project_root)
    return raw, raw_status


@st.cache_data(show_spinner=False)
def load_area_demand_scenario_bundle_cached(
    project_root: Path,
    times_tech_scope: tuple[str, ...],
) -> tuple[dict[str, object] | None, str]:
    xlsx_path = _find_area_demand_xlsx(project_root)
    if xlsx_path is None:
        return None, "AreaDemand.xlsx saknas"
    try:
        bundle = build_area_demand_scenario_bundle(xlsx_path, list(times_tech_scope))
    except Exception as exc:
        return None, f"kunde inte bygga AreaDemand-scenarier ({exc})"
    return bundle, f"loaded AreaDemand-scenarier: {xlsx_path}"


def load_timesreport_preview(
    project_root: Path,
) -> tuple[pd.DataFrame | None, dict[str, list[str]] | None, str]:
    if duckdb is not None:
        db_path, db_status = _resolve_duckdb(project_root)
        if db_path is not None:
            try:
                con = duckdb.connect(str(db_path), read_only=True)
                preview, summary, preview_status = _load_preview_frame_duckdb(con)
                con.close()
                if preview is not None:
                    return preview, summary, f"{db_status}; {preview_status}"
            except Exception:
                pass

    csv_path = _find_timesreport_csv(project_root)
    if csv_path is None:
        return None, None, "no file"
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return None, None, f"could not read file ({exc})"
    if df.empty:
        return df, {}, "empty file"

    cols_lower = {str(c).lower(): c for c in df.columns}
    summary: dict[str, list[str]] = {}
    for key in ["scen", "techgroup", "comgroup", "topic", "attr", "units", "year"]:
        col = cols_lower.get(key)
        if col is None:
            continue
        vals = (
            df[col].dropna().astype(str).str.strip().replace("", np.nan).dropna().drop_duplicates().tolist()
        )
        summary[key] = vals[:80]
    return df.head(25), summary, f"loaded: {csv_path}"


@st.cache_data(show_spinner=False)
def load_timesreport_mapping_audit(project_root: Path) -> tuple[dict[str, pd.DataFrame] | None, str]:
    if duckdb is not None:
        db_path, db_status = _resolve_duckdb(project_root)
        if db_path is not None:
            try:
                con = duckdb.connect(str(db_path), read_only=True)
                raw, raw_status = _load_energy_rows_duckdb(con)
                con.close()
                if raw is not None:
                    return _build_times_mapping_audit(raw), f"{db_status}; {raw_status}"
            except Exception as exc:
                return None, f"{db_status}; mapping audit misslyckades ({exc})"

    raw, raw_status = _load_energy_rows_csv(project_root)
    if raw is None:
        return None, raw_status
    return _build_times_mapping_audit(raw), raw_status


@st.cache_data(show_spinner=False)
def load_scenario_metadata_duckdb(project_root: Path) -> tuple[dict[str, str], dict[str, str], str]:
    if duckdb is None:
        return {}, {}, "duckdb package saknas"
    db_path, db_status = _resolve_duckdb(project_root)
    if db_path is None:
        return {}, {}, db_status

    descriptions: dict[str, str] = {}
    source_details: dict[str, str] = {}
    loaded_parts: list[str] = []
    try:
        con = duckdb.connect(str(db_path), read_only=True)

        if _duckdb_has_object(con, "scen_desc"):
            rows = con.execute(
                """
                SELECT scen, description
                FROM scen_desc
                WHERE scen IS NOT NULL
                """
            ).df()
            descriptions = {
                str(r["scen"]): str(r["description"]).strip()
                for _, r in rows.iterrows()
                if pd.notna(r["scen"]) and pd.notna(r["description"]) and str(r["description"]).strip()
            }
            if descriptions:
                loaded_parts.append("loaded scen_desc")

        if _duckdb_has_object(con, "scenario_model") and _duckdb_has_object(con, "source_files"):
            rows = con.execute(
                """
                SELECT
                    sm.scen,
                    sf.filename,
                    sf.load_timestamp
                FROM scenario_model AS sm
                LEFT JOIN source_files AS sf
                  ON sm.file_id = sf.file_id
                WHERE sm.scen IS NOT NULL
                """
            ).df()
            for _, r in rows.iterrows():
                scen = str(r["scen"]).strip()
                if not scen:
                    continue
                parts: list[str] = []
                if pd.notna(r["filename"]) and str(r["filename"]).strip():
                    parts.append(str(r["filename"]).strip())
                ts = r["load_timestamp"]
                if pd.notna(ts):
                    ts_str = ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts)
                    parts.append(ts_str)
                if parts:
                    source_details[scen] = " | ".join(parts)
            if source_details:
                loaded_parts.append("loaded source_files")
    except Exception as exc:
        return {}, {}, f"{db_status}; scenario metadata misslyckades ({exc})"
    finally:
        try:
            con.close()
        except Exception:
            pass

    if not loaded_parts:
        return descriptions, source_details, f"{db_status}; scenario metadata saknas"
    return descriptions, source_details, f"{db_status}; {'; '.join(loaded_parts)}"


@st.cache_data(show_spinner=False)
def _coerce_candidate_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        return numeric.fillna(0).gt(0)
    low = series.astype(str).str.strip().str.lower()
    return low.isin({"1", "true", "yes", "ja", "y", "allowed", "accept", "accepted"})


def _find_build_candidate_column(columns: list[str]) -> str | None:
    exact_names = [
        "build_candidate",
        "build_allowed",
        "allow_build",
        "accepted",
        "is_accepted",
        "is_buildable",
        "eligible",
    ]
    low_lookup = {str(c).lower(): str(c) for c in columns}
    for name in exact_names:
        if name in low_lookup:
            return low_lookup[name]
    for column in columns:
        low = str(column).lower()
        if "accept" in low and ("flag" in low or "allow" in low or "build" in low):
            return str(column)
    return None


def _find_acceptance_value_column(columns: list[str], excluded: set[str]) -> str | None:
    preferred = ["acceptance_score", "acceptance", "social_acceptance", "status"]
    low_lookup = {str(c).lower(): str(c) for c in columns}
    for name in preferred:
        if name in low_lookup and low_lookup[name] not in excluded:
            return low_lookup[name]
    for column in columns:
        low = str(column).lower()
        if "accept" in low and str(column) not in excluded:
            return str(column)
    return None


@st.cache_data(show_spinner=False)
def load_hex_context(
    points_path_str: str,
    scores_path_str: str | None = None,
    acceptance_path_str: str | None = None,
) -> pd.DataFrame:
    points_path = Path(points_path_str)
    pts = _read_table_file(points_path)
    if "hex_id" not in pts.columns:
        raise ValueError(f"Hexfil saknar kolumnen hex_id: {points_path}")

    df = pts.copy()

    if scores_path_str:
        scores_path = Path(scores_path_str)
        scores = _read_table_file(scores_path)
        if "hex_id" not in scores.columns:
            raise ValueError(f"Scorefil saknar kolumnen hex_id: {scores_path}")
        score_cols = [c for c in ["hex_id", "class_km", "F1", "F2", "F3", "F4", "F5"] if c in scores.columns]
        if score_cols and "hex_id" in score_cols:
            df = df.merge(scores[score_cols], on="hex_id", how="left")

    if acceptance_path_str:
        acceptance_path = Path(acceptance_path_str)
        acceptance = _read_table_file(acceptance_path)
        if "hex_id" not in acceptance.columns:
            raise ValueError(f"Acceptansfil saknar kolumnen hex_id: {acceptance_path}")
        rename_map: dict[str, str] = {}
        for column in acceptance.columns:
            if column == "hex_id":
                continue
            if column in df.columns:
                rename_map[str(column)] = f"accept_{column}"
        if rename_map:
            acceptance = acceptance.rename(columns=rename_map)
        df = df.merge(acceptance, on="hex_id", how="left")

        candidate_col = _find_build_candidate_column(list(acceptance.columns))
        if candidate_col is not None:
            df["build_candidate"] = _coerce_candidate_series(df[candidate_col]).fillna(False)
        else:
            df["build_candidate"] = True

        acceptance_value_col = _find_acceptance_value_column(list(acceptance.columns), {candidate_col} if candidate_col else set())
        if acceptance_value_col is not None:
            df["acceptance_value"] = df[acceptance_value_col].astype(str).replace("nan", "")
        else:
            df["acceptance_value"] = ""
    else:
        df["build_candidate"] = True
        df["acceptance_value"] = ""

    if "class_km" not in df.columns:
        df["class_km"] = 0
    df["class_km"] = pd.to_numeric(df["class_km"], errors="coerce").fillna(0).astype(int)

    for col in ["F1", "F2", "F3", "F4", "F5"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["build_candidate"] = df["build_candidate"].fillna(True).astype(bool)
    df["acceptance_value"] = df["acceptance_value"].fillna("").astype(str)
    return df


@st.cache_data(show_spinner=False)
def load_area_factors(project_root: Path) -> tuple[dict[str, float], str]:
    profiles, status = load_area_factor_profiles_sidecar(project_root)
    if profiles:
        profile_id = _recommended_area_profile_id(profiles)
        if profile_id is not None:
            profile = profiles[profile_id]
            return dict(profile["factors"]), f"{status}; rekommenderad profil: {profile['label']}"
    profiles, status = load_area_factor_profiles_xlsx(project_root)
    if profiles:
        profile_id = _recommended_area_profile_id(profiles)
        if profile_id is not None:
            profile = profiles[profile_id]
            return dict(profile["factors"]), f"{status}; rekommenderad profil: {profile['label']}"
    return {}, f"inga AreaDemand-profiler hittades ({status})"


def _hex_polygon(hex_id: str):
    if h3 is None:
        return None
    try:
        # h3-py v4 returns (lat, lng)
        boundary = h3.cell_to_boundary(hex_id)
        return [[lng, lat] for lat, lng in boundary]
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def build_map_frame(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    geom_col = "__gpkg_geom__" if "__gpkg_geom__" in work.columns else None
    if "hex_id" not in work.columns:
        raise ValueError("Hexramen saknar kolumnen hex_id.")
    if "class_km" not in work.columns:
        work["class_km"] = 0
    if "build_candidate" not in work.columns:
        work["build_candidate"] = True
    if "acceptance_value" not in work.columns:
        work["acceptance_value"] = ""
    if h3 is None:
        work["lat"] = np.nan
        work["lon"] = np.nan
        work["polygon"] = None
        work["hex_area_km2"] = np.nan
        return work

    lats = []
    lons = []
    polys = []
    areas = []
    geom_values = work[geom_col].tolist() if geom_col is not None else [None] * len(work)
    for h, geom_blob in zip(work["hex_id"].astype(str), geom_values):
        polygon = None
        polygon_area_km2 = None
        if geom_col is not None:
            polygon, polygon_area_km2 = _decode_gpkg_polygon(geom_blob)
        try:
            lat, lon = h3.cell_to_latlng(h)
            lats.append(lat)
            lons.append(lon)
            polys.append(polygon if polygon is not None else _hex_polygon(h))
            areas.append(
                float(polygon_area_km2)
                if polygon_area_km2 is not None and polygon_area_km2 > 0
                else float(h3.cell_area(h, unit="km^2"))
            )
        except Exception:
            lats.append(np.nan)
            lons.append(np.nan)
            polys.append(polygon)
            areas.append(float(polygon_area_km2) if polygon_area_km2 is not None else np.nan)
    work["lat"] = lats
    work["lon"] = lons
    work["polygon"] = polys
    work["hex_area_km2"] = areas
    if geom_col is not None:
        work = work.drop(columns=[geom_col])
    return work


@st.cache_data(show_spinner=False)
def build_suitability_frame(df: pd.DataFrame) -> pd.DataFrame:
    work = df[["hex_id", "F1", "F2", "F3", "F4", "F5"]].copy()
    for tech in SUITABILITY_TECHS:
        work[f"s_{tech}"] = suitability(work, tech)
    keep_cols = ["hex_id"] + [f"s_{tech}" for tech in SUITABILITY_TECHS]
    return work[keep_cols]


def _norm(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    lo = s.min()
    hi = s.max()
    if pd.isna(lo) or pd.isna(hi) or hi <= lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def suitability(df: pd.DataFrame, tech: str) -> pd.Series:
    f1 = _norm(df["F1"])
    f2 = _norm(df["F2"])
    f3 = _norm(df["F3"])
    f4 = _norm(df["F4"])
    f5 = _norm(df["F5"])
    if tech == "wind":
        return 0.45 * f1 + 0.35 * f3 + 0.20 * (1.0 - f2)
    if tech == "solar":
        return 0.55 * f4 + 0.25 * f1 + 0.20 * (1.0 - f2)
    if tech == "nuclear":
        return 0.60 * f5 + 0.25 * f1 + 0.15 * (1.0 - f2)
    if tech == "hydro":
        return 0.35 * f3 + 0.30 * f1 + 0.35 * (1.0 - f2)
    if tech in {"bio", "coal", "gas", "oil"}:
        return 0.35 * f1 + 0.35 * f5 + 0.30 * (1.0 - f2)
    if tech in {"renewables", "electricity", "demand"}:
        return 0.40 * f1 + 0.40 * f3 + 0.20 * (1.0 - f2)
    return 0.34 * f1 + 0.33 * f3 + 0.33 * (1.0 - f2)


st.set_page_config(page_title="GC4 + Energy Prototype", layout="wide")
st.title("GC4 + Energy Prototype (Bornholm)")
st.caption(_tr("Hexagoner + markanspråk kopplat till TIMES-scenarier.", "Hexagons + land demand linked to TIMES scenarios."))

app_base = Path(__file__).resolve().parent
project_root = app_base.parents[1]
if h3 is None:
    st.error(_tr("Python-paketet `h3` saknas. Installera beroenden och starta om appen.", "The Python package `h3` is missing. Install dependencies and restart the app."))
    st.stop()

hex_points_path, hex_scores_path, acceptance_layer_path, hex_source_status = _resolve_hex_sources(project_root)
if hex_points_path is None:
    st.error(_tr("Saknar hexagondata. Ange `HEX_POINTS_PATH` eller lägg en points-fil i standardplatsen.", "Hexagon data is missing. Set `HEX_POINTS_PATH` or place a points file in the default location."))
    st.caption(f"{_tr('Hexstatus', 'Hex status')}: `{hex_source_status}`")
    st.stop()

try:
    gc4 = load_hex_context(
        str(hex_points_path),
        str(hex_scores_path) if hex_scores_path is not None else None,
        str(acceptance_layer_path) if acceptance_layer_path is not None else None,
    )
except Exception as exc:
    st.error(_tr(f"Kunde inte läsa hexagondata ({exc})", f"Could not read hexagon data ({exc})"))
    st.caption(f"{_tr('Hexstatus', 'Hex status')}: `{hex_source_status}`")
    st.stop()
map_df = build_map_frame(gc4).dropna(subset=["lat", "lon", "polygon"]).copy()
suitability_scores = build_suitability_frame(gc4)
analysis_df = map_df.merge(suitability_scores, on="hex_id", how="left")
times_totals_db, times_mix_db, times_status_db = load_timesreport_scenarios_duckdb(project_root)
times_totals_csv, times_mix_csv, times_status_csv = load_timesreport_scenarios(project_root)
times_totals = times_totals_db if times_totals_db is not None else times_totals_csv
times_mix = times_mix_db if times_mix_db is not None else times_mix_csv
times_status = times_status_db if times_totals_db is not None else times_status_csv
if times_totals is None or times_mix is None:
    st.error(_tr("Saknar TIMES-scenarier. Appen använder inte längre hårdkodade mock-scenarier.", "TIMES scenarios are missing. The app no longer uses hardcoded mock scenarios."))
    st.caption(
        _tr(
            "Kontrollera `data/processed/speedlocal_times.duckdb`, `DUCKDB_PATH`, `DUCKDB_SHARE_URL` "
            f"eller TIMESreport-csv. (`{times_status}`)",
            "Check `data/processed/speedlocal_times.duckdb`, `DUCKDB_PATH`, `DUCKDB_SHARE_URL` "
            f"or the TIMES report csv. (`{times_status}`)",
        )
    )
    st.stop()

times_raw_df, times_raw_status = load_timesreport_energy_rows(project_root)
if times_raw_df is None or times_raw_df.empty:
    st.error(_tr("Kunde inte läsa råa TIMES-rader för markintensitetsmodellen.", "Could not read raw TIMES rows for the land-intensity model."))
    st.caption(f"{_tr('TIMES-radstatus', 'TIMES row status')}: `{times_raw_status}`")
    st.stop()
times_raw_df = times_raw_df.copy()
times_raw_df["times_tech"] = [
    _times_tech_code(comgroup=row.get("comgroup", ""), techgroup=row.get("techgroup", ""))
    for row in times_raw_df.to_dict("records")
]
times_tech_scope = tuple(sorted(code for code in times_raw_df["times_tech"].astype(str).unique().tolist() if code != "UNKNOWN"))
area_demand_bundle, area_demand_status = load_area_demand_scenario_bundle_cached(project_root, times_tech_scope)
if area_demand_bundle is None:
    st.error(_tr("Kunde inte bygga markintensitetsscenarier från AreaDemand.xlsx.", "Could not build land-intensity scenarios from AreaDemand.xlsx."))
    st.caption(f"AreaDemand-status: `{area_demand_status}`")
    st.stop()

scenario_totals = times_totals
base_mix_map = times_mix
times_preview_df, times_preview_summary, times_preview_status = load_timesreport_preview(project_root)
times_mapping_audit, times_mapping_status = load_timesreport_mapping_audit(project_root)
scenario_desc_map, scenario_source_map, scenario_meta_status = load_scenario_metadata_duckdb(project_root)
wind_placement_options = [scenario_id for scenario_id in WIND_PLACEMENT_ORDER if _wind_allowed_column(scenario_id) in gc4.columns]

if st.sidebar.button(_language_switch_label(), use_container_width=True):
    _toggle_language()
    st.rerun()
st.sidebar.caption(f"{_tr('Språk', 'Language')}: {_language_status_label()}")

st.sidebar.header(_tr("Scenario", "Scenario"))
scenario_options = list(scenario_totals.keys())
scenario = st.sidebar.selectbox(
    _tr("Scenario", "Scenario"),
    scenario_options,
    index=0,
    format_func=lambda scen: _scenario_display_label(str(scen), scenario_desc_map),
)
scenario_label = _scenario_display_label(str(scenario), scenario_desc_map)
scenario_years = sorted([int(y) for y in scenario_totals.get(scenario, {}).keys()])
year_options = scenario_years if scenario_years else [2050]
default_year = 2050 if 2050 in year_options else year_options[-1]
year = st.sidebar.segmented_control(
    _tr("Scenarioår (TIMES)", "Scenario year (TIMES)"),
    options=year_options,
    default=default_year,
    selection_mode="single",
    help=_tr(
        "Valet styr vilket år i TIMES-scenariot som används för total TWh, basmix och markanspråk.",
        "This selects which year in the TIMES scenario is used for total TWh, base mix, and land demand.",
    ),
)
if year is None:
    year = default_year
st.sidebar.caption(
    _tr(
        "Detta är inte kalenderåret i kartan, utan vilket scenarioår från TIMES-data som driver analysen.",
        "This is not the calendar year on the map, but the scenario year from TIMES data that drives the analysis.",
    )
)
base_total = float(scenario_totals.get(scenario, {}).get(year, 0.0))
base_mix = _resolve_base_mix_for_year(base_mix_map, str(scenario), int(year))

st.sidebar.subheader(_tr("Markintensitet", "Land intensity"))
area_scenario_id = st.sidebar.select_slider(
    _tr("Markanspråksscenario", "Land-demand scenario"),
    options=list(AREA_SCENARIO_ORDER),
    value="mid",
    format_func=lambda scenario_id: _area_scenario_label(str(scenario_id)),
)
area_scenario_label = _area_scenario_label(area_scenario_id)
st.sidebar.caption(
    _tr(
        "Tre scenarier byggs direkt från litteraturspann i AreaDemand.xlsx. "
        "Litteraturkällor visas bara i faktarutan nedan.",
        "Three scenarios are built directly from literature ranges in AreaDemand.xlsx. "
        "Literature sources are only shown in the fact box below.",
    )
)

if wind_placement_options:
    st.sidebar.subheader(_tr("Vindplacering", "Wind placement"))
    wind_placement_id = st.sidebar.segmented_control(
        _tr("Acceptansnivå för ny vindkraft", "Acceptance level for new wind power"),
        options=wind_placement_options,
        default="medium_acceptance" if "medium_acceptance" in wind_placement_options else wind_placement_options[0],
        selection_mode="single",
        format_func=_wind_placement_label,
        help=_tr(
            "Styr bara placering av ny vindkraft. Mellan är standard i v4.",
            "Controls placement of new wind power only. Medium is the default in v4.",
        ),
    )
    if wind_placement_id is None:
        wind_placement_id = "medium_acceptance" if "medium_acceptance" in wind_placement_options else wind_placement_options[0]
else:
    wind_placement_id = None
    st.sidebar.info(
        _tr(
            "Inga vindspecifika acceptansscenarier hittades i den valda hexkällan.",
            "No wind-specific acceptance scenarios were found in the selected hex source.",
        )
    )

st.sidebar.subheader(_tr("Elmix-sliders (%)", "Electricity mix sliders (%)"))
tech_keys = list(base_mix.keys())
if not tech_keys:
    tech_keys = ["other"]
    base_mix = {"other": 100.0}
base_mix = _normalize_mix_100({k: float(base_mix.get(k, 0.0)) for k in tech_keys})
_sync_mix_state(tech_keys, base_mix)
slider_state_keys = [f"mix_{tech}" for tech in tech_keys]
if st.sidebar.button(_tr("Återställ till TIMES-mix", "Reset to TIMES mix"), use_container_width=True):
    _set_mix_state(tech_keys, base_mix)
st.sidebar.caption(
    _tr(
        "Sliders är länkade och hålls ihop till totalt 100%. "
        "Din manuella mix ligger kvar när du byter scenario eller scenarioår.",
        "Sliders are linked and constrained to a total of 100%. "
        "Your manual mix stays in place when you switch scenario or scenario year.",
    )
)
st.sidebar.info(
    _tr(
        "Elmix-kategorierna är förenklade planeringskategorier byggda från TIMES-reporten. "
        "Vind, Sol, Olja och El ligger nära TIMES, Bioenergi är hopslagen och Övrigt är en samlingskategori. "
        "Se 'TIMES mapping audit' nedan för detaljer.",
        "The electricity-mix categories are simplified planning categories built from the TIMES report. "
        "Wind, Solar, Oil, and Electricity stay close to TIMES, Bioenergy is aggregated, and Other is a collection bucket. "
        "See 'TIMES mapping audit' below for details.",
    )
)
for tech in tech_keys:
    key = f"mix_{tech}"
    slider_kwargs = {
        "min_value": 0.0,
        "max_value": 100.0,
        "step": 0.1,
        "key": key,
        "on_change": _rebalance_slider,
        "args": (key, slider_state_keys),
    }
    if key not in st.session_state:
        slider_kwargs["value"] = float(base_mix.get(tech, 0.0))
    st.sidebar.slider(_human_tech_name(tech), **slider_kwargs)

mix_raw = {tech: float(st.session_state.get(f"mix_{tech}", 0.0)) for tech in tech_keys}
mix_pct = _normalize_mix_100(mix_raw)
st.sidebar.caption(f"{_tr('Summa elmix', 'Total electricity mix')}: {sum(mix_raw.values()):.1f}%")
twh = {tech: base_total * mix_pct[tech] / 100.0 for tech in tech_keys}
selected_times_raw_mix_df = times_raw_df[
    (times_raw_df["scen"].astype(str) == str(scenario))
    & (pd.to_numeric(times_raw_df["year"], errors="coerce") == int(year))
].copy()
selected_times_raw_mix_df = (
    selected_times_raw_mix_df.groupby(["times_tech", "energy_key"], as_index=False)["value_twh"]
    .sum()
    .sort_values(["energy_key", "times_tech"])
    .reset_index(drop=True)
)
if selected_times_raw_mix_df.empty:
    st.error(_tr("Inga råa TIMES-tekniker hittades för valt scenarioår.", "No raw TIMES technologies were found for the selected scenario year."))
    st.caption(f"{_tr('TIMES-radstatus', 'TIMES row status')}: `{times_raw_status}`")
    st.stop()

selected_times_raw_mix_df["bucket_base_twh"] = selected_times_raw_mix_df.groupby("energy_key")["value_twh"].transform("sum")
selected_times_raw_mix_df["within_bucket_share"] = np.where(
    selected_times_raw_mix_df["bucket_base_twh"] > 0,
    selected_times_raw_mix_df["value_twh"] / selected_times_raw_mix_df["bucket_base_twh"],
    0.0,
)
selected_times_raw_mix_df["selected_twh"] = (
    selected_times_raw_mix_df["energy_key"].map(lambda tech: float(twh.get(str(tech), 0.0)))
    * selected_times_raw_mix_df["within_bucket_share"]
)
selected_times_raw_mix_df["times_tech_display"] = selected_times_raw_mix_df.apply(
    lambda row: _times_tech_display(str(row["times_tech"]), str(row["energy_key"])),
    axis=1,
)

wind_allowed_col = _wind_allowed_column(wind_placement_id) if wind_placement_id else ""
wind_score_col = _wind_score_column(wind_placement_id) if wind_placement_id else ""
wind_class_col = _wind_class_column(wind_placement_id) if wind_placement_id else ""
wind_reason_col = _wind_reason_column(wind_placement_id) if wind_placement_id else ""
wind_acceptance_available = bool(wind_placement_id and wind_allowed_col in analysis_df.columns)
wind_score_available = bool(wind_acceptance_available and wind_score_col in analysis_df.columns)
wind_class_available = bool(wind_acceptance_available and wind_class_col in analysis_df.columns)
wind_reason_available = bool(wind_acceptance_available and wind_reason_col in analysis_df.columns)
wind_allowed_hex_count = 0
wind_allowed_share_pct = 0.0

if wind_acceptance_available:
    for target_df in (map_df, analysis_df):
        target_df["wind_allowed_selected"] = _coerce_candidate_series(target_df[wind_allowed_col]).fillna(False)
        target_df["wind_acceptance_score_selected"] = (
            pd.to_numeric(target_df[wind_score_col], errors="coerce").fillna(0.0) if wind_score_available else 0.0
        )
        target_df["wind_acceptance_class_selected"] = (
            target_df[wind_class_col].fillna("").astype(str) if wind_class_available else ""
        )
        target_df["wind_acceptance_reason_selected"] = (
            target_df[wind_reason_col].fillna("").astype(str) if wind_reason_available else ""
        )
        target_df["acceptance_value"] = np.where(
            target_df["wind_allowed_selected"],
            target_df["wind_acceptance_class_selected"],
            target_df["wind_acceptance_reason_selected"],
        )
    wind_allowed_hex_count = int(analysis_df["wind_allowed_selected"].sum())
    wind_allowed_share_pct = 100.0 * wind_allowed_hex_count / max(len(analysis_df), 1)

area_scenario_table = pd.DataFrame(area_demand_bundle.get("scenario_table", pd.DataFrame())).copy()
if not area_scenario_table.empty:
    selected_times_raw_mix_df = selected_times_raw_mix_df.merge(
        area_scenario_table[
            ["TIMES-teknik", "Workbook-rad", "Lagt km2/TWh", "Mellan km2/TWh", "Hogt km2/TWh", "Status", "Motivering"]
        ],
        left_on="times_tech",
        right_on="TIMES-teknik",
        how="left",
    )
selected_area_factors = dict(area_demand_bundle.get("factors_by_scenario", {}).get(area_scenario_id, {}))
selected_times_raw_mix_df["selected_km2_per_twh"] = selected_times_raw_mix_df["times_tech"].map(selected_area_factors)
selected_times_raw_mix_df["area_need_km2"] = (
    selected_times_raw_mix_df["selected_twh"] * selected_times_raw_mix_df["selected_km2_per_twh"]
)

active_times_tech_df = selected_times_raw_mix_df[selected_times_raw_mix_df["selected_twh"] > 1e-9].copy()
strict_missing_active_df = active_times_tech_df[active_times_tech_df["selected_km2_per_twh"].isna()].copy()
strict_supported_active_df = active_times_tech_df[active_times_tech_df["selected_km2_per_twh"].notna()].copy()
strict_ready = strict_missing_active_df.empty
total_area_need = float(strict_supported_active_df["area_need_km2"].sum()) if strict_ready else float("nan")

area_factor_detail_df = (
    active_times_tech_df[
        [
            "times_tech_display",
            "times_tech",
            "energy_key",
            "selected_twh",
            "selected_km2_per_twh",
            "area_need_km2",
            "Status",
            "Motivering",
        ]
    ]
    .rename(
        columns={
            "times_tech_display": "TIMES-teknik",
            "energy_key": "Appkategori",
            "selected_twh": "TWh",
            "selected_km2_per_twh": "km2_per_twh",
            "area_need_km2": "km2",
        }
    )
    .reset_index(drop=True)
)

area_sensitivity_rows: list[dict[str, object]] = []
for scenario_option in AREA_SCENARIO_ORDER:
    scenario_factor_map = dict(area_demand_bundle.get("factors_by_scenario", {}).get(str(scenario_option), {}))
    missing_df = active_times_tech_df[~active_times_tech_df["times_tech"].isin(list(scenario_factor_map.keys()))].copy()
    total_km2 = (
        float(sum(float(row["selected_twh"]) * float(scenario_factor_map[str(row["times_tech"])]) for _, row in active_times_tech_df.iterrows()))
        if missing_df.empty
        else np.nan
    )
    area_sensitivity_rows.append(
        {
            "Scenario": _area_scenario_label(str(scenario_option)),
            "Vald": str(scenario_option) == str(area_scenario_id),
            "Strikt klar": missing_df.empty,
            "Total km2": total_km2,
            "Saknade TIMES-tekniker": ", ".join(missing_df["times_tech"].astype(str).tolist()),
        }
    )
area_sensitivity_df = pd.DataFrame(area_sensitivity_rows)
if not area_sensitivity_df.empty and strict_ready and total_area_need > 0:
    area_sensitivity_df["Delta vs vald %"] = np.where(
        area_sensitivity_df["Total km2"].notna(),
        100.0 * (area_sensitivity_df["Total km2"] / total_area_need - 1.0),
        np.nan,
    )
else:
    area_sensitivity_df["Delta vs vald %"] = np.nan

active_times_tech_codes = active_times_tech_df["times_tech"].astype(str).tolist()
area_mapping_active_df = pd.DataFrame(area_demand_bundle.get("mapping_table", pd.DataFrame())).copy()
if not area_mapping_active_df.empty:
    area_mapping_active_df = area_mapping_active_df[
        area_mapping_active_df["TIMES-teknik"].astype(str).isin(active_times_tech_codes)
    ].reset_index(drop=True)
area_scenario_active_df = pd.DataFrame(area_demand_bundle.get("scenario_table", pd.DataFrame())).copy()
if not area_scenario_active_df.empty:
    area_scenario_active_df = area_scenario_active_df[
        area_scenario_active_df["TIMES-teknik"].astype(str).isin(active_times_tech_codes)
    ].copy()
    selected_col_name = {
        "low": "Lagt km2/TWh",
        "mid": "Mellan km2/TWh",
        "high": "Hogt km2/TWh",
    }.get(str(area_scenario_id), "Mellan km2/TWh")
    area_scenario_active_df["Vald scenario km2/TWh"] = area_scenario_active_df[selected_col_name]
    area_scenario_active_df = area_scenario_active_df.reset_index(drop=True)
active_area_observation_df = pd.DataFrame(area_demand_bundle.get("observation_table", pd.DataFrame())).copy()
if not active_area_observation_df.empty:
    active_area_observation_df = active_area_observation_df[
        active_area_observation_df["TIMES-teknik"].astype(str).isin(active_times_tech_codes)
    ].reset_index(drop=True)

selected_supported_times_techs = strict_supported_active_df["times_tech"].astype(str).tolist()
selected_unsupported_times_techs = strict_missing_active_df["times_tech"].astype(str).tolist()

times_coverage_df = (
    times_mapping_audit.get("coverage", pd.DataFrame()) if isinstance(times_mapping_audit, dict) else pd.DataFrame()
)
times_mix_audit_df = (
    times_mapping_audit.get("mix", pd.DataFrame()) if isinstance(times_mapping_audit, dict) else pd.DataFrame()
)
times_mapping_df = (
    times_mapping_audit.get("mapping", pd.DataFrame()) if isinstance(times_mapping_audit, dict) else pd.DataFrame()
)
selected_times_coverage = pd.Series(dtype="object")
selected_times_mix_df = pd.DataFrame()
selected_times_other_df = pd.DataFrame()
selected_times_unmapped_df = pd.DataFrame()
if not times_coverage_df.empty:
    selected_cov = times_coverage_df[
        (times_coverage_df["scen"].astype(str) == str(scenario))
        & (pd.to_numeric(times_coverage_df["year"], errors="coerce") == int(year))
    ]
    if not selected_cov.empty:
        selected_times_coverage = selected_cov.iloc[0]
if not times_mix_audit_df.empty:
    selected_times_mix_df = times_mix_audit_df[
        (times_mix_audit_df["scen"].astype(str) == str(scenario))
        & (pd.to_numeric(times_mix_audit_df["year"], errors="coerce") == int(year))
    ].copy()
if not times_mapping_df.empty:
    selected_mapping = times_mapping_df[
        (times_mapping_df["scen"].astype(str) == str(scenario))
        & (pd.to_numeric(times_mapping_df["year"], errors="coerce") == int(year))
    ].copy()
    if not selected_mapping.empty:
        selected_times_other_df = selected_mapping[selected_mapping["energy_key"] == "other"].copy()
        selected_times_unmapped_df = selected_mapping[selected_mapping["mapping_source"] == "unmapped"].copy()

build = analysis_df[analysis_df["build_candidate"] == True].copy()
if build.empty:
    build = analysis_df.copy()
if build.empty:
    st.error(_tr("Inga hexagoner hittades i kartlagret.", "No hexagons were found in the map layer."))
    st.stop()

hex_area = float(build["hex_area_km2"].median())
hex_need_total = int(math.ceil(total_area_need / max(1e-9, hex_area))) if strict_ready and pd.notna(total_area_need) else 0

selection_mode = st.sidebar.radio(
    _tr("Urvalsmetod för hexagoner", "Hexagon selection mode"),
    options=["auto", "manual"],
    index=0,
    format_func=_selection_mode_label,
)

alloc_parts = []
if strict_ready:
    for _, row in strict_supported_active_df.iterrows():
        tech_family = str(row["energy_key"])
        suitability_col = f"s_{tech_family}"
        candidate_frame = build.copy()
        ranking_col = suitability_col
        if tech_family == "wind" and wind_acceptance_available:
            candidate_frame = candidate_frame[candidate_frame["wind_allowed_selected"] == True].copy()
            if wind_score_available:
                ranking_col = "wind_acceptance_score_selected"
        if ranking_col not in candidate_frame.columns:
            continue
        n = int(math.ceil(float(row["area_need_km2"]) / max(1e-9, hex_area)))
        if n <= 0:
            continue
        top = candidate_frame.sort_values(ranking_col, ascending=False).head(min(n, len(candidate_frame))).copy()
        top["selected_for"] = _times_tech_display(str(row["times_tech"]), tech_family)
        alloc_parts.append(top[["hex_id", "selected_for"]])

if alloc_parts:
    alloc_auto = pd.concat(alloc_parts, ignore_index=True)
    alloc_auto["selected"] = 1
    alloc_auto = alloc_auto.groupby("hex_id", as_index=False).agg(
        selected=("selected", "max"),
        selected_for=("selected_for", "first"),
    )
else:
    alloc_auto = pd.DataFrame({"hex_id": [], "selected": [], "selected_for": []})

alloc = alloc_auto.copy()
manual_selected_count = 0
if selection_mode == "manual" and strict_ready:
    manual_df = build.copy()
    total_twh = max(1e-9, float(strict_supported_active_df["selected_twh"].sum()))
    weighted = pd.Series(np.zeros(len(manual_df)), index=manual_df.index)
    for _, row in strict_supported_active_df.iterrows():
        tech_family = str(row["energy_key"])
        if tech_family == "wind" and wind_acceptance_available:
            wind_component = (
                manual_df["wind_acceptance_score_selected"].fillna(0.0) / 100.0
                if wind_score_available
                else manual_df.get("s_wind", pd.Series(np.zeros(len(manual_df)), index=manual_df.index))
            )
            wind_component = wind_component.where(manual_df["wind_allowed_selected"], 0.0)
            weighted += wind_component * (float(row["selected_twh"]) / total_twh)
            continue
        s_col = f"s_{tech_family}"
        if s_col not in manual_df.columns:
            continue
        weighted += manual_df[s_col] * (float(row["selected_twh"]) / total_twh)
    manual_df["s_total"] = weighted
    manual_df = manual_df.sort_values("s_total", ascending=False)
    manual_df["use"] = False
    manual_df.iloc[: min(hex_need_total, len(manual_df)), manual_df.columns.get_loc("use")] = True

    st.subheader(_tr("Manuellt urval av utbyggnadshexagoner", "Manual selection of development hexagons"))
    st.caption(
        _tr(
            "Bocka i hexagoner som ska ingå i urvalet. Förvalet markerar högst rankade.",
            "Tick the hexagons to include in the selection. The preselection marks the highest-ranked ones.",
        )
    )
    manual_cols = ["use", "hex_id", "s_total", "hex_area_km2"]
    if "class_km" in manual_df.columns:
        manual_cols.insert(2, "class_km")
    if "acceptance_value" in manual_df.columns and manual_df["acceptance_value"].astype(str).str.strip().any():
        manual_cols.append("acceptance_value")
    manual_column_config = {
        "use": st.column_config.CheckboxColumn(_tr("Vald", "Selected")),
        "hex_id": st.column_config.TextColumn("hex_id"),
        "class_km": st.column_config.NumberColumn("class_km"),
        "s_total": st.column_config.NumberColumn("Suitability"),
        "hex_area_km2": st.column_config.NumberColumn("Hex km2"),
        "acceptance_value": st.column_config.TextColumn(_tr("Acceptans", "Acceptance")),
    }
    editor = st.data_editor(
        manual_df[manual_cols].round(4),
        use_container_width=True,
        height=260,
        hide_index=True,
        column_config=manual_column_config,
    )
    chosen_hex = editor.loc[editor["use"] == True, "hex_id"].astype(str).tolist()
    manual_selected_count = len(chosen_hex)
    alloc = pd.DataFrame({"hex_id": chosen_hex, "selected": 1, "selected_for": _tr("Manuellt", "Manual")})
elif selection_mode == "manual" and not strict_ready:
    st.subheader(_tr("Manuellt urval av utbyggnadshexagoner", "Manual selection of development hexagons"))
    st.warning(
        _tr(
            "Manuellt urval är avstängt i strikt läge tills den aktiva mixen bara innehåller TIMES-tekniker med "
            "stödd markintensitet i AreaDemand.xlsx.",
            "Manual selection is disabled in strict mode until the active mix only contains TIMES technologies with "
            "supported land intensity in AreaDemand.xlsx.",
        )
    )

view = map_df.merge(alloc, on="hex_id", how="left")
view["selected"] = view["selected"].fillna(0).astype(int)
view["selected_for"] = view["selected_for"].fillna("")

c1, c2, c3, c4 = st.columns(4)
c1.metric(_tr("Scenario", "Scenario"), scenario_label)
c2.metric(_tr("År", "Year"), str(year))
c3.metric(_tr("Markanspråk (km2)", "Land demand (km2)"), f"{total_area_need:.1f}" if strict_ready else _tr("Ej tillgängligt", "Not available"))
c4.metric(_tr("Hexbehov", "Hex demand"), f"{hex_need_total}" if strict_ready else _tr("Ej tillgängligt", "Not available"))
if not strict_ready:
    st.error(
        _tr(
            "Strikt markintensitetsläge kan inte beräkna geografin för nuvarande mix. "
            "Aktiva TIMES-tekniker utan workbook-stöd: ",
            "Strict land-intensity mode cannot calculate geography for the current mix. "
            "Active TIMES technologies without workbook support: ",
        )
        + ", ".join(sorted(set(selected_unsupported_times_techs)))
    )
if wind_acceptance_available:
    st.caption(
        _tr(
            f"Vindplacering: `{_wind_placement_label(str(wind_placement_id))}`. {wind_allowed_hex_count} av {len(analysis_df)} hex är tillåtna ({wind_allowed_share_pct:.2f}%).",
            f"Wind placement: `{_wind_placement_label(str(wind_placement_id))}`. {wind_allowed_hex_count} of {len(analysis_df)} hexes are allowed ({wind_allowed_share_pct:.2f}%).",
        )
    )
if selection_mode == "manual" and strict_ready:
    covered_area = manual_selected_count * hex_area
    st.caption(
        _tr(
            f"Manuellt valda hex: {manual_selected_count} (~{covered_area:.1f} km2) av behov {hex_need_total} hex (~{total_area_need:.1f} km2).",
            f"Manually selected hexes: {manual_selected_count} (~{covered_area:.1f} km2) out of a need for {hex_need_total} hexes (~{total_area_need:.1f} km2).",
        )
    )
    if manual_selected_count < hex_need_total:
        st.warning(_tr("Manuellt urval täcker inte hela beräknat markanspråk.", "Manual selection does not cover the full calculated land demand."))

mix_df = area_factor_detail_df.copy()
mix_df_display = _translate_app_category_column(mix_df)
mix_df_display = mix_df_display.rename(
    columns=_translate_columns(
        {
            "TIMES-teknik": ("TIMES-teknik", "TIMES technology"),
            "Appkategori": ("Appkategori", "App category"),
            "TWh": ("TWh", "TWh"),
            "km2_per_twh": ("km2 per TWh", "km2 per TWh"),
            "km2": ("km2", "km2"),
            "Status": ("Status", "Status"),
            "Motivering": ("Motivering", "Reason"),
        }
    )
)

baseline_df = (
    pd.DataFrame(scenario_totals)
    .rename_axis("year")
    .reset_index()
    .melt(id_vars="year", var_name="scenario", value_name="total_twh")
)
baseline_df["scenario"] = baseline_df["scenario"].astype(str)
baseline_df["scenario_label"] = baseline_df["scenario"].map(
    lambda scen: _scenario_display_label(scen, scenario_desc_map)
)
baseline_df = baseline_df.sort_values(["scenario", "year"]).reset_index(drop=True)
baseline_df["year_label"] = baseline_df["year"].astype(int).astype(str)
baseline_df["base_year_twh"] = baseline_df.groupby("scenario")["total_twh"].transform("first")
baseline_df["index_first_year"] = np.where(
    baseline_df["base_year_twh"] > 0,
    100.0 * baseline_df["total_twh"] / baseline_df["base_year_twh"],
    np.nan,
)
year_order = [str(year) for year in sorted(int(year) for year in baseline_df["year"].dropna().unique().tolist())]
scenario_order = baseline_df["scenario_label"].drop_duplicates().tolist()

map_col, side_col = st.columns([1.8, 1.1], gap="large")
with map_col:
    st.subheader(_tr("Karta: hexagoner + urval", "Map: hexagons + selection"))
    map_control_col, map_mode_caption_col = st.columns([1.0, 1.4], gap="small")
    with map_control_col:
        show_wind_acceptance = st.toggle(
            _tr("Visa vindacceptans", "Show wind acceptance"),
            value=wind_acceptance_available,
            disabled=not wind_acceptance_available,
            help=_tr(
                "Växla mellan vindacceptans och landskapsklasser i kartans färger.",
                "Switch the map colors between wind acceptance and landscape classes.",
            ),
        )
    with map_mode_caption_col:
        st.caption(
            _tr(
                "På: färger visar tillåten/otillåten vindplacering. Av: färger visar landskapsklasser.",
                "On: colors show allowed/blocked wind placement. Off: colors show landscape classes.",
            )
        )

    map_view = view.copy()
    map_view["cluster_color"] = map_view["class_km"].map(CLUSTER_COLORS).apply(
        lambda x: x if isinstance(x, list) else [180, 180, 180, 70]
    )
    map_view["fill_color"] = map_view["cluster_color"]
    if show_wind_acceptance and wind_acceptance_available:
        allowed_mask = map_view["wind_allowed_selected"].fillna(False).astype(bool).tolist()
        map_view["fill_color"] = [
            [46, 125, 50, 150] if is_allowed else [190, 190, 190, 45]
            for is_allowed in allowed_mask
        ]
        legend_items = [
            (_tr("Tillåten för vind", "Allowed for wind"), [46, 125, 50, 150]),
            (_tr("Ej tillåten för vind", "Not allowed for wind"), [190, 190, 190, 45]),
            (_tr("Valda hex", "Selected hexes"), [220, 20, 60, 180]),
        ]
    else:
        if "build_candidate" in map_view.columns:
            excluded_mask = ~map_view["build_candidate"].fillna(True)
            if excluded_mask.any():
                map_view.loc[excluded_mask, "fill_color"] = map_view.loc[excluded_mask, "fill_color"].apply(
                    lambda _: [185, 185, 185, 40]
                )
        legend_items = [(_tr("Valda hex", "Selected hexes"), [220, 20, 60, 180])]
        for class_id in sorted(CLUSTER_COLORS):
            legend_items.append((f"class_km {class_id}", CLUSTER_COLORS[class_id]))

    selected_mask = map_view["selected"] == 1
    if selected_mask.any():
        map_view.loc[selected_mask, "fill_color"] = map_view.loc[selected_mask, "fill_color"].apply(
            lambda _: [220, 20, 60, 180]
        )

    _render_map_legend(legend_items)

    tooltip_lines = [
        "<b>hex_id:</b> {hex_id}",
        f"<b>{_tr('vald för', 'selected for')}:</b> {{selected_for}}",
        f"<b>{_tr('byggkandidat', 'build candidate')}:</b> {{build_candidate}}",
    ]
    if "class_km" in view.columns:
        tooltip_lines.insert(1, "<b>class_km:</b> {class_km}")
    if wind_acceptance_available:
        tooltip_lines.append(f"<b>{_tr('vind tillåten', 'wind allowed')}:</b> {{wind_allowed_selected}}")
        tooltip_lines.append(f"<b>{_tr('vindscore', 'wind score')}:</b> {{wind_acceptance_score_selected}}")
        tooltip_lines.append(f"<b>{_tr('vindklass', 'wind class')}:</b> {{wind_acceptance_class_selected}}")
    if "acceptance_value" in view.columns and view["acceptance_value"].astype(str).str.strip().any():
        tooltip_lines.append(f"<b>{_tr('acceptans', 'acceptance')}:</b> {{acceptance_value}}")
    tooltip = {
        "html": "<br/>".join(tooltip_lines),
        "style": {"backgroundColor": "white", "color": "black"},
    }
    polygon_layer = pdk.Layer(
        "PolygonLayer",
        data=map_view,
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color=[90, 90, 90, 90],
        line_width_min_pixels=0.5,
        stroked=False,
        filled=True,
        pickable=True,
        auto_highlight=True,
    )
    center_lat = float(map_view["lat"].median())
    center_lon = float(map_view["lon"].median())
    deck = pdk.Deck(
        layers=[polygon_layer],
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=9, pitch=0),
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    )
    st.pydeck_chart(deck, use_container_width=True)
    if wind_acceptance_available:
        st.caption(
            _tr(
                f"V4-res9 används för kartan. Vindfilter `{_wind_placement_label(str(wind_placement_id))}` styr bara ny vindkraft, med `Mellan` som standard.",
                f"V4-res9 is used for the map. The `{_wind_placement_label(str(wind_placement_id))}` wind filter only affects new wind power, with `Medium` as the default.",
            )
        )
    elif "acceptance_value" in build.columns and build["acceptance_value"].astype(str).str.strip().any():
        st.caption(_tr("Kartlagret är kompletterat med acceptansinformation när den finns tillgänglig.", "The map layer is enriched with acceptance information when available."))

with side_col:
    st.subheader(_tr("Beräkning", "Calculation"))
    st.dataframe(mix_df_display.round(2), use_container_width=True, height=min(360, 80 + 35 * max(len(mix_df_display), 1)))
    calc_caption_sv = (
        f"Markanspråksscenario: `{area_scenario_label}`. "
        + (f"Vindplacering: `{_wind_placement_label(str(wind_placement_id))}`. " if wind_acceptance_available else "")
        + f"AreaDemand-status: `{area_demand_status}`. "
        + "Beräkningen sker per TIMES-teknik och stoppas om workbooken saknar kompatibel markintensitet för en aktiv teknik."
    )
    calc_caption_en = (
        f"Land-demand scenario: `{area_scenario_label}`. "
        + (f"Wind placement: `{_wind_placement_label(str(wind_placement_id))}`. " if wind_acceptance_available else "")
        + f"AreaDemand status: `{area_demand_status}`. "
        + "The calculation runs per TIMES technology and stops if the workbook lacks a compatible land intensity for an active technology."
    )
    st.caption(
        _tr(
            calc_caption_sv,
            calc_caption_en,
        )
    )
    st.markdown(f"### {_tr('Baslinjer (TIMES-data)', 'Baselines (TIMES data)')}")
    if float(baseline_df["total_twh"].max()) > 5 * float(max(1e-9, baseline_df["total_twh"].median())):
        st.caption(
            _tr(
                "Ett scenario ligger mycket högre än de andra i totalvyn. "
                "Titta på fliken 'Index' eller 'Tabell' för att se de lägre kurvorna tydligare.",
                "One scenario sits much higher than the others in the total view. "
                "Look at the 'Index' or 'Table' tab to see the lower curves more clearly.",
            )
        )

    total_tab, index_tab, table_tab = st.tabs(["Total TWh", "Index", _tr("Tabell", "Table")])
    with total_tab:
        total_chart = _build_baseline_line_chart(
            baseline_df,
            "total_twh",
            "Total TWh",
            year_order,
            scenario_order,
            zero=True,
            value_format=".2f",
        )
        if total_chart is not None:
            st.altair_chart(total_chart, width="stretch")
        else:
            baseline_fallback = baseline_df[["year_label", "scenario_label", "total_twh"]].rename(
                columns={"scenario_label": "scenario"}
            )
            st.line_chart(
                baseline_fallback,
                x="year_label",
                y="total_twh",
                color="scenario",
                width="stretch",
            )

    with index_tab:
        st.caption(_tr("Index visar utvecklingen relativt varje scenarios första tillgängliga år (=100).", "Index shows the change relative to each scenario's first available year (=100)."))
        index_chart = _build_baseline_line_chart(
            baseline_df,
            "index_first_year",
            _tr("Index (första år = 100)", "Index (first year = 100)"),
            year_order,
            scenario_order,
            zero=False,
            value_format=".1f",
        )
        if index_chart is not None:
            st.altair_chart(index_chart, width="stretch")
        else:
            baseline_index_fallback = baseline_df[["year_label", "scenario_label", "index_first_year"]].rename(
                columns={"scenario_label": "scenario"}
            )
            st.line_chart(
                baseline_index_fallback,
                x="year_label",
                y="index_first_year",
                color="scenario",
                width="stretch",
            )

    with table_tab:
        baseline_table = (
            baseline_df.pivot(index="year", columns="scenario_label", values="total_twh")
            .reset_index()
            .rename_axis(None, axis=1)
            .round(3)
        )
        st.dataframe(baseline_table, width="stretch", hide_index=True)

st.markdown(f"### {_tr('Datakvalitet och transparens', 'Data quality and transparency')}")
st.info(
    _tr(
        "Markintensitetstransparens: "
        f"{len(selected_supported_times_techs)} av {len(active_times_tech_codes)} aktiva TIMES-tekniker har "
        "direkt scenariofaktor från AreaDemand.xlsx.",
        "Land-intensity transparency: "
        f"{len(selected_supported_times_techs)} of {len(active_times_tech_codes)} active TIMES technologies have "
        "a direct scenario factor from AreaDemand.xlsx.",
    )
)
if selected_unsupported_times_techs:
    st.warning(
        _tr(
            "Strikt läge: följande aktiva TIMES-tekniker saknar kompatibel markintensitet i workbooken: ",
            "Strict mode: the following active TIMES technologies lack compatible land intensity in the workbook: ",
        )
        + ", ".join(selected_unsupported_times_techs)
        + _tr(
            ". Sätt deras andel till 0 eller bygg en explicit mapping innan kartanalysen tolkas.",
            ". Set their share to 0 or build an explicit mapping before interpreting the map analysis.",
        )
    )
st.caption(
    _tr(
        f"TIMESreport-status: `{times_status}`. AreaDemand-status: `{area_demand_status}`. "
        f"Markanspråksscenario: `{area_scenario_label}`.",
        f"TIMES report status: `{times_status}`. AreaDemand status: `{area_demand_status}`. "
        f"Land-demand scenario: `{area_scenario_label}`.",
    )
)
if not selected_times_coverage.empty:
    named_share = float(selected_times_coverage.get("named_share_pct", 0.0))
    other_share = float(selected_times_coverage.get("other_bucket_share_pct", 0.0))
    other_twh = float(selected_times_coverage.get("other_bucket_twh", 0.0))
    unmapped_twh = float(selected_times_coverage.get("unmapped_twh", 0.0))
    st.info(
        _tr(
            "TIMES-kartläggning för valt scenarioår: "
            f"{named_share:.1f}% ligger i namngivna planeringskategorier och "
            f"{other_share:.1f}% ligger i 'Övrigt' ({other_twh:.2f} TWh).",
            "TIMES mapping for the selected scenario year: "
            f"{named_share:.1f}% is in named planning categories and "
            f"{other_share:.1f}% is in 'Other' ({other_twh:.2f} TWh).",
        )
    )
    if unmapped_twh > 0:
        st.warning(
            _tr(
                f"Det finns fortfarande {unmapped_twh:.2f} TWh TIMES-rader utan explicit mappingregel. "
                "Se 'TIMES mapping audit' nedan innan resultaten tolkas som slutliga.",
                f"There are still {unmapped_twh:.2f} TWh of TIMES rows without an explicit mapping rule. "
                "See 'TIMES mapping audit' below before treating the results as final.",
            )
        )
if scenario in scenario_desc_map or scenario in scenario_source_map:
    meta_parts = [_tr(f"Kod: {scenario}", f"Code: {scenario}")]
    if scenario in scenario_source_map:
        meta_parts.append(_tr(f"Källdata: {scenario_source_map[scenario]}", f"Source data: {scenario_source_map[scenario]}"))
    st.caption(_tr("DuckDB-scenariometadata: ", "DuckDB scenario metadata: ") + ". ".join(meta_parts) + f". (`{scenario_meta_status}`)")
st.caption(f"{_tr('Hexkälla', 'Hex source')}: `{hex_source_status}`. {_tr('Urvalsmetod', 'Selection mode')}: {_selection_mode_label(selection_mode)}.")
with st.expander(_tr("TIMES-report förhandsvisning", "TIMES report output preview"), expanded=False):
    st.caption(f"{_tr('Preview-status', 'Preview status')}: `{times_preview_status}`")
    if times_preview_summary:
        if "scen" in times_preview_summary:
            scen_labels = [
                _scenario_display_label(str(scen), scenario_desc_map) for scen in times_preview_summary["scen"]
            ]
            st.write(f"{_tr('Scenarier', 'Scenarios')}:", ", ".join(scen_labels))
        if "techgroup" in times_preview_summary:
            st.write(f"{_tr('Techgroup (unika)', 'Techgroup (unique)')}:", ", ".join(times_preview_summary["techgroup"]))
        if "comgroup" in times_preview_summary:
            st.write(f"{_tr('Comgroup (unika)', 'Comgroup (unique)')}:", ", ".join(times_preview_summary["comgroup"]))
        if "units" in times_preview_summary:
            st.write(f"{_tr('Units (unika)', 'Units (unique)')}:", ", ".join(times_preview_summary["units"]))
    if times_preview_df is not None:
        st.dataframe(times_preview_df, use_container_width=True, height=260)
with st.expander("TIMES mapping audit", expanded=False):
    st.caption(f"{_tr('Mapping-status', 'Mapping status')}: `{times_mapping_status}`")
    if not selected_times_coverage.empty:
        selected_coverage_df = pd.DataFrame(
            [
                {
                    _tr("Scenario", "Scenario"): scenario_label,
                    _tr("År", "Year"): int(selected_times_coverage.get("year", year)),
                    "Total TWh": float(selected_times_coverage.get("total_twh", 0.0)),
                    _tr("Namngivna kategorier TWh", "Named categories TWh"): float(selected_times_coverage.get("named_twh", 0.0)),
                    _tr("Övrigt-bucket TWh", "Other bucket TWh"): float(selected_times_coverage.get("other_bucket_twh", 0.0)),
                    _tr("Övrigt-bucket %", "Other bucket %"): float(selected_times_coverage.get("other_bucket_share_pct", 0.0)),
                    _tr("Omatchat TWh", "Unmapped TWh"): float(selected_times_coverage.get("unmapped_twh", 0.0)),
                }
            ]
        )
        st.dataframe(selected_coverage_df.round(2), use_container_width=True, hide_index=True)
    if not selected_times_mix_df.empty:
        selected_mix_display = selected_times_mix_df.copy()
        selected_mix_display[_tr("Energislag", "Energy type")] = selected_mix_display["energy_key"].map(_human_tech_name)
        st.caption(_tr("Valt scenarioår, aggregerat till appens planeringskategorier.", "Selected scenario year, aggregated to the app's planning categories."))
        st.dataframe(
            selected_mix_display[[_tr("Energislag", "Energy type"), "value_twh", "share_pct", "row_count"]]
            .rename(columns={"value_twh": "TWh", "share_pct": _tr("Andel %", "Share %"), "row_count": _tr("Antal rader", "Row count")})
            .round(2),
            use_container_width=True,
            hide_index=True,
            height=220,
        )
    if not times_coverage_df.empty:
        overview_df = times_coverage_df.copy()
        overview_df[_tr("Scenario", "Scenario")] = overview_df["scen"].astype(str).map(
            lambda scen: _scenario_display_label(scen, scenario_desc_map)
        )
        st.caption(
            _tr(
                "Översikt för alla scenarioår och år. 'Övrigt' är en medveten samlingskategori, inte automatiskt saknad data.",
                "Overview for all scenario years and years. 'Other' is a deliberate collection category, not automatically missing data.",
            )
        )
        st.dataframe(
            overview_df[
                [
                    _tr("Scenario", "Scenario"),
                    "year",
                    "total_twh",
                    "named_twh",
                    "other_bucket_twh",
                    "other_bucket_share_pct",
                    "unmapped_twh",
                ]
            ]
            .rename(
                columns={
                    "year": _tr("År", "Year"),
                    "total_twh": "Total TWh",
                    "named_twh": _tr("Namngivna kategorier TWh", "Named categories TWh"),
                    "other_bucket_twh": _tr("Övrigt-bucket TWh", "Other bucket TWh"),
                    "other_bucket_share_pct": _tr("Övrigt-bucket %", "Other bucket %"),
                    "unmapped_twh": _tr("Omatchat TWh", "Unmapped TWh"),
                }
            )
            .round(2),
            use_container_width=True,
            hide_index=True,
            height=260,
        )
    if not selected_times_other_df.empty:
        st.caption(
            _tr(
                "'Övrigt' i valt scenarioår består just nu framför allt av dessa råa TIMES-koder.",
                "'Other' in the selected scenario year currently consists mainly of these raw TIMES codes.",
            )
        )
        st.dataframe(
            selected_times_other_df[["raw_mapping", "mapping_source", "value_twh", "row_count"]]
            .rename(
                columns={
                    "raw_mapping": _tr("TIMES-kodkombination", "TIMES code combination"),
                    "mapping_source": _tr("Regeltyp", "Rule type"),
                    "value_twh": "TWh",
                    "row_count": _tr("Antal rader", "Row count"),
                }
            )
            .round(3),
            use_container_width=True,
            hide_index=True,
            height=260,
        )
    if not selected_times_unmapped_df.empty:
        st.caption(
            _tr(
                "Dessa rader saknar fortfarande explicit mappingregel och bör gå igenom med EML.",
                "These rows still lack an explicit mapping rule and should be reviewed with EML.",
            )
        )
        st.dataframe(
            selected_times_unmapped_df[["raw_mapping", "value_twh", "row_count"]]
            .rename(
                columns={
                    "raw_mapping": _tr("TIMES-kodkombination", "TIMES code combination"),
                    "value_twh": "TWh",
                    "row_count": _tr("Antal rader", "Row count"),
                }
            )
            .round(3),
            use_container_width=True,
            hide_index=True,
            height=220,
        )
with st.expander(_tr("AreaDemand profiler och spann", "AreaDemand profiles and ranges"), expanded=False):
    st.markdown(
        _tr(
            "Scenarierna byggs transparent från `AreaDemand.xlsx`:\n"
            "- `Lågt markanspråk` = minsta observerade `km2/TWh` per TIMES-teknik.\n"
            "- `Mellan` = median av mittvärden per TIMES-teknik.\n"
            "- `Högt` = största observerade `km2/TWh` per TIMES-teknik.\n"
            "- Intervall och `+-` tolkas i källans egna enheter före konvertering till `km2/TWh`.\n"
            "- Inga fallback-värden används i denna modell.",
            "The scenarios are built transparently from `AreaDemand.xlsx`:\n"
            "- `Low land demand` = the smallest observed `km2/TWh` per TIMES technology.\n"
            "- `Medium` = the median of mid-values per TIMES technology.\n"
            "- `High` = the largest observed `km2/TWh` per TIMES technology.\n"
            "- Ranges and `+-` are interpreted in the source's own units before conversion to `km2/TWh`.\n"
            "- No fallback values are used in this model.",
        )
    )
    st.caption(
        _tr(
            "AreaDemand översätter TIMES-volymer till markbehov. Geografin uppstår först när markbehovet kombineras "
            "med suitability, byggbara hex och acceptanslager.",
            "AreaDemand translates TIMES volumes into land demand. Geography only emerges once land demand is combined "
            "with suitability, buildable hexes, and acceptance layers.",
        )
    )
    if not area_scenario_active_df.empty:
        st.caption(_tr("Scenario-tabell för aktiva TIMES-tekniker.", "Scenario table for active TIMES technologies."))
        area_scenario_display_df = _translate_app_category_column(area_scenario_active_df)
        st.dataframe(
            area_scenario_display_df[
                [
                    "TIMES-teknik",
                    "Appkategori",
                    "Workbook-rad",
                    "Lagt km2/TWh",
                    "Mellan km2/TWh",
                    "Hogt km2/TWh",
                    "Vald scenario km2/TWh",
                    "Status",
                    "Motivering",
                ]
            ]
            .rename(
                columns=_translate_columns(
                    {
                        "TIMES-teknik": ("TIMES-teknik", "TIMES technology"),
                        "Appkategori": ("Appkategori", "App category"),
                        "Workbook-rad": ("Workbook-rad", "Workbook row"),
                        "Lagt km2/TWh": ("Lågt km2/TWh", "Low km2/TWh"),
                        "Mellan km2/TWh": ("Mellan km2/TWh", "Medium km2/TWh"),
                        "Hogt km2/TWh": ("Högt km2/TWh", "High km2/TWh"),
                        "Vald scenario km2/TWh": ("Valt scenario km2/TWh", "Selected scenario km2/TWh"),
                        "Status": ("Status", "Status"),
                        "Motivering": ("Motivering", "Reason"),
                    }
                )
            )
            .round(3),
            use_container_width=True,
            hide_index=True,
            height=min(420, 80 + 35 * max(len(area_scenario_active_df), 1)),
        )
    if not area_mapping_active_df.empty:
        st.caption(_tr("Mapping mellan TIMES-tekniker och workbook-rader.", "Mapping between TIMES technologies and workbook rows."))
        area_mapping_display_df = _translate_app_category_column(area_mapping_active_df)
        st.dataframe(
            area_mapping_display_df.rename(
                columns=_translate_columns(
                    {
                        "TIMES-teknik": ("TIMES-teknik", "TIMES technology"),
                        "Appkategori": ("Appkategori", "App category"),
                        "Workbook-rad": ("Workbook-rad", "Workbook row"),
                        "Status": ("Status", "Status"),
                        "Motivering": ("Motivering", "Reason"),
                    }
                )
            ).round(3),
            use_container_width=True,
            hide_index=True,
            height=min(360, 80 + 35 * max(len(area_mapping_active_df), 1)),
        )
    if not active_area_observation_df.empty:
        st.caption(_tr("Excel-värden som ligger bakom scenarierna för aktiva TIMES-tekniker.", "Excel values behind the scenarios for active TIMES technologies."))
        active_area_observation_display_df = _translate_app_category_column(active_area_observation_df)
        st.dataframe(
            active_area_observation_display_df.rename(
                columns=_translate_columns(
                    {
                        "TIMES-teknik": ("TIMES-teknik", "TIMES technology"),
                        "Appkategori": ("Appkategori", "App category"),
                        "Workbook-rad": ("Workbook-rad", "Workbook row"),
                        "Kalla": ("Källa", "Source"),
                        "Metrik": ("Metrik", "Metric"),
                        "Excel-varde": ("Excel-värde", "Excel value"),
                        "Scenario-anvand": ("Scenario-använd", "Used in scenario"),
                        "Tolkningsregel": ("Tolkningsregel", "Interpretation rule"),
                        "Lagt km2/TWh": ("Lågt km2/TWh", "Low km2/TWh"),
                        "Mellan km2/TWh": ("Mellan km2/TWh", "Medium km2/TWh"),
                        "Hogt km2/TWh": ("Högt km2/TWh", "High km2/TWh"),
                        "Notering": ("Notering", "Note"),
                    }
                )
            ).round(3),
            use_container_width=True,
            hide_index=True,
            height=min(480, 80 + 35 * max(len(active_area_observation_df), 1)),
        )
    references = [str(ref) for ref in area_demand_bundle.get("references", []) if str(ref).strip()]
    if references:
        st.caption(_tr("Referenser som listas i workbooken.", "References listed in the workbook."))
        st.markdown("\n".join(f"- {ref}" for ref in references))
    st.caption(_tr("Osäkerheter och caveats.", "Uncertainties and caveats."))
    st.write(
        _tr(
            "- `NRG_WIN` kopplas till landbaserad vind. Offshore-vind exkluderas som inkompatibelt markkoncept för denna karta.",
            "- `NRG_WIN` is linked to onshore wind. Offshore wind is excluded as an incompatible land-use concept for this map.",
        )
    )
    st.write(_tr("- `NRG_SOL` kopplas till `Solar PV`. CSP exkluderas för att undvika att blanda olika soltekniker.", "- `NRG_SOL` is linked to `Solar PV`. CSP is excluded to avoid mixing different solar technologies."))
    st.write(_tr("- `NRG_NUK/NRG_NUC` kopplas till `Nuclear`. `SMR` visas i workbooken men blandas inte in automatiskt.", "- `NRG_NUK/NRG_NUC` is linked to `Nuclear`. `SMR` appears in the workbook but is not mixed in automatically."))
    st.write(_tr("- Tekniker utan tydlig workbook-rad stoppas i strikt läge i stället för att få fallback.", "- Technologies without a clear workbook row are stopped in strict mode instead of receiving fallback values."))
with st.expander(_tr("AreaDemand-känslighet", "AreaDemand sensitivity"), expanded=False):
    if area_sensitivity_df.empty:
        st.caption(_tr("Inga markintensitetsscenarier kunde byggas.", "No land-intensity scenarios could be built."))
    else:
        st.caption(_tr("Jämför totalt markanspråk mellan Lågt, Mellan och Högt för nuvarande scenario och elmix.", "Compare total land demand between Low, Medium, and High for the current scenario and electricity mix."))
        st.dataframe(
            area_sensitivity_df[["Scenario", "Vald", "Strikt klar", "Total km2", "Delta vs vald %", "Saknade TIMES-tekniker"]]
            .rename(
                columns=_translate_columns(
                    {
                        "Scenario": ("Scenario", "Scenario"),
                        "Vald": ("Vald", "Selected"),
                        "Strikt klar": ("Strikt klar", "Strict-ready"),
                        "Total km2": ("Total km2", "Total km2"),
                        "Delta vs vald %": ("Delta vs vald %", "Delta vs selected %"),
                        "Saknade TIMES-tekniker": ("Saknade TIMES-tekniker", "Missing TIMES technologies"),
                    }
                )
            )
            .round(2),
            use_container_width=True,
            height=260,
        )
with st.expander(_tr("AreaDemand transparens", "AreaDemand transparency"), expanded=False):
    st.caption(_tr("Visar exakt vilka aktiva TIMES-tekniker som driver markbehovet i valt scenario.", "Shows exactly which active TIMES technologies drive land demand in the selected scenario."))
    area_factor_display_df = _translate_app_category_column(
        area_factor_detail_df[
            ["TIMES-teknik", "Appkategori", "TWh", "km2_per_twh", "km2", "Status", "Motivering"]
        ]
    ).rename(
        columns=_translate_columns(
            {
                "TIMES-teknik": ("TIMES-teknik", "TIMES technology"),
                "Appkategori": ("Appkategori", "App category"),
                "TWh": ("TWh", "TWh"),
                "km2_per_twh": ("km2 per TWh", "km2 per TWh"),
                "km2": ("km2", "km2"),
                "Status": ("Status", "Status"),
                "Motivering": ("Motivering", "Reason"),
            }
        )
    )
    st.dataframe(
        area_factor_display_df.round(3),
        use_container_width=True,
        height=min(360, 80 + 35 * max(len(area_factor_detail_df), 1)),
    )
