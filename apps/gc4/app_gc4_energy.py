import hashlib
import math
import os
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

try:
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

try:
    import h3
except Exception:  # pragma: no cover
    h3 = None


SCENARIO_TOTALS_TWH = {
    "Teknologioptimist": {2030: 190.0, 2040: 320.0, 2050: 370.0},
    "Gjennomgripende omstilling": {2030: 180.0, 2040: 225.0, 2050: 235.0},
    "Litt her og der": {2030: 170.0, 2040: 235.0, 2050: 245.0},
    "Ny hverdag": {2030: 175.0, 2040: 185.0, 2050: 182.0},
}

BASE_MIX_PCT = {
    "Teknologioptimist": {"wind": 52.0, "solar": 16.0, "nuclear": 10.0},
    "Gjennomgripende omstilling": {"wind": 42.0, "solar": 24.0, "nuclear": 7.0},
    "Litt her og der": {"wind": 34.0, "solar": 15.0, "nuclear": 5.0},
    "Ny hverdag": {"wind": 28.0, "solar": 12.0, "nuclear": 4.0},
}

DEFAULT_AREA_FACTORS = {"wind": 1.20, "solar": 2.10, "nuclear": 0.12}  # km2/TWh
DEFAULT_AREA_FACTOR_GENERIC = 1.00
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


GEOCONTEXT_APP_URL = _get_config_value("GEOCONTEXT_APP_URL")


def _find_first_col(columns: list[str], tokens: list[str]) -> str | None:
    for c in columns:
        low = c.lower()
        if any(t in low for t in tokens):
            return c
    return None


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
    return ENERGY_LABELS.get(tech, tech.replace("_", " ").title())


def _scenario_display_label(scen: str, descriptions: dict[str, str]) -> str:
    desc = str(descriptions.get(scen, "")).strip()
    if not desc or desc == scen:
        return scen
    return f"{desc} [{scen}]"


