import math
from pathlib import Path

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

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
TECH_ALIASES = {
    "wind": ["wind", "vind", "onshore", "offshore"],
    "solar": ["solar", "pv", "sol"],
    "nuclear": ["nuclear", "karn", "karnkraft", "atom"],
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
    if xlsx_path is None:
        return DEFAULT_AREA_FACTORS, "fallback: AreaDemand.xlsx saknas"
    try:
        raw = pd.read_excel(xlsx_path, sheet_name=0)
    except Exception as exc:
        return DEFAULT_AREA_FACTORS, f"fallback: kunde inte lasa excel ({exc})"
    if raw.empty:
        return DEFAULT_AREA_FACTORS, "fallback: excel tom"

    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)
    tech_col = _find_first_col(cols, ["tech", "technology", "energi", "energy", "type", "slag"])
    area_col = _find_first_col(cols, ["area", "land", "km2", "km^2", "demand", "factor"])
    if tech_col is None or area_col is None:
        return DEFAULT_AREA_FACTORS, "fallback: kunde inte identifiera teknik-/areakolumn"

    work = df[[tech_col, area_col]].copy()
    work[tech_col] = work[tech_col].astype(str).str.lower().str.strip()
    work[area_col] = pd.to_numeric(work[area_col], errors="coerce")
    work = work.dropna(subset=[area_col])

    factors = DEFAULT_AREA_FACTORS.copy()
    for target, aliases in TECH_ALIASES.items():
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
    return 0.60 * f5 + 0.25 * f1 + 0.15 * (1.0 - f2)  # nuclear


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
area_factors, area_status = load_area_factors(project_root)

st.sidebar.header("Scenario")
scenario = st.sidebar.selectbox("Valj framtidsbild", list(SCENARIO_TOTALS_TWH.keys()), index=0)
year = st.sidebar.select_slider("Ar", options=[2030, 2040, 2050], value=2050)
base_total = SCENARIO_TOTALS_TWH[scenario][year]
base_mix = BASE_MIX_PCT[scenario]

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
wind_pct = st.sidebar.slider("Vind", 0.0, 100.0, float(base_mix["wind"]), 1.0)
solar_pct = st.sidebar.slider("Sol", 0.0, 100.0, float(base_mix["solar"]), 1.0)
nuclear_pct = st.sidebar.slider("Karnkraft", 0.0, 100.0, float(base_mix["nuclear"]), 1.0)
sum_pct = wind_pct + solar_pct + nuclear_pct
if sum_pct > 100.0:
    st.error("Summan av vind + sol + karnkraft kan inte vara over 100%.")
    st.stop()

twh = {
    "wind": base_total * wind_pct / 100.0,
    "solar": base_total * solar_pct / 100.0,
    "nuclear": base_total * nuclear_pct / 100.0,
}
area_need = {k: twh[k] * area_factors[k] for k in ["wind", "solar", "nuclear"]}
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
for tech in ["wind", "solar", "nuclear"]:
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
    alloc_auto["selected_for"] = alloc_auto["selected_for"].map(
        {"wind": "Vind", "solar": "Sol", "nuclear": "Karnkraft"}
    )
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
    manual_df["s_wind"] = suitability(manual_df, "wind")
    manual_df["s_solar"] = suitability(manual_df, "solar")
    manual_df["s_nuclear"] = suitability(manual_df, "nuclear")
    total_twh = max(1e-9, twh["wind"] + twh["solar"] + twh["nuclear"])
    manual_df["s_total"] = (
        manual_df["s_wind"] * (twh["wind"] / total_twh)
        + manual_df["s_solar"] * (twh["solar"] / total_twh)
        + manual_df["s_nuclear"] * (twh["nuclear"] / total_twh)
    )
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
    f"AreaDemand-status: `{area_status}`. Faktorer km2/TWh -> "
    f"vind={area_factors['wind']:.3f}, sol={area_factors['solar']:.3f}, karnkraft={area_factors['nuclear']:.3f}"
)
st.caption(f"Utbyggnadszon: class_km {sorted(allowed_clusters)}. Urvalsmetod: {selection_mode}.")
if selection_mode == "Manuellt":
    covered_area = manual_selected_count * hex_area
    st.caption(
        f"Manuellt valda hex: {manual_selected_count} (~{covered_area:.1f} km2) av behov {hex_need_total} hex (~{total_area_need:.1f} km2)."
    )
    if manual_selected_count < hex_need_total:
        st.warning("Manuellt urval tacker inte hela beraknat markansprak.")

mix_df = pd.DataFrame(
    [
        {"Energislag": "Vind", "TWh": twh["wind"], "km2": area_need["wind"]},
        {"Energislag": "Sol", "TWh": twh["solar"], "km2": area_need["solar"]},
        {"Energislag": "Karnkraft", "TWh": twh["nuclear"], "km2": area_need["nuclear"]},
    ]
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

st.markdown("### Baslinjer (mock, ersatts senare av TIMES-data)")
baseline_df = (
    pd.DataFrame(SCENARIO_TOTALS_TWH)
    .rename_axis("year")
    .reset_index()
    .melt(id_vars="year", var_name="scenario", value_name="total_twh")
)
st.line_chart(baseline_df, x="year", y="total_twh", color="scenario", use_container_width=True)
