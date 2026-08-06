from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from speedlocal.area_result import build_area_group_preview, run_area_analysis
from speedlocal.catalogs import load_analysis, load_region
from speedlocal.contracts import (
    AnalysisContract,
    ParameterContract,
    RooftopSolarContract,
)
from speedlocal.distributed_generation import (
    RooftopSolarAccountingResult,
    calculate_rooftop_solar_accounting,
    load_rooftop_population_counts,
)
from speedlocal.engine import run_analysis
from speedlocal.geometry import (
    VectorBufferPreview,
    build_vector_buffer_preview,
)
from speedlocal.sources import (
    resolve_analysis_domain_cell_areas_km2,
    resolve_analysis_domain_cell_ids,
)
from speedlocal.validation import validate_contract, validate_layer


CANONICAL_ROADS_GROUP_ID = "roads"
CANONICAL_POPULATION_GROUP_ID = "population"
CANONICAL_NATURE_GROUP_ID = "nature"
CANONICAL_CULTURE_GROUP_ID = "culture"
CANONICAL_GRID_GROUP_ID = "grid_infrastructure"
CANONICAL_DISTANCE_OPERATIONS = {
    "distance_exclusion",
    "hard_exclusion",
    "proximity_feasibility",
}
CANONICAL_TO_TRANSITIONAL_GROUP_ID = {
    "nature": "protected",
    "culture": "culture",
    "grid_infrastructure": "electrical",
}


@dataclass(frozen=True)
class WindLayerControlContract:
    id: str
    group_id: str
    label: str
    note: str
    source_color: tuple[int, int, int]
    point_radius: int
    quality_flag: str | None
    ready: bool
    message: str


@dataclass(frozen=True)
class WindGroupControlContract:
    id: str
    canonical_id: str
    label: str
    analysis_kind: str
    analysis_label: str
    analysis_min_m: int
    analysis_max_m: int
    analysis_step_m: int
    analysis_default_m: int
    blend_default: int
    group_color: tuple[int, int, int]
    interpretation: str
    expanded_by_default: bool
    layers: tuple[WindLayerControlContract, ...]


# Compatibility names for downstream code that imported the roads-only bridge.
RoadLayerControlContract = WindLayerControlContract
RoadGroupControlContract = WindGroupControlContract


def _hex_color_to_rgb(value: str) -> tuple[int, int, int]:
    normalized = str(value).strip().removeprefix("#")
    if len(normalized) != 6:
        raise ValueError(f"Invalid manifest UI color: {value!r}")
    return tuple(
        int(normalized[offset : offset + 2], 16)
        for offset in (0, 2, 4)
    )


def _validated_analysis(
    region_id: str,
    analysis_id: str,
) -> AnalysisContract:
    analysis = load_analysis(str(region_id), str(analysis_id))
    validate_contract(analysis)
    return analysis


def _validated_wind_analysis(region_id: str) -> AnalysisContract:
    return _validated_analysis(region_id, "wind")


def _validated_area_analysis(
    region_id: str,
    technology: str,
) -> AnalysisContract:
    analysis = _validated_analysis(region_id, technology)
    if analysis.area_result is None:
        raise ValueError(
            f"{region_id}/{technology} has no area-result contract"
        )
    if analysis.area_result.technology != str(technology):
        raise ValueError(
            f"{region_id}/{technology} declares area technology "
            f"{analysis.area_result.technology}"
        )
    return analysis


def wind_analysis_domain_resolution(region_id: str) -> int:
    """Return the canonical wind-analysis resolution from its manifest."""
    analysis = _validated_wind_analysis(region_id)
    if analysis.analysis_domain is None:
        raise ValueError(f"{region_id}/wind has no analysis-domain contract")
    return int(analysis.analysis_domain.resolution)


def wind_analysis_domain_cell_areas_km2(
    region_id: str,
    resolution: int | None = None,
) -> dict[str, float]:
    """Return validated manifest-domain cell areas in square kilometres."""
    analysis = _validated_wind_analysis(region_id)
    return resolve_analysis_domain_cell_areas_km2(analysis, resolution)


