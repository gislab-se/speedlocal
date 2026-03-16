from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
import math

import duckdb
import h3
import pandas as pd


UNIT_TO_TWH = {
    "twh": 1.0,
    "gwh": 1e-3,
    "mwh": 1e-6,
    "pj": 1.0 / 3.6,
    "tj": 1.0 / 3600.0,
}
DEFAULT_AREA_FACTORS = {
    "wind": 1.20,
    "solar": 2.10,
    "nuclear": 0.12,
    "hydro": 1.20,
    "bio": 1.40,
    "coal": 0.90,
    "gas": 0.60,
    "oil": 0.70,
    "renewables": 1.30,
    "electricity": 1.00,
    "demand": 1.00,
    "other": 1.00,
}
ENERGY_LABELS = {
    "wind": "Vind",
    "solar": "Sol",
    "nuclear": "Karnkraft",
    "hydro": "Vattenkraft",
    "bio": "Bioenergi",
    "coal": "Kol",
    "gas": "Gas",
    "oil": "Olja",
    "renewables": "Fornybart",
    "electricity": "El",
    "demand": "Efterfragan",
    "other": "Ovrigt",
}
ENERGY_ALIASES = {
    "wind": ["wind", "win", "elewin"],
    "solar": ["solar", "sol", "elesol"],
    "hydro": ["hydro", "hyd", "water", "elehyd"],
    "nuclear": ["nuclear", "nuc", "karn", "elenuc", "nrg_nuk", "tg_nuc"],
    "bio": ["biomass", "bio", "elebio", "nrg_bio", "tg_bio"],
    "coal": ["coal", "coa", "elecoa", "nrg_coa", "tg_coa"],
    "gas": ["gas", "elegas", "nrg_gas", "tg_gas"],
    "oil": ["oil", "dsl", "hfo", "ker", "lpg", "nap", "eleoil", "nrg_oil", "tg_oil"],
    "renewables": ["renew", "rnw", "rew", "elernw", "tg_rew", "nrg_rnw"],
    "electricity": ["electricity", "elc", "tg_elc", "nrg_elc"],
    "demand": ["demand", "dem", "tg_dmd", "dem_com"],
}
CLUSTER_COLORS = {
    0: "#7fb3d5",
    1: "#f39c12",
    2: "#f7dc6f",
    3: "#c39bd3",
    4: "#e74c3c",
    5: "#82e0aa",
    6: "#76d7c4",
    7: "#aeb6bf",
}
LINE_COLORS = ["#1f77b4", "#e15759", "#59a14f", "#f28e2b", "#4e79a7", "#af7aa1"]
SUITABILITY_TECHS = tuple(ENERGY_LABELS.keys())


@dataclass
class ExampleCase:
    scenario: str
    scenario_label: str
    year: int
    area_profile_id: str
    area_profile_label: str
    base_total_twh: float
    total_area_need_km2: float
    hex_need_total: int
    build_hex_count: int
    selected_hex_count: int
    mix_pct: dict[str, float]
    twh: dict[str, float]
    area_need: dict[str, float]
    area_factor_sources: dict[str, str]
    selected_fallback_techs: list[str]
    allowed_clusters: list[int]
    view_df: pd.DataFrame
    sensitivity_df: pd.DataFrame


def human_tech_name(tech: str) -> str:
    return ENERGY_LABELS.get(tech, tech.replace("_", " ").title())


def scenario_display_label(scen: str, descriptions: dict[str, str]) -> str:
    desc = str(descriptions.get(scen, "")).strip()
    if not desc or desc == scen:
        return scen
    return f"{desc} [{scen}]"


def tech_from_text(text: str) -> str:
    low = str(text).lower().strip()
    if not low:
        return "other"
    for tech, aliases in ENERGY_ALIASES.items():
        if any(alias in low for alias in aliases):
            return tech
    return "other"


def normalize_mix_100(values: dict[str, float]) -> dict[str, float]:
    keys = list(values.keys())
    if not keys:
        return {}
    clean = {k: max(0.0, float(values.get(k, 0.0))) for k in keys}
    total = sum(clean.values())
    if total <= 0:
        eq = 100.0 / len(keys)
        return {k: eq for k in keys}
    return {k: clean[k] * 100.0 / total for k in keys}


