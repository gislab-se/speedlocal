from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import h3
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from .catalogs import load_analysis, load_region
from .contracts import (
    AnalysisContract,
    AnalysisDomainContract,
    LayerContract,
)
from .geometry import (
    GeometryPreviewError,
    VectorBufferPreview,
    WEB_CRS,
    _atomic_geometry_parts,
    _direct_distance_domain_geometries,
    _load_source_geometries,
    _metric_crs,
)
from .sources import (
    eligible_surface_contract_for_analysis,
    eligible_surface_level,
    resolve_analysis_domain_cell_areas_km2,
    resolve_eligible_surface_cell_areas_km2,
)
from .validation import validate_contract, validate_layer


FEASIBILITY_DISSOLVE_MIN_BUFFER_M = 5_000.0
FEASIBILITY_DISSOLVE_MIN_PARTS = 1_000


@dataclass(frozen=True)
class AreaCellResult:
    cell_id: str
    model_area_km2: float
    remaining_area_km2: float
    potential_pct: float


@dataclass(frozen=True)
class TechnologyAreaResult:
    region_id: str
    analysis_id: str
    technology: str
    resolution: int
    selected_layer_ids: tuple[str, ...]
    active_group_ids: tuple[str, ...]
    model_area_km2: float
    remaining_area_km2: float
    potential_pct: float
    cells: tuple[AreaCellResult, ...]


@dataclass(frozen=True)
class _BufferedLayerGeometry:
    parts: tuple[BaseGeometry, ...]
    source_feature_count: int
    declared_feature_count: int


def _clip_cells_with_parts(
    cells: np.ndarray,
    parts: np.ndarray,
    *,
    keep_inside: bool,
) -> np.ndarray:
    """Clip cells against a local overlap-safe union of nearby parts."""

    if len(parts) == 0:
        if keep_inside:
            return np.asarray([Polygon() for _ in cells], dtype=object)
        return cells.copy()

    pairs = STRtree(parts).query(cells, predicate="intersects")
    if pairs.shape[1] == 0:
        if keep_inside:
            return np.asarray([Polygon() for _ in cells], dtype=object)
        return cells.copy()

    order = np.argsort(pairs[0], kind="stable")
    cell_indices = pairs[0][order]
    part_indices = pairs[1][order]
    intersections = shapely.intersection(
        cells[cell_indices],
        parts[part_indices],
    )
    starts = np.flatnonzero(
        np.r_[True, cell_indices[1:] != cell_indices[:-1]]
    )
    ends = np.r_[starts[1:], len(cell_indices)]
    if keep_inside:
        result = np.asarray([Polygon() for _ in cells], dtype=object)
    else:
        result = cells.copy()
    for start, end in zip(starts, ends):
        cell_index = int(cell_indices[start])
        local_union = shapely.union_all(intersections[start:end])
        if keep_inside:
            result[cell_index] = local_union
        else:
            result[cell_index] = shapely.difference(
                cells[cell_index],
                local_union,
            )
    return result