def technology_area_result_frame(
    region_id: str,
    technology: str,
    layer_ids: Collection[str],
    group_buffer_m: dict[str, float],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt one exact manifest-declared technology area to V2 Final."""

    analysis = _validated_area_analysis(region_id, technology)
    requested = tuple(str(layer_id) for layer_id in layer_ids)
    if len(requested) != len(set(requested)):
        raise ValueError("A wind area-result request contains duplicate layers")
    unknown = set(requested) - set(analysis.layers)
    if unknown:
        raise ValueError(
            f"{region_id}/{technology} has no canonical area-result layers: "
            f"{sorted(unknown)}"
        )
    ordered = tuple(
        layer_id for layer_id in analysis.layers if layer_id in set(requested)
    )
    parameters: dict[str, dict[str, float]] = {}
    for layer_id in ordered:
        layer = analysis.layers[layer_id]
        if layer.group_id not in group_buffer_m:
            raise ValueError(
                f"{technology.title()} area-result group {layer.group_id} "
                "has no applied distance"
            )
        parameters[layer_id] = {
            "buffer_m": float(group_buffer_m[layer.group_id]),
        }
    result = run_area_analysis(
        region=str(region_id),
        analysis=str(technology),
        layers=ordered,
        parameters=parameters,
        target_resolution=target_resolution,
    )
    frame = pd.DataFrame(
        (
            {
                "hex_id": cell.cell_id,
                "display_area_km2": cell.model_area_km2,
                "potential_area_km2": cell.remaining_area_km2,
                "potential_area_share_pct": cell.potential_pct,
            }
            for cell in result.cells
        )
    )
    if frame.empty or frame["hex_id"].duplicated().any():
        raise ValueError("Canonical wind area result is empty or duplicated")
    frame.attrs["area_result"] = {
        "technology": result.technology,
        "active_group_ids": result.active_group_ids,
        "selected_layer_ids": result.selected_layer_ids,
        "model_area_km2": result.model_area_km2,
        "remaining_area_km2": result.remaining_area_km2,
        "potential_pct": result.potential_pct,
        "resolution": result.resolution,
    }
    return frame.sort_values("hex_id").reset_index(drop=True)


def wind_area_result_frame(
    region_id: str,
    layer_ids: Collection[str],
    group_buffer_m: dict[str, float],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt the exact manifest-declared wind area result to V2 Final."""

    return technology_area_result_frame(
        region_id,
        "wind",
        layer_ids,
        group_buffer_m,
        target_resolution,
    )


def solar_area_result_frame(
    region_id: str,
    layer_ids: Collection[str],
    group_buffer_m: dict[str, float],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt the exact manifest-declared solar area result to V2 Final."""

    return technology_area_result_frame(
        region_id,
        "solar",
        layer_ids,
        group_buffer_m,
        target_resolution,
    )


def solar_rooftop_contract(region_id: str) -> RooftopSolarContract:
    """Return the validated manifest-declared rooftop planning proxy."""

    analysis = _validated_area_analysis(region_id, "solar")
    distributed_generation = analysis.distributed_generation
    rooftop = (
        distributed_generation.rooftop_solar
        if distributed_generation is not None
        else None
    )
    if rooftop is None:
        raise ValueError(
            f"{region_id}/solar has no rooftop-solar accounting contract"
        )
    return rooftop


def solar_rooftop_population_frame(
    region_id: str,
    target_resolution: int | None = None,
) -> pd.DataFrame:
    """Load the rooftop proxy's manifest-pinned population counts."""

    analysis = _validated_area_analysis(region_id, "solar")
    distributed_generation = analysis.distributed_generation
    rooftop = (
        distributed_generation.rooftop_solar
        if distributed_generation is not None
        else None
    )
    if rooftop is None:
        raise ValueError(
            f"{region_id}/solar has no rooftop-solar accounting contract"
        )
    canonical_resolution = rooftop.population_source.analysis_h3_resolution
    domain_ids = resolve_analysis_domain_cell_ids(
        analysis,
        canonical_resolution,
    )
    return load_rooftop_population_counts(
        rooftop.population_source,
        domain_ids,
        target_resolution,
    )


def solar_rooftop_accounting(
    region_id: str,
    population: float,
    panel_area_m2_per_person: float,
    gross_solar_target_twh: float,
    ground_km2_per_twh: float,
) -> RooftopSolarAccountingResult:
    """Calculate residual ground-solar demand from the canonical contract."""

    return calculate_rooftop_solar_accounting(
        solar_rooftop_contract(region_id),
        population,
        panel_area_m2_per_person,
        gross_solar_target_twh,
        ground_km2_per_twh,
    )


def area_applicable_group_ids(
    region_id: str,
    technology: str,
) -> tuple[str, ...]:
    """Return one technology's manifest-declared area groups in order."""

    analysis = _validated_area_analysis(region_id, technology)
    return tuple(analysis.area_result.applicable_group_ids)


def analysis_group_layer_ids(
    region_id: str,
    analysis_id: str,
    group_id: str,
) -> tuple[str, ...]:
    """Return preview-compatible layers for one applicable area group."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    canonical_group_id = str(group_id)
    if canonical_group_id not in analysis.area_result.applicable_group_ids:
        raise ValueError(
            f"{region_id}/{analysis_id} does not apply group "
            f"{canonical_group_id!r}"
        )
    layer_ids = tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id == canonical_group_id
        and layer.operation in CANONICAL_DISTANCE_OPERATIONS
        and layer.source.source_geometry_required
    )
    if not layer_ids:
        raise ValueError(
            f"{region_id}/{analysis_id} declares no preview-compatible "
            f"{canonical_group_id} layers"
        )
    return layer_ids


def public_wind_group_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical ids for migrated groups and adapter ids for the rest."""
    analysis = _validated_wind_analysis(region_id)
    group_ids: list[str] = []
    for group_id in analysis.groups:
        if group_id in {
            CANONICAL_ROADS_GROUP_ID,
            CANONICAL_POPULATION_GROUP_ID,
        }:
            group_ids.append(group_id)
            continue
        if group_id in {
            CANONICAL_NATURE_GROUP_ID,
            CANONICAL_CULTURE_GROUP_ID,
            CANONICAL_GRID_GROUP_ID,
        } and any(
            layer.group_id == group_id for layer in analysis.layers.values()
        ):
            group_ids.append(group_id)
            continue
        transitional_id = CANONICAL_TO_TRANSITIONAL_GROUP_ID.get(group_id)
        if transitional_id is not None:
            group_ids.append(transitional_id)
    return tuple(group_ids)


def canonical_wind_group_is_declared(
    region_id: str,
    group_id: str,
) -> bool:
    """Return whether a canonical group has manifest-declared layers."""
    analysis = _validated_wind_analysis(region_id)
    return any(
        layer.group_id == str(group_id)
        for layer in analysis.layers.values()
    )


def default_wind_layer_selection(region_id: str) -> dict[str, list[str]]:
    """Return the manifest startup request in current public group ids."""
    analysis = _validated_wind_analysis(region_id)
    if analysis.default_request is None:
        raise ValueError(f"{region_id}/wind has no default_request")

    selected: dict[str, list[str]] = {
        group_id: [] for group_id in public_wind_group_ids(region_id)
    }
    for layer_id in analysis.default_request.selected_layer_ids:
        layer = analysis.layers.get(layer_id)
        if layer is None:
            raise ValueError(
                f"{region_id}/wind default request references unknown layer: "
                f"{layer_id}"
            )
        public_group_id = layer.group_id
        if layer.group_id not in {
            CANONICAL_ROADS_GROUP_ID,
            CANONICAL_POPULATION_GROUP_ID,
            CANONICAL_NATURE_GROUP_ID,
            CANONICAL_CULTURE_GROUP_ID,
            CANONICAL_GRID_GROUP_ID,
        }:
            public_group_id = CANONICAL_TO_TRANSITIONAL_GROUP_ID.get(
                layer.group_id
            )
        if public_group_id is None:
            raise ValueError(
                f"{region_id}/wind default layer {layer_id} belongs to an "
                f"unsupported public group: {layer.group_id}"
            )
        selected.setdefault(public_group_id, []).append(layer_id)
    return selected


def vector_preview_layer_ids(
    region_id: str,
    analysis_id: str = "wind",
    group_id: str | None = None,
) -> tuple[str, ...]:
    """Return manifest layers that can produce a dynamic vector preview."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    applicable_group_ids = set(analysis.area_result.applicable_group_ids)
    requested_group_id = str(group_id) if group_id is not None else None
    if (
        requested_group_id is not None
        and requested_group_id not in applicable_group_ids
    ):
        raise ValueError(
            f"{region_id}/{analysis_id} does not apply group "
            f"{requested_group_id!r}"
        )
    return tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id in applicable_group_ids
        and (
            requested_group_id is None
            or layer.group_id == requested_group_id
        )
        and layer.operation in CANONICAL_DISTANCE_OPERATIONS
        and layer.source.source_geometry_required
    )


def analysis_area_group_preview(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
) -> VectorBufferPreview:
    """Build one exact manifest area-group geometry for map review."""

    requested = tuple(str(layer_id) for layer_id in layer_ids)
    if not requested:
        raise ValueError("An area-group preview requires at least one layer")
    allowed = set(
        analysis_group_layer_ids(
            region_id,
            analysis_id,
            canonical_group_id,
        )
    )
    unknown = set(requested) - allowed
    if unknown:
        raise ValueError(
            f"{region_id}/{analysis_id} has no {canonical_group_id} "
            f"preview layers: {sorted(unknown)}"
        )
    return build_area_group_preview(
        region=str(region_id),
        analysis=str(analysis_id),
        group_id=str(canonical_group_id),
        layers=requested,
        buffer_m=float(buffer_m),
    )


def vector_buffer_preview(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
) -> VectorBufferPreview:
    """Build one manifest-resolved preview for selected canonical layers."""
    analysis = _validated_wind_analysis(region_id)
    requested = tuple(str(layer_id) for layer_id in layer_ids)
    if not requested:
        raise ValueError("A vector preview requires at least one layer")
    unknown = set(requested) - set(analysis.layers)
    if unknown:
        raise ValueError(
            f"{region_id}/wind has no canonical preview layers: "
            f"{sorted(unknown)}"
        )
    region = load_region(str(region_id))
    native_crs = str(region.get("native_crs") or "")
    requested_layers = [analysis.layers[layer_id] for layer_id in requested]
    if all(layer.operation == "proximity_feasibility" for layer in requested_layers):
        group_ids = {layer.group_id for layer in requested_layers}
        if len(group_ids) != 1:
            raise ValueError(
                "A proximity preview requires one manifest-declared group"
            )
        return analysis_area_group_preview(
            region_id=str(region_id),
            analysis_id="wind",
            canonical_group_id=next(iter(group_ids)),
            layer_ids=requested,
            buffer_m=float(buffer_m),
        )
    return build_vector_buffer_preview(
        requested_layers,
        native_crs=native_crs,
        buffer_m=float(buffer_m),
    )


def canonical_wind_group_layer_ids(
    region_id: str,
    group_id: str,
) -> tuple[str, ...]:
    """Return one canonical group's layers in manifest order."""
    analysis = _validated_wind_analysis(region_id)
    layer_ids = tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id == str(group_id)
        and layer.operation in CANONICAL_DISTANCE_OPERATIONS
    )
    if not layer_ids:
        raise ValueError(
            f"{region_id}/wind declares no canonical {group_id} layers"
        )
    return layer_ids


def canonical_road_layer_ids(region_id: str) -> tuple[str, ...]:
    """Return road layers in manifest order for the active wind contract."""
    return canonical_wind_group_layer_ids(region_id, CANONICAL_ROADS_GROUP_ID)


def canonical_population_layer_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical population layers in manifest order."""
    return canonical_wind_group_layer_ids(
        region_id,
        CANONICAL_POPULATION_GROUP_ID,
    )


def canonical_nature_layer_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical nature layers in manifest order."""
    return canonical_wind_group_layer_ids(
        region_id,
        CANONICAL_NATURE_GROUP_ID,
    )


def canonical_culture_layer_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical culture layers in manifest order."""
    return canonical_wind_group_layer_ids(
        region_id,
        CANONICAL_CULTURE_GROUP_ID,
    )


def canonical_grid_layer_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical grid-infrastructure layers in manifest order."""
    return canonical_wind_group_layer_ids(
        region_id,
        CANONICAL_GRID_GROUP_ID,
    )


def analysis_group_control_contract(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
    *,
    public_group_id: str | None = None,
) -> WindGroupControlContract:
    """Build one public distance-group control from an area manifest."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    if analysis.ui is None:
        raise ValueError(f"{region_id}/{analysis_id} has no ui contract")
    group_ui = analysis.ui.groups.get(str(canonical_group_id))
    if group_ui is None:
        raise ValueError(
            f"{region_id}/{analysis_id} has no {canonical_group_id} "
            "ui descriptor"
        )
    parameter = analysis_group_buffer_parameter_contract(
        region_id,
        analysis_id,
        canonical_group_id,
    )
    if (
        parameter.minimum is None
        or parameter.maximum is None
        or parameter.step is None
    ):
        raise ValueError(
            f"{region_id}/{analysis_id} {canonical_group_id} buffer must "
            "declare "
            "minimum, maximum and step"
        )

    public_id = str(public_group_id or canonical_group_id)
    operations = {
        analysis.layers[layer_id].operation
        for layer_id in analysis_group_layer_ids(
            region_id,
            analysis_id,
            canonical_group_id,
        )
    }
    if len(operations) != 1:
        raise ValueError(
            f"{region_id}/{analysis_id} {canonical_group_id} layers must "
            "use one operation"
        )
    operation = operations.pop()
    analysis_kind = (
        "hard_exclusion"
        if operation == "hard_exclusion"
        else "proximity_feasibility"
        if operation == "proximity_feasibility"
        else "distance_conflict"
    )
    layer_controls: list[WindLayerControlContract] = []
    for layer_id in analysis_group_layer_ids(
        region_id,
        analysis_id,
        canonical_group_id,
    ):
        layer = analysis.layers[layer_id]
        if layer.ui is None:
            raise ValueError(
                f"{region_id}/{analysis_id} layer {layer_id} has no ui"
            )
        ready = True
        message = layer.ui.note
        try:
            validate_layer(layer)
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            ready = False
            message = f"{layer.ui.note} Datakällan är inte redo: {exc}"
        layer_controls.append(
            WindLayerControlContract(
                id=layer.id,
                group_id=public_id,
                label=layer.label,
                note=layer.ui.note,
                source_color=_hex_color_to_rgb(layer.ui.source_color),
                point_radius=layer.ui.point_radius,
                quality_flag=layer.ui.quality_flag,
                ready=ready,
                message=message,
            )
        )

    return WindGroupControlContract(
        id=public_id,
        canonical_id=str(canonical_group_id),
        label=group_ui.label,
        analysis_kind=analysis_kind,
        analysis_label=group_ui.analysis_label,
        analysis_min_m=int(parameter.minimum),
        analysis_max_m=int(parameter.maximum),
        analysis_step_m=int(parameter.step),
        analysis_default_m=int(parameter.default),
        blend_default=group_ui.blend_default,
        group_color=_hex_color_to_rgb(group_ui.group_color),
        interpretation=group_ui.interpretation,
        expanded_by_default=group_ui.expanded_by_default,
        layers=tuple(layer_controls),
    )


def wind_group_control_contract(
    region_id: str,
    canonical_group_id: str,
    *,
    public_group_id: str | None = None,
) -> WindGroupControlContract:
    """Build one public distance-group control from the wind manifest."""

    return analysis_group_control_contract(
        region_id,
        "wind",
        canonical_group_id,
        public_group_id=public_group_id,
    )


def roads_control_contract(region_id: str) -> WindGroupControlContract:
    """Build the complete public roads control contract from the manifest."""
    return wind_group_control_contract(
        region_id,
        CANONICAL_ROADS_GROUP_ID,
    )


def population_control_contract(region_id: str) -> WindGroupControlContract:
    """Expose canonical manifest-driven population controls."""
    return wind_group_control_contract(
        region_id,
        CANONICAL_POPULATION_GROUP_ID,
    )


def nature_control_contract(region_id: str) -> WindGroupControlContract:
    """Expose canonical manifest-driven nature controls."""
    return wind_group_control_contract(
        region_id,
        CANONICAL_NATURE_GROUP_ID,
    )


def culture_control_contract(region_id: str) -> WindGroupControlContract:
    """Expose canonical manifest-driven culture controls."""
    return wind_group_control_contract(
        region_id,
        CANONICAL_CULTURE_GROUP_ID,
    )


def grid_control_contract(region_id: str) -> WindGroupControlContract:
    """Expose canonical manifest-driven grid-infrastructure controls."""
    return wind_group_control_contract(
        region_id,
        CANONICAL_GRID_GROUP_ID,
    )


def analysis_source_geojson(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
    layer_id: str,
) -> dict:
    """Read one applicable analysis source through the provider resolver."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    if layer_id not in analysis_group_layer_ids(
        region_id,
        analysis_id,
        canonical_group_id,
    ):
        raise ValueError(
            f"{region_id}/{analysis_id} has no canonical "
            f"{canonical_group_id} "
            f"source: {layer_id}"
        )
    validated = validate_layer(analysis.layers[layer_id])
    source_path: Path = validated.assets.geojson_path
    with source_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(
            f"Canonical {canonical_group_id} source is not a GeoJSON "
            f"object: {layer_id}"
        )
    return payload


