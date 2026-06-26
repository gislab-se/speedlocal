from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from statistics import median
from typing import Any

import pandas as pd

try:
    import duckdb
except Exception:  # pragma: no cover - optional runtime dependency
    duckdb = None


UNIT_TO_TWH = {
    "twh": 1.0,
    "gwh": 1e-3,
    "mwh": 1e-6,
    "pj": 1.0 / 3.6,
    "tj": 1.0 / 3600.0,
}

HOURS_PER_YEAR = 8760.0
AREA_SCENARIO_ORDER = ("low", "mid", "high")
AREA_SCENARIO_LABELS = {
    "low": "Lag",
    "mid": "Mellan",
    "high": "Hog",
}
PLANNING_SCENARIO_ORDER = ("low", "medium", "high")
PLANNING_SCENARIO_LABELS = {
    "low": "Lag",
    "medium": "Mellan",
    "high": "Hog",
}

DEFAULT_DUCKDB_CONFIG: dict[str, Any] = {
    "source_tables": ["timesreport", "timesreport_raw"],
    "description_tables": ["scen_desc"],
    "columns": {
        "scenario": ["scen", "scenario"],
        "year": ["year"],
        "value": ["value"],
        "unit": ["unit", "units"],
        "time_slice": ["all_ts", "timeslice"],
        "topic": ["topic"],
        "attribute": ["attr", "attribute"],
        "technology": ["comgroup", "techgroup", "prc", "com", "technology", "tech"],
    },
    "filters": {
        "topic": ["energy"],
        "attribute": ["f_out", "comnet"],
        "time_slice": ["annual"],
    },
    "technology_map": {
        "NRG_WIN": "wind",
        "NRG_SOL": "solar",
    },
    "scenario_description": {
        "scenario_column": ["scen", "id", "scenario"],
        "description_column": ["description", "label", "name"],
    },
}

DEFAULT_AREA_DEMAND_CONFIG: dict[str, Any] = {
    "technology_rows": {
        "wind": "Wind (onshore)",
        "solar": "Solar PV",
    },
    "times_technology_map": {
        "NRG_WIN": {
            "energy_key": "wind",
            "literature_key": "wind",
            "literature_label": "Wind (onshore)",
        },
        "NRG_SOL": {
            "energy_key": "solar",
            "literature_key": "solar",
            "literature_label": "Solar PV",
        },
    },
    "quality_rules": {
        "gwh_per_km2": {
            "wind": {"min": 0.1, "max": 500.0},
            "solar": {"min": 0.1, "max": 500.0},
        },
        "w_per_m2": {
            "wind": {"min": 0.01, "max": 100.0},
            "solar": {"min": 0.01, "max": 200.0},
        },
    },
    "scenario_factor_caps": {},
    "local_reference": {
        "section_label": "Bornholm",
        "technology_map": {
            "Landvind": "wind",
            "Solceller": "solar",
            "Havvind": "offshore_wind",
            "Halm": "straw",
            "Trae": "wood",
            "Træ": "wood",
        },
    },
}


@dataclass(frozen=True)
class EnergyModelInputs:
    times_rows: pd.DataFrame
    scenario_descriptions: dict[str, str]
    source_status: str


@dataclass(frozen=True)
class AreaDemandBundle:
    factors_by_scenario: dict[str, dict[str, float]]
    scenario_table: pd.DataFrame
    observation_table: pd.DataFrame
    warning_table: pd.DataFrame
    local_reference_table: pd.DataFrame
    references: list[str]
    rules_text: str
    source_path: str