def calculate_remaining_area_cells(
    model_cells: Mapping[str, BaseGeometry],
    model_areas_km2: Mapping[str, float],
    *,
    exclusion_groups: Iterable[Iterable[BaseGeometry]] = (),
    feasibility_groups: Iterable[Iterable[BaseGeometry]] = (),
) -> tuple[AreaCellResult, ...]:
    """Return overlap-safe remaining area using one declared denominator.

    Exclusions are unioned before removal. Each feasibility group is a union
    internally, while multiple feasibility groups are intersected. Geometry
    area is used only to derive the remaining fraction; the final denominator
    is always the manifest-declared model area.
    """

    cell_ids = tuple(str(cell_id) for cell_id in model_areas_km2)
    if not cell_ids or set(cell_ids) != set(model_cells):
        raise ValueError(
            "Model geometries and declared model areas must contain the same cells"
        )
    cells = np.asarray([model_cells[cell_id] for cell_id in cell_ids], dtype=object)
    geometry_areas = np.asarray(shapely.area(cells), dtype=float)
    if not bool(np.all(np.isfinite(geometry_areas) & (geometry_areas > 0.0))):
        raise ValueError("Model-cell geometries must have positive finite area")
    declared_areas = np.asarray(
        [float(model_areas_km2[cell_id]) for cell_id in cell_ids],
        dtype=float,
    )
    if not bool(np.all(np.isfinite(declared_areas) & (declared_areas > 0.0))):
        raise ValueError("Declared model-cell areas must be positive and finite")

    remaining = cells.copy()
    for group in feasibility_groups:
        group_parts = [part for part in group if not part.is_empty]
        remaining = _clip_cells_with_parts(
            remaining,
            np.asarray(group_parts, dtype=object),
            keep_inside=True,
        )
    exclusion_parts = [
        part
        for group in exclusion_groups
        for part in group
        if not part.is_empty
    ]
    if exclusion_parts:
        remaining = _clip_cells_with_parts(
            remaining,
            np.asarray(exclusion_parts, dtype=object),
            keep_inside=False,
        )

    remaining_geometry_areas = np.asarray(shapely.area(remaining), dtype=float)
    fractions = np.divide(
        remaining_geometry_areas,
        geometry_areas,
        out=np.zeros_like(remaining_geometry_areas),
        where=geometry_areas > 0.0,
    )
    fractions = np.clip(fractions, 0.0, 1.0)
    remaining_declared_areas = declared_areas * fractions
    return tuple(
        AreaCellResult(
            cell_id=cell_id,
            model_area_km2=float(model_area),
            remaining_area_km2=float(remaining_area),
            potential_pct=float(fraction * 100.0),
        )
        for cell_id, model_area, remaining_area, fraction in zip(
            cell_ids,
            declared_areas,
            remaining_declared_areas,
            fractions,
        )
    )


def _domain_level(
    contract: AnalysisContract,
    resolution: int,
) -> AnalysisDomainContract:
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis-domain contract"
        )
    if int(resolution) == int(domain.resolution):
        return domain
    rollup = domain.rollups.get(int(resolution))
    if rollup is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no R{resolution} "
            "analysis-domain rollup"
        )
    return AnalysisDomainContract(
        provider=rollup.provider,
        path=rollup.path,
        id_field=rollup.id_field,
        area_field=rollup.area_field,
        area_unit=rollup.area_unit,
        cell_kind=domain.cell_kind,
        resolution=rollup.resolution,
        expected_cell_count=rollup.expected_cell_count,
    )


def _requested_resolution(
    contract: AnalysisContract,
    target_resolution: int | None,
) -> int:
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis-domain contract"
        )
    if target_resolution is None:
        return int(domain.resolution)
    if isinstance(target_resolution, bool) or not isinstance(
        target_resolution,
        int,
    ):
        raise TypeError("target_resolution must be an integer")
    resolution = int(target_resolution)
    if resolution > int(domain.resolution):
        raise ValueError(
            f"Area results must be calculated at R{int(domain.resolution)} "
            f"or rolled up to a coarser declared resolution, not R{resolution}"
        )
    _domain_level(contract, resolution)
    eligible_surface_level(contract, resolution)
    return resolution