def build_base_mix_by_year(
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
        available_mix_lookup.setdefault(str(scen), {})[int(year)] = normalize_mix_100(
            {k: float(by_tech.get(k, 0.0)) for k in all_techs}
        )

    base_mix: dict[str, dict[int, dict[str, float]]] = {}
    for scen, year_totals in scenario_totals.items():
        yearly_mix: dict[int, dict[str, float]] = {}
        available_years = sorted(available_mix_lookup.get(str(scen), {}).keys())
        for year in sorted(int(v) for v in year_totals.keys()):
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


def resolve_base_mix_for_year(
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
        available_years = sorted(int(v) for v in scenario_mix.keys())
        if available_years:
            fallback_year = min(available_years, key=lambda available: abs(available - int(year)))
            fallback_mix = scenario_mix.get(fallback_year, {})
            if isinstance(fallback_mix, dict) and fallback_mix:
                return dict(fallback_mix)
        return {"other": 100.0}
    return {str(k): float(v) for k, v in scenario_mix.items()}


def find_duckdb(root: Path) -> Path:
    candidates = [
        root / "data" / "processed" / "speedlocal_times.duckdb",
        root / "duckdb" / "speedlocal_times.duckdb",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find speedlocal_times.duckdb")


def find_area_profile_duckdb(root: Path) -> Path:
    candidates = [
        root / "data" / "processed" / "area_demand_profiles.duckdb",
        root / "data" / "processed" / "speedlocal_area_profiles.duckdb",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find area_demand_profiles.duckdb")


def find_gc4_base(root: Path) -> Path:
    path = root / "jyp_note_book_geocontext"
    if not path.exists():
        raise FileNotFoundError(f"Missing GC4 directory: {path}")
    return path


def duckdb_has_object(con, name: str) -> bool:
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


def duckdb_columns(con, name: str) -> list[str]:
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


def load_scenario_metadata(db_path: Path) -> dict[str, str]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if not duckdb_has_object(con, "scen_desc"):
            return {}
        rows = con.execute("SELECT scen, description FROM scen_desc").fetchall()
    finally:
        con.close()
    return {str(scen): str(desc) for scen, desc in rows if scen is not None}


def load_times_data(db_path: Path) -> tuple[dict[str, dict[int, float]], dict[str, dict[int, dict[str, float]]]]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if duckdb_has_object(con, "v_energy_mix"):
            mix = con.execute(
                """
                SELECT scen, CAST(year AS INTEGER) AS year, COALESCE(energy_key, 'other') AS energy_key, value_twh
                FROM v_energy_mix
                WHERE CAST(year AS INTEGER) IN (2030, 2040, 2050)
                """
            ).df()
        else:
            source_table = next(
                (name for name in ["timesreport_raw", "timesreport"] if duckdb_has_object(con, name)),
                None,
            )
            if source_table is None:
                raise ValueError("DuckDB has neither timesreport_raw nor timesreport")
            cols = set(duckdb_columns(con, source_table))
            unit_col = "units" if "units" in cols else ("unit" if "unit" in cols else None)
            if unit_col is None:
                raise ValueError("timesreport table is missing units")
            ts_col = "timeslice" if "timeslice" in cols else ("all_ts" if "all_ts" in cols else None)
            select_cols = ["scen", "year", "value", f"{unit_col} AS units"]
            for name in ["techgroup", "comgroup", "prc", "com"]:
                if name in cols:
                    select_cols.append(name)
            where = [
                "lower(topic) = 'energy'",
                "lower(attr) IN ('f_out', 'comnet')",
                "TRY_CAST(year AS INTEGER) IN (2030, 2040, 2050)",
            ]
            if ts_col is not None:
                where.append(f"upper(coalesce({ts_col}, '')) = 'ANNUAL'")
            raw = con.execute(
                f"SELECT {', '.join(select_cols)} FROM {source_table} WHERE {' AND '.join(where)}"
            ).df()
            source_cols = [c for c in ["techgroup", "comgroup", "prc", "com"] if c in raw.columns]
            if source_cols:
                raw["energy_key"] = raw[source_cols].fillna("").astype(str).agg(" ".join, axis=1).apply(tech_from_text)
            else:
                raw["energy_key"] = "other"
            raw["year"] = pd.to_numeric(raw["year"], errors="coerce")
            raw["value"] = pd.to_numeric(raw["value"], errors="coerce")
            raw["units"] = raw["units"].astype(str).str.lower().str.strip()
            raw["value_twh"] = raw["value"] * raw["units"].map(UNIT_TO_TWH).fillna(1.0)
            raw = raw.dropna(subset=["year", "value_twh"])
            raw["year"] = raw["year"].astype(int)
            mix = (
                raw.groupby(["scen", "year", "energy_key"], as_index=False)["value_twh"]
                .sum()
                .sort_values(["scen", "year", "energy_key"])
            )
    finally:
        con.close()

    totals = mix.groupby(["scen", "year"], as_index=False)["value_twh"].sum()
    scenario_totals: dict[str, dict[int, float]] = {}
    for _, row in totals.iterrows():
        scenario_totals.setdefault(str(row["scen"]), {})[int(row["year"])] = float(row["value_twh"])
    base_mix_map = build_base_mix_by_year(mix, scenario_totals)
    return scenario_totals, base_mix_map


def load_area_profiles(area_db_path: Path) -> dict[str, dict[str, object]]:
    con = duckdb.connect(str(area_db_path), read_only=True)
    try:
        factor_cols = set(duckdb_columns(con, "area_factor_profiles"))
        value_source_sql = "value_source" if "value_source" in factor_cols else "'profile_unknown' AS value_source"
        profiles_df = con.execute(
            """
            SELECT profile_id, label, source_name, metric, source_path, sort_order
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
    finally:
        con.close()

    profiles: dict[str, dict[str, object]] = {}
    for _, row in profiles_df.iterrows():
        profiles[str(row["profile_id"])] = {
            "label": str(row["label"]),
            "source_name": str(row["source_name"]),
            "metric": str(row["metric"]),
            "path": str(row["source_path"]),
            "factors": dict(DEFAULT_AREA_FACTORS),
            "factor_sources": {key: "fallback_default" for key in DEFAULT_AREA_FACTORS},
            "coverage": [],
        }
    for _, row in factors_df.iterrows():
        profile = profiles.get(str(row["profile_id"]))
        if profile is None:
            continue
        energy_key = str(row["energy_key"])
        profile["factors"][energy_key] = float(row["km2_per_twh"])
        source_key = str(row["value_source"]) if row["value_source"] is not None else "profile_unknown"
        profile["factor_sources"][energy_key] = source_key
        if source_key == "profile":
            profile["coverage"].append(energy_key)
    return profiles


def recommended_area_profile_id(area_profiles: dict[str, dict[str, object]]) -> str:
    for profile_id, profile in area_profiles.items():
        if "norway specific" in str(profile.get("label", "")).lower():
            return profile_id
    return next(iter(area_profiles.keys()))


def load_gc4_data(gc4_base: Path) -> pd.DataFrame:
    pts = pd.read_csv(gc4_base / "bornholm_points_with_context_gc4.csv")
    scores = pd.read_csv(gc4_base / "bornholm_r8_factor_scores_gc4.csv")
    df = pts.merge(scores[["hex_id", "class_km", "F1", "F2", "F3", "F4", "F5"]], on="hex_id", how="left")
    df["class_km"] = df["class_km"].fillna(-1).astype(int)
    return df


def normalize_series(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    low = values.min()
    high = values.max()
    if pd.isna(low) or pd.isna(high) or high <= low:
        return pd.Series([0.0] * len(values), index=series.index)
    return (values - low) / (high - low)


def suitability(df: pd.DataFrame, tech: str) -> pd.Series:
    f1 = normalize_series(df["F1"])
    f2 = normalize_series(df["F2"])
    f3 = normalize_series(df["F3"])
    f4 = normalize_series(df["F4"])
    f5 = normalize_series(df["F5"])
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


def add_map_geometry(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    lats: list[float] = []
    lons: list[float] = []
    areas: list[float] = []
    for hex_id in work["hex_id"].astype(str):
        lat, lon = h3.cell_to_latlng(hex_id)
        lats.append(float(lat))
        lons.append(float(lon))
        areas.append(float(h3.cell_area(hex_id, unit="km^2")))
    work["lat"] = lats
    work["lon"] = lons
    work["hex_area_km2"] = areas
    return work


def build_suitability_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["hex_id", "F1", "F2", "F3", "F4", "F5"]].copy()
    for tech in SUITABILITY_TECHS:
        out[f"s_{tech}"] = suitability(out, tech)
    return out


def build_example_case(
    scenario_totals: dict[str, dict[int, float]],
    base_mix_map: dict[str, dict[int, dict[str, float]]],
    area_profiles: dict[str, dict[str, object]],
    scenario_descriptions: dict[str, str],
    gc4_df: pd.DataFrame,
) -> ExampleCase:
    if "BASELINE2050" in scenario_totals:
        scenario = "BASELINE2050"
    else:
        scenario = sorted(scenario_totals.keys())[0]
    available_years = sorted(int(year) for year in scenario_totals[scenario].keys())
    year = 2050 if 2050 in available_years else available_years[-1]
    area_profile_id = recommended_area_profile_id(area_profiles)
    area_profile = area_profiles[area_profile_id]
    base_total = float(scenario_totals[scenario][year])
    mix_pct = normalize_mix_100(resolve_base_mix_for_year(base_mix_map, scenario, year))
    tech_keys = list(mix_pct.keys())

    area_factors = dict(area_profile["factors"])
    factor_sources = dict(area_profile["factor_sources"])
    twh = {tech: base_total * mix_pct[tech] / 100.0 for tech in tech_keys}
    area_need = {tech: float(twh[tech]) * float(area_factors.get(tech, 1.0)) for tech in tech_keys}
    total_area_need = float(sum(area_need.values()))
    selected_fallback_techs = [
        tech for tech in tech_keys if str(factor_sources.get(tech, "missing_generic")) in {"fallback_default", "missing_generic"}
    ]

    map_df = add_map_geometry(gc4_df)
    suitability_scores = build_suitability_frame(gc4_df)
    analysis_df = map_df.merge(
        suitability_scores[["hex_id"] + [f"s_{tech}" for tech in SUITABILITY_TECHS]],
        on="hex_id",
        how="left",
    )
    allowed_clusters = [0]
    build = analysis_df[analysis_df["class_km"].isin(allowed_clusters)].copy()
    hex_area = float(build["hex_area_km2"].median())
    hex_need_total = int(math.ceil(total_area_need / max(1e-9, hex_area)))

    alloc_parts = []
    for tech in tech_keys:
        count = int(math.ceil(area_need[tech] / max(1e-9, hex_area)))
        if count <= 0:
            continue
        top = build.sort_values(f"s_{tech}", ascending=False).head(min(count, len(build))).copy()
        top["selected_for"] = tech
        alloc_parts.append(top[["hex_id", "selected_for"]])

    if alloc_parts:
        alloc_auto = pd.concat(alloc_parts, ignore_index=True)
        alloc_auto["selected"] = 1
        alloc_auto["selected_for"] = alloc_auto["selected_for"].apply(human_tech_name)
        alloc_auto = alloc_auto.groupby("hex_id", as_index=False).agg(
            selected=("selected", "max"),
            selected_for=("selected_for", "first"),
        )
    else:
        alloc_auto = pd.DataFrame({"hex_id": [], "selected": [], "selected_for": []})

    view = map_df.merge(alloc_auto, on="hex_id", how="left")
    view["selected"] = view["selected"].fillna(0).astype(int)
    view["selected_for"] = view["selected_for"].fillna("")

    sensitivity_rows = []
    for profile_id, profile in area_profiles.items():
        profile_factors = dict(profile["factors"])
        profile_sources = dict(profile["factor_sources"])
        total_km2 = float(sum(twh[tech] * float(profile_factors.get(tech, 1.0)) for tech in tech_keys))
        fallback_techs = [
            human_tech_name(tech)
            for tech in tech_keys
            if str(profile_sources.get(tech, "missing_generic")) in {"fallback_default", "missing_generic"}
        ]
        sensitivity_rows.append(
            {
                "profile_id": profile_id,
                "profile": str(profile["label"]),
                "total_km2": total_km2,
                "fallback_count": len(fallback_techs),
                "fallback_techs": ", ".join(fallback_techs),
            }
        )
    sensitivity_df = pd.DataFrame(sensitivity_rows).sort_values("total_km2").reset_index(drop=True)
    if not sensitivity_df.empty and total_area_need > 0:
        sensitivity_df["delta_vs_selected_pct"] = 100.0 * (sensitivity_df["total_km2"] / total_area_need - 1.0)
    else:
        sensitivity_df["delta_vs_selected_pct"] = 0.0

    return ExampleCase(
        scenario=scenario,
        scenario_label=scenario_display_label(scenario, scenario_descriptions),
        year=year,
        area_profile_id=area_profile_id,
        area_profile_label=str(area_profile["label"]),
        base_total_twh=base_total,
        total_area_need_km2=total_area_need,
        hex_need_total=hex_need_total,
        build_hex_count=int(len(build)),
        selected_hex_count=int(view["selected"].sum()),
        mix_pct=mix_pct,
        twh=twh,
        area_need=area_need,
        area_factor_sources=factor_sources,
        selected_fallback_techs=selected_fallback_techs,
        allowed_clusters=allowed_clusters,
        view_df=view,
        sensitivity_df=sensitivity_df,
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def svg_wrap(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">{body}</svg>'
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def map_svg(view: pd.DataFrame, title: str, subtitle: str) -> str:
    width = 980
    height = 620
    pad = 48
    lon_min = float(view["lon"].min())
    lon_max = float(view["lon"].max())
    lat_min = float(view["lat"].min())
    lat_max = float(view["lat"].max())
    lon_span = max(1e-9, lon_max - lon_min)
    lat_span = max(1e-9, lat_max - lat_min)

    def project(lon: float, lat: float) -> tuple[float, float]:
        x = pad + (lon - lon_min) / lon_span * (width - 2 * pad)
        y = height - pad - (lat - lat_min) / lat_span * (height - 2 * pad)
        return x, y

    parts = [
        '<rect width="100%" height="100%" fill="#fbfbf9" />',
        f'<text x="{pad}" y="32" font-size="22" font-family="Arial, sans-serif" fill="#222">{escape(title)}</text>',
        f'<text x="{pad}" y="54" font-size="13" font-family="Arial, sans-serif" fill="#555">{escape(subtitle)}</text>',
    ]
    for _, row in view.iterrows():
        x, y = project(float(row["lon"]), float(row["lat"]))
        color = CLUSTER_COLORS.get(int(row["class_km"]), "#d0d3d4")
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.0" fill="{color}" opacity="0.75" />')
    selected = view[view["selected"] == 1]
    for _, row in selected.iterrows():
        x, y = project(float(row["lon"]), float(row["lat"]))
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.6" fill="#c0392b" opacity="0.92" />')

    legend_x = width - 230
    legend_y = 82
    parts.append(f'<rect x="{legend_x}" y="{legend_y}" width="182" height="108" rx="10" fill="white" stroke="#dddddd" />')
    parts.append(f'<text x="{legend_x + 14}" y="{legend_y + 22}" font-size="14" font-family="Arial, sans-serif" fill="#222">Legend</text>')
    parts.append(
        f'<circle cx="{legend_x + 18}" cy="{legend_y + 44}" r="4" fill="#c0392b" /><text x="{legend_x + 32}" y="{legend_y + 48}" font-size="12" font-family="Arial, sans-serif" fill="#444">Valda hexagoner</text>'
    )
    parts.append(
        f'<circle cx="{legend_x + 18}" cy="{legend_y + 68}" r="4" fill="{CLUSTER_COLORS[0]}" /><text x="{legend_x + 32}" y="{legend_y + 72}" font-size="12" font-family="Arial, sans-serif" fill="#444">class_km 0</text>'
    )
    parts.append(
        f'<circle cx="{legend_x + 18}" cy="{legend_y + 92}" r="4" fill="{CLUSTER_COLORS[5]}" /><text x="{legend_x + 32}" y="{legend_y + 96}" font-size="12" font-family="Arial, sans-serif" fill="#444">Ovriga GC4-kluster</text>'
    )
    return svg_wrap(width, height, "".join(parts))


def line_chart_svg(
    series_by_label: dict[str, dict[int, float]],
    title: str,
    subtitle: str,
    y_label: str,
) -> str:
    width = 980
    height = 520
    left = 72
    right = 220
    top = 62
    bottom = 58
    years = sorted({year for data in series_by_label.values() for year in data.keys()})
    y_max = max((value for data in series_by_label.values() for value in data.values()), default=1.0)
    y_max = max(1.0, y_max * 1.1)

    def px(year: int) -> float:
        if len(years) == 1:
            return left
        return left + (year - years[0]) / (years[-1] - years[0]) * (width - left - right)

    def py(value: float) -> float:
        return height - bottom - value / y_max * (height - top - bottom)

    parts = [
        '<rect width="100%" height="100%" fill="#ffffff" />',
        f'<text x="{left}" y="30" font-size="22" font-family="Arial, sans-serif" fill="#222">{escape(title)}</text>',
        f'<text x="{left}" y="50" font-size="13" font-family="Arial, sans-serif" fill="#555">{escape(subtitle)}</text>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#777" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#777" stroke-width="1"/>',
    ]

    for i in range(5):
        value = y_max * i / 4.0
        y = py(value)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#ececec" stroke-width="1"/>')
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="11" font-family="Arial, sans-serif" fill="#666">{value:.0f}</text>'
        )
    for year in years:
        x = px(year)
        parts.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{height - bottom}" stroke="#f2f2f2" stroke-width="1"/>')
        parts.append(
            f'<text x="{x:.2f}" y="{height - bottom + 22}" text-anchor="middle" font-size="11" font-family="Arial, sans-serif" fill="#666">{year}</text>'
        )

    for idx, (label, data) in enumerate(series_by_label.items()):
        color = LINE_COLORS[idx % len(LINE_COLORS)]
        points = []
        for year in years:
            if year not in data:
                continue
            points.append((px(year), py(float(data[year]))))
        if not points:
            continue
        path = " ".join([f"M {points[0][0]:.2f} {points[0][1]:.2f}"] + [f"L {x:.2f} {y:.2f}" for x, y in points[1:]])
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3"/>')
        for x, y in points:
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}" />')

    legend_x = width - right + 16
    legend_y = top
    parts.append(f'<text x="{legend_x}" y="{legend_y - 12}" font-size="12" font-family="Arial, sans-serif" fill="#666">{escape(y_label)}</text>')
    for idx, label in enumerate(series_by_label.keys()):
        color = LINE_COLORS[idx % len(LINE_COLORS)]
        y = legend_y + idx * 24
        parts.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 18}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        parts.append(
            f'<text x="{legend_x + 26}" y="{y + 4}" font-size="11" font-family="Arial, sans-serif" fill="#444">{escape(label)}</text>'
        )

    return svg_wrap(width, height, "".join(parts))


def horizontal_bar_chart_svg(
    labels: list[str],
    values: list[float],
    annotations: list[str],
    title: str,
    subtitle: str,
    x_label: str,
) -> str:
    width = 980
    bar_h = 32
    gap = 12
    left = 300
    right = 80
    top = 78
    bottom = 50
    height = top + bottom + len(labels) * (bar_h + gap)
    value_max = max(values) if values else 1.0
    value_max = max(1.0, value_max * 1.1)

    def px(value: float) -> float:
        return left + value / value_max * (width - left - right)

    parts = [
        '<rect width="100%" height="100%" fill="#ffffff" />',
        f'<text x="{left}" y="32" font-size="22" font-family="Arial, sans-serif" fill="#222">{escape(title)}</text>',
        f'<text x="{left}" y="54" font-size="13" font-family="Arial, sans-serif" fill="#555">{escape(subtitle)}</text>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#777" stroke-width="1"/>',
    ]

    for i in range(5):
        value = value_max * i / 4.0
        x = px(value)
        parts.append(f'<line x1="{x:.2f}" y1="{top - 8}" x2="{x:.2f}" y2="{height - bottom}" stroke="#efefef" stroke-width="1"/>')
        parts.append(
            f'<text x="{x:.2f}" y="{height - bottom + 20}" text-anchor="middle" font-size="11" font-family="Arial, sans-serif" fill="#666">{value:.0f}</text>'
        )

    for idx, label in enumerate(labels):
        y = top + idx * (bar_h + gap)
        bar_w = px(values[idx]) - left
        color = LINE_COLORS[idx % len(LINE_COLORS)]
        parts.append(
            f'<text x="{left - 12}" y="{y + 21}" text-anchor="end" font-size="12" font-family="Arial, sans-serif" fill="#333">{escape(label)}</text>'
        )
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_w:.2f}" height="{bar_h}" rx="6" fill="{color}" opacity="0.88"/>')
        parts.append(
            f'<text x="{left + bar_w + 8:.2f}" y="{y + 21}" font-size="11" font-family="Arial, sans-serif" fill="#333">{values[idx]:.1f} km2</text>'
        )
        if annotations[idx]:
            parts.append(
                f'<text x="{left + bar_w + 92:.2f}" y="{y + 21}" font-size="11" font-family="Arial, sans-serif" fill="#777">{escape(annotations[idx])}</text>'
            )
    parts.append(
        f'<text x="{(left + width - right) / 2:.2f}" y="{height - 12}" text-anchor="middle" font-size="12" font-family="Arial, sans-serif" fill="#666">{escape(x_label)}</text>'
    )
    return svg_wrap(width, height, "".join(parts))


def build_report_text(
    example: ExampleCase,
    scenario_totals: dict[str, dict[int, float]],
    scenario_descriptions: dict[str, str],
    area_profiles: dict[str, dict[str, object]],
    generated_at: str,
    assets_dir_name: str,
) -> str:
    scenario_table_rows = []
    for scen, year_data in scenario_totals.items():
        years = ", ".join(str(year) for year in sorted(year_data.keys()))
        scenario_table_rows.append(f"| `{scen}` | {scenario_display_label(scen, scenario_descriptions)} | {years} |")
    scenario_table = "\n".join(scenario_table_rows)
    app_rows = [
        ("Valj framtidsbild", "Valjer vilket TIMES-scenario som styr total energimangd och standardmix."),
        ("Scenarioar (TIMES)", "Valjer vilket scenarioar som driver TWh, startmix och markansprak."),
        ("AreaDemand-kalla", "Valjer vilken litteraturkolumn for markintensitet som ska anvandas."),
        ("Utbyggnadszon", "Styr om bara `class_km 0` eller aven extra kluster ska kunna bebyggas."),
        ("Elmix sliders (%)", "Lat anvandaren justera mixen. Sliders ar lankade och summerar till 100 %."),
        ("Nyckeltal", "Visar scenario, ar, markansprak i km2 och uppskattat antal hexagoner som behovs."),
        ("Karta", "Visar GC4-hexagoner, klustertillhorighet och auto-/manuellt valda hexagoner."),
        ("TIMESreport output preview", "Visar kalldiagnostik och ett preview-utdrag ur TIMES-data."),
        ("AreaDemand sensitivity", "Jamfor total markyta mellan alla tillgangliga AreaDemand-profiler."),
        ("AreaDemand transparens", "Visar exakt vilka energislag som kommer fran vald kalla respektive fallback."),
        ("Urvalsmetod for hexagoner", "Valjer autoallokering eller manuell utpekning av utbyggnadshexagoner."),
        ("Baslinjer (TIMES-data)", "Visar total TWh per scenario och ar som snabb oversikt."),
    ]
    component_rows = "\n".join([f"| `{name}` | {role} |" for name, role in app_rows])

    mix_rows = []
    for tech, pct in sorted(example.mix_pct.items(), key=lambda item: item[1], reverse=True):
        source_key = str(example.area_factor_sources.get(tech, "missing_generic"))
        if source_key == "profile":
            source_label = example.area_profile_label
        elif source_key == "fallback_default":
            source_label = "Intern standard-fallback"
        elif source_key == "missing_generic":
            source_label = "Generisk fallback"
        else:
            source_label = source_key
        mix_rows.append(
            f"| {human_tech_name(tech)} | {pct:.2f} | {example.twh[tech]:.2f} | {example.area_need[tech]:.2f} | {source_label} |"
        )
    mix_table = "\n".join(mix_rows)

    fallback_text = ", ".join(human_tech_name(tech) for tech in example.selected_fallback_techs)
    if not fallback_text:
        fallback_text = "Inga fallback-rader anvands i standardexemplet."

    profile_count = len(area_profiles)

    return f"""# GC4 Energy App WIP-rapport

Autogenererad: `{generated_at}`

Detta ar en kort arbetsrapport for Streamlit-appen i `apps/gc4/app_gc4_energy.py`. Rapporten ar byggd fran samma lokala data som appen anvander, men figurerna nedan ar statiska rapportbilder och inte webblasar-screenshots.

## Appens roll

Appen ar ett arbetsverktyg for att koppla ihop:

1. TIMES-scenarier for energi per scenario och ar.
2. AreaDemand-antaganden for markintensitet i `km2/TWh`.
3. GC4-geokontext och hexagoner for att visa var olika energiscenarier kan ge landskapspaverkan.

Kort logik:

`TIMES scenario + scenarioar + elmix + AreaDemand-profil -> TWh per energislag -> km2 markbehov -> uppskattat hexbehov och karta`

## Vad som finns i appen

| Del i appen | Roll |
| --- | --- |
{component_rows}

## Data som rapporten och appen bygger pa

- TIMES-data lases fran lokal DuckDB: `data/processed/speedlocal_times.duckdb`
- AreaDemand-profiler lases fran sidcar-DuckDB: `data/processed/area_demand_profiles.duckdb`
- GC4-poang och klasser lases fran:
  - `jyp_note_book_geocontext/bornholm_points_with_context_gc4.csv`
  - `jyp_note_book_geocontext/bornholm_r8_factor_scores_gc4.csv`
- Tillgangliga AreaDemand-profiler just nu: **{profile_count}**

## Tillgangliga scenarier i appen

| Scenario-kod | Visningsnamn | Ar i appen |
| --- | --- | --- |
{scenario_table}

## Standardexempel i denna rapport

- Scenario: **{example.scenario_label}**
- Scenarioar: **{example.year}**
- AreaDemand-kalla: **{example.area_profile_label}**
- Utbyggnadszon i exemplet: **class_km {example.allowed_clusters}**
- Urvalsmetod i exemplet: **Auto**
- Total energimangd: **{example.base_total_twh:.2f} TWh**
- Utraknat markansprak: **{example.total_area_need_km2:.2f} km2**
- Beraknat hexbehov: **{example.hex_need_total}**
- Tillgangliga bygghex i zonen: **{example.build_hex_count}**
- Valda hex i autoallokering: **{example.selected_hex_count}**

## Karta

Nedan visas en statisk rapportkarta for standardexemplet. Alla GC4-hex visas som punkter, och de autoallokerade hexagonerna ar markerade i rott.

![Standardkarta]({assets_dir_name}/example_map.svg)

## Diagram

Det forsta diagrammet visar total TWh per scenario och ar. Det andra visar hur kansligt standardexemplet ar for olika AreaDemand-profiler.

![Baslinjer]({assets_dir_name}/baseline_totals.svg)

![AreaDemand sensitivity]({assets_dir_name}/area_sensitivity.svg)

## Energi- och markberakning for standardexemplet

| Energislag | Andel % | TWh | km2 | Area-faktorens kalla |
| --- | --- | --- | --- | --- |
{mix_table}

## Transparens och fallback

- Arvalet hanger nu ihop med **bade** total TWh och standardmix.
- AreaDemand ar transparent: om en vald profil saknar direkta litteraturvarden for vissa energislag visas fallback i appen.
- Standardexemplet anvander fallback for: **{fallback_text}**
- `AreaDemand sensitivity` ar viktig eftersom olika litteraturkolumner kan ge mycket olika markbehov for samma energiscenario.
- `Manuellt` urval i appen ersatter autoallokeringen och ska tolkas som ett interaktivt planeringslage, inte en optimering.

## Hur denna WIP-rapport uppdateras

Rapporten ar byggd for att kunna uppdateras regelbundet. Nar du vill uppdatera den igen kan vi kora samma generator pa nytt:

```powershell
.\\.venv\\Scripts\\python.exe script\\build_gc4_energy_wip_report.py
```

Generatorn skriver over:

- `docs/GC4_ENERGY_APP_WIP_REPORT.md`
- `docs/assets/gc4_energy_app_wip/example_map.svg`
- `docs/assets/gc4_energy_app_wip/baseline_totals.svg`
- `docs/assets/gc4_energy_app_wip/area_sensitivity.svg`

## WIP-status

Detta dokument ar avsiktligt kort och ska fungera som en levande arbetsrapport. Nar du sager till uppdaterar jag samma rapport med nytt innehall, nya figurer och ny status.
"""


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    docs_dir = root / "docs"
    assets_dir = docs_dir / "assets" / "gc4_energy_app_wip"
    ensure_dir(assets_dir)

    duckdb_path = find_duckdb(root)
    area_db_path = find_area_profile_duckdb(root)
    gc4_base = find_gc4_base(root)

    scenario_descriptions = load_scenario_metadata(duckdb_path)
    scenario_totals, base_mix_map = load_times_data(duckdb_path)
    area_profiles = load_area_profiles(area_db_path)
    gc4_df = load_gc4_data(gc4_base)
    example = build_example_case(scenario_totals, base_mix_map, area_profiles, scenario_descriptions, gc4_df)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    map_title = "GC4 + energy example"
    map_subtitle = (
        f"{example.scenario_label} | {example.year} | {example.area_profile_label} | "
        f"{example.total_area_need_km2:.1f} km2"
    )
    write_text(assets_dir / "example_map.svg", map_svg(example.view_df, map_title, map_subtitle))

    baseline_series = {
        scenario_display_label(scen, scenario_descriptions): {
            int(year): float(value) for year, value in sorted(years.items()) if int(year) in {2030, 2040, 2050}
        }
        for scen, years in sorted(scenario_totals.items())
    }
    baseline_series = {label: data for label, data in baseline_series.items() if data}
    write_text(
        assets_dir / "baseline_totals.svg",
        line_chart_svg(
            baseline_series,
            "Baslinjer fran TIMES-data",
            "Total energimangd per scenario och ar",
            "TWh",
        ),
    )

    sensitivity_df = example.sensitivity_df.copy()
    labels = sensitivity_df["profile"].astype(str).tolist()
    values = sensitivity_df["total_km2"].astype(float).tolist()
    annotations = [f"fallback: {int(v)}" for v in sensitivity_df["fallback_count"].astype(int).tolist()]
    write_text(
        assets_dir / "area_sensitivity.svg",
        horizontal_bar_chart_svg(
            labels,
            values,
            annotations,
            "AreaDemand sensitivity for standardexemplet",
            "Total markyta for samma scenario och mix under olika AreaDemand-profiler",
            "Totalt markansprak (km2)",
        ),
    )

    report_path = docs_dir / "GC4_ENERGY_APP_WIP_REPORT.md"
    report_text = build_report_text(
        example,
        scenario_totals,
        scenario_descriptions,
        area_profiles,
        generated_at,
        "assets/gc4_energy_app_wip",
    )
    write_text(report_path, report_text)
    print(f"Wrote report: {report_path}")


if __name__ == "__main__":
    main()
