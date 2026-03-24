from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd

try:
    import duckdb
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "duckdb package saknas. Installera först: .\\.venv\\Scripts\\python -m pip install duckdb"
    ) from exc


UNIT_TO_TWH = {
    "twh": 1.0,
    "gwh": 1e-3,
    "mwh": 1e-6,
    "pj": 1.0 / 3.6,
    "tj": 1.0 / 3600.0,
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
AREA_TECH_ALIASES = {
    "wind": ["wind"],
    "solar": ["solar"],
    "hydro": ["hydro", "water", "run-of-river", "reservoir"],
    "nuclear": ["nuclear", "smr"],
    "bio": ["bio", "biomass"],
    "coal": ["coal"],
    "gas": ["gas"],
    "oil": ["oil"],
}


def normalize_text(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.strip()


def energy_tokens(*values: object) -> list[str]:
    tokens: list[str] = []
    for value in values:
        low = str(value).lower().strip()
        if not low or low == "nan":
            continue
        tokens.extend(re.findall(r"[a-z0-9]+", low))
    return tokens


def tech_from_fields(
    techgroup: object = "",
    comgroup: object = "",
    prc: object = "",
    com: object = "",
) -> str:
    comgroup_key = str(comgroup).lower().strip()
    if comgroup_key in ENERGY_COMGROUP_MAP:
        return ENERGY_COMGROUP_MAP[comgroup_key]

    techgroup_key = str(techgroup).lower().strip()
    if techgroup_key in ENERGY_TECHGROUP_MAP:
        return ENERGY_TECHGROUP_MAP[techgroup_key]

    tokens = energy_tokens(prc, com, techgroup, comgroup)
    for token in tokens:
        if token in ENERGY_EXACT_TOKEN_MAP:
            return ENERGY_EXACT_TOKEN_MAP[token]
    for token in tokens:
        for prefix, tech in ENERGY_PREFIX_RULES:
            if token.startswith(prefix):
                return tech
    for token in tokens:
        for suffix, tech in ENERGY_SUFFIX_RULES:
            if token.endswith(suffix):
                return tech
    return "other"


def read_timesreport_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = {"scen", "year", "value", "units"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"TIMESreport CSV saknar kolumner: {sorted(missing)}")

    if "regionfrom" in df.columns and "regfrom" not in df.columns:
        df["regfrom"] = df["regionfrom"]
    if "regionto" in df.columns and "regto" not in df.columns:
        df["regto"] = df["regionto"]

    if any(c in df.columns for c in ["techgroup", "comgroup", "prc", "com"]):
        df["energy_key"] = df.apply(
            lambda row: tech_from_fields(
                techgroup=row.get("techgroup", ""),
                comgroup=row.get("comgroup", ""),
                prc=row.get("prc", ""),
                com=row.get("com", ""),
            ),
            axis=1,
        )
    else:
        df["energy_key"] = "other"

    units = normalize_text(df["units"])
    factor = units.map(UNIT_TO_TWH).fillna(1.0)
    df["value_twh"] = pd.to_numeric(df["value"], errors="coerce") * factor
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


def find_first_col(columns: list[str], tokens: list[str]) -> str | None:
    for c in columns:
        low = c.lower()
        if any(t in low for t in tokens):
            return c
    return None


def read_area_factors(area_path: Path) -> pd.DataFrame:
    base = pd.DataFrame({"energy_key": list(DEFAULT_AREA_FACTORS.keys()), "km2_per_twh": list(DEFAULT_AREA_FACTORS.values())})
    if not area_path.exists():
        return base

    raw = pd.read_excel(area_path, sheet_name=0)
    if raw.empty:
        return base
    raw.columns = [str(c).strip() for c in raw.columns]
    cols = list(raw.columns)
    tech_col = find_first_col(cols, ["tech", "technology", "energi", "energy", "type", "slag"])
    area_col = find_first_col(cols, ["area", "land", "km2", "km^2", "demand", "factor", "gwh/km2", "w/m2"])
    if tech_col is None or area_col is None:
        return base

    work = raw[[tech_col, area_col]].copy()
    work[tech_col] = work[tech_col].astype(str).str.strip()
    work[area_col] = pd.to_numeric(work[area_col], errors="coerce")
    work = work.dropna(subset=[area_col])
    if work.empty:
        return base

    factors = DEFAULT_AREA_FACTORS.copy()
    low = work[tech_col].astype(str).str.lower()
    for tech, aliases in AREA_TECH_ALIASES.items():
        mask = low.apply(lambda v: any(a in v for a in aliases))
        if mask.any():
            # Heuristic: if source likely GWh/km2, convert to km2/TWh via 1000/x.
            val = float(work.loc[mask, area_col].iloc[0])
            if val > 15:  # high production density
                factors[tech] = 1000.0 / val
            else:
                factors[tech] = val

    return pd.DataFrame({"energy_key": list(factors.keys()), "km2_per_twh": list(factors.values())})


def build_duckdb(csv_path: Path, area_path: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    times = read_timesreport_csv(csv_path)
    area = read_area_factors(area_path)

    con = duckdb.connect(str(db_path))
    try:
        con.execute("DROP TABLE IF EXISTS timesreport_raw")
        con.execute("DROP TABLE IF EXISTS area_factors")
        con.execute("DROP VIEW IF EXISTS v_energy_mix")

        con.register("times_df", times)
        con.execute("CREATE TABLE timesreport_raw AS SELECT * FROM times_df")

        con.register("area_df", area)
        con.execute("CREATE TABLE area_factors AS SELECT * FROM area_df")

        con.execute(
            """
            CREATE VIEW v_energy_mix AS
            SELECT
              scen,
              CAST(year AS INTEGER) AS year,
              energy_key,
              SUM(value_twh) AS value_twh
            FROM timesreport_raw
            WHERE topic = 'energy'
              AND attr IN ('f_out', 'comnet')
              AND lower(timeslice) = 'annual'
              AND year IS NOT NULL
            GROUP BY 1,2,3
            """
        )

        con.execute(
            """
            CREATE VIEW v_energy_totals AS
            SELECT scen, year, SUM(value_twh) AS total_twh
            FROM v_energy_mix
            GROUP BY 1,2
            """
        )
    finally:
        con.close()


def find_default_csv(root: Path) -> Path | None:
    candidates = [
        root / "external" / "DemoS_012_timesreport" / "TIMESreport" / "compare_timesreport.csv",
        root / "external" / "DemoS_012_timesreport" / "compare_timesreport.csv",
        root / "data" / "external" / "timesreport" / "compare_timesreport.csv",
    ]
    return next((p for p in candidates if p.exists()), None)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build DuckDB from TIMESreport CSV + AreaDemand Excel")
    parser.add_argument("--csv", type=Path, default=find_default_csv(root))
    parser.add_argument("--area", type=Path, default=root / "data" / "raw" / "AreaDemand.xlsx")
    parser.add_argument("--db", type=Path, default=root / "data" / "processed" / "speedlocal_times.duckdb")
    args = parser.parse_args()

    if args.csv is None or not args.csv.exists():
        raise SystemExit("compare_timesreport.csv hittades inte. Ange --csv explicit.")

    build_duckdb(args.csv, args.area, args.db)
    print(f"Built DuckDB: {args.db}")


if __name__ == "__main__":
    main()