def wind_source_geojson(
    region_id: str,
    canonical_group_id: str,
    layer_id: str,
) -> dict:
    """Read one canonical wind source through the provider resolver."""

    return analysis_source_geojson(
        region_id,
        "wind",
        canonical_group_id,
        layer_id,
    )


def road_source_geojson(region_id: str, layer_id: str) -> dict:
    """Read one validated canonical road source through the provider resolver."""
    return wind_source_geojson(
        region_id,
        CANONICAL_ROADS_GROUP_ID,
        layer_id,
    )


def population_source_geojson(region_id: str, layer_id: str) -> dict:
    """Read one validated canonical population source."""
    return wind_source_geojson(
        region_id,
        CANONICAL_POPULATION_GROUP_ID,
        layer_id,
    )


def nature_source_geojson(region_id: str, layer_id: str) -> dict:
    """Read one validated canonical nature source."""
    return wind_source_geojson(
        region_id,
        CANONICAL_NATURE_GROUP_ID,
        layer_id,
    )


def culture_source_geojson(region_id: str, layer_id: str) -> dict:
    """Read one validated canonical culture source."""
    return wind_source_geojson(
        region_id,
        CANONICAL_CULTURE_GROUP_ID,
        layer_id,
    )


def grid_source_geojson(region_id: str, layer_id: str) -> dict:
    """Read one validated canonical grid-infrastructure source."""
    return wind_source_geojson(
        region_id,
        CANONICAL_GRID_GROUP_ID,
        layer_id,
    )


