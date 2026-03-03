import math
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


def _find_first_col(columns: list[str], tokens: list[str]) -> str | None:
    for c in columns:
        low = c.lower()
        if any(t in low for t in tokens):
            return c
    return None


def _human_tech_name(tech: str) -> str:
    return ENERGY_LABELS.get(tech, tech.replace("_", " ").title())


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

    # Final numerical cleanup to guarantee exact 100.
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


def load_timesreport_scenarios(
    project_root: Path,
) -> tuple[dict[str, dict[int, float]] | None, dict[str, dict[str, float]] | None, str]:
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

    base_mix: dict[str, dict[str, float]] = {}
    for scen, block in agg.groupby("scen"):
        y2050 = block[block["year"] == 2050]
        y_block = y2050 if not y2050.empty else block
        total = float(y_block["twh"].sum())
        if total <= 0 or y_block.empty:
            continue
        mix = {str(t): float(v) * 100.0 / total for t, v in y_block.groupby("tech")["twh"].sum().items()}
        base_mix[str(scen)] = _normalize_mix_100(mix)

    if not scenario_totals:
        return None, None, "fallback: kunde inte bygga scenarios fran TIMESreport csv"

    for scen in list(scenario_totals.keys()):
        if scen not in base_mix:
            base_mix[scen] = {"other": 100.0}

    # Ensure all scenarios share the same tech key-space for UI consistency.
    all_techs = sorted({k for v in base_mix.values() for k in v.keys()})
    for scen in list(base_mix.keys()):
        mixed = {k: float(base_mix[scen].get(k, 0.0)) for k in all_techs}
        base_mix[scen] = _normalize_mix_100(mixed)

    return scenario_totals, base_mix, f"loaded: {csv_path}"


def load_timesreport_scenarios_duckdb(
    project_root: Path,
) -> tuple[dict[str, dict[int, float]] | None, dict[str, dict[str, float]] | None, str]:
    if duckdb is None:
        return None, None, "duckdb package saknas"
    db_path = _find_duckdb(project_root)
    if db_path is None:
        return None, None, "duckdb-fil saknas"

    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        return None, None, f"duckdb kunde inte oppnas ({exc})"

    try:
        try:
            mix = con.execute(
                """
                SELECT scen, year, energy_key, value_twh
                FROM v_energy_mix
                WHERE year IN (2030, 2040, 2050)
                """
            ).df()
        except Exception:
            mix = con.execute(
                """
                SELECT
                    scen,
                    CAST(year AS INTEGER) AS year,
                    COALESCE(energy_key, 'other') AS energy_key,
                    SUM(value_twh) AS value_twh
                FROM timesreport_raw
                WHERE topic = 'energy'
                  AND attr IN ('f_out', 'comnet')
                  AND lower(timeslice) = 'annual'
                  AND year IS NOT NULL
                GROUP BY 1,2,3
                HAVING year IN (2030, 2040, 2050)
                """
            ).df()
    except Exception as exc:
        con.close()
        return None, None, f"duckdb-fraga misslyckades ({exc})"
    finally:
        try:
            con.close()
        except Exception:
            pass

    if mix.empty:
        return None, None, "duckdb gav tomt resultat"

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

    base_mix: dict[str, dict[str, float]] = {}
    for scen, block in mix.groupby("scen"):
        y2050 = block[block["year"] == 2050]
        y_block = y2050 if not y2050.empty else block
        total = float(y_block["value_twh"].sum())
        if total <= 0:
            continue
        tmp = (
            y_block.groupby("energy_key", as_index=False)["value_twh"]
            .sum()
            .set_index("energy_key")["value_twh"]
            .to_dict()
        )
        base_mix[str(scen)] = _normalize_mix_100({k: (float(v) * 100.0 / total) for k, v in tmp.items()})

    if not scenario_totals:
        return None, None, "duckdb innehaller inga scenariototaler"

    all_techs = sorted({k for v in base_mix.values() for k in v.keys()})
    for scen in list(scenario_totals.keys()):
        mix_sc = base_mix.get(scen, {"other": 100.0})
        if not all_techs:
            all_techs = ["other"]
        base_mix[scen] = _normalize_mix_100({k: float(mix_sc.get(k, 0.0)) for k in all_techs})

    return scenario_totals, base_mix, f"loaded duckdb: {db_path}"


