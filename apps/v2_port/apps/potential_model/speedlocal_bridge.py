from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from speedlocal.catalogs import load_analysis, load_region
from speedlocal.contracts import AnalysisContract, ParameterContract
from speedlocal.engine import run_analysis
from speedlocal.geometry import VectorBufferPreview, build_vector_buffer_preview
from speedlocal.sources import resolve_analysis_domain_cell_areas_km2
from speedlocal.validation import validate_contract


LEGACY_ROADS_GROUP_ID = "transport"
CANONICAL_ROADS_GROUP_ID = "roads"
CANONICAL_ROADS_LAYER_IDS = ("roads_medium", "roads_large")
MIGRATED_ROADS_LAYER_ID = "roads_large"
CANONICAL_TO_LEGACY_GROUP_ID = {
    "roads": "transport",
    "population": "settlement",
    "nature": "protected",
    "culture": "culture",
    "grid_infrastructure": "electrical",
}


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


def transitional_public_legacy_group_ids(region_id: str) -> tuple[str, ...]:
    """Map the current product-group whitelist to unmigrated registry ids."""
    analysis = _validated_wind_analysis(region_id)
    return tuple(
        CANONICAL_TO_LEGACY_GROUP_ID[group_id]
        for group_id in analysis.groups
        if group_id in CANONICAL_TO_LEGACY_GROUP_ID
    )


def default_wind_layer_selection(region_id: str) -> dict[str, list[str]]:
    """Adapt the canonical manifest's startup request to legacy registry ids."""
    analysis = _validated_wind_analysis(region_id)
    if analysis.default_request is None:
        raise ValueError(f"{region_id}/wind has no default_request")

    selected: dict[str, list[str]] = {
        legacy_group_id: []
        for legacy_group_id in CANONICAL_TO_LEGACY_GROUP_ID.values()
    }
    for layer_id in analysis.default_request.selected_layer_ids:
        layer = analysis.layers.get(layer_id)
        if layer is None:
            raise ValueError(
                f"{region_id}/wind default request references unknown layer: "
                f"{layer_id}"
            )
        legacy_group_id = CANONICAL_TO_LEGACY_GROUP_ID.get(layer.group_id)
        if legacy_group_id is None:
            raise ValueError(
                f"{region_id}/wind default layer {layer_id} belongs to an "
                f"unsupported public group: {layer.group_id}"
            )
        selected.setdefault(legacy_group_id, []).append(layer_id)
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


def roads_buffer_parameter_contract(region_id: str) -> ParameterContract:
    """Return the one shared road-buffer contract used by the transitional UI."""
    analysis = _validated_wind_analysis(region_id)
    parameters: list[ParameterContract] = []
    for layer_id in CANONICAL_ROADS_LAYER_IDS:
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


def roads_large_acceptance_frame(
    region_id: str,
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt canonical display-resolution results to V2 Final."""
    requested_ids = tuple(str(value).strip() for value in analysis_cell_ids)
    if not requested_ids:
        raise ValueError("roads_large requires a non-empty analysis-cell universe")
    if any(not value for value in requested_ids):
        raise ValueError("roads_large analysis-cell universe contains a blank id")
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("roads_large analysis-cell universe contains duplicate ids")

    result = run_analysis(
        str(region_id),
        "wind",
        [MIGRATED_ROADS_LAYER_ID],
        {
            MIGRATED_ROADS_LAYER_ID: {
                "buffer_m": float(buffer_m),
            }
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
        raise ValueError("Canonical roads_large result has no roads group")
    if group.cell_count != len(requested_ids) or len(group.cells) != len(
        requested_ids
    ):
        raise ValueError(
            "Canonical roads_large result does not cover the requested "
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
        raise ValueError("Canonical roads_large result contains duplicate cells")
    return frame.sort_values("hex_id").reset_index(drop=True)
