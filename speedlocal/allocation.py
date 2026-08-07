from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping


FLOAT_TOLERANCE = 1e-9


def _identifier(value: str, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} must be non-blank")
    return normalized


def _nonnegative(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return number


@dataclass(frozen=True)
class TechnologyEnergy:
    technology: str
    twh: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "technology",
            _identifier(self.technology, "Technology id"),
        )
        object.__setattr__(self, "twh", _nonnegative(self.twh, "Energy TWh"))


@dataclass(frozen=True)
class EnergyMixResult:
    energies: tuple[TechnologyEnergy, ...]
    rebalanced_technologies: tuple[str, ...]
    rebalanced_total_twh: float

    def __post_init__(self) -> None:
        technologies = tuple(item.technology for item in self.energies)
        if len(set(technologies)) != len(technologies):
            raise ValueError("Energy mix technologies must be unique")
        if len(set(self.rebalanced_technologies)) != len(
            self.rebalanced_technologies
        ):
            raise ValueError("Rebalanced technologies must be unique")
        if not set(self.rebalanced_technologies).issubset(technologies):
            raise ValueError("Every rebalanced technology must exist in the result")
        declared_total = _nonnegative(
            self.rebalanced_total_twh,
            "Rebalanced total TWh",
        )
        actual_total = math.fsum(
            item.twh
            for item in self.energies
            if item.technology in self.rebalanced_technologies
        )
        if not math.isclose(
            actual_total,
            declared_total,
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        ):
            raise ValueError("Rebalanced energy does not conserve its declared total")

    def energy_twh(self, technology: str) -> float:
        requested = _identifier(technology, "Technology id")
        return next(
            (item.twh for item in self.energies if item.technology == requested),
            0.0,
        )


@dataclass(frozen=True)
class TechnologyDemand:
    technology: str
    twh: float
    km2_per_twh: float
    area_need_km2: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "technology",
            _identifier(self.technology, "Technology id"),
        )
        energy = _nonnegative(self.twh, "Demand energy TWh")
        factor = float(self.km2_per_twh)
        if not math.isfinite(factor) or factor <= 0.0:
            raise ValueError("Demand km2/TWh must be finite and positive")
        area = _nonnegative(self.area_need_km2, "Demand area km2")
        if not math.isclose(
            area,
            energy * factor,
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        ):
            raise ValueError("Technology demand area must equal TWh times km2/TWh")


@dataclass(frozen=True)
class AllocationCandidate:
    cell_id: str
    eligible_area_km2: float
    potential_area_km2: float
    priority: tuple[float, ...] = ()
    outside_potential: bool = False
    reserved_by_other_technology: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", _identifier(self.cell_id, "Cell id"))
        eligible = _nonnegative(self.eligible_area_km2, "Eligible area km2")
        potential = _nonnegative(self.potential_area_km2, "Potential area km2")
        if eligible <= 0.0:
            raise ValueError("Eligible area km2 must be positive")
        if potential > eligible + FLOAT_TOLERANCE:
            raise ValueError("Potential area cannot exceed eligible area")
        if self.outside_potential and potential > FLOAT_TOLERANCE:
            raise ValueError("Outside-potential candidates cannot declare potential area")
        normalized_priority = tuple(float(value) for value in self.priority)
        if not all(math.isfinite(value) for value in normalized_priority):
            raise ValueError("Allocation priority values must be finite")
        object.__setattr__(self, "eligible_area_km2", eligible)
        object.__setattr__(self, "potential_area_km2", potential)
        object.__setattr__(self, "priority", normalized_priority)


@dataclass(frozen=True)
class AllocatedCell:
    cell_id: str
    allocated_area_km2: float
    allocated_twh: float
    eligible_area_km2: float
    potential_area_km2: float
    selected_rank: int
    outside_potential: bool
    reserved_by_other_technology: bool


