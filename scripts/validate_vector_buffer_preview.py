from __future__ import annotations

import json
import math
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal.catalogs import load_analysis, load_region


GEOMETRY_IMPORT_ERROR: ModuleNotFoundError | None = None
try:
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    from apps.v2_port.apps.potential_model.speedlocal_bridge import (
        analysis_area_group_preview,
        analysis_source_geojson,
        area_applicable_group_ids,
        solar_area_result_frame,
        vector_preview_layer_ids,
        vector_buffer_preview as build_manifest_vector_buffer_preview,
        wind_area_result_frame,
    )
    from speedlocal.geometry import GeometryPreviewError, build_vector_buffer_preview
except ModuleNotFoundError as exc:
    GEOMETRY_IMPORT_ERROR = exc


@dataclass
class Report:
    passes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def check(self, condition: bool, ok: str, fail: str) -> None:
        (self.passes if condition else self.failures).append(ok if condition else fail)

    def emit(self) -> int:
        print("SpeedLocal vector-buffer preview")
        print("=" * 32)
        print("\nBLOCKERS")
        if self.failures:
            for index, failure in enumerate(self.failures, start=1):
                print(f"{index}. FAIL {failure}")
        else:
            print("None")
        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")
        if self.notes:
            print("\nNOTES")
            for item in self.notes:
                print(f"- {item}")
        status = "FAIL" if self.failures else "PASS"
        print(
            f"\nRESULT: {status} "
            f"({len(self.passes)} passed, {len(self.failures)} blocker(s))"
        )
        return 1 if self.failures else 0


def _failure_code(action: Callable[[], object]) -> str | None:
    try:
        action()
    except GeometryPreviewError as exc:  # type: ignore[possibly-undefined]
        return exc.code
    return None


def _raises_value_error(action: Callable[[], object]) -> bool:
    try:
        action()
    except (KeyError, ValueError):
        return True
    return False