def _rollup_cells(
    source_cells: tuple[AreaCellResult, ...],
    target_areas_km2: Mapping[str, float],
    target_resolution: int,
) -> tuple[AreaCellResult, ...]:
    grouped_model_area: dict[str, float] = {}
    grouped_remaining_area: dict[str, float] = {}
    for cell in source_cells:
        parent_id = str(
            h3.cell_to_parent(cell.cell_id, int(target_resolution))
        )
        grouped_model_area[parent_id] = (
            grouped_model_area.get(parent_id, 0.0) + cell.model_area_km2
        )
        grouped_remaining_area[parent_id] = (
            grouped_remaining_area.get(parent_id, 0.0)
            + cell.remaining_area_km2
        )
    if set(grouped_model_area) != set(target_areas_km2):
        missing = sorted(set(target_areas_km2) - set(grouped_model_area))[:5]
        extra = sorted(set(grouped_model_area) - set(target_areas_km2))[:5]
        raise ValueError(
            "R7 area-result children do not cover the declared rollup domain "
            f"(missing={missing}, extra={extra})"
        )
    rows: list[AreaCellResult] = []
    for cell_id, target_area_km2 in target_areas_km2.items():
        source_model_area = grouped_model_area[cell_id]
        if not math.isfinite(source_model_area) or source_model_area <= 0.0:
            raise ValueError(
                f"Area-result rollup cell {cell_id} has no positive R7 area"
            )
        fraction = max(
            0.0,
            min(
                1.0,
                grouped_remaining_area[cell_id] / source_model_area,
            ),
        )
        declared_area = float(target_area_km2)
        rows.append(
            AreaCellResult(
                cell_id=str(cell_id),
                model_area_km2=declared_area,
                remaining_area_km2=declared_area * fraction,
                potential_pct=fraction * 100.0,
            )
        )
    return tuple(rows)


def _buffered_layer_geometry(
    layer: LayerContract,
    *,
    native_crs: str,
    buffer_m: float,
) -> _BufferedLayerGeometry:
    validated = validate_layer(layer)
    parameter = layer.parameters.get("buffer_m")
    if parameter is None or parameter.unit != "m":
        raise ValueError(f"Layer {layer.id} has no metric buffer contract")
    distance = parameter.validate_value(buffer_m)
    target_crs = _metric_crs(native_crs)
    source_geometries, source_crs = _load_source_geometries(
        validated.assets.geojson_path,
        layer_id=layer.id,
        expected_family=validated.geometry_family,
        geometry_collection_policy=layer.source.geometry_collection_policy,
        geometry_validity_policy=layer.source.geometry_validity_policy,
    )
    transformer = Transformer.from_crs(
        source_crs,
        target_crs,
        always_xy=True,
    )
    atomic_parts: list[BaseGeometry] = []
    for geometry in source_geometries:
        transformed = transform(transformer.transform, geometry)
        atomic_parts.extend(
            _atomic_geometry_parts(
                transformed,
                validated.geometry_family,
            )
        )
    parts = np.asarray(atomic_parts, dtype=object)
    if distance > 0.0:
        parts = shapely.buffer(parts, distance, quad_segs=16)
    usable = tuple(
        part
        for part in parts
        if not part.is_empty and math.isfinite(float(part.area))
    )
    if not usable:
        raise GeometryPreviewError(
            "area_result_empty",
            f"Layer {layer.id!r} produced no area geometry.",
        )
    return _BufferedLayerGeometry(
        parts=usable,
        source_feature_count=len(source_geometries),
        declared_feature_count=int(validated.assets.feature_count),
    )


def _layer_buffer_parts(
    layer: LayerContract,
    *,
    native_crs: str,
    buffer_m: float,
) -> tuple[BaseGeometry, ...]:
    return _buffered_layer_geometry(
        layer,
        native_crs=native_crs,
        buffer_m=buffer_m,
    ).parts


