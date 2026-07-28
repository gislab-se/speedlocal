from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    STANDARD_GROUP_IDS,
    SUPPORTED_GEOMETRY_FAMILIES,
    SUPPORTED_OPERATIONS,
    AnalysisContract,
    LayerContract,
)
from .sources import LayerAssets, detect_geojson_geometry_family, resolve_layer_assets


@dataclass(frozen=True)
class ValidatedLayer:
    contract: LayerContract
    assets: LayerAssets
    geometry_family: str
    processing_adapter: str


def select_processing_adapter(
    group_id: str,
    geometry_family: str,
    data_representation: str = "auto",
) -> str:
    """Select common processing from data shape, never from a region id."""
    if group_id == "population":
        if data_representation == "grid":
            if geometry_family not in {"point", "polygon"}:
                raise ValueError("Population grids must be represented by points or polygons")
            return "population_grid"
        if geometry_family == "point":
            return "population_points"
        if geometry_family == "polygon":
            return "population_polygons"
        raise ValueError(f"Unsupported population geometry: {geometry_family}")
    if group_id == "roads" and geometry_family == "line":
        return "line_distance"
    return f"{geometry_family}_generic"


def validate_contract(contract: AnalysisContract) -> None:
    unknown_groups = set(contract.groups) - set(STANDARD_GROUP_IDS)
    if unknown_groups:
        raise ValueError(f"Unknown standard groups: {sorted(unknown_groups)}")
    for layer in contract.layers.values():
        if layer.group_id not in contract.groups:
            raise ValueError(f"Layer {layer.id} uses undeclared group {layer.group_id}")
        if layer.operation not in SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation for {layer.id}: {layer.operation}")
        unknown_families = set(layer.source.expected_geometry_families) - SUPPORTED_GEOMETRY_FAMILIES
        if unknown_families:
            raise ValueError(f"Unsupported geometry families for {layer.id}: {sorted(unknown_families)}")


def validate_layer(layer: LayerContract) -> ValidatedLayer:
    assets = resolve_layer_assets(layer)
    if assets.manifest_status != "ok":
        raise ValueError(f"Layer {layer.id} asset status is {assets.manifest_status!r}")
    if not assets.geojson_path.is_file() or not assets.distance_path.is_file():
        raise FileNotFoundError(f"Layer {layer.id} runtime assets are incomplete")
    detected = detect_geojson_geometry_family(assets.geojson_path)
    if detected not in layer.source.expected_geometry_families:
        raise ValueError(
            f"Layer {layer.id} geometry is {detected}; expected {layer.source.expected_geometry_families}"
        )
    if assets.declared_geometry_family not in {"unknown", detected}:
        raise ValueError(
            f"Layer {layer.id} asset manifest says {assets.declared_geometry_family}, data says {detected}"
        )
    adapter = select_processing_adapter(
        layer.group_id,
        detected,
        layer.source.data_representation,
    )
    return ValidatedLayer(
        contract=layer,
        assets=assets,
        geometry_family=detected,
        processing_adapter=adapter,
    )