def main() -> int:
    report = Report()
    if GEOMETRY_IMPORT_ERROR is not None:
        report.failures.append(
            "The declared geometry dependencies are not installed: "
            f"{GEOMETRY_IMPORT_ERROR.name}. Install requirements.txt first."
        )
        return report.emit()

    source_root = os.environ.get("SPEEDLOCAL_V2_SOURCE_ROOT", "").strip()
    report.check(
        bool(source_root),
        "SPEEDLOCAL_V2_SOURCE_ROOT is configured.",
        "SPEEDLOCAL_V2_SOURCE_ROOT is not configured.",
    )
    if not source_root:
        return report.emit()
    report.check(
        Path(source_root).is_dir(),
        "The configured V2 source root exists.",
        "The configured V2 source root does not exist.",
    )
    if not Path(source_root).is_dir():
        return report.emit()

    contract = load_analysis("trondelag", "wind")
    region = load_region("trondelag")
    layer = contract.layers["roads_large"]
    medium_layer = contract.layers["roads_medium"]
    population_layer = contract.layers["population_points"]
    built_centre_layer = contract.layers["built_centre"]
    built_low_layer = contract.layers["built_low_selection"]
    nature_layer = contract.layers["protected_areas"]
    cultural_preservation_layer = contract.layers["cultural_preservation"]
    cultural_environment_layer = contract.layers[
        "valuable_cultural_environment"
    ]
    high_voltage_layer = contract.layers["high_voltage_lines"]
    underground_cable_layer = contract.layers["underground_cables"]
    wind_turbine_layer = contract.layers["existing_wind_turbines"]
    native_crs = str(region["native_crs"])

    zero = build_vector_buffer_preview(
        [layer],
        native_crs=native_crs,
        buffer_m=0,
    )
    at_300 = build_vector_buffer_preview(
        [layer],
        native_crs=native_crs,
        buffer_m=300,
    )
    at_1000 = build_vector_buffer_preview(
        [layer],
        native_crs=native_crs,
        buffer_m=1000,
    )
    medium_at_300 = build_vector_buffer_preview(
        [medium_layer],
        native_crs=native_crs,
        buffer_m=300,
    )
    combined_at_300 = build_vector_buffer_preview(
        [medium_layer, layer],
        native_crs=native_crs,
        buffer_m=300,
    )
    population_at_100 = build_vector_buffer_preview(
        [population_layer],
        native_crs=native_crs,
        buffer_m=100,
    )
    population_at_1000 = build_vector_buffer_preview(
        [population_layer],
        native_crs=native_crs,
        buffer_m=1000,
    )
    built_centre_at_500 = build_vector_buffer_preview(
        [built_centre_layer],
        native_crs=native_crs,
        buffer_m=500,
    )
    built_low_at_500 = build_vector_buffer_preview(
        [built_low_layer],
        native_crs=native_crs,
        buffer_m=500,
    )
    all_population_at_500 = build_vector_buffer_preview(
        [population_layer, built_centre_layer, built_low_layer],
        native_crs=native_crs,
        buffer_m=500,
    )
    nature_at_0 = build_vector_buffer_preview(
        [nature_layer],
        native_crs=native_crs,
        buffer_m=0,
    )
    nature_at_250 = build_vector_buffer_preview(
        [nature_layer],
        native_crs=native_crs,
        buffer_m=250,
    )
    nature_at_1000 = build_vector_buffer_preview(
        [nature_layer],
        native_crs=native_crs,
        buffer_m=1000,
    )
    cultural_preservation_at_0 = build_vector_buffer_preview(
        [cultural_preservation_layer],
        native_crs=native_crs,
        buffer_m=0,
    )
    cultural_environment_at_0 = build_vector_buffer_preview(
        [cultural_environment_layer],
        native_crs=native_crs,
        buffer_m=0,
    )
    culture_at_0 = build_vector_buffer_preview(
        [cultural_preservation_layer, cultural_environment_layer],
        native_crs=native_crs,
        buffer_m=0,
    )
    culture_at_250 = build_vector_buffer_preview(
        [cultural_preservation_layer, cultural_environment_layer],
        native_crs=native_crs,
        buffer_m=250,
    )
    culture_at_1000 = build_vector_buffer_preview(
        [cultural_preservation_layer, cultural_environment_layer],
        native_crs=native_crs,
        buffer_m=1000,
    )
    grid_layer_ids = (
        high_voltage_layer.id,
        underground_cable_layer.id,
        wind_turbine_layer.id,
    )
    grid_at_500 = build_manifest_vector_buffer_preview(
        "trondelag", grid_layer_ids, 500
    )
    grid_at_2000 = build_manifest_vector_buffer_preview(
        "trondelag", grid_layer_ids, 2000
    )
    grid_at_15000 = build_manifest_vector_buffer_preview(
        "trondelag", grid_layer_ids, 15000
    )
    wind_grid_at_2000 = wind_area_result_frame(
        "trondelag",
        grid_layer_ids,
        {"grid_infrastructure": 2000.0},
        7,
    )
    solar_grid_at_2000 = solar_area_result_frame(
        "trondelag",
        grid_layer_ids,
        {"grid_infrastructure": 2000.0},
        7,
    )
    solar_preview_cases = {
        "roads": (("roads_medium", "roads_large"), 300.0),
        "population": (("population_points",), 100.0),
        "nature": (("protected_areas",), 0.0),
        "culture": (
            ("cultural_preservation", "valuable_cultural_environment"),
            0.0,
        ),
        "grid_infrastructure": (grid_layer_ids, 2000.0),
    }
    solar_group_previews = {
        group_id: analysis_area_group_preview(
            "trondelag",
            "solar",
            group_id,
            layer_ids,
            buffer_m,
        )
        for group_id, (layer_ids, buffer_m) in solar_preview_cases.items()
    }
    solar_source_previews = {
        group_id: analysis_source_geojson(
            "trondelag",
            "solar",
            group_id,
            layer_ids[0],
        )
        for group_id, (layer_ids, _) in solar_preview_cases.items()
    }
    wind_grid_rollups_at_2000 = {
        resolution: wind_area_result_frame(
            "trondelag",
            grid_layer_ids,
            {"grid_infrastructure": 2000.0},
            resolution,
        )
        for resolution in (6, 5)
    }

    report.check(
        zero.semantics == "dissolved_source_footprint"
        and zero.geometry_type in {"LineString", "MultiLineString"}
        and math.isclose(zero.area_m2, 0.0, rel_tol=0.0, abs_tol=1e-9),
        "A 0 m road preview is the dissolved line footprint, not an empty polygon.",
        "A 0 m road preview did not preserve dissolved source-footprint semantics.",
    )
    report.check(
        at_300.semantics == "metric_buffer"
        and at_300.geometry_type in {"Polygon", "MultiPolygon"}
        and at_300.area_m2 > 0,
        "The roads_large 300 m preview is a non-empty polygonal metric buffer.",
        "The roads_large 300 m preview is not a non-empty polygonal buffer.",
    )
    report.check(
        at_1000.semantics == "metric_buffer"
        and at_1000.geometry_type in {"Polygon", "MultiPolygon"}
        and at_1000.area_m2 > at_300.area_m2,
        "The roads_large 1000 m preview area is greater than its 300 m area.",
        "The roads_large preview area did not increase from 300 m to 1000 m.",
    )
    report.check(
        medium_at_300.geometry_type in {"Polygon", "MultiPolygon"}
        and medium_at_300.source_feature_count > 0
        and medium_at_300.area_m2 > 0,
        "The roads_medium 300 m preview is a validated polygonal buffer.",
        "The roads_medium 300 m preview is not a usable polygonal buffer.",
    )
    report.check(
        combined_at_300.layer_ids == ("roads_medium", "roads_large")
        and combined_at_300.geometry_type in {"Polygon", "MultiPolygon"}
        and combined_at_300.area_m2 >= max(
            medium_at_300.area_m2,
            at_300.area_m2,
        ),
        "The combined-roads preview dissolves both declared vector sources.",
        "The combined-roads preview did not preserve both layer contracts.",
    )
    report.check(
        population_at_100.layer_ids == ("population_points",)
        and population_at_100.geometry_type in {"Polygon", "MultiPolygon"}
        and population_at_100.source_feature_count == 1
        and population_at_100.declared_feature_count == 26_029
        and population_at_100.area_m2 > 0,
        "The population 100 m preview uses the declared polygon grid proxy.",
        "The population 100 m preview did not preserve its manifest source.",
    )
    report.check(
        population_at_1000.geometry_type in {"Polygon", "MultiPolygon"}
        and population_at_1000.area_m2 > population_at_100.area_m2,
        "The population preview grows monotonically from 100 m to 1000 m.",
        "The population preview did not grow from 100 m to 1000 m.",
    )
    report.check(
        built_centre_at_500.layer_ids == ("built_centre",)
        and built_centre_at_500.source_feature_count == 1
        and built_centre_at_500.declared_feature_count == 1
        and built_centre_at_500.geometry_type in {"Polygon", "MultiPolygon"}
        and built_centre_at_500.area_m2 > 0,
        "The optional built-centre preview uses its declared polygon source.",
        "The optional built-centre preview drifted from its manifest source.",
    )
    report.check(
        built_low_at_500.layer_ids == ("built_low_selection",)
        and built_low_at_500.source_feature_count == 10_966
        and built_low_at_500.declared_feature_count == 10_966
        and built_low_at_500.geometry_type in {"Polygon", "MultiPolygon"}
        and built_low_at_500.area_m2 > 0,
        "The optional leisure-home preview buffers its declared point source.",
        "The optional leisure-home point preview drifted from its manifest source.",
    )
    report.check(
        all_population_at_500.layer_ids
        == ("population_points", "built_centre", "built_low_selection")
        and all_population_at_500.geometry_type in {"Polygon", "MultiPolygon"}
        and all_population_at_500.area_m2
        >= max(
            built_centre_at_500.area_m2,
            built_low_at_500.area_m2,
        ),
        "All three manifest population geometries dissolve into one preview.",
        "The combined population preview did not preserve all three sources.",
    )
    report.check(
        nature_at_0.layer_ids == ("protected_areas",)
        and nature_at_0.semantics == "dissolved_source_footprint"
        and nature_at_0.geometry_type in {"Polygon", "MultiPolygon"}
        and nature_at_0.source_feature_count == 412
        and nature_at_0.declared_feature_count == 420
        and nature_at_0.area_m2 > 0,
        "The 0 m nature preview applies its declared highest-dimension policy.",
        "The 0 m nature preview did not preserve the manifest geometry policy.",
    )
    report.check(
        nature_at_250.geometry_type in {"Polygon", "MultiPolygon"}
        and nature_at_250.area_m2 > nature_at_0.area_m2
        and nature_at_1000.area_m2 > nature_at_250.area_m2,
        "The protected-nature preview grows monotonically at 0/250/1000 m.",
        "The protected-nature preview did not grow with its metric buffer.",
    )
    report.check(
        cultural_preservation_at_0.layer_ids
        == ("cultural_preservation",)
        and cultural_preservation_at_0.source_feature_count == 1
        and cultural_preservation_at_0.declared_feature_count == 64
        and cultural_preservation_at_0.geometry_type
        in {"Polygon", "MultiPolygon"}
        and cultural_preservation_at_0.area_m2 > 0,
        "The cultural-preservation preview uses its dissolved polygon source.",
        "The cultural-preservation preview drifted from its manifest source.",
    )
    report.check(
        cultural_environment_at_0.layer_ids
        == ("valuable_cultural_environment",)
        and cultural_environment_at_0.source_feature_count == 1
        and cultural_environment_at_0.declared_feature_count == 146
        and cultural_environment_at_0.geometry_type
        in {"Polygon", "MultiPolygon"}
        and cultural_environment_at_0.area_m2 > 0,
        "The valuable-cultural-environment preview uses its polygon source.",
        "The valuable-cultural-environment preview drifted from its source.",
    )
    report.check(
        culture_at_0.layer_ids
        == (
            "cultural_preservation",
            "valuable_cultural_environment",
        )
        and culture_at_0.source_feature_count == 2
        and culture_at_0.declared_feature_count == 210
        and culture_at_0.area_m2
        >= max(
            cultural_preservation_at_0.area_m2,
            cultural_environment_at_0.area_m2,
        ),
        "Both culture sources dissolve into one complete 0 m footprint.",
        "The combined culture footprint did not preserve both sources.",
    )
    report.check(
        culture_at_250.geometry_type in {"Polygon", "MultiPolygon"}
        and culture_at_250.area_m2 > culture_at_0.area_m2
        and culture_at_1000.area_m2 > culture_at_250.area_m2,
        "The combined culture preview grows monotonically at 0/250/1000 m.",
        "The combined culture preview did not grow with its metric buffer.",
    )
    report.check(
        grid_at_500.layer_ids
        == (
            "high_voltage_lines",
            "underground_cables",
            "existing_wind_turbines",
        )
        and grid_at_500.source_feature_count == 3
        and grid_at_500.declared_feature_count == 17_732,
        "The combined grid preview resolves all declared line/point sources.",
        "The combined grid preview did not preserve its three-source contract.",
    )
    report.check(
        grid_at_500.semantics == "exact_area_clip"
        and grid_at_500.geometry_type in {"Polygon", "MultiPolygon"}
        and grid_at_500.area_m2 < grid_at_2000.area_m2
        < grid_at_15000.area_m2
        and float(grid_at_500.model_area_m2 or 0.0)
        < float(grid_at_2000.model_area_m2 or 0.0)
        < float(grid_at_15000.model_area_m2 or 0.0),
        "The exact domain-clipped grid preview grows monotonically at 500/2000/15000 m.",
        "The exact grid preview did not grow with maximum connection distance.",
    )
    report.check(
        all(
            feature.get("geometry", {}).get("type")
            in {"Polygon", "MultiPolygon"}
            for feature in grid_at_2000.geojson.get("features", [])
        )
        and grid_at_2000.geojson["features"][0]["properties"].get(
            "source_h3_resolution"
        )
        == 7
        and grid_at_2000.geojson["features"][0]["properties"].get(
            "operation"
        )
        == "proximity_feasibility"
        and grid_at_2000.geojson["features"][0]["properties"].get(
            "semantics"
        )
        == "exact_area_clip",
        "The mixed grid line/point buffer serializes as exact clipped R7 GeoJSON.",
        "The mixed grid line/point buffer emitted an invalid exact preview.",
    )
    preview_grid_areas = {
        500: float(grid_at_500.model_area_m2 or 0.0) / 1_000_000.0,
        2000: float(grid_at_2000.model_area_m2 or 0.0) / 1_000_000.0,
        15000: float(grid_at_15000.model_area_m2 or 0.0) / 1_000_000.0,
    }
    expected_grid_areas = {
        500: 8_992.417252706564,
        2000: 23_137.469491933643,
        15000: 43_995.63150207577,
    }
    report.check(
        all(
            math.isclose(
                preview_grid_areas[distance],
                expected_grid_areas[distance],
                rel_tol=0.0,
                abs_tol=1e-8,
            )
            for distance in expected_grid_areas
        )
        and math.isclose(
            preview_grid_areas[2000],
            float(wind_grid_at_2000["potential_area_km2"].sum()),
            rel_tol=0.0,
            abs_tol=1e-8,
        ),
        "The 500/2000/15000 m previews equal the accepted exact R7 model areas.",
        "The grid preview and exact R7 technology-area calculation disagree.",
    )
    cell_counts = {
        distance: (
            int(preview.zero_cell_count or 0),
            int(preview.partial_cell_count or 0),
            int(preview.full_cell_count or 0),
        )
        for distance, preview in {
            500: grid_at_500,
            2000: grid_at_2000,
            15000: grid_at_15000,
        }.items()
    }
    report.check(
        cell_counts
        == {
            500: (7565, 6160, 10),
            2000: (5066, 3815, 4854),
            15000: (277, 185, 13273),
        },
        "Exact grid feasibility retains accepted zero/partial/full R7 cells.",
        "Grid feasibility cell classes drifted or collapsed to whole cells: "
        f"{cell_counts}.",
    )
    rollup_areas = {
        resolution: float(frame["potential_area_km2"].sum())
        for resolution, frame in wind_grid_rollups_at_2000.items()
    }
    report.check(
        all(
            math.isclose(
                area,
                expected_grid_areas[2000],
                rel_tol=0.0,
                abs_tol=1e-8,
            )
            for area in rollup_areas.values()
        )
        and {
            resolution: int(frame["potential_area_km2"].gt(0.0).sum())
            for resolution, frame in wind_grid_rollups_at_2000.items()
        }
        == {6: 1611, 5: 311},
        "The exact 2000 m R7 area is preserved through R6/R5 rollup.",
        "The exact 2000 m grid area or positive-cell count drifted at R6/R5.",
    )
    report.check(
        wind_grid_at_2000[
            ["hex_id", "potential_area_km2", "potential_area_share_pct"]
        ].equals(
            solar_grid_at_2000[
                ["hex_id", "potential_area_km2", "potential_area_share_pct"]
            ]
        ),
        "Wind and solar consume the same exact 2000 m grid geometry per R7 cell.",
        "Wind and solar grid geometry diverged at 2000 m.",
    )
    report.check(
        area_applicable_group_ids("trondelag", "solar")
        == ("roads", "population", "nature", "culture", "grid_infrastructure")
        and all(
            set(layer_ids).issubset(
                set(vector_preview_layer_ids("trondelag", "solar", group_id))
            )
            for group_id, (layer_ids, _) in solar_preview_cases.items()
        ),
        "Solar review availability comes from all five applicable manifest groups.",
        "Solar review availability drifted from the solar area manifest.",
    )
    report.check(
        all(
            preview.semantics == "exact_area_clip"
            and preview.model_area_m2 is not None
            and preview.model_area_m2 > 0.0
            and preview.geojson["features"][0]["properties"].get(
                "analysis_id"
            )
            == "solar"
            and preview.geojson["features"][0]["properties"].get(
                "group_id"
            )
            == group_id
            for group_id, preview in solar_group_previews.items()
        ),
        "All five solar review buffers use exact solar-manifest geometry.",
        "A solar review buffer fell back to legacy or non-exact geometry.",
    )
    report.check(
        all(
            payload.get("type") == "FeatureCollection"
            and bool(payload.get("features"))
            for payload in solar_source_previews.values()
        ),
        "All five solar source previews resolve through manifest providers.",
        "A solar source preview could not resolve through its manifest provider.",
    )
    solar_grid_preview = solar_group_previews["grid_infrastructure"]
    report.check(
        math.isclose(
            float(solar_grid_preview.model_area_m2 or 0.0),
            float(grid_at_2000.model_area_m2 or 0.0),
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        and solar_grid_preview.partial_cell_count
        == grid_at_2000.partial_cell_count,
        "Solar and wind map review share the exact 2000 m grid geometry.",
        "Solar and wind map review diverged for the shared grid contract.",
    )
    report.check(
        _raises_value_error(
            lambda: analysis_area_group_preview(
                "trondelag",
                "solar",
                "nature",
                ("roads_large",),
                0.0,
            )
        )
        and _raises_value_error(
            lambda: vector_preview_layer_ids(
                "trondelag",
                "solar",
                "not_applicable",
            )
        ),
        "Solar review rejects wrong-group and non-applicable manifest requests.",
        "Solar review accepted a wrong-group or non-applicable request.",
    )
    serialized_grid_geometry = shape(
        grid_at_2000.geojson["features"][0]["geometry"]
    )
    to_native = Transformer.from_crs(
        "EPSG:4326",
        grid_at_2000.native_crs,
        always_xy=True,
    )
    serialized_native_area_m2 = float(
        transform(to_native.transform, serialized_grid_geometry).area
    )
    report.check(
        math.isclose(
            serialized_native_area_m2,
            float(grid_at_2000.area_m2),
            rel_tol=1e-8,
            abs_tol=1.0,
        ),
        "The serialized exact grid GeoJSON round-trips to its clipped metric area.",
        "The displayed grid geometry drifted from its exact clipped metric area.",
    )
    report.check(
        _failure_code(
            lambda: build_vector_buffer_preview(
                [
                    replace(
                        cultural_preservation_layer,
                        source=replace(
                            cultural_preservation_layer.source,
                            geometry_validity_policy="reject_invalid",
                        ),
                    )
                ],
                native_crs=native_crs,
                buffer_m=0,
            )
        )
        == "source_geometry_invalid",
        "The invalid culture geometry requires its explicit manifest repair policy.",
        "Invalid culture geometry was repaired without manifest authorization.",
    )
    report.check(
        at_300.geojson.get("type") == "FeatureCollection"
        and len(at_300.geojson.get("features") or []) == 1
        and bool((at_300.geojson["features"][0].get("geometry") or {}).get("coordinates")),
        "The preview is one non-empty EPSG:4326 GeoJSON feature.",
        "The preview is not a non-empty one-feature GeoJSON FeatureCollection.",
    )
    try:
        json.dumps(at_300.geojson, allow_nan=False)
    except (TypeError, ValueError):
        serializable = False
    else:
        serializable = True
    report.check(
        serializable,
        "The preview GeoJSON is finite and JSON-serializable.",
        "The preview GeoJSON contains a non-serializable or non-finite value.",
    )
    report.check(
        zero.source_feature_count > 0 and zero.declared_feature_count > 0,
        "The result records resolved source and manifest feature counts.",
        "The result did not record resolved source and manifest feature counts.",
    )
    report.check(
        _failure_code(
            lambda: build_vector_buffer_preview(
                [layer],
                native_crs=native_crs,
                buffer_m=-1,
            )
        )
        == "buffer_negative",
        "Negative buffer distances fail closed.",
        "A negative buffer distance did not fail with buffer_negative.",
    )
    report.check(
        _failure_code(
            lambda: build_vector_buffer_preview(
                [layer],
                native_crs=native_crs,
                buffer_m=3000,
            )
        )
        == "buffer_outside_contract",
        "Positive buffer distances outside the layer manifest fail closed.",
        "An out-of-contract buffer did not fail with buffer_outside_contract.",
    )
    report.check(
        _failure_code(
            lambda: build_vector_buffer_preview(
                [layer],
                native_crs="EPSG:4326",
                buffer_m=300,
            )
        )
        == "native_crs_not_projected",
        "Geographic native CRS input fails before metric buffering.",
        "A geographic native CRS did not fail with native_crs_not_projected.",
    )
    report.check(
        _failure_code(
            lambda: build_vector_buffer_preview(
                [],
                native_crs=native_crs,
                buffer_m=300,
            )
        )
        == "layers_empty",
        "An empty layer selection fails closed.",
        "An empty layer selection did not fail with layers_empty.",
    )
    report.notes.append(f"roads_large 300 m area: {at_300.area_m2:,.0f} m2")
    report.notes.append(f"roads_large 1000 m area: {at_1000.area_m2:,.0f} m2")
    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