@dataclass(frozen=True)
class TechnologyAllocationResult:
    demand: TechnologyDemand
    cells: tuple[AllocatedCell, ...]
    selected_area_km2: float
    selected_twh: float
    unmet_area_km2: float
    available_potential_area_km2: float
    available_outside_area_km2: float

    def __post_init__(self) -> None:
        selected_area = _nonnegative(
            self.selected_area_km2,
            "Selected area km2",
        )
        selected_twh = _nonnegative(self.selected_twh, "Selected TWh")
        unmet_area = _nonnegative(self.unmet_area_km2, "Unmet area km2")
        if not math.isclose(
            selected_area + unmet_area,
            self.demand.area_need_km2,
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        ):
            raise ValueError("Selected plus unmet area must equal area demand")
        if not math.isclose(
            math.fsum(cell.allocated_area_km2 for cell in self.cells),
            selected_area,
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        ):
            raise ValueError("Selected cell areas do not match the result total")
        if not math.isclose(
            math.fsum(cell.allocated_twh for cell in self.cells),
            selected_twh,
            rel_tol=0.0,
            abs_tol=FLOAT_TOLERANCE,
        ):
            raise ValueError("Selected cell energy does not match the result total")


@dataclass(frozen=True)
class AllocationRollupCell:
    cell_id: str
    allocated_area_km2: float
    allocated_twh: float
    inside_potential_area_km2: float
    outside_potential_area_km2: float
    selected_child_count: int


def rebalance_energy_mix(
    energies: Iterable[TechnologyEnergy],
    technology_shares_pct: Mapping[str, float],
) -> EnergyMixResult:
    """Rebalance declared technologies while preserving their combined TWh."""

    source = tuple(energies)
    source_ids = tuple(item.technology for item in source)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Source energy technologies must be unique")
    if not technology_shares_pct:
        raise ValueError("At least one technology share is required")

    shares = {
        _identifier(technology, "Technology share id"): _nonnegative(
            value,
            "Technology share percent",
        )
        for technology, value in technology_shares_pct.items()
    }
    if any(value > 100.0 for value in shares.values()) or not math.isclose(
        math.fsum(shares.values()),
        100.0,
        rel_tol=0.0,
        abs_tol=FLOAT_TOLERANCE,
    ):
        raise ValueError("Technology shares must be between 0 and 100 and sum to 100")

    rebalanced_ids = tuple(sorted(shares))
    source_by_id = {item.technology: item.twh for item in source}
    rebalanced_total = math.fsum(
        source_by_id.get(technology, 0.0) for technology in rebalanced_ids
    )
    targets: dict[str, float] = {}
    assigned = 0.0
    for index, technology in enumerate(rebalanced_ids):
        if index == len(rebalanced_ids) - 1:
            value = max(0.0, rebalanced_total - assigned)
        else:
            value = rebalanced_total * shares[technology] / 100.0
            assigned += value
        targets[technology] = value

    output_ids = list(source_ids)
    output_ids.extend(
        technology for technology in rebalanced_ids if technology not in source_by_id
    )
    output = tuple(
        TechnologyEnergy(
            technology,
            (
                targets[technology]
                if technology in targets
                else source_by_id[technology]
            ),
        )
        for technology in output_ids
    )
    return EnergyMixResult(output, rebalanced_ids, rebalanced_total)


def calculate_technology_demands(
    energies: Iterable[TechnologyEnergy],
    km2_per_twh: Mapping[str, float],
) -> tuple[TechnologyDemand, ...]:
    """Convert technology energy to area demand through declared factors."""

    source = tuple(energies)
    technologies = tuple(item.technology for item in source)
    if len(set(technologies)) != len(technologies):
        raise ValueError("Demand energy technologies must be unique")
    demands: list[TechnologyDemand] = []
    for item in source:
        if item.technology not in km2_per_twh:
            raise ValueError(
                f"Area-demand factor is missing for {item.technology}"
            )
        try:
            factor = float(km2_per_twh[item.technology])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Area-demand factor is invalid for {item.technology}"
            ) from exc
        demands.append(
            TechnologyDemand(
                technology=item.technology,
                twh=item.twh,
                km2_per_twh=factor,
                area_need_km2=item.twh * factor,
            )
        )
    return tuple(demands)