def analysis_group_buffer_parameter_contract(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
) -> ParameterContract:
    """Return one analysis group's shared manifest buffer contract."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    parameters: list[ParameterContract] = []
    for layer_id in analysis_group_layer_ids(
        region_id,
        analysis_id,
        canonical_group_id,
    ):
        layer = analysis.layers.get(layer_id)
        if layer is None:
            raise KeyError(
                f"{region_id}/{analysis_id} is missing canonical "
                f"{canonical_group_id} layer: {layer_id}"
            )
        if (
            layer.group_id != canonical_group_id
            or layer.operation not in CANONICAL_DISTANCE_OPERATIONS
        ):
            raise ValueError(
                f"{region_id}/{analysis_id} layer {layer_id} is not a "
                "canonical "
                f"{canonical_group_id} "
                "distance-based layer"
            )
        parameter = layer.parameters.get("buffer_m")
        if parameter is None:
            raise KeyError(
                f"{region_id}/{analysis_id} layer {layer_id} has no buffer_m"
            )
        parameters.append(parameter)

    signatures = {
        (
            item.value_type,
            item.unit,
            item.default,
            item.minimum,
            item.maximum,
            item.step,
        )
        for item in parameters
    }
    if len(signatures) != 1:
        raise ValueError(
            f"{region_id}/{analysis_id} {canonical_group_id} layers do not "
            "share one "
            "buffer contract"
        )
    return parameters[0]


def wind_group_buffer_parameter_contract(
    region_id: str,
    canonical_group_id: str,
) -> ParameterContract:
    """Return one canonical wind group's shared buffer contract."""

    return analysis_group_buffer_parameter_contract(
        region_id,
        "wind",
        canonical_group_id,
    )


