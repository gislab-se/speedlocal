from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from speedlocal.catalogs import load_analysis, load_region
from speedlocal.contracts import AnalysisContract, ParameterContract
from speedlocal.engine import run_analysis
from speedlocal.geometry import VectorBufferPreview, build_vector_buffer_preview
from speedlocal.sources import resolve_analysis_domain_cell_areas_km2
from speedlocal.validation import validate_contract, validate_layer


CANONICAL_ROADS_GROUP_ID = "roads"
CANONICAL_TO_TRANSITIONAL_GROUP_ID = {
    "population": "settlement",
    "nature": "protected",
    "culture": "culture",
    "grid_infrastructure": "electrical",
}


@dataclass(frozen=True)
class RoadLayerControlContract:
    id: str
    group_id: str
    label: str
    note: str
    source_color: tuple[int, int, int]
    point_radius: int
    ready: bool
    message: str


@dataclass(frozen=True)
class RoadGroupControlContract:
    id: str
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
    layers: tuple[RoadLayerControlContract, ...]


def _hex_color_to_rgb(value: str) -> tuple[int, int, int]:
    normalized = str(value).strip().removeprefix("#")
    if len(normalized) != 6:
        raise ValueError(f"Invalid manifest UI color: {value!r}")
    return tuple(
        int(normalized[offset : offset + 2], 16)
        for offset in (0, 2, 4)
    )


def _validated_wind_analysis(region_id: str) -> AnalysisContract:
    analysis = load_analysis(str(region_id), "wind")
    validate_contract(analysis)
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


def public_wind_group_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical ids for migrated groups and adapter ids for the rest."""
    analysis = _validated_wind_analysis(region_id)
    group_ids: list[str] = []
    for group_id in analysis.groups:
        if group_id == CANONICAL_ROADS_GROUP_ID:
            group_ids.append(group_id)
            continue
        transitional_id = CANONICAL_TO_TRANSITIONAL_GROUP_ID.get(group_id)
        if transitional_id is not None:
            group_ids.append(transitional_id)
    return tuple(group_ids)


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
        public_group_id = (
            CANONICAL_ROADS_GROUP_ID
            if layer.group_id == CANONICAL_ROADS_GROUP_ID
            else CANONICAL_TO_TRANSITIONAL_GROUP_ID.get(layer.group_id)
        )
        if public_group_id is None:
            raise ValueError(
                f"{region_id}/wind default layer {layer_id} belongs to an "
                f"unsupported public group: {layer.group_id}"
            )
        selected.setdefault(public_group_id, []).append(layer_id)
    return selected


def vector_preview_layer_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical layers that can produce a dynamic vector preview."""
    analysis = _validated_wind_analysis(region_id)
    return tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.operation == "distance_exclusion"
        and layer.source.source_geometry_required
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
    return build_vector_buffer_preview(
        [analysis.layers[layer_id] for layer_id in requested],
        native_crs=native_crs,
        buffer_m=float(buffer_m),
    )


def canonical_road_layer_ids(region_id: str) -> tuple[str, ...]:
    """Return road layers in manifest order for the active wind contract."""
    analysis = _validated_wind_analysis(region_id)
    layer_ids = tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id == CANONICAL_ROADS_GROUP_ID
        and layer.operation == "distance_exclusion"
    )
    if not layer_ids:
        raise ValueError(f"{region_id}/wind declares no canonical road layers")
    return layer_ids


