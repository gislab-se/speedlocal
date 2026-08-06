from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from collections.abc import Collection

import h3
import pandas as pd

from .contracts import PopulationCountSourceContract, RooftopSolarContract
from .paths import resolve_source_path


@dataclass(frozen=True)
class RooftopSolarAccountingResult:
    population: float
    panel_area_m2_per_person: float
    panel_area_m2: float
    installed_capacity_kwp: float
    annual_yield_kwh_per_m2: float
    technical_rooftop_twh: float
    rooftop_contribution_twh: float
    gross_solar_target_twh: float
    ground_solar_twh: float
    ground_km2_per_twh: float
    gross_ground_area_need_km2: float
    ground_area_need_km2: float


def _validated_population_total(
    frame: pd.DataFrame,
    contract: PopulationCountSourceContract,
) -> float:
    total = math.fsum(float(value) for value in frame["population"])
    if not math.isclose(
        total,
        contract.expected_total,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError(
            "Rooftop-solar population total does not match its manifest: "
            f"{total:g} != {contract.expected_total:g}"
        )
    return total


def load_rooftop_population_counts(
    contract: PopulationCountSourceContract,
    analysis_domain_cell_ids: Collection[str],
    target_resolution: int | None = None,
) -> pd.DataFrame:
    """Load R8, clip at canonical R7, then derive every coarser map rollup."""

    source_path = resolve_source_path(contract.provider, contract.path)
    if not source_path.is_file():
        raise FileNotFoundError(
            f"Rooftop-solar population source is missing: {source_path}"
        )
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if digest != contract.sha256:
        raise ValueError(
            "Rooftop-solar population source checksum does not match its "
            f"manifest: {digest} != {contract.sha256}"
        )
    raw = pd.read_csv(source_path, dtype={contract.h3_id_field: "string"})
    required_columns = {
        contract.h3_id_field,
        contract.value_field,
    }
    missing_columns = required_columns - set(raw.columns)
    if missing_columns:
        raise ValueError(
            "Rooftop-solar population source is missing columns: "
            f"{sorted(missing_columns)}"
        )
    if len(raw) != contract.expected_row_count:
        raise ValueError(
            "Rooftop-solar population row count does not match its manifest: "
            f"{len(raw)} != {contract.expected_row_count}"
        )

    source = pd.DataFrame(
        {
            "hex_id": raw[contract.h3_id_field].astype("string").str.strip(),
            "population": pd.to_numeric(
                raw[contract.value_field],
                errors="coerce",
            ),
        }
    )
    invalid_values = (
        source["hex_id"].isna()
        | source["hex_id"].eq("")
        | source["population"].isna()
        | ~source["population"].map(math.isfinite)
        | source["population"].lt(0.0)
    )
    if invalid_values.any():
        raise ValueError(
            "Rooftop-solar population source contains blank ids or invalid values"
        )
    if source["hex_id"].duplicated().any():
        raise ValueError(
            "Rooftop-solar population source contains duplicate H3 ids"
        )
    invalid_h3_ids = [
        cell_id
        for cell_id in source["hex_id"].astype(str)
        if not h3.is_valid_cell(cell_id)
        or h3.get_resolution(cell_id) != contract.source_h3_resolution
    ]
    if invalid_h3_ids:
        raise ValueError(
            "Rooftop-solar population source contains invalid or wrong-resolution "
            f"H3 ids: {invalid_h3_ids[:3]}"
        )
    _validated_population_total(source, contract)

    analysis_resolution = contract.analysis_h3_resolution
    if contract.source_h3_resolution == analysis_resolution:
        analysis = source.copy()
    else:
        analysis = source.copy()
        analysis["hex_id"] = analysis["hex_id"].map(
            lambda cell_id: h3.cell_to_parent(
                str(cell_id),
                analysis_resolution,
            )
        )
        analysis = analysis.groupby("hex_id", as_index=False)["population"].sum()

    domain_ids = {str(cell_id) for cell_id in analysis_domain_cell_ids}
    if not domain_ids:
        raise ValueError(
            "Rooftop-solar analysis domain must contain canonical H3 ids"
        )
    invalid_domain_ids = [
        cell_id
        for cell_id in domain_ids
        if not h3.is_valid_cell(cell_id)
        or h3.get_resolution(cell_id) != analysis_resolution
    ]
    if invalid_domain_ids:
        raise ValueError(
            "Rooftop-solar analysis domain contains invalid or "
            f"wrong-resolution ids: {invalid_domain_ids[:3]}"
        )
    analysis = analysis[analysis["hex_id"].isin(domain_ids)].copy()

    target = analysis_resolution if target_resolution is None else target_resolution
    if isinstance(target, bool) or not isinstance(target, int):
        raise ValueError("Rooftop-solar target resolution must be an integer")
    if target < 0 or target > analysis_resolution:
        raise ValueError(
            "Rooftop-solar target resolution must be between 0 and its "
            f"canonical R{analysis_resolution} analysis resolution"
        )
    if target < analysis_resolution:
        analysis["hex_id"] = analysis["hex_id"].map(
            lambda cell_id: h3.cell_to_parent(str(cell_id), target)
        )
        analysis = analysis.groupby("hex_id", as_index=False)["population"].sum()

    expected_mapped_total = contract.expected_analysis_domain_totals.get(target)
    if expected_mapped_total is None:
        raise ValueError(
            f"Rooftop-solar manifest has no expected R{target} domain total"
        )
    mapped_total = math.fsum(
        float(value) for value in analysis["population"]
    )
    if not math.isclose(
        mapped_total,
        expected_mapped_total,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError(
            "Rooftop-solar mapped population total does not match its "
            f"R{target} manifest value: {mapped_total:g} != "
            f"{expected_mapped_total:g}"
        )
    return analysis.sort_values("hex_id").reset_index(drop=True)


def calculate_rooftop_solar_accounting(
    contract: RooftopSolarContract,
    population: float,
    panel_area_m2_per_person: float,
    gross_solar_target_twh: float,
    ground_km2_per_twh: float,
) -> RooftopSolarAccountingResult:
    """Reduce ground-solar demand without altering geographic potential."""

    population_value = float(population)
    target_twh = float(gross_solar_target_twh)
    ground_factor = float(ground_km2_per_twh)
    if not math.isfinite(population_value) or population_value < 0:
        raise ValueError("Rooftop-solar population must be finite and non-negative")
    if not math.isfinite(target_twh) or target_twh < 0:
        raise ValueError("Gross solar target must be finite and non-negative")
    if not math.isfinite(ground_factor) or ground_factor < 0:
        raise ValueError(
            "Ground-solar area factor must be finite and non-negative"
        )
    panel_area_value = contract.panel_area_m2_per_person.validate_value(
        panel_area_m2_per_person
    )
    if panel_area_value < 0.0:
        raise ValueError(
            "Rooftop-solar panel area per person must be non-negative"
        )
    annual_yield = (
        contract.annual_yield.specific_yield_kwh_per_kwp
        * contract.annual_yield.module_efficiency_stc_fraction
    )
    panel_area_m2 = population_value * panel_area_value
    installed_capacity_kwp = (
        panel_area_m2
        * contract.annual_yield.module_efficiency_stc_fraction
    )
    technical_rooftop_twh = panel_area_m2 * annual_yield / 1_000_000_000.0
    if contract.accounting.cap_at_solar_target:
        rooftop_contribution_twh = min(target_twh, technical_rooftop_twh)
    else:
        rooftop_contribution_twh = technical_rooftop_twh
    ground_solar_twh = max(0.0, target_twh - rooftop_contribution_twh)
    gross_ground_area_need_km2 = target_twh * ground_factor
    ground_area_need_km2 = ground_solar_twh * ground_factor
    return RooftopSolarAccountingResult(
        population=population_value,
        panel_area_m2_per_person=panel_area_value,
        panel_area_m2=panel_area_m2,
        installed_capacity_kwp=installed_capacity_kwp,
        annual_yield_kwh_per_m2=annual_yield,
        technical_rooftop_twh=technical_rooftop_twh,
        rooftop_contribution_twh=rooftop_contribution_twh,
        gross_solar_target_twh=target_twh,
        ground_solar_twh=ground_solar_twh,
        ground_km2_per_twh=ground_factor,
        gross_ground_area_need_km2=gross_ground_area_need_km2,
        ground_area_need_km2=ground_area_need_km2,
    )
