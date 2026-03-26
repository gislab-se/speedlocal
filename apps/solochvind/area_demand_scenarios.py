from __future__ import annotations

import math
import re
from pathlib import Path
from statistics import median

import pandas as pd


HOURS_PER_YEAR = 8760.0
SCENARIO_ORDER = ("low", "mid", "high")
SCENARIO_LABELS = {
    "low": "Lågt markanspråk",
    "mid": "Mellan",
    "high": "Högt markanspråk",
}

LITERATURE_ROWS = {
    "wind_onshore": "Wind (onshore)",
    "solar_pv": "Solar PV",
}

TIMES_TECH_RULES = {
    "NRG_WIN": {
        "app_energy_key": "wind",
        "literature_key": "wind_onshore",
        "literature_label": "Wind (onshore)",
        "status": "supported",
        "reason": "Vind i appen kopplas till onshore-vind i AreaDemand.xlsx.",
    },
    "NRG_SOL": {
        "app_energy_key": "solar",
        "literature_key": "solar_pv",
        "literature_label": "Solar PV",
        "status": "supported",
        "reason": "Sol i appen kopplas till Solar PV i AreaDemand.xlsx.",
    },
}


def _clean_text(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return (
        text.replace("\u00a0", " ")
        .replace("Ã‚Â±", "±")
        .replace("Ä…", "±")
        .replace("Ã¢â‚¬â€œ", "-")
        .replace("â€“", "-")
        .replace("âˆ’", "-")
        .replace("Â±", "±")
    )


def _metric_kind(metric: str) -> str | None:
    metric_low = _clean_text(metric).lower()
    if "gwh/km2" in metric_low:
        return "gwh_per_km2"
    if "w/m2" in metric_low:
        return "w_per_m2"
    return None


def _metric_label(metric: str) -> str:
    kind = _metric_kind(metric)
    if kind == "gwh_per_km2":
        return "Production density"
    if kind == "w_per_m2":
        return "Power density"
    return _clean_text(metric)


def _resolve_source_name(header: str, previous_header: str) -> str:
    clean = _clean_text(header)
    if clean and not clean.lower().startswith("unnamed:"):
        return clean
    return previous_header


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


def _parse_excel_value(raw_value: object, metric_kind: str) -> dict[str, object] | None:
    text = _clean_text(raw_value)
    if not text:
        return None

    nums = _extract_numbers(text)
    if not nums:
        return None

    if "≤" in text or "≥" in text or text.startswith("<") or text.startswith(">"):
        mid = _to_km2_per_twh(nums[0], metric_kind)
        return {
            "used_in_scenarios": False,
            "rule": "one_sided_bound",
            "source_low": None,
            "source_mid": nums[0],
            "source_high": None,
            "low_km2_per_twh": None,
            "mid_km2_per_twh": mid,
            "high_km2_per_twh": None,
            "note": "Ensidigt bounds-värde visas men används inte i scenariospannet.",
        }

    if "±" in text and len(nums) >= 2:
        center = nums[0]
        spread = nums[1]
        bounds = [center + spread]
        note = ""
        lower = center - spread
        if lower > 0:
            bounds.append(lower)
        else:
            note = "Nedre bound blev icke-positivt och togs bort före konvertering."
        converted_bounds = [value for value in (_to_km2_per_twh(bound, metric_kind) for bound in bounds) if value is not None]
        mid = _to_km2_per_twh(center, metric_kind)
        values = converted_bounds + ([mid] if mid is not None else [])
        if not values:
            return None
        return {
            "used_in_scenarios": True,
            "rule": "plus_minus",
            "source_low": lower if lower > 0 else None,
            "source_mid": center,
            "source_high": center + spread,
            "low_km2_per_twh": min(values),
            "mid_km2_per_twh": mid,
            "high_km2_per_twh": max(values),
            "note": note,
        }

    if "-" in text and len(nums) >= 2:
        lo = min(nums[0], nums[1])
        hi = max(nums[0], nums[1])
        mid_source = math.sqrt(lo * hi) if lo > 0 and hi > 0 else (lo + hi) / 2.0
        converted_bounds = [value for value in (_to_km2_per_twh(lo, metric_kind), _to_km2_per_twh(hi, metric_kind)) if value is not None]
        mid = _to_km2_per_twh(mid_source, metric_kind)
        values = converted_bounds + ([mid] if mid is not None else [])
        if not values:
            return None
        return {
            "used_in_scenarios": True,
            "rule": "range",
            "source_low": lo,
            "source_mid": mid_source,
            "source_high": hi,
            "low_km2_per_twh": min(values),
            "mid_km2_per_twh": mid,
            "high_km2_per_twh": max(values),
            "note": "Mellanvärde sattes till geometriskt medel för intervallet.",
        }

    mid = _to_km2_per_twh(nums[0], metric_kind)
    if mid is None:
        return None
    return {
        "used_in_scenarios": True,
        "rule": "single_value",
        "source_low": nums[0],
        "source_mid": nums[0],
        "source_high": nums[0],
        "low_km2_per_twh": mid,
        "mid_km2_per_twh": mid,
        "high_km2_per_twh": mid,
        "note": "",
    }


def _extract_references(df: pd.DataFrame) -> list[str]:
    first_col = df.iloc[:, 0].astype(str).tolist()
    source_idx = next((idx for idx, value in enumerate(first_col) if _clean_text(value).lower().startswith("sources:")), None)
    if source_idx is None:
        return []
    references: list[str] = []
    for raw in first_col[source_idx + 1 :]:
        clean = _clean_text(raw)
        if clean:
            references.append(clean)
    return references


def _load_column_defs(df: pd.DataFrame) -> list[dict[str, str | int]]:
    columns = [str(value) for value in df.columns]
    metric_row = df.iloc[0]
    column_defs: list[dict[str, str | int]] = []
    previous_header = ""
    for idx in range(2, len(columns)):
        metric = _clean_text(metric_row.iloc[idx])
        metric_kind = _metric_kind(metric)
        if metric_kind is None:
            continue
        source_name = _resolve_source_name(columns[idx], previous_header)
        if source_name:
            previous_header = source_name
        column_defs.append(
            {
                "column_idx": idx,
                "source_name": source_name,
                "metric": metric,
                "metric_label": _metric_label(metric),
                "metric_kind": metric_kind,
            }
        )
    return column_defs


def _build_row_lookup(df: pd.DataFrame) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for row_idx in range(1, len(df)):
        label = _clean_text(df.iloc[row_idx, 0])
        if not label:
            continue
        if label.lower().startswith("sources:"):
            break
        for key, expected_label in LITERATURE_ROWS.items():
            if label == expected_label and key not in lookup:
                lookup[key] = row_idx
    return lookup


def build_area_demand_scenario_bundle(
    workbook_path: Path,
    times_techs: list[str] | tuple[str, ...] | None = None,
) -> dict[str, object]:
    df = pd.read_excel(workbook_path, sheet_name=0)
    column_defs = _load_column_defs(df)
    row_lookup = _build_row_lookup(df)
    references = _extract_references(df)

    requested_times_techs = sorted(
        {
            str(times_tech).strip().upper()
            for times_tech in (times_techs or TIMES_TECH_RULES.keys())
            if str(times_tech).strip()
        }
    )

    scenario_rows: list[dict[str, object]] = []
    mapping_rows: list[dict[str, object]] = []
    observation_rows: list[dict[str, object]] = []
    factors_by_scenario = {scenario_id: {} for scenario_id in SCENARIO_ORDER}

    for times_tech in requested_times_techs:
        rule = TIMES_TECH_RULES.get(times_tech)
        if rule is None:
            mapping_rows.append(
                {
                    "TIMES-teknik": times_tech,
                    "Appkategori": "",
                    "Workbook-rad": "",
                    "Status": "unsupported",
                    "Motivering": "Ingen mappingregel definierad.",
                }
            )
            scenario_rows.append(
                {
                    "TIMES-teknik": times_tech,
                    "Appkategori": "",
                    "Workbook-rad": "",
                    "Lågt km2/TWh": None,
                    "Mellan km2/TWh": None,
                    "Högt km2/TWh": None,
                    "Status": "unsupported",
                    "Motivering": "Ingen mappingregel definierad.",
                }
            )
            continue

        app_energy_key = str(rule["app_energy_key"])
        literature_key = str(rule["literature_key"])
        literature_label = str(rule["literature_label"])
        reason = str(rule["reason"])

        mapping_rows.append(
            {
                "TIMES-teknik": times_tech,
                "Appkategori": app_energy_key,
                "Workbook-rad": literature_label,
                "Status": "supported",
                "Motivering": reason,
            }
        )

        row_idx = row_lookup.get(literature_key)
        if row_idx is None:
            scenario_rows.append(
                {
                    "TIMES-teknik": times_tech,
                    "Appkategori": app_energy_key,
                    "Workbook-rad": literature_label,
                    "Lågt km2/TWh": None,
                    "Mellan km2/TWh": None,
                    "Högt km2/TWh": None,
                    "Status": "unsupported",
                    "Motivering": f"Workbook-raden '{literature_label}' hittades inte.",
                }
            )
            continue

        used_observations: list[dict[str, object]] = []
        for column_def in column_defs:
            raw_value = df.iloc[row_idx, int(column_def["column_idx"])]
            parsed = _parse_excel_value(raw_value, str(column_def["metric_kind"]))
            if parsed is None:
                continue
            observation = {
                "TIMES-teknik": times_tech,
                "Appkategori": app_energy_key,
                "Workbook-rad": literature_label,
                "Källa": str(column_def["source_name"]),
                "Metrik": str(column_def["metric_label"]),
                "Excel-värde": _clean_text(raw_value),
                "Scenario-använd": bool(parsed["used_in_scenarios"]),
                "Tolkningsregel": str(parsed["rule"]),
                "Lågt km2/TWh": parsed["low_km2_per_twh"],
                "Mellan km2/TWh": parsed["mid_km2_per_twh"],
                "Högt km2/TWh": parsed["high_km2_per_twh"],
                "Notering": str(parsed["note"]),
            }
            observation_rows.append(observation)
            if bool(parsed["used_in_scenarios"]):
                used_observations.append(observation)

        if not used_observations:
            scenario_rows.append(
                {
                    "TIMES-teknik": times_tech,
                    "Appkategori": app_energy_key,
                    "Workbook-rad": literature_label,
                    "Lågt km2/TWh": None,
                    "Mellan km2/TWh": None,
                    "Högt km2/TWh": None,
                    "Status": "unsupported",
                    "Motivering": f"Inga kompatibla workbook-värden hittades för '{literature_label}'.",
                }
            )
            continue

        low_value = min(float(row["Lågt km2/TWh"]) for row in used_observations if row["Lågt km2/TWh"] is not None)
        mid_value = float(median(float(row["Mellan km2/TWh"]) for row in used_observations if row["Mellan km2/TWh"] is not None))
        high_value = max(float(row["Högt km2/TWh"]) for row in used_observations if row["Högt km2/TWh"] is not None)

        factors_by_scenario["low"][times_tech] = low_value
        factors_by_scenario["mid"][times_tech] = mid_value
        factors_by_scenario["high"][times_tech] = high_value
        scenario_rows.append(
            {
                "TIMES-teknik": times_tech,
                "Appkategori": app_energy_key,
                "Workbook-rad": literature_label,
                "Lågt km2/TWh": low_value,
                "Mellan km2/TWh": mid_value,
                "Högt km2/TWh": high_value,
                "Status": "supported",
                "Motivering": reason,
            }
        )

    return {
        "workbook_path": str(workbook_path),
        "scenario_order": list(SCENARIO_ORDER),
        "scenario_labels": dict(SCENARIO_LABELS),
        "factors_by_scenario": factors_by_scenario,
        "scenario_table": pd.DataFrame(scenario_rows),
        "mapping_table": pd.DataFrame(mapping_rows),
        "observation_table": pd.DataFrame(observation_rows),
        "references": references,
        "rules_text": (
            "Lågt = minsta observerade km2/TWh, Mellan = median av mittvärden, "
            "Högt = största observerade km2/TWh. Intervall och plus/minus tolkas före konvertering till km2/TWh."
        ),
    }
