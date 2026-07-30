from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from speedlocal.catalogs import load_analysis
from speedlocal.contracts import ParameterContract
from speedlocal.engine import run_analysis
from speedlocal.sources import resolve_analysis_domain_cell_ids


LEGACY_ROADS_GROUP_ID = "transport"
CANONICAL_ROADS_GROUP_ID = "roads"
CANONICAL_ROADS_LAYER_IDS = ("roads_medium", "roads_large")
MIGRATED_ROADS_LAYER_ID = "roads_large"


def roads_buffer_parameter_contract(region_id: str) -> ParameterContract:
    """Return the one shared road-buffer contract used by the transitional UI."""
    analysis = load_analysis(str(region_id), "wind")
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
) -> pd.DataFrame:
    """Adapt canonical R7 cell results to the V2 Final fast-distance frame."""
    requested_ids = tuple(str(value).strip() for value in analysis_cell_ids)
    if not requested_ids:
        raise ValueError("roads_large requires a non-empty analysis-cell universe")
    if any(not value for value in requested_ids):
        raise ValueError("roads_large analysis-cell universe contains a blank id")
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("roads_large analysis-cell universe contains duplicate ids")

    analysis = load_analysis(str(region_id), "wind")
    canonical_ids = resolve_analysis_domain_cell_ids(analysis)
    if len(requested_ids) != len(canonical_ids) or set(requested_ids) != set(
        canonical_ids
    ):
        requested_set = set(requested_ids)
        canonical_set = set(canonical_ids)
        raise ValueError(
            "V2 Final display cells do not match the canonical analysis domain: "
            f"missing={len(canonical_set - requested_set)}, "
            f"unexpected={len(requested_set - canonical_set)}"
        )
    result = run_analysis(
        str(region_id),
        "wind",
        [MIGRATED_ROADS_LAYER_ID],
        {
            MIGRATED_ROADS_LAYER_ID: {
                "buffer_m": float(buffer_m),
            }
        },
        analysis_cell_ids=canonical_ids,
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
    if group.cell_count != len(canonical_ids) or len(group.cells) != len(
        canonical_ids
    ):
        raise ValueError(
            "Canonical roads_large result does not cover the requested "
            f"analysis domain ({len(group.cells)}/{len(canonical_ids)})"
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