def deep_merge(defaults: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(defaults)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _path_from_config(value: object, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = root / path
    return path


def _first_present(columns: set[str], aliases: list[str] | tuple[str, ...]) -> str | None:
    lookup = {column.lower(): column for column in columns}
    for alias in aliases:
        found = lookup.get(str(alias).lower())
        if found:
            return found
    return None


def _table_exists(con: Any, name: str) -> bool:
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


def _table_columns(con: Any, name: str) -> list[str]:
    return [
        str(row[0])
        for row in con.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
              AND lower(table_name) = lower(?)
            ORDER BY ordinal_position
            """,
            [name],
        ).fetchall()
    ]


def _as_twh(value: pd.Series, unit: pd.Series) -> pd.Series:
    factor = unit.astype(str).str.strip().str.lower().map(UNIT_TO_TWH).fillna(1.0)
    return pd.to_numeric(value, errors="coerce") * factor


def _apply_filter(frame: pd.DataFrame, column: str | None, values: list[str] | tuple[str, ...] | None) -> pd.DataFrame:
    if not column or not values or column not in frame.columns:
        return frame
    allowed = {str(value).strip().lower() for value in values}
    if not allowed:
        return frame
    return frame[frame[column].astype(str).str.strip().str.lower().isin(allowed)].copy()


def _map_energy_key(row: pd.Series, tech_columns: list[str], technology_map: dict[str, str]) -> str:
    normalized_map = {str(key).strip().upper(): str(value) for key, value in technology_map.items()}
    for column in tech_columns:
        value = str(row.get(column, "")).strip().upper()
        if value in normalized_map:
            return normalized_map[value]
    return ""


def _load_scenario_descriptions(con: Any, config: dict[str, Any]) -> dict[str, str]:
    desc_cfg = config.get("scenario_description") or {}
    for table in config.get("description_tables") or []:
        if not _table_exists(con, str(table)):
            continue
        columns = set(_table_columns(con, str(table)))
        scenario_col = _first_present(columns, desc_cfg.get("scenario_column") or ["scen", "id"])
        desc_col = _first_present(columns, desc_cfg.get("description_column") or ["description"])
        if not scenario_col or not desc_col:
            continue
        rows = con.execute(
            f"SELECT DISTINCT {scenario_col} AS scenario_id, {desc_col} AS description FROM {table}"
        ).fetchall()
        return {
            str(scenario_id): str(description)
            for scenario_id, description in rows
            if scenario_id is not None and description is not None
        }
    return {}


def load_energy_model_inputs(manifest: dict[str, Any] | None, root: Path) -> EnergyModelInputs:
    if duckdb is None:
        raise RuntimeError("Pythonpaketet duckdb saknas.")

    model_cfg = (manifest or {}).get("energy_model") or {}
    duck_cfg = deep_merge(DEFAULT_DUCKDB_CONFIG, model_cfg.get("duckdb") or {})
    db_path = _path_from_config(duck_cfg.get("path"), root)
    if db_path is None or not db_path.exists():
        raise FileNotFoundError(f"DuckDB saknas: {db_path or duck_cfg.get('path') or '-'}")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        source_table = next((str(table) for table in duck_cfg.get("source_tables") or [] if _table_exists(con, str(table))), None)
        if source_table is None:
            raise RuntimeError("DuckDB saknar konfigurerad TIMES-tabell.")

        columns = set(_table_columns(con, source_table))
        aliases = duck_cfg.get("columns") or {}
        scenario_col = _first_present(columns, aliases.get("scenario") or [])
        year_col = _first_present(columns, aliases.get("year") or [])
        value_col = _first_present(columns, aliases.get("value") or [])
        unit_col = _first_present(columns, aliases.get("unit") or [])
        topic_col = _first_present(columns, aliases.get("topic") or [])
        attr_col = _first_present(columns, aliases.get("attribute") or [])
        time_col = _first_present(columns, aliases.get("time_slice") or [])
        tech_cols = [
            column
            for alias in aliases.get("technology") or []
            for column in [_first_present(columns, [alias])]
            if column is not None
        ]

        missing = [
            label
            for label, column in {
                "scenario": scenario_col,
                "year": year_col,
                "value": value_col,
                "unit": unit_col,
            }.items()
            if column is None
        ]
        if missing:
            raise RuntimeError(f"DuckDB-tabellen saknar nodvandiga kolumner: {', '.join(missing)}")
        if not tech_cols:
            raise RuntimeError("DuckDB-tabellen saknar konfigurerade teknikkolumner.")

        select_cols = [scenario_col, year_col, value_col, unit_col, *tech_cols]
        for optional in [topic_col, attr_col, time_col]:
            if optional and optional not in select_cols:
                select_cols.append(optional)
        sql = "SELECT " + ", ".join(select_cols) + f" FROM {source_table}"
        frame = con.execute(sql).df()
        filters = duck_cfg.get("filters") or {}
        frame = _apply_filter(frame, topic_col, filters.get("topic"))
        frame = _apply_filter(frame, attr_col, filters.get("attribute"))
        frame = _apply_filter(frame, time_col, filters.get("time_slice"))

        frame["energy_key"] = frame.apply(
            lambda row: _map_energy_key(row, tech_cols, duck_cfg.get("technology_map") or {}),
            axis=1,
        )
        frame = frame[frame["energy_key"].astype(str).ne("")].copy()
        frame["scenario"] = frame[scenario_col].astype(str)
        frame["year"] = pd.to_numeric(frame[year_col], errors="coerce")
        frame["value_twh"] = _as_twh(frame[value_col], frame[unit_col])
        frame = frame.dropna(subset=["year", "value_twh"])
        frame["year"] = frame["year"].astype(int)
        descriptions = _load_scenario_descriptions(con, duck_cfg)
    finally:
        con.close()

    return EnergyModelInputs(
        times_rows=frame[["scenario", "year", "energy_key", "value_twh"]].reset_index(drop=True),
        scenario_descriptions=descriptions,
        source_status=f"DuckDB: {db_path}; table={source_table}",
    )


def build_times_summary(rows: pd.DataFrame) -> tuple[dict[str, dict[int, float]], pd.DataFrame]:
    if rows.empty:
        return {}, pd.DataFrame(columns=["scenario", "year", "energy_key", "value_twh"])
    mix = (
        rows.groupby(["scenario", "year", "energy_key"], as_index=False)["value_twh"]
        .sum()
        .sort_values(["scenario", "year", "energy_key"])
    )
    totals_frame = mix.groupby(["scenario", "year"], as_index=False)["value_twh"].sum()
    totals: dict[str, dict[int, float]] = {}
    for _, row in totals_frame.iterrows():
        totals.setdefault(str(row["scenario"]), {})[int(row["year"])] = float(row["value_twh"])
    return totals, mix.reset_index(drop=True)


def scenario_display_label(scenario_id: str, descriptions: dict[str, str]) -> str:
    description = str(descriptions.get(str(scenario_id), "")).strip()
    if not description or description == str(scenario_id):
        return str(scenario_id)
    return f"{description} [{scenario_id}]"


def planning_scenarios(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    planning_cfg = ((manifest or {}).get("energy_model") or {}).get("planning") or {}
    configured = planning_cfg.get("scenarios") or []
    if configured:
        return [dict(item) for item in configured if isinstance(item, dict) and item.get("id")]
    planning_year = int(planning_cfg.get("planning_year", 2050))
    source_scenario = str(planning_cfg.get("source_scenario", ""))
    return [
        {
            "id": "low",
            "label": "Lag",
            "source_scenario": source_scenario,
            "planning_year": planning_year,
            "energy_scale": 0.7,
            "area_demand_scenario": "low",
        },
        {
            "id": "medium",
            "label": "Mellan",
            "source_scenario": source_scenario,
            "planning_year": planning_year,
            "energy_scale": 1.0,
            "area_demand_scenario": "mid",
        },
        {
            "id": "high",
            "label": "Hog",
            "source_scenario": source_scenario,
            "planning_year": planning_year,
            "energy_scale": 1.25,
            "area_demand_scenario": "high",
        },
    ]


def planning_scenario_label(scenario: dict[str, Any]) -> str:
    label = str(scenario.get("label", "")).strip()
    if label:
        return label
    return PLANNING_SCENARIO_LABELS.get(str(scenario.get("id")), str(scenario.get("id", "-")))


def select_planning_mix(mix: pd.DataFrame, scenario: dict[str, Any]) -> pd.DataFrame:
    source_scenario = str(scenario.get("source_scenario", "")).strip()
    planning_year = int(scenario.get("planning_year", 2050))
    selected = mix.copy()
    if source_scenario:
        selected = selected[selected["scenario"].astype(str) == source_scenario].copy()
    selected = selected[pd.to_numeric(selected["year"], errors="coerce").astype("Int64") == planning_year].copy()
    energy_scale = float(scenario.get("energy_scale", 1.0) or 1.0)
    selected["value_twh"] = pd.to_numeric(selected["value_twh"], errors="coerce").fillna(0.0) * energy_scale
    selected["planning_scenario_id"] = str(scenario.get("id", ""))
    selected["planning_scenario_label"] = planning_scenario_label(scenario)
    return selected.reset_index(drop=True)


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return (
        text.replace("\u00a0", " ")
        .replace("Ãƒâ€šÃ‚Â±", "+/-")
        .replace("Ã„â€¦", "+/-")
        .replace("ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“", "-")
        .replace("Ã¢â‚¬â€œ", "-")
        .replace("Ã¢Ë†â€™", "-")
        .replace("Ã‚Â±", "+/-")
        .replace("±", "+/-")
        .replace("–", "-")
    )


def _metric_kind(metric: str) -> str | None:
    metric_low = _clean_text(metric).lower()
    if "gwh/km" in metric_low:
        return "gwh_per_km2"
    if "w/m" in metric_low:
        return "w_per_m2"
    return None


def _extract_numbers(text: str) -> list[float]:
    return [float(token) for token in re.findall(r"\d+(?:\.\d+)?", _clean_text(text).replace(",", "."))]


def _to_km2_per_twh(source_value: float, metric_kind: str) -> float | None:
    if source_value <= 0:
        return None
    if metric_kind == "gwh_per_km2":
        return 1000.0 / source_value
    if metric_kind == "w_per_m2":
        return 1000.0 / (source_value * (HOURS_PER_YEAR / 1000.0))
    return None


def _quality_rule(config: dict[str, Any], energy_key: str, metric_kind: str) -> dict[str, float]:
    rules = ((config.get("quality_rules") or {}).get(metric_kind) or {}).get(energy_key) or {}
    return {"min": float(rules.get("min", 0.0)), "max": float(rules.get("max", math.inf))}


def _quality_warning(
    config: dict[str, Any],
    energy_key: str,
    source_value: float,
    metric_kind: str,
    source_name: str,
    raw_value: object,
) -> str:
    rule = _quality_rule(config, energy_key, metric_kind)
    if source_value < rule["min"] or source_value > rule["max"]:
        return (
            f"Outlier for {energy_key}: {source_value:g} in {metric_kind} from {source_name} "
            f"(raw={_clean_text(raw_value)}). Excluded from scenario factors."
        )
    return ""


def _parse_excel_value(raw_value: object, metric_kind: str) -> dict[str, object] | None:
    text = _clean_text(raw_value)
    if not text:
        return None
    nums = _extract_numbers(text)
    if not nums:
        return None

    if "<" in text or ">" in text or "≤" in text or "≥" in text:
        mid = _to_km2_per_twh(nums[0], metric_kind)
        return {
            "used_in_scenarios": False,
            "rule": "one_sided_bound",
            "source_values": [nums[0]],
            "low_km2_per_twh": None,
            "mid_km2_per_twh": mid,
            "high_km2_per_twh": None,
            "note": "One-sided bounds are shown but not used in scenario span.",
        }

    if "+/-" in text and len(nums) >= 2:
        center = nums[0]
        spread = nums[1]
        source_values = [center]
        lower = center - spread
        upper = center + spread
        if lower > 0:
            source_values.append(lower)
        source_values.append(upper)
        converted = [value for value in (_to_km2_per_twh(value, metric_kind) for value in source_values) if value is not None]
        mid = _to_km2_per_twh(center, metric_kind)
        return {
            "used_in_scenarios": bool(converted and mid is not None),
            "rule": "plus_minus",
            "source_values": source_values,
            "low_km2_per_twh": min(converted) if converted else None,
            "mid_km2_per_twh": mid,
            "high_km2_per_twh": max(converted) if converted else None,
            "note": "",
        }

    if "-" in text and len(nums) >= 2:
        lo = min(nums[0], nums[1])
        hi = max(nums[0], nums[1])
        mid_source = math.sqrt(lo * hi) if lo > 0 and hi > 0 else (lo + hi) / 2.0
        source_values = [lo, mid_source, hi]
        converted = [value for value in (_to_km2_per_twh(value, metric_kind) for value in source_values) if value is not None]
        mid = _to_km2_per_twh(mid_source, metric_kind)
        return {
            "used_in_scenarios": bool(converted and mid is not None),
            "rule": "range",
            "source_values": source_values,
            "low_km2_per_twh": min(converted) if converted else None,
            "mid_km2_per_twh": mid,
            "high_km2_per_twh": max(converted) if converted else None,
            "note": "Mid value uses geometric mean for positive ranges.",
        }

    mid = _to_km2_per_twh(nums[0], metric_kind)
    return {
        "used_in_scenarios": mid is not None,
        "rule": "single_value",
        "source_values": [nums[0]],
        "low_km2_per_twh": mid,
        "mid_km2_per_twh": mid,
        "high_km2_per_twh": mid,
        "note": "",
    }


def _load_column_defs(df: pd.DataFrame) -> list[dict[str, object]]:
    columns = [str(value) for value in df.columns]
    metric_row = df.iloc[0]
    column_defs: list[dict[str, object]] = []
    previous_header = ""
    for idx in range(2, len(columns)):
        metric = _clean_text(metric_row.iloc[idx])
        metric_kind = _metric_kind(metric)
        if metric_kind is None:
            continue
        header = _clean_text(columns[idx])
        if header and not header.lower().startswith("unnamed:"):
            previous_header = header
        column_defs.append(
            {
                "column_idx": idx,
                "source_name": previous_header or f"AreaDemand column {idx + 1}",
                "metric": metric,
                "metric_kind": metric_kind,
            }
        )
    return column_defs


def _build_row_lookup(df: pd.DataFrame, technology_rows: dict[str, str]) -> dict[str, int]:
    expected = {key: _clean_text(label) for key, label in technology_rows.items()}
    lookup: dict[str, int] = {}
    for row_idx in range(1, len(df)):
        label = _clean_text(df.iloc[row_idx, 0])
        if not label:
            continue
        if label.lower().startswith("sources:"):
            break
        for key, expected_label in expected.items():
            if label == expected_label and key not in lookup:
                lookup[key] = row_idx
    return lookup


def _extract_references(df: pd.DataFrame) -> list[str]:
    first_col = df.iloc[:, 0].astype(str).tolist()
    source_idx = next((idx for idx, value in enumerate(first_col) if _clean_text(value).lower().startswith("sources:")), None)
    if source_idx is None:
        return []
    return [_clean_text(raw) for raw in first_col[source_idx + 1 :] if _clean_text(raw)]


def _normalize_reference_key(value: object) -> str:
    text = _clean_text(value).lower()
    text = (
        text.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("ø", "o")
        .replace("æ", "ae")
        .replace("Ã¥", "a")
        .replace("Ã¤", "a")
        .replace("Ã¶", "o")
        .replace("Ã¸", "o")
        .replace("Ã¦", "ae")
    )
    return re.sub(r"\s+", " ", text).strip()


def _local_energy_reference_table(workbook_path: Path, area_cfg: dict[str, Any]) -> pd.DataFrame:
    ref_cfg = area_cfg.get("local_reference") or {}
    section_label = str(ref_cfg.get("section_label", "")).strip()
    if not section_label:
        return pd.DataFrame(columns=["energy_key", "label", "km2_per_gwh", "km2_per_twh", "note"])

    raw = pd.read_excel(workbook_path, sheet_name=area_cfg.get("sheet_name", 0), header=None)
    first_col = raw.iloc[:, 0].map(_clean_text).tolist()
    section_idx = next((idx for idx, value in enumerate(first_col) if value == section_label), None)
    if section_idx is None:
        return pd.DataFrame(columns=["energy_key", "label", "km2_per_gwh", "km2_per_twh", "note"])

    tech_map = {
        _normalize_reference_key(label): str(energy_key)
        for label, energy_key in (ref_cfg.get("technology_map") or {}).items()
    }
    rows: list[dict[str, Any]] = []
    for idx in range(section_idx + 1, min(section_idx + 30, len(raw))):
        label = _clean_text(raw.iloc[idx, 0])
        if not label:
            continue
        key = tech_map.get(_normalize_reference_key(label))
        if not key:
            continue
        km2_per_gwh = pd.to_numeric(raw.iloc[idx, 1], errors="coerce")
        unit = _clean_text(raw.iloc[idx, 2])
        if pd.isna(km2_per_gwh) or "km2/gwh" not in unit.lower():
            continue
        km2_per_gwh_float = float(km2_per_gwh)
        rows.append(
            {
                "energy_key": key,
                "label": label,
                "km2_per_gwh": km2_per_gwh_float,
                "km2_per_twh": km2_per_gwh_float * 1000.0,
                "note": f"Lokal {section_label}-referens från nedre sektion i AreaDemand.xlsx.",
            }
        )
    return pd.DataFrame(rows)


def _cap_for_factor(
    area_cfg: dict[str, Any],
    factor_column: str,
    energy_key: str,
    times_tech: str,
    literature_key: str,
) -> float | None:
    caps = area_cfg.get("scenario_factor_caps") or {}
    column_caps = caps.get(str(factor_column)) if isinstance(caps, dict) else None
    if not isinstance(column_caps, dict):
        return None
    for key in (energy_key, times_tech, literature_key):
        if key in column_caps:
            try:
                return float(column_caps[key])
            except Exception:
                return None
    return None


def _apply_factor_caps(
    area_cfg: dict[str, Any],
    values: dict[str, float],
    energy_key: str,
    times_tech: str,
    literature_key: str,
) -> tuple[dict[str, float], list[str], dict[str, float]]:
    capped_values = dict(values)
    notes: list[str] = []
    original_values: dict[str, float] = {}
    for factor_column, value in values.items():
        cap = _cap_for_factor(area_cfg, factor_column, energy_key, times_tech, literature_key)
        if cap is None or not math.isfinite(float(value)) or float(value) <= cap:
            continue
        original_values[factor_column] = float(value)
        capped_values[factor_column] = cap
        notes.append(f"{factor_column}: {float(value):.2f} -> {cap:.2f} km2/TWh")
    return capped_values, notes, original_values


def load_area_demand_bundle(manifest: dict[str, Any] | None, root: Path) -> AreaDemandBundle:
    area_cfg = deep_merge(DEFAULT_AREA_DEMAND_CONFIG, ((manifest or {}).get("energy_model") or {}).get("area_demand") or {})
    workbook_path = _path_from_config(area_cfg.get("path"), root)
    if workbook_path is None or not workbook_path.exists():
        raise FileNotFoundError(f"AreaDemand workbook saknas: {workbook_path or area_cfg.get('path') or '-'}")

    df = pd.read_excel(workbook_path, sheet_name=area_cfg.get("sheet_name", 0))
    column_defs = _load_column_defs(df)
    row_lookup = _build_row_lookup(df, area_cfg.get("technology_rows") or {})
    references = _extract_references(df)
    local_reference_table = _local_energy_reference_table(workbook_path, area_cfg)

    scenario_rows: list[dict[str, object]] = []
    observation_rows: list[dict[str, object]] = []
    warning_rows: list[dict[str, object]] = []
    factors_by_scenario = {scenario_id: {} for scenario_id in AREA_SCENARIO_ORDER}

    for times_tech, rule in (area_cfg.get("times_technology_map") or {}).items():
        energy_key = str(rule.get("energy_key", "")).strip()
        literature_key = str(rule.get("literature_key", energy_key)).strip()
        literature_label = str(rule.get("literature_label", literature_key)).strip()
        row_idx = row_lookup.get(literature_key)
        if row_idx is None:
            scenario_rows.append(
                {
                    "times_tech": times_tech,
                    "energy_key": energy_key,
                    "workbook_row": literature_label,
                    "low_km2_per_twh": None,
                    "mid_km2_per_twh": None,
                    "high_km2_per_twh": None,
                    "status": "missing",
                }
            )
            continue

        used_observations: list[dict[str, object]] = []
        for column_def in column_defs:
            raw_value = df.iloc[row_idx, int(column_def["column_idx"])]
            parsed = _parse_excel_value(raw_value, str(column_def["metric_kind"]))
            if parsed is None:
                continue
            source_values = list(parsed.get("source_values") or [])
            warnings = [
                warning
                for warning in (
                    _quality_warning(
                        area_cfg,
                        energy_key,
                        float(source_value),
                        str(column_def["metric_kind"]),
                        str(column_def["source_name"]),
                        raw_value,
                    )
                    for source_value in source_values
                )
                if warning
            ]
            include = bool(parsed.get("used_in_scenarios")) and not warnings
            observation = {
                "times_tech": times_tech,
                "energy_key": energy_key,
                "workbook_row": literature_label,
                "source": str(column_def["source_name"]),
                "metric": str(column_def["metric"]),
                "raw_value": _clean_text(raw_value),
                "rule": str(parsed["rule"]),
                "used_in_scenarios": include,
                "low_km2_per_twh": parsed["low_km2_per_twh"],
                "mid_km2_per_twh": parsed["mid_km2_per_twh"],
                "high_km2_per_twh": parsed["high_km2_per_twh"],
                "note": "; ".join(warnings) or str(parsed["note"]),
            }
            observation_rows.append(observation)
            if warnings:
                for warning in warnings:
                    warning_rows.append(
                        {
                            "times_tech": times_tech,
                            "energy_key": energy_key,
                            "source": str(column_def["source_name"]),
                            "raw_value": _clean_text(raw_value),
                            "warning": warning,
                        }
                    )
            if include:
                used_observations.append(observation)

        if not used_observations:
            scenario_rows.append(
                {
                    "times_tech": times_tech,
                    "energy_key": energy_key,
                    "workbook_row": literature_label,
                    "low_km2_per_twh": None,
                    "mid_km2_per_twh": None,
                    "high_km2_per_twh": None,
                    "status": "unsupported",
                }
            )
            continue

        raw_values = {
            "low_km2_per_twh": min(float(row["low_km2_per_twh"]) for row in used_observations if row["low_km2_per_twh"] is not None),
            "mid_km2_per_twh": float(median(float(row["mid_km2_per_twh"]) for row in used_observations if row["mid_km2_per_twh"] is not None)),
            "high_km2_per_twh": max(float(row["high_km2_per_twh"]) for row in used_observations if row["high_km2_per_twh"] is not None),
        }
        capped_values, cap_notes, original_values = _apply_factor_caps(
            area_cfg,
            raw_values,
            energy_key,
            str(times_tech),
            literature_key,
        )
        low_value = capped_values["low_km2_per_twh"]
        mid_value = capped_values["mid_km2_per_twh"]
        high_value = capped_values["high_km2_per_twh"]
        factors_by_scenario["low"][str(times_tech)] = low_value
        factors_by_scenario["mid"][str(times_tech)] = mid_value
        factors_by_scenario["high"][str(times_tech)] = high_value
        scenario_rows.append(
            {
                "times_tech": times_tech,
                "energy_key": energy_key,
                "workbook_row": literature_label,
                "low_km2_per_twh": low_value,
                "mid_km2_per_twh": mid_value,
                "high_km2_per_twh": high_value,
                "raw_low_km2_per_twh": raw_values["low_km2_per_twh"],
                "raw_mid_km2_per_twh": raw_values["mid_km2_per_twh"],
                "raw_high_km2_per_twh": raw_values["high_km2_per_twh"],
                "cap_note": "; ".join(cap_notes),
                "status": "supported",
            }
        )
        for factor_column, original_value in original_values.items():
            warning_rows.append(
                {
                    "times_tech": times_tech,
                    "energy_key": energy_key,
                    "source": "scenario_factor_caps",
                    "raw_value": f"{original_value:.6g}",
                    "warning": (
                        f"{factor_column} capped from {original_value:.2f} to "
                        f"{capped_values[factor_column]:.2f} km2/TWh by manifest."
                    ),
                }
            )

    cap_cfg = area_cfg.get("scenario_factor_caps") or {}
    cap_text = " Manifestets scenario_factor_caps appliceras efter att scenariovardena har raknats fram." if cap_cfg else ""
    return AreaDemandBundle(
        factors_by_scenario=factors_by_scenario,
        scenario_table=pd.DataFrame(scenario_rows),
        observation_table=pd.DataFrame(observation_rows),
        warning_table=pd.DataFrame(warning_rows),
        local_reference_table=local_reference_table,
        references=references,
        rules_text=(
            "Lag = minsta observerade km2/TWh, Mellan = median av mittvarden, "
            "Hog = storsta observerade km2/TWh. Outliers enligt manifestets quality_rules exkluderas."
            + cap_text
        ),
        source_path=str(workbook_path),
    )


def calculate_area_demand(
    times_mix: pd.DataFrame,
    area_bundle: AreaDemandBundle,
    area_scenario_id: str,
    technology_to_times: dict[str, str],
) -> pd.DataFrame:
    factors = area_bundle.factors_by_scenario.get(str(area_scenario_id), {})
    rows: list[dict[str, object]] = []
    for energy_key, times_tech in technology_to_times.items():
        twh = float(times_mix.loc[times_mix["energy_key"].astype(str) == str(energy_key), "value_twh"].sum())
        factor = factors.get(str(times_tech))
        km2_per_twh = float(factor) if factor is not None else math.nan
        rows.append(
            {
                "energy_key": energy_key,
                "times_tech": times_tech,
                "twh": twh,
                "km2_per_twh": km2_per_twh,
                "area_need_km2": twh * km2_per_twh if math.isfinite(km2_per_twh) else math.nan,
            }
        )
    return pd.DataFrame(rows)


def h3_hex_area_km2(resolution: int) -> float:
    try:
        import h3

        return float(h3.average_hexagon_area(int(resolution), unit="km^2"))
    except Exception:
        fallback = {6: 36.1, 7: 5.16, 8: 0.737, 9: 0.105, 10: 0.015}
        return float(fallback.get(int(resolution), 0.1))


def allocate_wind_area_from_core_hexes(
    frame: pd.DataFrame,
    area_need_km2: float,
    hex_area_km2: float,
    min_share_pct: float = 65.0,
    avoid_hex_ids: set[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    empty = pd.DataFrame(
        columns=[
            "hex_id",
            "potential_area_share_pct",
            "potential_area_km2",
            "allocated_area_km2",
            "allocated_hex_share_pct",
            "remaining_area_after_km2",
            "allocation_phase",
            "core_score",
            "zone_size",
            "selected_rank",
            "reserved_by_other_technology",
        ]
    )
    if frame.empty or area_need_km2 <= 0 or hex_area_km2 <= 0:
        return empty, {
            "selected_area_km2": 0.0,
            "selected_potential_area_km2": 0.0,
            "selected_hex_footprint_km2": 0.0,
            "unmet_area_km2": max(0.0, float(area_need_km2)),
            "needed_hex": 0,
            "selected_hex_count": 0,
            "primary_candidate_hex": 0,
            "extension_candidate_hex": 0,
        }

    candidates = frame.copy()
    candidates["potential_area_share_pct"] = pd.to_numeric(
        candidates.get("potential_area_share_pct", pd.Series(0.0, index=candidates.index)),
        errors="coerce",
    ).fillna(0.0)
    candidates["core_score"] = pd.to_numeric(
        candidates.get("core_score", pd.Series(0.0, index=candidates.index)),
        errors="coerce",
    ).fillna(0.0)
    candidates["zone_size"] = pd.to_numeric(
        candidates.get("zone_size", pd.Series(0, index=candidates.index)),
        errors="coerce",
    ).fillna(0).astype(int)
    candidates["allocation_priority_score"] = pd.to_numeric(
        candidates.get("allocation_priority_score", candidates["core_score"]),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    candidates = candidates[candidates["potential_area_share_pct"].gt(0.0)].copy()
    if candidates.empty:
        return empty, {
            "selected_area_km2": 0.0,
            "selected_potential_area_km2": 0.0,
            "selected_hex_footprint_km2": 0.0,
            "unmet_area_km2": float(area_need_km2),
            "needed_hex": int(math.ceil(area_need_km2 / hex_area_km2)),
            "selected_hex_count": 0,
            "available_candidate_hex": 0,
            "primary_candidate_hex": 0,
            "extension_candidate_hex": 0,
        }

    candidates["allocation_phase"] = candidates["potential_area_share_pct"].ge(float(min_share_pct)).map(
        {True: "Karn-LP", False: "Kompletterande LP"}
    )
    candidates["priority_group"] = candidates["allocation_phase"].map({"Karn-LP": 0, "Kompletterande LP": 1}).fillna(1).astype(int)
    reserved_hexes = {str(hex_id) for hex_id in (avoid_hex_ids or set())}
    candidates["reserved_by_other_technology"] = candidates["hex_id"].astype(str).isin(reserved_hexes)
    if "potential_area_km2" in candidates.columns:
        candidates["potential_area_km2"] = pd.to_numeric(candidates["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    else:
        candidates["potential_area_km2"] = (
            candidates["potential_area_share_pct"].clip(lower=0.0, upper=100.0).div(100.0) * float(hex_area_km2)
        )
    candidates = candidates[candidates["potential_area_km2"].gt(0.0)].copy()
    if candidates.empty:
        return empty, {
            "selected_area_km2": 0.0,
            "selected_potential_area_km2": 0.0,
            "selected_hex_footprint_km2": 0.0,
            "unmet_area_km2": float(area_need_km2),
            "needed_hex": int(math.ceil(area_need_km2 / hex_area_km2)),
            "selected_hex_count": 0,
            "available_candidate_hex": 0,
            "primary_candidate_hex": 0,
            "extension_candidate_hex": 0,
        }
    candidates = candidates.sort_values(
        [
            "allocation_priority_score",
            "core_score",
            "potential_area_share_pct",
            "priority_group",
            "zone_size",
            "potential_area_km2",
            "reserved_by_other_technology",
            "hex_id",
        ],
        ascending=[False, False, False, True, False, False, True, True],
    ).reset_index(drop=True)

    remaining_area = float(area_need_km2)
    selected_rows: list[dict[str, object]] = []
    for rank, row in enumerate(candidates.itertuples(index=False), start=1):
        potential_area = float(getattr(row, "potential_area_km2", 0.0) or 0.0)
        allocated_area = min(potential_area, max(0.0, remaining_area))
        if allocated_area <= 0:
            break
        record = row._asdict()
        record["selected_rank"] = rank
        record["reserved_by_other_technology"] = bool(getattr(row, "reserved_by_other_technology", False))
        record["allocated_area_km2"] = allocated_area
        record["allocated_hex_share_pct"] = (allocated_area / max(float(hex_area_km2), 1e-9)) * 100.0
        remaining_area = max(0.0, remaining_area - allocated_area)
        record["remaining_area_after_km2"] = remaining_area
        selected_rows.append(record)
        if remaining_area <= 1e-9:
            break

    selected = pd.DataFrame(selected_rows) if selected_rows else empty.copy()
    selected_area = float(selected["allocated_area_km2"].sum()) if not selected.empty else 0.0
    selected_potential_area = float(selected["potential_area_km2"].sum()) if not selected.empty else 0.0
    selected_hex_footprint = float(len(selected) * float(hex_area_km2))
    needed_hex = int(math.ceil(float(area_need_km2) / max(float(hex_area_km2), 1e-9)))
    phase_counts = selected["allocation_phase"].value_counts().to_dict() if not selected.empty else {}
    return selected, {
        "selected_area_km2": selected_area,
        "selected_potential_area_km2": selected_potential_area,
        "selected_hex_footprint_km2": selected_hex_footprint,
        "unmet_area_km2": max(0.0, float(area_need_km2) - selected_area),
        "needed_hex": needed_hex,
        "selected_hex_count": int(len(selected)),
        "mean_selected_share_pct": float(selected["potential_area_share_pct"].mean()) if not selected.empty else 0.0,
        "available_candidate_hex": int(len(candidates)),
        "available_candidate_area_km2": float(candidates["potential_area_km2"].sum()),
        "primary_candidate_hex": int(candidates["allocation_phase"].eq("Karn-LP").sum()),
        "extension_candidate_hex": int(candidates["allocation_phase"].eq("Kompletterande LP").sum()),
        "selected_primary_hex": int(phase_counts.get("Karn-LP", 0)),
        "selected_extension_hex": int(phase_counts.get("Kompletterande LP", 0)),
        "reserved_candidate_hex": int(candidates["reserved_by_other_technology"].sum()),
        "selected_reserved_hex": int(selected["reserved_by_other_technology"].sum()) if not selected.empty else 0,
        "min_share_pct": float(min_share_pct),
    }
