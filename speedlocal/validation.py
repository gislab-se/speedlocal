from __future__ import annotations

import re
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
    geometry_validation: str


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
    if contract.default_request is None:
        raise ValueError("Analysis default_request is required")
    selected_layer_ids = contract.default_request.selected_layer_ids
    if len(selected_layer_ids) != len(set(selected_layer_ids)):
        raise ValueError(
            "Analysis default_request selected_layer_ids must not contain duplicates"
        )
    unknown_default_layers = set(selected_layer_ids) - set(contract.layers)
    if unknown_default_layers:
        raise ValueError(
            "Analysis default_request selects undeclared layers: "
            f"{sorted(unknown_default_layers)}"
        )

    domain = contract.analysis_domain
    if domain is not None:
        if (
            not domain.provider.strip()
            or not domain.path.strip()
            or not domain.id_field.strip()
        ):
            raise ValueError("Analysis domain provider, path, and id field are required")
        if domain.cell_kind != "h3":
            raise ValueError(
                f"Unsupported analysis-domain cell kind: {domain.cell_kind}"
            )
        if domain.resolution < 0 or domain.resolution > 15:
            raise ValueError(
                f"Invalid H3 analysis-domain resolution: {domain.resolution}"
            )
        if domain.expected_cell_count <= 0:
            raise ValueError("Analysis domain expected cell count must be positive")
        if not domain.area_field.strip():
            raise ValueError("Analysis domain area field is required")
        if domain.area_unit not in {"m2", "km2"}:
            raise ValueError(
                f"Unsupported analysis-domain area unit: {domain.area_unit}"
            )
        for resolution, rollup in domain.rollups.items():
            if resolution != rollup.resolution:
                raise ValueError(
                    f"Analysis-domain rollup key R{resolution} does not match "
                    f"its declared R{rollup.resolution}"
                )
            if (
                not rollup.provider.strip()
                or not rollup.path.strip()
                or not rollup.id_field.strip()
            ):
                raise ValueError(
                    f"Analysis-domain R{resolution} rollup provider, path, "
                    "and id field are required"
                )
            if resolution < 0 or resolution > 15:
                raise ValueError(
                    f"Invalid H3 analysis-domain rollup resolution: {resolution}"
                )
            if resolution >= domain.resolution:
                raise ValueError(
                    f"Analysis-domain rollup R{resolution} must be coarser "
                    f"than the R{domain.resolution} source domain"
                )
            if rollup.expected_cell_count <= 0:
                raise ValueError(
                    f"Analysis-domain R{resolution} expected cell count "
                    "must be positive"
                )
            if not rollup.area_field.strip():
                raise ValueError(
                    f"Analysis-domain R{resolution} area field is required"
                )
            if rollup.area_unit not in {"m2", "km2"}:
                raise ValueError(
                    "Unsupported analysis-domain "
                    f"R{resolution} area unit: {rollup.area_unit}"
                )
    unknown_groups = set(contract.groups) - set(STANDARD_GROUP_IDS)
    if unknown_groups:
        raise ValueError(f"Unknown standard groups: {sorted(unknown_groups)}")
    if contract.ui is not None:
        unknown_ui_groups = set(contract.ui.groups) - set(contract.groups)
        if unknown_ui_groups:
            raise ValueError(
                "Analysis ui describes undeclared groups: "
                f"{sorted(unknown_ui_groups)}"
            )
        for group_ui in contract.ui.groups.values():
            if not all(
                value.strip()
                for value in (
                    group_ui.label,
                    group_ui.analysis_label,
                    group_ui.interpretation,
                )
            ):
                raise ValueError(
                    f"Analysis ui group {group_ui.id} has blank copy"
                )
            if not 0 <= group_ui.blend_default <= 100:
                raise ValueError(
                    f"Analysis ui group {group_ui.id} blend_default must be 0-100"
                )
            if re.fullmatch(r"#[0-9a-fA-F]{6}", group_ui.group_color) is None:
                raise ValueError(
                    f"Analysis ui group {group_ui.id} has invalid group_color"
                )
    for layer in contract.layers.values():
        if layer.group_id not in contract.groups:
            raise ValueError(f"Layer {layer.id} uses undeclared group {layer.group_id}")
        if layer.operation not in SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation for {layer.id}: {layer.operation}")
        unknown_families = set(layer.source.expected_geometry_families) - SUPPORTED_GEOMETRY_FAMILIES
        if unknown_families:
            raise ValueError(f"Unsupported geometry families for {layer.id}: {sorted(unknown_families)}")
        coverage = layer.source.distance_coverage
        source_resolution = layer.source.distance_h3_resolution
        if (
            domain is not None
            and source_resolution is not None
            and domain.resolution > source_resolution
        ):
            raise ValueError(
                f"Layer {layer.id} analysis domain R{domain.resolution} is "
                f"finer than its R{source_resolution} distance source"
            )
        if coverage.mode == "declared_sparse":
            if domain is None:
                raise ValueError(
                    f"Layer {layer.id} declares sparse distance coverage "
                    "without an analysis domain"
                )
            if source_resolution is None:
                raise ValueError(
                    f"Layer {layer.id} declares sparse distance coverage "
                    "without distance_h3_resolution"
                )
            expected_targets = {
                domain.resolution: domain.expected_cell_count,
                **{
                    resolution: rollup.expected_cell_count
                    for resolution, rollup in domain.rollups.items()
                },
            }
            if set(coverage.targets) != set(expected_targets):
                raise ValueError(
                    f"Layer {layer.id} sparse coverage targets must exactly "
                    "match the analysis-domain resolutions"
                )
            for resolution, expected_cell_count in expected_targets.items():
                target = coverage.targets[resolution]
                if resolution > source_resolution:
                    raise ValueError(
                        f"Layer {layer.id} sparse coverage R{resolution} is "
                        f"finer than its R{source_resolution} distance source"
                    )
                if target.target_cell_count != expected_cell_count:
                    raise ValueError(
                        f"Layer {layer.id} sparse coverage R{resolution} "
                        "target count does not match the analysis domain"
                    )
        if contract.ui is not None and layer.group_id in contract.ui.groups:
            if layer.ui is None:
                raise ValueError(
                    f"Layer {layer.id} needs ui metadata for described group "
                    f"{layer.group_id}"
                )
            if not layer.ui.note.strip():
                raise ValueError(f"Layer {layer.id} ui note is blank")
            if re.fullmatch(r"#[0-9a-fA-F]{6}", layer.ui.source_color) is None:
                raise ValueError(f"Layer {layer.id} has invalid ui source_color")
            if layer.ui.point_radius <= 0:
                raise ValueError(f"Layer {layer.id} ui point_radius must be positive")
            if layer.ui.quality_flag not in {None, "caution"}:
                raise ValueError(
                    f"Layer {layer.id} ui quality_flag must be 'caution' or null"
                )


def validate_layer(layer: LayerContract) -> ValidatedLayer:
    assets = resolve_layer_assets(layer)
    if assets.manifest_status != "ok":
        raise ValueError(f"Layer {layer.id} asset status is {assets.manifest_status!r}")
    if not assets.geojson_path.is_file() or not assets.distance_path.is_file():
        raise FileNotFoundError(f"Layer {layer.id} runtime assets are incomplete")
    try:
        detected = detect_geojson_geometry_family(
            assets.geojson_path,
            layer.source.geometry_collection_policy,
        )
        geometry_validation = "detected"
    except ValueError:
        if layer.source.source_geometry_required:
            raise
        if len(layer.source.expected_geometry_families) != 1:
            raise ValueError(
                f"Layer {layer.id} needs exactly one declared geometry family "
                "when source geometry is optional"
            )
        detected = layer.source.expected_geometry_families[0]
        geometry_validation = "declared_from_validated_distance_artifact"
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
        geometry_validation=geometry_validation,
    )