def load_area_factors_duckdb(project_root: Path) -> tuple[dict[str, float] | None, str]:
    if duckdb is None:
        return None, "duckdb package saknas"
    db_path = _find_duckdb(project_root)
    if db_path is None:
        return None, "duckdb-fil saknas"
    try:
        con = duckdb.connect(str(db_path), read_only=True)
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
    return (out if out else None), f"loaded duckdb: {db_path}"


def load_timesreport_preview(
    project_root: Path,
) -> tuple[pd.DataFrame | None, dict[str, list[str]] | None, str]:
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
def load_gc4(base_dir: Path) -> pd.DataFrame:
    pts = pd.read_csv(base_dir / "bornholm_points_with_context_gc4.csv")
    scores = pd.read_csv(base_dir / "bornholm_r8_factor_scores_gc4.csv")
    df = pts.merge(scores[["hex_id", "class_km", "F1", "F2", "F3", "F4", "F5"]], on="hex_id", how="left")
    df["class_km"] = df["class_km"].fillna(-1).astype(int)
    return df


@st.cache_data(show_spinner=False)
def load_area_factors(project_root: Path) -> tuple[dict[str, float], str]:
    candidates = [
        project_root.parent / "eml" / "data" / "raw" / "AreaDemand.xlsx",
        project_root / "data" / "raw" / "AreaDemand.xlsx",
        Path.cwd() / "data" / "raw" / "AreaDemand.xlsx",
    ]
    xlsx_path = next((p for p in candidates if p.exists()), None)
    base = {
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
    if xlsx_path is None:
        return base, "fallback: AreaDemand.xlsx saknas"
    try:
        raw = pd.read_excel(xlsx_path, sheet_name=0)
    except Exception as exc:
        return base, f"fallback: kunde inte lasa excel ({exc})"
    if raw.empty:
        return base, "fallback: excel tom"

    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)
    tech_col = _find_first_col(cols, ["tech", "technology", "energi", "energy", "type", "slag"])
    area_col = _find_first_col(cols, ["area", "land", "km2", "km^2", "demand", "factor"])
    if tech_col is None or area_col is None:
        return base, "fallback: kunde inte identifiera teknik-/areakolumn"

    work = df[[tech_col, area_col]].copy()
    work[tech_col] = work[tech_col].astype(str).str.lower().str.strip()
    work[area_col] = pd.to_numeric(work[area_col], errors="coerce")
    work = work.dropna(subset=[area_col])

    factors = base.copy()
    for target, aliases in ENERGY_ALIASES.items():
        match = work[work[tech_col].apply(lambda v: any(a in v for a in aliases))]
        if not match.empty:
            factors[target] = float(match[area_col].iloc[0])
    return factors, "loaded"


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
times_totals_db, times_mix_db, times_status_db = load_timesreport_scenarios_duckdb(project_root)
times_totals_csv, times_mix_csv, times_status_csv = load_timesreport_scenarios(project_root)
times_totals = times_totals_db if times_totals_db is not None else times_totals_csv
times_mix = times_mix_db if times_mix_db is not None else times_mix_csv
times_status = times_status_db if times_totals_db is not None else times_status_csv

area_factors_db, area_status_db = load_area_factors_duckdb(project_root)
area_factors_csv, area_status_csv = load_area_factors(project_root)
area_factors = area_factors_db if area_factors_db is not None else area_factors_csv
area_status = area_status_db if area_factors_db is not None else area_status_csv

scenario_totals = times_totals if times_totals is not None else SCENARIO_TOTALS_TWH
base_mix_map = times_mix if times_mix is not None else BASE_MIX_PCT
times_preview_df, times_preview_summary, times_preview_status = load_timesreport_preview(project_root)