def roads_control_contract(region_id: str) -> RoadGroupControlContract:
    """Build the complete public roads control contract from the manifest."""
    analysis = _validated_wind_analysis(region_id)
    if analysis.ui is None:
        raise ValueError(f"{region_id}/wind has no ui contract")
    group_ui = analysis.ui.groups.get(CANONICAL_ROADS_GROUP_ID)
    if group_ui is None:
        raise ValueError(f"{region_id}/wind has no roads ui descriptor")
    parameter = roads_buffer_parameter_contract(region_id)
    if (
        parameter.minimum is None
        or parameter.maximum is None
        or parameter.step is None
    ):
        raise ValueError(
            f"{region_id}/wind roads buffer must declare minimum, maximum and step"
        )

    layer_controls: list[RoadLayerControlContract] = []
    for layer_id in canonical_road_layer_ids(region_id):
        layer = analysis.layers[layer_id]
        if layer.ui is None:
            raise ValueError(f"{region_id}/wind layer {layer_id} has no ui")
        ready = True
        message = layer.ui.note
        try:
            validate_layer(layer)
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            ready = False
            message = f"{layer.ui.note} Datakällan är inte redo: {exc}"
        layer_controls.append(
            RoadLayerControlContract(
                id=layer.id,
                group_id=CANONICAL_ROADS_GROUP_ID,
                label=layer.label,
                note=layer.ui.note,
                source_color=_hex_color_to_rgb(layer.ui.source_color),
                point_radius=layer.ui.point_radius,
                ready=ready,
                message=message,
            )
        )

    return RoadGroupControlContract(
        id=CANONICAL_ROADS_GROUP_ID,
        label=group_ui.label,
        analysis_kind="distance_conflict",
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


def road_source_geojson(region_id: str, layer_id: str) -> dict:
    """Read one validated canonical road source through the provider resolver."""
    analysis = _validated_wind_analysis(region_id)
    if layer_id not in canonical_road_layer_ids(region_id):
        raise ValueError(
            f"{region_id}/wind has no canonical road source: {layer_id}"
        )
    validated = validate_layer(analysis.layers[layer_id])
    source_path: Path = validated.assets.geojson_path
    with source_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Canonical road source is not a GeoJSON object: {layer_id}")
    return payload


def roads_buffer_parameter_contract(region_id: str) -> ParameterContract:
    """Return the shared manifest road-buffer contract."""
    analysis = _validated_wind_analysis(region_id)
    parameters: list[ParameterContract] = []
    for layer_id in canonical_road_layer_ids(region_id):
        layer = analysis.layers.get(layer_id)
        if layer is None:
            raise KeyError(
                f"{region_id}/wind is missing canonical road layer: {layer_id}"
            )
        if (
            layer.group_id != CANONICAL_ROADS_GROUP_ID
            or layer.operation != "distance_exclusion"
        ):
            raise ValueError(
                f"{region_id}/wind layer {layer_id} is not a canonical road "
                "distance-exclusion layer"
            )
        parameter = layer.parameters.get("buffer_m")
        if parameter is None:
            raise KeyError(f"{region_id}/wind layer {layer_id} has no buffer_m")
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
            f"{region_id}/wind road layers do not share one buffer contract"
        )
    return parameters[0]


def roads_acceptance_frame(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt one manifest-selected canonical roads result to V2 Final."""
    raw_requested_layers = tuple(str(value).strip() for value in layer_ids)
    if not raw_requested_layers:
        raise ValueError("A canonical roads request requires at least one layer")
    if any(not value for value in raw_requested_layers):
        raise ValueError("A canonical roads request contains a blank layer id")
    if len(raw_requested_layers) != len(set(raw_requested_layers)):
        raise ValueError("A canonical roads request contains duplicate layer ids")
    available_layers = canonical_road_layer_ids(region_id)
    requested_layer_set = set(raw_requested_layers)
    unknown_layers = requested_layer_set - set(available_layers)
    if unknown_layers:
        raise ValueError(
            f"{region_id}/wind has no canonical road layers: "
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
            "Canonical roads require a non-empty analysis-cell universe"
        )
    if any(not value for value in requested_ids):
        raise ValueError("Canonical roads analysis-cell universe contains a blank id")
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError(
            "Canonical roads analysis-cell universe contains duplicate ids"
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
            if item.group_id == CANONICAL_ROADS_GROUP_ID
        ),
        None,
    )
    if group is None:
        raise ValueError("Canonical roads result has no roads group")
    if tuple(group.layer_ids) != requested_layers:
        raise ValueError(
            "Canonical roads result does not preserve the requested layers: "
            f"{group.layer_ids}"
        )
    if group.cell_count != len(requested_ids) or len(group.cells) != len(
        requested_ids
    ):
        raise ValueError(
            "Canonical roads result does not cover the requested "
            f"analysis domain ({len(group.cells)}/{len(requested_ids)})"
        )

    frame = pd.DataFrame(
        (
            {
                "hex_id": cell.cell_id,
                "distance_m": cell.min_distance_m,
                "intersects": cell.any_intersection,
                "acceptance": cell.acceptance,
            }
            for cell in group.cells
        )
    )
    if frame["hex_id"].duplicated().any():
        raise ValueError("Canonical roads result contains duplicate cells")
    return frame.sort_values("hex_id").reset_index(drop=True)