def build_area_group_preview(
    region: str,
    analysis: str,
    group_id: str,
    layers: Iterable[str],
    buffer_m: float,
) -> VectorBufferPreview:
    """Build the exact, analysis-domain-clipped geometry for one area group.

    The preview uses the same validated source resolver, metric buffering,
    R7 domain geometry and local overlap-safe clipping primitives as the
    technology area calculation. It intentionally avoids the historical
    whole-cell proximity proxy and the much slower global source dissolve.
    """

    contract = load_analysis(str(region), str(analysis))
    validate_contract(contract)
    area_contract = contract.area_result
    if area_contract is None:
        raise ValueError(f"{region}/{analysis} has no area_result contract")
    canonical_group_id = str(group_id)
    if canonical_group_id not in area_contract.applicable_group_ids:
        raise ValueError(
            f"{region}/{analysis} does not apply group {canonical_group_id!r}"
        )
    requested = tuple(str(layer_id) for layer_id in layers)
    if not requested:
        raise ValueError("An area-group preview requires at least one layer")
    if len(requested) != len(set(requested)):
        raise ValueError("Area-group preview layer ids must not contain duplicates")
    unknown = set(requested) - set(contract.layers)
    if unknown:
        raise KeyError(
            f"Layers are not configured for {region}/{analysis}: {sorted(unknown)}"
        )
    selected_layers = tuple(contract.layers[layer_id] for layer_id in requested)
    if any(layer.group_id != canonical_group_id for layer in selected_layers):
        raise ValueError(
            "Every area-group preview layer must belong to the requested group"
        )
    operations = {layer.operation for layer in selected_layers}
    if len(operations) != 1:
        raise ValueError("An area-group preview requires one shared operation")
    operation = operations.pop()

    region_contract = load_region(str(region))
    native_crs = str(region_contract.get("native_crs") or "").strip()
    if not native_crs:
        raise ValueError(f"{region} has no native_crs")
    if contract.analysis_domain is None:
        raise ValueError(f"{region}/{analysis} has no analysis-domain contract")
    source_resolution = int(contract.analysis_domain.resolution)
    domain_level = _domain_level(contract, source_resolution)
    target_crs = _metric_crs(native_crs)
    model_cells = _direct_distance_domain_geometries(domain_level, target_crs)

    parts: list[BaseGeometry] = []
    source_feature_count = 0
    declared_feature_count = 0
    thresholds: list[float] = []
    for layer in selected_layers:
        parameter = layer.parameters.get("buffer_m")
        if parameter is None:
            raise ValueError(f"Layer {layer.id} has no buffer_m contract")
        threshold = parameter.validate_value(buffer_m)
        thresholds.append(threshold)
        buffered = _buffered_layer_geometry(
            layer,
            native_crs=native_crs,
            buffer_m=threshold,
        )
        parts.extend(buffered.parts)
        source_feature_count += buffered.source_feature_count
        declared_feature_count += buffered.declared_feature_count
    if not all(
        math.isclose(value, thresholds[0], rel_tol=0.0, abs_tol=1e-9)
        for value in thresholds
    ):
        raise ValueError("Area-group preview layers must share one threshold")
    if (
        operation == "proximity_feasibility"
        and thresholds[0] >= FEASIBILITY_DISSOLVE_MIN_BUFFER_M
        and len(parts) >= FEASIBILITY_DISSOLVE_MIN_PARTS
    ):
        dissolved = shapely.union_all(np.asarray(parts, dtype=object))
        parts = [
            part
            for part in shapely.get_parts(dissolved)
            if not part.is_empty
        ]

    clipped = _clip_cells_with_parts(
        np.asarray(list(model_cells.values()), dtype=object),
        np.asarray(parts, dtype=object),
        keep_inside=True,
    )
    nonempty = [geometry for geometry in clipped if not geometry.is_empty]
    if not nonempty:
        raise GeometryPreviewError(
            "area_group_preview_empty",
            "The exact area-group preview contains no geometry.",
        )
    try:
        native_result = unary_union(nonempty)
    except Exception as exc:
        raise GeometryPreviewError(
            "area_group_preview_union_failed",
            "The exact clipped area-group geometry could not be dissolved.",
        ) from exc
    if (
        native_result.is_empty
        or not native_result.is_valid
        or not all(math.isfinite(float(value)) for value in native_result.bounds)
    ):
        raise GeometryPreviewError(
            "area_group_preview_invalid",
            "The exact clipped area-group geometry is invalid.",
        )
    area_m2 = float(native_result.area)
    cell_ids = tuple(model_cells)
    cell_geometry_areas = np.asarray(
        shapely.area(np.asarray(list(model_cells.values()), dtype=object)),
        dtype=float,
    )
    clipped_geometry_areas = np.asarray(shapely.area(clipped), dtype=float)
    declared_cell_areas_km2 = resolve_analysis_domain_cell_areas_km2(
        contract,
        source_resolution,
    )
    if set(cell_ids) != set(declared_cell_areas_km2):
        raise ValueError(
            "Exact area-group preview cells do not match the declared domain"
        )
    fractions = np.divide(
        clipped_geometry_areas,
        cell_geometry_areas,
        out=np.zeros_like(clipped_geometry_areas),
        where=cell_geometry_areas > 0.0,
    )
    fractions = np.clip(fractions, 0.0, 1.0)
    # The public percentages are reported on a 0–100 scale. A 1e-12
    # percentage tolerance therefore corresponds to 1e-14 as a fraction.
    zero_cell_count = int(np.count_nonzero(fractions <= 1e-14))
    full_cell_count = int(np.count_nonzero(fractions >= 1.0 - 1e-14))
    partial_cell_count = int(len(fractions) - zero_cell_count - full_cell_count)
    model_area_m2 = math.fsum(
        float(declared_cell_areas_km2[cell_id])
        * float(fraction)
        * 1_000_000.0
        for cell_id, fraction in zip(cell_ids, fractions)
    )
    try:
        to_web = Transformer.from_crs(target_crs, WEB_CRS, always_xy=True)
        web_geometry = transform(to_web.transform, native_result)
    except Exception as exc:
        raise GeometryPreviewError(
            "area_group_preview_transform_failed",
            "The exact clipped area-group geometry could not be transformed.",
        ) from exc
    if not web_geometry.is_valid:
        web_geometry = shapely.make_valid(web_geometry)
        polygon_parts = [
            part
            for part in shapely.get_parts(web_geometry)
            if "Polygon" in part.geom_type and not part.is_empty
        ]
        if polygon_parts:
            web_geometry = unary_union(polygon_parts)
    if web_geometry.is_empty or not web_geometry.is_valid:
        raise GeometryPreviewError(
            "area_group_preview_web_invalid",
            "The transformed exact area-group geometry is invalid.",
        )
    distance = float(thresholds[0])
    return VectorBufferPreview(
        geojson={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "analysis_id": str(analysis),
                        "group_id": canonical_group_id,
                        "layer_ids": list(requested),
                        "native_crs": target_crs.to_string(),
                        "buffer_m": distance,
                        "operation": operation,
                        "source_h3_resolution": source_resolution,
                        "semantics": "exact_area_clip",
                    },
                    "geometry": mapping(web_geometry),
                }
            ],
        },
        layer_ids=requested,
        native_crs=target_crs.to_string(),
        buffer_m=distance,
        semantics="exact_area_clip",
        geometry_type=web_geometry.geom_type,
        source_feature_count=source_feature_count,
        declared_feature_count=declared_feature_count,
        area_m2=area_m2,
        model_area_m2=model_area_m2,
        zero_cell_count=zero_cell_count,
        partial_cell_count=partial_cell_count,
        full_cell_count=full_cell_count,
    )