def _tech_from_text(text: str) -> str:
    t = str(text).lower().strip()
    if not t:
        return "other"
    for tech, aliases in ENERGY_ALIASES.items():
        if any(a in t for a in aliases):
            return tech
    return "other"


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
            WHERE CAST(year AS INTEGER) IN (2030, 2040, 2050)
            """
        ).df()
        return mix, "loaded duckdb view: v_energy_mix"

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
        "TRY_CAST(year AS INTEGER) IN (2030, 2040, 2050)",
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

    source_cols = [c for c in ["techgroup", "comgroup", "prc", "com"] if c in raw.columns]
    if source_cols:
        merged_source = raw[source_cols].fillna("").astype(str).agg(" ".join, axis=1)
        raw["energy_key"] = merged_source.apply(_tech_from_text)
    else:
        raw["energy_key"] = "other"

    raw["year"] = pd.to_numeric(raw["year"], errors="coerce")
    raw["value_twh"] = _as_twh(raw["value"], raw["units"])
    raw = raw.dropna(subset=["year", "value_twh"])
    if raw.empty:
        return None, f"duckdb-tabell {source_table} saknar giltiga year/value"

    raw["year"] = raw["year"].astype(int)
    mix = (
        raw.groupby(["scen", "year", "energy_key"], as_index=False)["value_twh"]
        .sum()
        .sort_values(["scen", "year", "energy_key"])
    )
    return mix, f"loaded duckdb raw: {source_table}"


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


def load_timesreport_scenarios(
    project_root: Path,
) -> tuple[dict[str, dict[int, float]] | None, dict[str, dict[int, dict[str, float]]] | None, str]:
    csv_path = _find_timesreport_csv(project_root)
    if csv_path is None:
        return None, None, "fallback: compare_timesreport.csv saknas"

    try:
        raw = pd.read_csv(csv_path)
    except Exception as exc:
        return None, None, f"fallback: kunde inte lasa TIMESreport csv ({exc})"
    if raw.empty:
        return None, None, "fallback: TIMESreport csv tom"

    raw.columns = [str(c).strip().lower() for c in raw.columns]
    need = {"scen", "year", "value", "units"}
    if not need.issubset(set(raw.columns)):
        return None, None, "fallback: TIMESreport csv saknar nodvandiga kolumner (scen/year/value/units)"

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
        return None, None, "fallback: inga rader kvar efter TIMESreport-filtrering"

    source_cols = [c for c in ["techgroup", "comgroup", "prc", "com"] if c in df.columns]
    if not source_cols:
        return None, None, "fallback: ingen energikolumn hittades i TIMESreport csv"
    merged_source = df[source_cols].fillna("").astype(str).agg(" ".join, axis=1)
    df["tech"] = merged_source.apply(_tech_from_text)
    if df.empty:
        return None, None, "fallback: inga energirader hittades i TIMESreport csv"

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year"])
    df["year"] = df["year"].astype(int)
    df = df[df["year"].isin([2030, 2040, 2050])]
    if df.empty:
        return None, None, "fallback: hittade inte ar 2030/2040/2050 i TIMESreport csv"

    df["value_twh"] = _as_twh(df["value"], df["units"])
    df = df.dropna(subset=["value_twh"])
    if df.empty:
        return None, None, "fallback: alla values blev ogiltiga efter enhetskonvertering"

    agg_all = (
        df.groupby(["scen", "year", "tech"], as_index=False)["value_twh"]
        .sum()
        .rename(columns={"value_twh": "twh"})
    )
    known = agg_all[agg_all["tech"] != "other"].copy()
    agg = known if not known.empty else agg_all
    totals = agg.groupby(["scen", "year"], as_index=False)["twh"].sum()

    scenario_totals: dict[str, dict[int, float]] = {}
    for _, r in totals.iterrows():
        scenario_totals.setdefault(str(r["scen"]), {})[int(r["year"])] = float(r["twh"])

    if not scenario_totals:
        return None, None, "fallback: kunde inte bygga scenarios fran TIMESreport csv"

    mix_rows = agg.rename(columns={"tech": "energy_key", "twh": "value_twh"})
    base_mix = _build_base_mix_by_year(mix_rows, scenario_totals)
    for scen, year_totals in scenario_totals.items():
        if scen not in base_mix:
            base_mix[scen] = {}
        for year in year_totals.keys():
            if int(year) not in base_mix[scen]:
                base_mix[scen][int(year)] = {"other": 100.0}

    return scenario_totals, base_mix, f"loaded: {csv_path}"


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
def load_gc4(base_dir: Path) -> pd.DataFrame:
    pts = pd.read_csv(base_dir / "bornholm_points_with_context_gc4.csv")
    scores = pd.read_csv(base_dir / "bornholm_r8_factor_scores_gc4.csv")
    df = pts.merge(scores[["hex_id", "class_km", "F1", "F2", "F3", "F4", "F5"]], on="hex_id", how="left")
    df["class_km"] = df["class_km"].fillna(-1).astype(int)
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
    work = df[["hex_id", "class_km", "F1", "F2", "F3", "F4", "F5"]].copy()
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
    for h in work["hex_id"].astype(str):
        try:
            lat, lon = h3.cell_to_latlng(h)
            lats.append(lat)
            lons.append(lon)
            polys.append(_hex_polygon(h))
            areas.append(float(h3.cell_area(h, unit="km^2")))
        except Exception:
            lats.append(np.nan)
            lons.append(np.nan)
            polys.append(None)
            areas.append(np.nan)
    work["lat"] = lats
    work["lon"] = lons
    work["polygon"] = polys
    work["hex_area_km2"] = areas
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
st.caption("Hexagoner + kluster + markansprak. class_km = 0 anvands som utbyggnadszon.")

app_base = Path(__file__).resolve().parent
project_root = app_base.parents[1]  # .../speedlocal_bornholm
gc4_base = project_root / "jyp_note_book_geocontext"

if not gc4_base.exists():
    st.error(f"Saknar GC4-data: {gc4_base}")
    st.stop()
if h3 is None:
    st.error("Python-paketet `h3` saknas. Installera dependencies och starta om appen.")
    st.stop()

gc4 = load_gc4(gc4_base)
map_df = build_map_frame(gc4).dropna(subset=["lat", "lon", "polygon"]).copy()
suitability_scores = build_suitability_frame(gc4)
analysis_df = map_df.merge(suitability_scores, on="hex_id", how="left")
times_totals_db, times_mix_db, times_status_db = load_timesreport_scenarios_duckdb(project_root)
times_totals_csv, times_mix_csv, times_status_csv = load_timesreport_scenarios(project_root)
times_totals = times_totals_db if times_totals_db is not None else times_totals_csv
times_mix = times_mix_db if times_mix_db is not None else times_mix_csv
times_status = times_status_db if times_totals_db is not None else times_status_csv

area_factors_db, area_status_db = load_area_factors_duckdb(project_root)
area_profiles_sidecar, area_profiles_sidecar_status = load_area_factor_profiles_sidecar(project_root)
area_profiles_xlsx, area_profiles_xlsx_status = load_area_factor_profiles_xlsx(project_root)
area_profiles_source = area_profiles_sidecar if area_profiles_sidecar else area_profiles_xlsx
area_profiles_status = area_profiles_sidecar_status if area_profiles_sidecar else area_profiles_xlsx_status

area_profile_catalog: dict[str, dict[str, object]] = {}
if area_factors_db is not None:
    area_profile_catalog["duckdb"] = {
        "label": "DuckDB area_factors",
        "factors": area_factors_db,
        "status": area_status_db,
        "factor_sources": {energy_key: "duckdb" for energy_key in area_factors_db.keys()},
        "coverage": sorted(area_factors_db.keys()),
    }
for profile_id, profile in area_profiles_source.items():
    area_profile_catalog[profile_id] = {
        "label": str(profile["label"]),
        "factors": dict(profile["factors"]),
        "status": f"{area_profiles_status}; {profile['metric']}",
        "factor_sources": dict(profile.get("factor_sources", {})),
        "coverage": list(profile["coverage"]),
    }
if not area_profile_catalog:
    st.error("Inga AreaDemand-profiler hittades. Bygg eller peka ut AreaDemand-profiler innan appen startar.")
    st.stop()

scenario_totals = times_totals if times_totals is not None else SCENARIO_TOTALS_TWH
base_mix_map = times_mix if times_mix is not None else BASE_MIX_PCT
times_preview_df, times_preview_summary, times_preview_status = load_timesreport_preview(project_root)
scenario_desc_map, scenario_source_map, scenario_meta_status = load_scenario_metadata_duckdb(project_root)

st.sidebar.header("Scenario")
scenario_options = list(scenario_totals.keys())
scenario = st.sidebar.selectbox(
    "Valj framtidsbild",
    scenario_options,
    index=0,
    format_func=lambda scen: _scenario_display_label(str(scen), scenario_desc_map),
)
scenario_label = _scenario_display_label(str(scenario), scenario_desc_map)
st.sidebar.subheader("Landskapsanalys")
if GEOCONTEXT_APP_URL:
    st.sidebar.link_button("Oppna fristaende geocontext-app", GEOCONTEXT_APP_URL, use_container_width=True)
else:
    st.sidebar.caption("Satt GEOCONTEXT_APP_URL for lank till fristaende geocontext-app.")
scenario_years = sorted([int(y) for y in scenario_totals.get(scenario, {}).keys()])
preferred_years = [y for y in [2030, 2040, 2050] if y in scenario_years]
year_options = preferred_years if preferred_years else (scenario_years if scenario_years else [2050])
default_year = 2050 if 2050 in year_options else year_options[-1]
if len(year_options) <= 1:
    year = st.sidebar.selectbox(
        "Scenarioar (TIMES)",
        options=year_options,
        index=0,
        help="Valet styr vilket ar i TIMES-scenariot som används for total TWh, basmix och markansprak.",
    )
else:
    year = st.sidebar.select_slider(
        "Scenarioar (TIMES)",
        options=year_options,
        value=default_year,
        help="Valet styr vilket ar i TIMES-scenariot som används for total TWh, basmix och markansprak.",
    )
st.sidebar.caption("Detta ar inte kalenderaret i kartan, utan vilket scenarioar fran TIMES-data som driver analysen.")
base_total = float(scenario_totals.get(scenario, {}).get(year, 0.0))
base_mix = _resolve_base_mix_for_year(base_mix_map, str(scenario), int(year))

st.sidebar.subheader("Markintensitet")
area_profile_options = list(area_profile_catalog.keys())
default_area_profile = _recommended_area_profile_id(area_profiles_source) or (
    "duckdb" if "duckdb" in area_profile_catalog else area_profile_options[0]
)
default_area_profile_index = (
    area_profile_options.index(default_area_profile) if default_area_profile in area_profile_options else 0
)
area_profile_id = st.sidebar.selectbox(
    "AreaDemand-kalla",
    options=area_profile_options,
    index=default_area_profile_index,
    format_func=lambda profile_id: str(area_profile_catalog[profile_id]["label"]),
)
st.sidebar.caption("Production density = arsproduktion per area. Power density = medeleffekt per area, omraknad till arsproduktion.")
area_profile = area_profile_catalog[area_profile_id]
area_factors = dict(area_profile["factors"])
area_status = str(area_profile["status"])
area_profile_label = str(area_profile["label"])
area_factor_sources = dict(area_profile.get("factor_sources", {}))

st.sidebar.subheader("Utbyggnadszon")
zone_mode = st.sidebar.toggle("Tillat class_km 1-7 ocksa", value=False)
all_clusters = sorted([int(v) for v in gc4["class_km"].dropna().unique().tolist() if int(v) >= 0])
extra_cluster_choices = [c for c in all_clusters if c != 0]
selected_extra_clusters = []
if zone_mode:
    selected_extra_clusters = st.sidebar.multiselect(
        "Valj extra kluster (utover class 0)",
        options=extra_cluster_choices,
        default=[],
    )

st.sidebar.subheader("Elmix sliders (%)")
tech_keys = list(base_mix.keys())
if not tech_keys:
    tech_keys = ["other"]
    base_mix = {"other": 100.0}
base_mix = _normalize_mix_100({k: float(base_mix.get(k, 0.0)) for k in tech_keys})

mix_ctx = f"{scenario}|{year}|{'|'.join(tech_keys)}"
ctx_key = "_mix_ctx"
if st.session_state.get(ctx_key) != mix_ctx:
    st.session_state[ctx_key] = mix_ctx
    for tech in tech_keys:
        st.session_state[f"mix_{tech}"] = float(base_mix.get(tech, 0.0))
slider_state_keys = [f"mix_{tech}" for tech in tech_keys]
st.sidebar.caption("Sliders ar lankade och halls ihop till totalt 100%. Startvarden kommer fran valt scenarioar.")
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
st.sidebar.caption(f"Summa elmix: {sum(mix_raw.values()):.1f}%")
twh = {tech: base_total * mix_pct[tech] / 100.0 for tech in tech_keys}
area_need = {tech: twh[tech] * float(area_factors.get(tech, DEFAULT_AREA_FACTOR_GENERIC)) for tech in tech_keys}
total_area_need = float(sum(area_need.values()))
area_factor_detail_rows: list[dict[str, float | str]] = []
selected_profile_fallback_techs: list[str] = []
selected_profile_direct_techs: list[str] = []
for tech in tech_keys:
    source_key = str(area_factor_sources.get(tech, "missing_generic"))
    if source_key in {"fallback_default", "missing_generic"}:
        selected_profile_fallback_techs.append(tech)
    else:
        selected_profile_direct_techs.append(tech)
    area_factor_detail_rows.append(
        {
            "energy_key": tech,
            "Energislag": _human_tech_name(tech),
            "km2_per_twh": float(area_factors.get(tech, DEFAULT_AREA_FACTOR_GENERIC)),
            "Kalla": _area_factor_source_label(source_key, area_profile_label),
        }
    )
area_factor_detail_df = pd.DataFrame(area_factor_detail_rows)
area_sensitivity_rows: list[dict[str, float | str]] = []
for profile_id, profile in area_profile_catalog.items():
    profile_factors = dict(profile["factors"])
    profile_sources = dict(profile.get("factor_sources", {}))
    profile_total = float(
        sum(twh[tech] * float(profile_factors.get(tech, DEFAULT_AREA_FACTOR_GENERIC)) for tech in tech_keys)
    )
    fallback_techs = [
        _human_tech_name(tech)
        for tech in tech_keys
        if str(profile_sources.get(tech, "missing_generic")) in {"fallback_default", "missing_generic"}
    ]
    area_sensitivity_rows.append(
        {
            "profile_id": profile_id,
            "profile": str(profile["label"]),
            "total_km2": profile_total,
            "fallback_count": len(fallback_techs),
            "fallback_techs": ", ".join(fallback_techs) if fallback_techs else "",
        }
    )
area_sensitivity_df = pd.DataFrame(area_sensitivity_rows).sort_values("total_km2").reset_index(drop=True)
if not area_sensitivity_df.empty:
    area_sensitivity_df["delta_vs_selected_pct"] = np.where(
        total_area_need > 0,
        100.0 * (area_sensitivity_df["total_km2"] / total_area_need - 1.0),
        0.0,
    )

allowed_clusters = [0] + selected_extra_clusters
build = analysis_df[analysis_df["class_km"].isin(allowed_clusters)].copy()
if build.empty:
    st.error("Inga hexagons hittades i vald utbyggnadszon.")
    st.stop()

hex_area = float(build["hex_area_km2"].median())
hex_need_total = int(math.ceil(total_area_need / max(1e-9, hex_area)))

selection_mode = st.sidebar.radio("Urvalsmetod for hexagoner", options=["Auto", "Manuellt"], index=0)

alloc_parts = []
for tech in tech_keys:
    tmp = build.copy()
    n = int(math.ceil(area_need[tech] / max(1e-9, hex_area)))
    if n <= 0:
        continue
    top = tmp.sort_values(f"s_{tech}", ascending=False).head(min(n, len(tmp))).copy()
    top["selected_for"] = tech
    alloc_parts.append(top[["hex_id", "selected_for"]])

if alloc_parts:
    alloc_auto = pd.concat(alloc_parts, ignore_index=True)
    alloc_auto["selected"] = 1
    alloc_auto["selected_for"] = alloc_auto["selected_for"].apply(_human_tech_name)
    alloc_auto = alloc_auto.groupby("hex_id", as_index=False).agg(
        selected=("selected", "max"),
        selected_for=("selected_for", "first"),
    )
else:
    alloc_auto = pd.DataFrame({"hex_id": [], "selected": [], "selected_for": []})

alloc = alloc_auto.copy()
manual_selected_count = 0
if selection_mode == "Manuellt":
    manual_df = build.copy()
    total_twh = max(1e-9, float(sum(twh.values())))
    weighted = pd.Series(np.zeros(len(manual_df)), index=manual_df.index)
    for tech in tech_keys:
        s_col = f"s_{tech}"
        weighted += manual_df[s_col] * (float(twh.get(tech, 0.0)) / total_twh)
    manual_df["s_total"] = weighted
    manual_df = manual_df.sort_values("s_total", ascending=False)
    manual_df["use"] = False
    manual_df.iloc[: min(hex_need_total, len(manual_df)), manual_df.columns.get_loc("use")] = True

    st.subheader("Manuellt urval av utbyggnadshexagoner")
    st.caption("Bocka i hexagoner som ska inga i urvalet. Forvalet markerar hogst rankade.")
    editor = st.data_editor(
        manual_df[["use", "hex_id", "class_km", "s_total", "hex_area_km2"]].round(4),
        use_container_width=True,
        height=260,
        hide_index=True,
        column_config={
            "use": st.column_config.CheckboxColumn("Vald"),
            "hex_id": st.column_config.TextColumn("hex_id"),
            "class_km": st.column_config.NumberColumn("class_km"),
            "s_total": st.column_config.NumberColumn("Suitability"),
            "hex_area_km2": st.column_config.NumberColumn("Hex km2"),
        },
    )
    chosen_hex = editor.loc[editor["use"] == True, "hex_id"].astype(str).tolist()
    manual_selected_count = len(chosen_hex)
    alloc = pd.DataFrame({"hex_id": chosen_hex, "selected": 1, "selected_for": "Manuellt"})

view = map_df.merge(alloc, on="hex_id", how="left")
view["selected"] = view["selected"].fillna(0).astype(int)
view["selected_for"] = view["selected_for"].fillna("")
view["cluster_color"] = view["class_km"].map(CLUSTER_COLORS).apply(lambda x: x if isinstance(x, list) else [180, 180, 180, 70])
view["line_color"] = np.where(view["class_km"] == 0, "[30,30,30,120]", "[120,120,120,80]")
view["fill_color"] = view["cluster_color"]
selected_mask = view["selected"] == 1
if selected_mask.any():
    view.loc[selected_mask, "fill_color"] = view.loc[selected_mask, "fill_color"].apply(
        lambda _: [220, 20, 60, 180]
    )

c1, c2, c3, c4 = st.columns(4)
c1.metric("Scenario", scenario_label)
c2.metric("Ar", str(year))
c3.metric("Markansprak (km2)", f"{total_area_need:.1f}")
c4.metric("Hex behov (vald zon)", f"{hex_need_total}")
st.caption(
    f"AreaDemand-profil: `{area_profile_label}`. AreaDemand-status: "
    f"`{area_status}`. Faktorer km2/TWh -> "
    + ", ".join([f"{_human_tech_name(k)}={float(area_factors.get(k, DEFAULT_AREA_FACTOR_GENERIC)):.3f}" for k in tech_keys])
)
st.info(
    "AreaDemand-transparens: "
    f"{len(selected_profile_direct_techs)} av {len(tech_keys)} aktiva energislag har direkta kallvarden i vald profil. "
    f"{len(selected_profile_fallback_techs)} anvander fallback."
)
if selected_profile_fallback_techs:
    st.warning(
        "Vald AreaDemand-profil saknar direkta kallvarden for: "
        + ", ".join(_human_tech_name(tech) for tech in selected_profile_fallback_techs)
        + ". Dessa rader anvander fallback-varden i berakningen."
    )
st.caption(f"TIMESreport-status: `{times_status}`.")
if scenario in scenario_desc_map or scenario in scenario_source_map:
    meta_parts = [f"Kod: {scenario}"]
    if scenario in scenario_source_map:
        meta_parts.append(f"Kalldata: {scenario_source_map[scenario]}")
    st.caption("DuckDB-scenariometadata: " + ". ".join(meta_parts) + f". (`{scenario_meta_status}`)")
st.caption(f"Utbyggnadszon: class_km {sorted(allowed_clusters)}. Urvalsmetod: {selection_mode}.")
with st.expander("TIMESreport output preview", expanded=False):
    st.caption(f"Preview-status: `{times_preview_status}`")
    if times_preview_summary:
        if "scen" in times_preview_summary:
            scen_labels = [
                _scenario_display_label(str(scen), scenario_desc_map) for scen in times_preview_summary["scen"]
            ]
            st.write("Scenarier:", ", ".join(scen_labels))
        if "techgroup" in times_preview_summary:
            st.write("Techgroup (unika):", ", ".join(times_preview_summary["techgroup"]))
        if "comgroup" in times_preview_summary:
            st.write("Comgroup (unika):", ", ".join(times_preview_summary["comgroup"]))
        if "units" in times_preview_summary:
            st.write("Units (unika):", ", ".join(times_preview_summary["units"]))
    if times_preview_df is not None:
        st.dataframe(times_preview_df, use_container_width=True, height=260)
with st.expander("AreaDemand sensitivity", expanded=False):
    if area_sensitivity_df.empty:
        st.caption("Inga alternativa AreaDemand-profiler hittades.")
    else:
        st.caption("Jämför totalt markanspråk för vald scenario/mix över alla tillgängliga AreaDemand-antaganden.")
        st.dataframe(
            area_sensitivity_df[["profile", "total_km2", "delta_vs_selected_pct", "fallback_count", "fallback_techs"]]
            .round(2),
            use_container_width=True,
            height=260,
        )
with st.expander("AreaDemand transparens", expanded=False):
    st.caption("Visar exakt vilka faktorer som kommer fran vald kalla och vilka som kommer fran fallback.")
    st.dataframe(
        area_factor_detail_df[["Energislag", "km2_per_twh", "Kalla"]].round(3),
        use_container_width=True,
        height=220,
    )
if selection_mode == "Manuellt":
    covered_area = manual_selected_count * hex_area
    st.caption(
        f"Manuellt valda hex: {manual_selected_count} (~{covered_area:.1f} km2) av behov {hex_need_total} hex (~{total_area_need:.1f} km2)."
    )
    if manual_selected_count < hex_need_total:
        st.warning("Manuellt urval tacker inte hela beraknat markansprak.")

mix_df = pd.DataFrame(
    [{"Energislag": _human_tech_name(k), "TWh": float(twh.get(k, 0.0)), "km2": float(area_need.get(k, 0.0))} for k in tech_keys]
)

left, right = st.columns([1.0, 2.0], gap="large")
with left:
    st.subheader("Berakning")
    st.dataframe(mix_df.round(2), use_container_width=True, height=180)
    st.caption("Toggle styr om utbyggnad ar endast class 0 eller class 0 + valda kluster.")

with right:
    st.subheader("Karta: GC4-hex + utbyggnadsval")
    tooltip = {
        "html": "<b>hex_id:</b> {hex_id}<br/><b>class_km:</b> {class_km}<br/><b>selected_for:</b> {selected_for}",
        "style": {"backgroundColor": "white", "color": "black"},
    }
    polygon_layer = pdk.Layer(
        "PolygonLayer",
        data=view,
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color=[90, 90, 90, 90],
        line_width_min_pixels=0.5,
        stroked=True,
        filled=True,
        pickable=True,
        auto_highlight=True,
    )
    center_lat = float(view["lat"].median())
    center_lon = float(view["lon"].median())
    deck = pdk.Deck(
        layers=[polygon_layer],
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=9, pitch=0),
        tooltip=tooltip,
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    )
    st.pydeck_chart(deck, use_container_width=True)

baseline_title = "### Baslinjer (TIMES-data)" if times_totals is not None else "### Baslinjer (mock, ersatts senare av TIMES-data)"
st.markdown(baseline_title)
baseline_df = (
    pd.DataFrame(scenario_totals)
    .rename_axis("year")
    .reset_index()
    .melt(id_vars="year", var_name="scenario", value_name="total_twh")
)
baseline_df["scenario"] = baseline_df["scenario"].astype(str).map(
    lambda scen: _scenario_display_label(scen, scenario_desc_map)
)
st.line_chart(baseline_df, x="year", y="total_twh", color="scenario", use_container_width=True)