def allocate_technology_area(
    demand: TechnologyDemand,
    candidates: Iterable[AllocationCandidate],
) -> TechnologyAllocationResult:
    """Allocate one technology deterministically within declared capacities.

    Priority tuple values are compared from left to right, highest first.
    Reservation is a final tie-breaker, so a higher-priority co-use candidate
    may still win while an equally ranked separate cell is preferred.
    """

    source = tuple(candidates)
    cell_ids = tuple(candidate.cell_id for candidate in source)
    if len(set(cell_ids)) != len(cell_ids):
        raise ValueError("Allocation candidate cell ids must be unique")

    ordered = sorted(
        source,
        key=lambda item: (
            item.outside_potential,
            tuple(-value for value in item.priority),
            item.reserved_by_other_technology,
            item.cell_id,
        ),
    )
    available_potential = math.fsum(
        item.potential_area_km2
        for item in ordered
        if not item.outside_potential
    )
    available_outside = math.fsum(
        item.eligible_area_km2 for item in ordered if item.outside_potential
    )
    remaining = demand.area_need_km2
    selected: list[AllocatedCell] = []
    for candidate in ordered:
        capacity = (
            candidate.eligible_area_km2
            if candidate.outside_potential
            else candidate.potential_area_km2
        )
        allocated_area = min(capacity, remaining)
        if allocated_area <= FLOAT_TOLERANCE:
            continue
        selected.append(
            AllocatedCell(
                cell_id=candidate.cell_id,
                allocated_area_km2=allocated_area,
                allocated_twh=allocated_area / demand.km2_per_twh,
                eligible_area_km2=candidate.eligible_area_km2,
                potential_area_km2=candidate.potential_area_km2,
                selected_rank=len(selected) + 1,
                outside_potential=candidate.outside_potential,
                reserved_by_other_technology=(
                    candidate.reserved_by_other_technology
                ),
            )
        )
        remaining = max(0.0, remaining - allocated_area)
        if remaining <= FLOAT_TOLERANCE:
            remaining = 0.0
            break

    selected_area = math.fsum(item.allocated_area_km2 for item in selected)
    selected_twh = math.fsum(item.allocated_twh for item in selected)
    return TechnologyAllocationResult(
        demand=demand,
        cells=tuple(selected),
        selected_area_km2=selected_area,
        selected_twh=selected_twh,
        unmet_area_km2=remaining,
        available_potential_area_km2=available_potential,
        available_outside_area_km2=available_outside,
    )


def rollup_allocation(
    result: TechnologyAllocationResult,
    parent_by_cell: Mapping[str, str],
) -> tuple[AllocationRollupCell, ...]:
    """Sum a fine-resolution allocation without reranking parent cells."""

    grouped: dict[str, list[AllocatedCell]] = {}
    for cell in result.cells:
        if cell.cell_id not in parent_by_cell:
            raise ValueError(f"Allocation parent is missing for {cell.cell_id}")
        parent = _identifier(parent_by_cell[cell.cell_id], "Parent cell id")
        grouped.setdefault(parent, []).append(cell)

    return tuple(
        AllocationRollupCell(
            cell_id=parent,
            allocated_area_km2=math.fsum(
                item.allocated_area_km2 for item in children
            ),
            allocated_twh=math.fsum(item.allocated_twh for item in children),
            inside_potential_area_km2=math.fsum(
                item.allocated_area_km2
                for item in children
                if not item.outside_potential
            ),
            outside_potential_area_km2=math.fsum(
                item.allocated_area_km2
                for item in children
                if item.outside_potential
            ),
            selected_child_count=len(children),
        )
        for parent, children in sorted(grouped.items())
    )