def run_area_analysis(
    region: str,
    analysis: str,
    layers: Iterable[str],
    parameters: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    target_resolution: int | None = None,
) -> TechnologyAreaResult:
    """Run the manifest-declared exact vector area contract."""

    contract = load_analysis(region, analysis)
    validate_contract(contract)
    area_contract = contract.area_result
    if area_contract is None:
        raise ValueError(f"{region}/{analysis} has no area_result contract")
    requested = tuple(str(layer_id) for layer_id in layers)
    if len(requested) != len(set(requested)):
        raise ValueError("Area analysis layer ids must not contain duplicates")
    unknown = set(requested) - set(contract.layers)
    if unknown:
        raise KeyError(
            f"Layers are not configured for {region}/{analysis}: {sorted(unknown)}"
        )
    resolution = _requested_resolution(contract, target_resolution)
    region_contract = load_region(region)
    native_crs = str(region_contract.get("native_crs") or "").strip()
    if not native_crs:
        raise ValueError(f"{region} has no native_crs")

    selected_by_group: dict[str, list[LayerContract]] = {}
    for layer_id in requested:
        layer = contract.layers[layer_id]
        if layer.group_id not in area_contract.applicable_group_ids:
            raise ValueError(
                f"Layer {layer_id} group {layer.group_id} is not applicable "
                f"to {area_contract.technology}"
            )
        selected_by_group.setdefault(layer.group_id, []).append(layer)

    exclusion_groups: list[tuple[BaseGeometry, ...]] = []
    feasibility_groups: list[tuple[BaseGeometry, ...]] = []
    active_group_ids: list[str] = []
    for group_id in area_contract.applicable_group_ids:
        group_layers = selected_by_group.get(group_id, [])
        if not group_layers:
            continue
        operations = {layer.operation for layer in group_layers}
        if len(operations) != 1:
            raise ValueError(
                f"Area-result group {group_id} must use one operation"
            )
        operation = operations.pop()
        thresholds: list[float] = []
        group_parts: list[BaseGeometry] = []
        for layer in group_layers:
            parameter = layer.parameters.get("buffer_m")
            if parameter is None:
                raise ValueError(f"Layer {layer.id} has no buffer_m contract")
            raw_value = (parameters or {}).get(layer.id, {}).get(
                "buffer_m",
                parameter.default,
            )
            threshold = parameter.validate_value(raw_value)
            thresholds.append(threshold)
            group_parts.extend(
                _layer_buffer_parts(
                    layer,
                    native_crs=native_crs,
                    buffer_m=threshold,
                )
            )
        if not all(
            math.isclose(value, thresholds[0], rel_tol=0.0, abs_tol=1e-9)
            for value in thresholds
        ):
            raise ValueError(
                f"Area-result group {group_id} layers must share one threshold"
            )
        if operation in {"distance_exclusion", "hard_exclusion"}:
            exclusion_groups.append(tuple(group_parts))
        elif operation == "proximity_feasibility":
            if (
                thresholds[0] >= FEASIBILITY_DISSOLVE_MIN_BUFFER_M
                and len(group_parts) >= FEASIBILITY_DISSOLVE_MIN_PARTS
            ):
                dissolved = shapely.union_all(
                    np.asarray(group_parts, dtype=object)
                )
                group_parts = [
                    part
                    for part in shapely.get_parts(dissolved)
                    if not part.is_empty
                ]
            feasibility_groups.append(tuple(group_parts))
        else:
            raise ValueError(
                f"Area-result group {group_id} has unsupported operation {operation}"
            )
        active_group_ids.append(group_id)

    surface = eligible_surface_contract_for_analysis(contract)
    source_resolution = int(surface.resolution)
    surface_level = eligible_surface_level(contract, source_resolution)
    target_crs = _metric_crs(native_crs)
    source_model_areas_km2 = resolve_eligible_surface_cell_areas_km2(
        contract,
        source_resolution,
    )
    model_cells = _direct_distance_domain_geometries(
        surface_level,
        target_crs,
    )
    source_cells = calculate_remaining_area_cells(
        model_cells,
        source_model_areas_km2,
        exclusion_groups=exclusion_groups,
        feasibility_groups=feasibility_groups,
    )
    cells = source_cells
    if resolution < source_resolution:
        cells = _rollup_cells(
            source_cells,
            resolve_eligible_surface_cell_areas_km2(contract, resolution),
            resolution,
        )
    model_area_km2 = math.fsum(cell.model_area_km2 for cell in cells)
    remaining_area_km2 = math.fsum(
        cell.remaining_area_km2 for cell in cells
    )
    return TechnologyAreaResult(
        region_id=region,
        analysis_id=analysis,
        technology=area_contract.technology,
        resolution=resolution,
        selected_layer_ids=requested,
        active_group_ids=tuple(active_group_ids),
        model_area_km2=model_area_km2,
        remaining_area_km2=remaining_area_km2,
        potential_pct=(remaining_area_km2 / model_area_km2 * 100.0),
        cells=cells,
    )