st.sidebar.header("Scenario")
scenario = st.sidebar.selectbox("Valj framtidsbild", list(scenario_totals.keys()), index=0)
scenario_years = sorted([int(y) for y in scenario_totals.get(scenario, {}).keys()])
preferred_years = [y for y in [2030, 2040, 2050] if y in scenario_years]
year_options = preferred_years if preferred_years else (scenario_years if scenario_years else [2050])
default_year = 2050 if 2050 in year_options else year_options[-1]
if len(year_options) <= 1:
    year = st.sidebar.selectbox("Ar", options=year_options, index=0)
else:
    year = st.sidebar.select_slider("Ar", options=year_options, value=default_year)
base_total = float(scenario_totals.get(scenario, {}).get(year, 0.0))
base_mix = base_mix_map.get(scenario, {"other": 100.0})

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

for tech in tech_keys:
    key = f"mix_{tech}"
    st.sidebar.slider(
        _human_tech_name(tech),
        0.0,
        100.0,
        float(st.session_state.get(key, base_mix.get(tech, 0.0))),
        0.1,
        key=key,
        on_change=_rebalance_slider,
        args=(key, [f"mix_{t}" for t in tech_keys]),
    )

mix_pct = {tech: float(st.session_state.get(f"mix_{tech}", 0.0)) for tech in tech_keys}
twh = {tech: base_total * mix_pct[tech] / 100.0 for tech in tech_keys}
area_need = {tech: twh[tech] * float(area_factors.get(tech, DEFAULT_AREA_FACTOR_GENERIC)) for tech in tech_keys}
total_area_need = float(sum(area_need.values()))

allowed_clusters = [0] + selected_extra_clusters
build = map_df[map_df["class_km"].isin(allowed_clusters)].copy()
if build.empty:
    st.error("Inga hexagons hittades i vald utbyggnadszon.")
    st.stop()

hex_area = float(build["hex_area_km2"].median())
hex_need_total = int(math.ceil(total_area_need / max(1e-9, hex_area)))

selection_mode = st.sidebar.radio("Urvalsmetod for hexagoner", options=["Auto", "Manuellt"], index=0)

alloc_parts = []
for tech in tech_keys:
    tmp = build.copy()
    tmp[f"s_{tech}"] = suitability(tmp, tech)
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
        manual_df[s_col] = suitability(manual_df, tech)
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
c1.metric("Scenario", scenario)
c2.metric("Ar", str(year))
c3.metric("Markansprak (km2)", f"{total_area_need:.1f}")
c4.metric("Hex behov (vald zon)", f"{hex_need_total}")
st.caption(
    "AreaDemand-status: "
    f"`{area_status}`. Faktorer km2/TWh -> "
    + ", ".join([f"{_human_tech_name(k)}={float(area_factors.get(k, DEFAULT_AREA_FACTOR_GENERIC)):.3f}" for k in tech_keys])
)
st.caption(f"TIMESreport-status: `{times_status}`.")
st.caption(f"Utbyggnadszon: class_km {sorted(allowed_clusters)}. Urvalsmetod: {selection_mode}.")
with st.expander("TIMESreport output preview", expanded=False):
    st.caption(f"Preview-status: `{times_preview_status}`")
    if times_preview_summary:
        if "scen" in times_preview_summary:
            st.write("Scenarier:", ", ".join(times_preview_summary["scen"]))
        if "techgroup" in times_preview_summary:
            st.write("Techgroup (unika):", ", ".join(times_preview_summary["techgroup"]))
        if "comgroup" in times_preview_summary:
            st.write("Comgroup (unika):", ", ".join(times_preview_summary["comgroup"]))
        if "units" in times_preview_summary:
            st.write("Units (unika):", ", ".join(times_preview_summary["units"]))
    if times_preview_df is not None:
        st.dataframe(times_preview_df, use_container_width=True, height=260)
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
    st.subheader("Kluster")
    cc = gc4["class_km"].value_counts().sort_index().rename_axis("class_km").reset_index(name="n_hex")
    st.bar_chart(cc, x="class_km", y="n_hex", use_container_width=True)
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
st.line_chart(baseline_df, x="year", y="total_twh", color="scenario", use_container_width=True)
