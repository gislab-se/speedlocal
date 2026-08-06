from __future__ import annotations

import math
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

    area_result = contract.area_result
    if area_result is not None:
        if area_result.technology not in {"wind", "solar"}:
            raise ValueError(
                "Analysis area_result technology must be 'wind' or 'solar'"
            )
        applicable_group_ids = area_result.applicable_group_ids
        if not applicable_group_ids:
            raise ValueError(
                "Analysis area_result applicable_group_ids must not be empty"
            )
        if len(applicable_group_ids) != len(set(applicable_group_ids)):
            raise ValueError(
                "Analysis area_result applicable_group_ids must not contain duplicates"
            )
        unknown_area_groups = set(applicable_group_ids) - set(contract.groups)
        if unknown_area_groups:
            raise ValueError(
                "Analysis area_result contains undeclared groups: "
                f"{sorted(unknown_area_groups)}"
            )
        if area_result.restriction_combination != "geometry_union":
            raise ValueError(
                "Analysis area_result restriction_combination must be "
                "'geometry_union'"
            )
        if area_result.operation_order != "feasibility_then_exclusion":
            raise ValueError(
                "Analysis area_result operation_order must be "
                "'feasibility_then_exclusion'"
            )
        if area_result.denominator != "eligible_surface":
            raise ValueError(
                "Analysis area_result denominator must be 'eligible_surface'"
            )
        if area_result.geometry_semantics != "exact_vector_clip":
            raise ValueError(
                "Analysis area_result geometry_semantics must be "
                "'exact_vector_clip'"
            )
        if contract.analysis_domain is None:
            raise ValueError(
                "Analysis area_result requires an analysis-domain contract"
            )
        surface_id = area_result.eligible_surface_id.strip()
        if not surface_id:
            raise ValueError(
                "Analysis area_result eligible_surface_id is required"
            )
        surface = contract.eligible_surfaces.get(surface_id)
        if surface is None:
            raise ValueError(
                "Analysis area_result references an undeclared eligible "
                f"surface: {surface_id}"
            )
        if area_result.technology not in surface.technologies:
            raise ValueError(
                f"Eligible surface {surface_id} does not support "
                f"{area_result.technology}"
            )

    distributed_generation = contract.distributed_generation
    if distributed_generation is not None:
        rooftop = distributed_generation.rooftop_solar
        if rooftop is not None:
            if area_result is None or area_result.technology != "solar":
                raise ValueError(
                    "Rooftop solar requires a solar area-result contract"
                )
            if rooftop.status != "planning_proxy":
                raise ValueError(
                    "Rooftop-solar status must be 'planning_proxy'"
                )
            if rooftop.technology_key != "solar":
                raise ValueError(
                    "Rooftop-solar technology_key must be 'solar'"
                )
            if rooftop.panel_area_m2_per_person.unit != "m2/person":
                raise ValueError(
                    "Rooftop-solar panel area must use m2/person"
                )
            if any(
                value is None
                for value in (
                    rooftop.panel_area_m2_per_person.minimum,
                    rooftop.panel_area_m2_per_person.maximum,
                    rooftop.panel_area_m2_per_person.step,
                )
            ):
                raise ValueError(
                    "Rooftop-solar panel area must declare min, max, and step"
                )
            panel_parameter = rooftop.panel_area_m2_per_person
            if (
                float(panel_parameter.minimum) < 0.0
                or float(panel_parameter.default) < 0.0
                or float(panel_parameter.maximum) <= 0.0
                or float(panel_parameter.step) <= 0.0
            ):
                raise ValueError(
                    "Rooftop-solar panel area must use a non-negative range "
                    "and a positive maximum and step"
                )
            if contract.analysis_domain is None:
                raise ValueError(
                    "Rooftop solar requires an analysis-domain contract"
                )
            if (
                rooftop.population_source.analysis_h3_resolution
                != contract.analysis_domain.resolution
            ):
                raise ValueError(
                    "Rooftop-solar population analysis resolution must match "
                    "the solar analysis domain"
                )
            map_review = rooftop.map_review
            if map_review.canonical_group_id not in (
                area_result.applicable_group_ids
            ):
                raise ValueError(
                    "Rooftop-solar map review must reference an applicable "
                    "solar group"
                )
            unknown_review_layers = set(map_review.layer_ids) - set(
                contract.layers
            )
            if unknown_review_layers:
                raise ValueError(
                    "Rooftop-solar map review references unknown layers: "
                    f"{sorted(unknown_review_layers)}"
                )
            for layer_id in map_review.layer_ids:
                layer = contract.layers[layer_id]
                if layer.group_id != map_review.canonical_group_id:
                    raise ValueError(
                        "Rooftop-solar map-review layer belongs to the wrong "
                        f"group: {layer_id}"
                    )
                buffer_parameter = layer.parameters.get("buffer_m")
                if buffer_parameter is None:
                    raise ValueError(
                        "Rooftop-solar map-review layer has no canonical "
                        f"buffer parameter: {layer_id}"
                    )
            expected_domain_resolutions = {
                contract.analysis_domain.resolution,
                *contract.analysis_domain.rollups,
            }
            declared_domain_totals = (
                rooftop.population_source.expected_analysis_domain_totals
            )
            if set(declared_domain_totals) != expected_domain_resolutions:
                raise ValueError(
                    "Rooftop-solar mapped population totals must cover the "
                    "analysis domain and every declared rollup"
                )
            canonical_mapped_total = declared_domain_totals[
                contract.analysis_domain.resolution
            ]
            if any(
                not math.isclose(
                    total,
                    canonical_mapped_total,
                    rel_tol=0.0,
                    abs_tol=1e-6,
                )
                for total in declared_domain_totals.values()
            ):
                raise ValueError(
                    "Rooftop-solar mapped population must clip at the "
                    "canonical analysis resolution before parent rollup"
                )
            accounting = rooftop.accounting
            if not accounting.cap_at_solar_target:
                raise ValueError(
                    "Rooftop-solar accounting must cap output at the solar target"
                )
            if accounting.affects_geographic_potential:
                raise ValueError(
                    "Rooftop solar must not affect geographic potential"
                )
            if accounting.adds_establishment_candidates:
                raise ValueError(
                    "Rooftop solar must not add establishment candidates"
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
    for surface_id, surface in contract.eligible_surfaces.items():
        if surface.id != surface_id or not surface_id.strip():
            raise ValueError(
                "Eligible-surface ids must be non-blank and match their keys"
            )
        if not surface.label.strip():
            raise ValueError(f"Eligible surface {surface_id} label is required")
        if (
            not surface.technologies
            or len(surface.technologies) != len(set(surface.technologies))
            or any(item not in {"wind", "solar"} for item in surface.technologies)
        ):
            raise ValueError(
                f"Eligible surface {surface_id} technologies must be unique "
                "wind/solar ids"
            )
        if surface.geometry_operation != "intersection":
            raise ValueError(
                f"Eligible surface {surface_id} geometry_operation must be "
                "'intersection'"
            )
        if surface.surface_scope not in {
            "onshore_land",
            "offshore_water",
            "land_and_water",
        }:
            raise ValueError(
                f"Eligible surface {surface_id} has unsupported surface_scope"
            )
        if surface.water_policy not in {
            "exclude_sea_retain_inland_water",
            "exclude_all_water",
            "include_water",
        }:
            raise ValueError(
                f"Eligible surface {surface_id} has unsupported water_policy"
            )
        if surface.outside_region_policy != "exclude":
            raise ValueError(
                f"Eligible surface {surface_id} outside_region_policy must "
                "be 'exclude'"
            )
        if surface.source.geometry_family != "polygon":
            raise ValueError(
                f"Eligible surface {surface_id} source must be polygonal"
            )
        for label, value in (
            ("source provider", surface.source.provider),
            ("source path", surface.source.path),
            ("provider", surface.provider),
            ("path", surface.path),
            ("id field", surface.id_field),
            ("area field", surface.area_field),
        ):
            if not value.strip():
                raise ValueError(
                    f"Eligible surface {surface_id} {label} is required"
                )
        for label, digest in (
            ("source", surface.source.sha256),
            ("R" + str(surface.resolution), surface.sha256),
        ):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} {label} sha256 is invalid"
                )
        if surface.cell_kind != "h3":
            raise ValueError(
                f"Eligible surface {surface_id} cell_kind must be 'h3'"
            )
        if surface.resolution < 0 or surface.resolution > 15:
            raise ValueError(
                f"Eligible surface {surface_id} resolution is invalid"
            )
        if surface.area_unit not in {"m2", "km2"}:
            raise ValueError(
                f"Eligible surface {surface_id} area unit is invalid"
            )
        if surface.expected_cell_count <= 0:
            raise ValueError(
                f"Eligible surface {surface_id} cell count must be positive"
            )
        if (
            not math.isfinite(surface.expected_total_area_km2)
            or surface.expected_total_area_km2 <= 0.0
        ):
            raise ValueError(
                f"Eligible surface {surface_id} total area must be positive"
            )
        if domain is None:
            raise ValueError(
                f"Eligible surface {surface_id} requires an analysis domain"
            )
        if (
            surface.resolution != domain.resolution
            or surface.expected_cell_count > domain.expected_cell_count
        ):
            raise ValueError(
                f"Eligible surface {surface_id} must be a subset of the "
                "canonical analysis cells at the same resolution"
            )
        if set(surface.rollups) != set(domain.rollups):
            raise ValueError(
                f"Eligible surface {surface_id} rollups must match the "
                "analysis domain"
            )
        for resolution, rollup in surface.rollups.items():
            if resolution != rollup.resolution:
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} key mismatch"
                )
            if resolution >= surface.resolution:
                raise ValueError(
                    f"Eligible surface {surface_id} rollups must be coarser "
                    f"than R{surface.resolution}"
                )
            for label, value in (
                ("provider", rollup.provider),
                ("path", rollup.path),
                ("id field", rollup.id_field),
                ("area field", rollup.area_field),
            ):
                if not value.strip():
                    raise ValueError(
                        f"Eligible surface {surface_id} R{resolution} "
                        f"{label} is required"
                    )
            if rollup.expected_cell_count <= 0:
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} cell count "
                    "must be positive"
                )
            if (
                rollup.expected_cell_count
                > domain.rollups[resolution].expected_cell_count
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} cell count "
                    "exceeds the canonical analysis domain"
                )
            if rollup.area_unit not in {"m2", "km2"}:
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} area unit "
                    "is invalid"
                )
            if len(rollup.sha256) != 64 or any(
                character not in "0123456789abcdef"
                for character in rollup.sha256
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} sha256 is "
                    "invalid"
                )
            if (
                not math.isfinite(rollup.expected_total_area_km2)
                or rollup.expected_total_area_km2 <= 0.0
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} total area "
                    "must be positive"
                )
            if not math.isclose(
                rollup.expected_total_area_km2,
                surface.expected_total_area_km2,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} total must "
                    f"derive from R{surface.resolution}"
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
