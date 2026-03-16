from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import pandas as pd

try:
    import duckdb
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "duckdb package saknas. Installera forst: .\\.venv\\Scripts\\python -m pip install duckdb"
    ) from exc


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
HOURS_PER_YEAR = 8760.0


def find_area_xlsx(root: Path) -> Path | None:
    candidates = [
        root.parent / "eml" / "data" / "raw" / "AreaDemand.xlsx",
        root / "data" / "raw" / "AreaDemand.xlsx",
        Path.cwd() / "data" / "raw" / "AreaDemand.xlsx",
    ]
    return next((p for p in candidates if p.exists()), None)


def area_metric_kind(metric: str) -> str | None:
    metric_low = str(metric).lower()
    if "gwh/km2" in metric_low:
        return "gwh_per_km2"
    if "w/m2" in metric_low:
        return "w_per_m2"
    return None


def area_metric_label(metric: str) -> str:
    kind = area_metric_kind(metric)
    if kind == "gwh_per_km2":
        return "Production density"
    if kind == "w_per_m2":
        return "Power density"
    return str(metric).strip()


def area_profile_source_name(header: str, previous_header: str) -> str:
    clean = str(header).strip()
    if clean and not clean.lower().startswith("unnamed:"):
        return clean
    return previous_header.strip()


def area_tech_from_text(text: str) -> str | None:
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


def extract_area_numbers(text: str) -> list[float]:
    cleaned = str(text).replace(",", ".")
    return [float(token) for token in re.findall(r"\d+(?:\.\d+)?", cleaned)]


def representative_area_value(value: object) -> float | None:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    nums = extract_area_numbers(text)
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


def area_value_to_km2_per_twh(value: object, metric: str) -> float | None:
    rep = representative_area_value(value)
    if rep is None or rep <= 0:
        return None
    kind = area_metric_kind(metric)
    if kind == "gwh_per_km2":
        return 1000.0 / rep
    if kind == "w_per_m2":
        return 1000.0 / (rep * (HOURS_PER_YEAR / 1000.0))
    return None


def load_profiles(area_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(area_path, sheet_name=0)
    if raw.empty or raw.shape[0] < 2 or raw.shape[1] < 3:
        raise ValueError("AreaDemand.xlsx saknar profiler")

    columns = [str(c).strip() for c in raw.columns]
    metric_row = raw.iloc[0]
    data = raw.iloc[1:].copy()
    profiles_rows: list[dict[str, object]] = []
    factors_rows: list[dict[str, object]] = []
    previous_source = ""

    for idx in range(2, len(columns)):
        metric = str(metric_row.iloc[idx]).strip()
        if area_metric_kind(metric) is None:
            continue

        source_name = area_profile_source_name(columns[idx], previous_source)
        if source_name:
            previous_source = source_name
        label = source_name or f"AreaDemand column {idx + 1}"
        label = f"{label} [{area_metric_label(metric)}]"
        profile_id = f"xlsx_{idx}"

        profiles_rows.append(
            {
                "profile_id": profile_id,
                "sort_order": idx,
                "label": label,
                "source_name": source_name or f"AreaDemand column {idx + 1}",
                "metric": metric,
                "source_path": str(area_path),
            }
        )

        factors = DEFAULT_AREA_FACTORS.copy()
        factor_sources = {energy_key: "fallback_default" for energy_key in factors}
        seen: set[str] = set()
        for _, row in data.iterrows():
            tech = area_tech_from_text(row.iloc[0])
            if tech is None:
                first_cell = str(row.iloc[0]).strip().lower()
                if first_cell.startswith("sources:"):
                    break
                continue
            if tech in seen:
                continue
            km2_per_twh = area_value_to_km2_per_twh(row.iloc[idx], metric)
            if km2_per_twh is None:
                continue
            factors[tech] = float(km2_per_twh)
            factor_sources[tech] = "profile"
            seen.add(tech)

        for energy_key, km2_per_twh in factors.items():
            factors_rows.append(
                {
                    "profile_id": profile_id,
                    "energy_key": energy_key,
                    "km2_per_twh": float(km2_per_twh),
                    "value_source": factor_sources.get(energy_key, "fallback_default"),
                }
            )

    profiles_df = pd.DataFrame(profiles_rows)
    factors_df = pd.DataFrame(factors_rows)
    if profiles_df.empty or factors_df.empty:
        raise ValueError("AreaDemand.xlsx gav inga profiler")
    return profiles_df, factors_df


def build_duckdb(area_path: Path, db_path: Path) -> None:
    profiles_df, factors_df = load_profiles(area_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("DROP TABLE IF EXISTS area_profiles")
        con.execute("DROP TABLE IF EXISTS area_factor_profiles")

        con.register("profiles_df", profiles_df)
        con.execute("CREATE TABLE area_profiles AS SELECT * FROM profiles_df")

        con.register("factors_df", factors_df)
        con.execute("CREATE TABLE area_factor_profiles AS SELECT * FROM factors_df")
    finally:
        con.close()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build local sidecar DuckDB for AreaDemand profiles")
    parser.add_argument("--area", type=Path, default=find_area_xlsx(root))
    parser.add_argument(
        "--db",
        type=Path,
        default=root / "data" / "processed" / "area_demand_profiles.duckdb",
    )
    args = parser.parse_args()

    if args.area is None or not args.area.exists():
        raise SystemExit("AreaDemand.xlsx hittades inte. Ange --area explicit.")

    build_duckdb(args.area, args.db)
    print(f"Built AreaDemand DuckDB: {args.db}")


if __name__ == "__main__":
    main()
