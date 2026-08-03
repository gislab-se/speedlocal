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
