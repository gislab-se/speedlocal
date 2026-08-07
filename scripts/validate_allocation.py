from __future__ import annotations

import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal.allocation import (
    AllocationCandidate,
    TechnologyDemand,
    TechnologyEnergy,
    allocate_technology_area,
    calculate_technology_demands,
    rebalance_energy_mix,
    rollup_allocation,
)


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        (self.passes if condition else self.failures).append(ok if condition else fail)

    def emit(self) -> int:
        print("SpeedLocal continuous-allocation validation")
        print("=" * 43)
        print("\nBLOCKERS")
        if self.failures:
            for index, failure in enumerate(self.failures, start=1):
                print(f"{index}. FAIL {failure}")
        else:
            print("None")
        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")
        status = "FAIL" if self.failures else "PASS"
        print(
            f"\nRESULT: {status} "
            f"({len(self.passes)} passed, {len(self.failures)} blocker(s))"
        )
        return 1 if self.failures else 0


def _raises(callable_object, message: str) -> bool:
    try:
        callable_object()
    except ValueError:
        return True
    raise AssertionError(message)


def main() -> int:
    report = Report()
    source = (
        TechnologyEnergy("wind", 31.05),
        TechnologyEnergy("solar", 31.05),
    )
    endpoint_rows: list[tuple[float, float, float, float]] = []
    for solar_share in (0.0, 50.0, 100.0):
        mix = rebalance_energy_mix(
            source,
            {"wind": 100.0 - solar_share, "solar": solar_share},
        )
        demands = calculate_technology_demands(
            mix.energies,
            {"wind": 50.0, "solar": 10.0},
        )
        endpoint_rows.append(
            (
                mix.energy_twh("wind"),
                mix.energy_twh("solar"),
                math.fsum(item.twh for item in mix.energies),
                math.fsum(item.area_need_km2 for item in demands),
            )
        )
    report.check(
        endpoint_rows
        == [
            (62.1, 0.0, 62.1, 3105.0),
            (31.05, 31.05, 62.1, 1863.0),
            (0.0, 62.1, 62.1, 621.0),
        ],
        "0/50/100 mix endpoints preserve total TWh and exact technology demand.",
        f"Continuous mix endpoints drifted: {endpoint_rows}.",
    )

    geothermal = rebalance_energy_mix(
        (TechnologyEnergy("geothermal", 8.0), TechnologyEnergy("tidal", 2.0)),
        {"geothermal": 25.0, "tidal": 75.0},
    )
    report.check(
        geothermal.energy_twh("geothermal") == 2.5
        and geothermal.energy_twh("tidal") == 7.5,
        "Mix calculation is technology-neutral.",
        "Mix calculation depends on wind/solar technology ids.",
    )

    added_technology = rebalance_energy_mix(
        (TechnologyEnergy("wind", 8.0),),
        {"wind": 25.0, "solar": 75.0},
    )
    report.check(
        added_technology.energy_twh("wind") == 2.0
        and added_technology.energy_twh("solar") == 6.0,
        "A declared target technology absent from the source receives its share.",
        "A missing target technology could not be added to the mix.",
    )

    report.check(
        _raises(
            lambda: rebalance_energy_mix(
                source,
                {"wind": 60.0, "solar": 60.0},
            ),
            "Invalid technology shares did not fail closed",
        ),
        "Invalid technology shares fail closed.",
        "Invalid technology shares were accepted.",
    )

    report.check(
        _raises(
            lambda: calculate_technology_demands(
                source,
                {"wind": 50.0, "solar": None},
            ),
            "Invalid area-demand factor did not fail closed",
        ),
        "Missing or invalid area-demand factors fail closed.",
        "An invalid area-demand factor was accepted.",
    )

    demand = TechnologyDemand("wind", 0.07, 10.0, 0.7)
    candidates = (
        AllocationCandidate("coast", 0.4, 0.4, (1.0,)),
        AllocationCandidate("inland", 1.0, 0.6, (0.8,)),
    )
    allocation = allocate_technology_area(demand, candidates)
    report.check(
        math.isclose(allocation.selected_area_km2, 0.7, abs_tol=1e-12)
        and allocation.unmet_area_km2 == 0.0
        and allocation.cells[0].cell_id == "coast"
        and allocation.cells[0].allocated_area_km2 == 0.4
        and all(
            item.allocated_area_km2 <= item.eligible_area_km2
            for item in allocation.cells
        ),
        "Partial coastal cells are capped by declared eligible/potential area.",
        f"Coastal allocation exceeded its declared capacity: {allocation}.",
    )

    reversed_allocation = allocate_technology_area(
        demand,
        tuple(reversed(candidates)),
    )
    report.check(
        allocation.cells == reversed_allocation.cells,
        "Allocation is deterministic under reversed input order.",
        "Allocation order depends on source row order.",
    )

    overlap = allocate_technology_area(
        TechnologyDemand("wind", 0.05, 10.0, 0.5),
        (
            AllocationCandidate(
                "reserved-high",
                0.5,
                0.5,
                (2.0,),
                reserved_by_other_technology=True,
            ),
            AllocationCandidate("separate-high", 0.5, 0.5, (1.0,)),
            AllocationCandidate(
                "reserved-tie",
                0.5,
                0.5,
                (1.0,),
                reserved_by_other_technology=True,
            ),
        ),
    )
    tied = allocate_technology_area(
        TechnologyDemand("wind", 0.05, 10.0, 0.5),
        (
            AllocationCandidate(
                "reserved",
                0.5,
                0.5,
                (1.0,),
                reserved_by_other_technology=True,
            ),
            AllocationCandidate("separate", 0.5, 0.5, (1.0,)),
        ),
    )
    report.check(
        overlap.cells[0].cell_id == "reserved-high"
        and tied.cells[0].cell_id == "separate",
        "Co-use remains allowed at higher priority and separate cells win ties.",
        "Allocation overlap policy drifted.",
    )

    shortage = allocate_technology_area(
        TechnologyDemand("solar", 0.1, 10.0, 1.0),
        (
            AllocationCandidate("inside", 0.3, 0.3, (1.0,)),
            AllocationCandidate(
                "outside",
                0.5,
                0.0,
                (10.0,),
                outside_potential=True,
            ),
        ),
    )
    report.check(
        [item.cell_id for item in shortage.cells] == ["inside", "outside"]
        and shortage.cells[1].outside_potential
        and shortage.selected_area_km2 == 0.8
        and math.isclose(shortage.unmet_area_km2, 0.2, abs_tol=1e-12),
        "Outside-potential capacity is used only after positive potential and remains classified.",
        f"Outside-potential shortage behavior drifted: {shortage}.",
    )

    zero = allocate_technology_area(
        TechnologyDemand("solar", 0.0, 10.0, 0.0),
        candidates,
    )
    report.check(
        not zero.cells and zero.selected_area_km2 == zero.unmet_area_km2 == 0.0,
        "Zero technology demand creates no phantom allocation or shortage.",
        f"Zero demand produced allocation state: {zero}.",
    )

    rollup = rollup_allocation(
        shortage,
        {"inside": "parent", "outside": "parent"},
    )
    report.check(
        len(rollup) == 1
        and rollup[0].allocated_area_km2 == 0.8
        and rollup[0].inside_potential_area_km2 == 0.3
        and rollup[0].outside_potential_area_km2 == 0.5
        and rollup[0].selected_child_count == 2,
        "Parent allocation is an exact sum of selected fine children.",
        f"Allocation rollup reranked or lost child totals: {rollup}.",
    )

    report.check(
        _raises(
            lambda: AllocationCandidate("bad", 0.4, 0.5),
            "Over-capacity candidate did not fail closed",
        ),
        "Potential area greater than eligible area fails closed.",
        "An over-capacity allocation candidate was accepted.",
    )
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