def roads_buffer_parameter_contract(region_id: str) -> ParameterContract:
    """Return the shared manifest road-buffer contract."""
    return wind_group_buffer_parameter_contract(
        region_id,
        CANONICAL_ROADS_GROUP_ID,
    )


def wind_group_acceptance_frame(
    region_id: str,
    canonical_group_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt one manifest-selected distance group to V2 Final."""
    raw_requested_layers = tuple(str(value).strip() for value in layer_ids)
    if not raw_requested_layers:
        raise ValueError(
            f"A canonical {canonical_group_id} request requires at least one layer"
        )
    if any(not value for value in raw_requested_layers):
        raise ValueError(
            f"A canonical {canonical_group_id} request contains a blank layer id"
        )
    if len(raw_requested_layers) != len(set(raw_requested_layers)):
        raise ValueError(
            f"A canonical {canonical_group_id} request contains duplicate layer ids"
        )
    available_layers = canonical_wind_group_layer_ids(
        region_id,
        canonical_group_id,
    )
    requested_layer_set = set(raw_requested_layers)
    unknown_layers = requested_layer_set - set(available_layers)
    if unknown_layers:
        layer_kind = (
            "road"
            if canonical_group_id == CANONICAL_ROADS_GROUP_ID
            else canonical_group_id
        )
        raise ValueError(
            f"{region_id}/wind has no canonical {layer_kind} layers: "
            f"{sorted(unknown_layers)}"
        )
    requested_layers = tuple(
        layer_id
        for layer_id in available_layers
        if layer_id in requested_layer_set
    )

    requested_ids = tuple(str(value).strip() for value in analysis_cell_ids)
    if not requested_ids:
        raise ValueError(
            f"Canonical {canonical_group_id} requires a non-empty "
            "analysis-cell universe"
        )
    if any(not value for value in requested_ids):
        raise ValueError(
            f"Canonical {canonical_group_id} analysis-cell universe contains "
            "a blank id"
        )
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError(
            f"Canonical {canonical_group_id} analysis-cell universe contains "
            "duplicate ids"
        )

    result = run_analysis(
        str(region_id),
        "wind",
        list(requested_layers),
        {
            layer_id: {
                "buffer_m": float(buffer_m),
            }
            for layer_id in requested_layers
        },
        analysis_cell_ids=requested_ids,
        target_resolution=target_resolution,
    )
    group = next(
        (
            item
            for item in result.groups
            if item.group_id == canonical_group_id
        ),
        None,
    )
    if group is None:
        raise ValueError(
            f"Canonical result has no {canonical_group_id} group"
        )
    if tuple(group.layer_ids) != requested_layers:
        raise ValueError(
            f"Canonical {canonical_group_id} result does not preserve the "
            "requested layers: "
            f"{group.layer_ids}"
        )
    if group.cell_count != len(requested_ids) or len(group.cells) != len(
        requested_ids
    ):
        raise ValueError(
            f"Canonical {canonical_group_id} result does not cover the requested "
            f"analysis domain ({len(group.cells)}/{len(requested_ids)})"
        )

    frame = pd.DataFrame(
        (
            {
                "hex_id": cell.cell_id,
                "distance_m": cell.min_distance_m,
                "intersects": cell.any_intersection,
                "acceptance": cell.acceptance,
                "coverage_missing": cell.coverage_missing,
            }
            for cell in group.cells
        )
    )
    if frame["hex_id"].duplicated().any():
        raise ValueError(
            f"Canonical {canonical_group_id} result contains duplicate cells"
        )
    return frame.sort_values("hex_id").reset_index(drop=True)


def roads_acceptance_frame(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt one manifest-selected canonical roads result to V2 Final."""
    return wind_group_acceptance_frame(
        region_id,
        CANONICAL_ROADS_GROUP_ID,
        layer_ids,
        buffer_m,
        analysis_cell_ids,
        target_resolution,
    )


def population_acceptance_frame(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt canonical population distance results to V2 Final."""
    return wind_group_acceptance_frame(
        region_id,
        CANONICAL_POPULATION_GROUP_ID,
        layer_ids,
        buffer_m,
        analysis_cell_ids,
        target_resolution,
    )


def nature_acceptance_frame(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt canonical nature hard-exclusion results to V2 Final."""
    return wind_group_acceptance_frame(
        region_id,
        CANONICAL_NATURE_GROUP_ID,
        layer_ids,
        buffer_m,
        analysis_cell_ids,
        target_resolution,
    )


def culture_acceptance_frame(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt canonical culture hard-exclusion results to V2 Final."""
    return wind_group_acceptance_frame(
        region_id,
        CANONICAL_CULTURE_GROUP_ID,
        layer_ids,
        buffer_m,
        analysis_cell_ids,
        target_resolution,
    )


def grid_acceptance_frame(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt canonical grid proximity-feasibility results to V2 Final."""
    return wind_group_acceptance_frame(
        region_id,
        CANONICAL_GRID_GROUP_ID,
        layer_ids,
        buffer_m,
        analysis_cell_ids,
        target_resolution,
    )
