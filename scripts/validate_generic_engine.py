from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal import run_analysis
from speedlocal.catalogs import load_analysis
from speedlocal.validation import select_processing_adapter, validate_contract, validate_layer


DEFAULT_V2_ROOT = Path(r"C:\gislab\data\landskapsanalys-v2-multiregion")


def main() -> int:
    os.environ.setdefault("SPEEDLOCAL_V2_SOURCE_ROOT", str(DEFAULT_V2_ROOT))
    checks = 0
    assert select_processing_adapter("population", "point") == "population_points"
    assert select_processing_adapter("population", "polygon") == "population_polygons"
    assert select_processing_adapter("population", "polygon", "grid") == "population_grid"
    checks += 3
    for region_id in ("bornholm", "trondelag"):
        contract = load_analysis(region_id, "wind")
        validate_contract(contract)
        checks += 1
        roads = validate_layer(contract.layers["roads_large"])
        assert roads.geometry_family == "line"
        assert roads.processing_adapter == "line_distance"
        assert roads.assets.feature_count > 0
        checks += 3

        default_result = run_analysis(region_id, "wind", ["roads_large"])
        wider_result = run_analysis(
            region_id,
            "wind",
            ["roads_large"],
            {"roads_large": {"buffer_m": 500}},
        )
        default_layer = default_result.layers[0]
        wider_layer = wider_result.layers[0]
        assert default_layer.cell_count > 0
        assert default_layer.blocked_cell_count > 0
        assert wider_layer.blocked_cell_count >= default_layer.blocked_cell_count
        checks += 3
        print(
            f"PASS {region_id}: {default_layer.source_feature_count} road features, "
            f"{default_layer.cell_count} H3 cells, "
            f"{default_layer.blocked_cell_count} blocked at {default_layer.threshold_m:g} m"
        )

    print(f"Generic engine validation passed: {checks}/17 checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
