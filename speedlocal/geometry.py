from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from pyproj import CRS, Transformer
import h3
from shapely import make_valid
from shapely.geometry import Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from shapely.validation import explain_validity

from .contracts import (
    AnalysisDomainContract,
    EligibleSurfaceContract,
    EligibleSurfaceRollupContract,
    LayerContract,
)
from .paths import resolve_source_path
from .validation import validate_layer


SOURCE_CRS = CRS.from_user_input("OGC:CRS84")
WEB_CRS = CRS.from_epsg(4326)
SUPPORTED_VECTOR_FAMILIES = {"point", "line", "polygon"}

PreviewSemantics = Literal[
    "dissolved_source_footprint",
    "metric_buffer",
    "exact_area_clip",
]


class GeometryPreviewError(ValueError):
    """A safe, explicit failure while constructing a vector preview."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class VectorBufferPreview:
    """One dissolved GeoJSON preview plus its native-CRS measurements.

    At ``buffer_m == 0``, ``geojson`` contains the dissolved source footprint:
    source lines remain lines, source polygons remain polygons, and source points
    remain points. Positive distances return the dissolved metric buffer as a
    polygon or multipolygon.
    """

    geojson: dict[str, Any]
    layer_ids: tuple[str, ...]
    native_crs: str
    buffer_m: float
    semantics: PreviewSemantics
    geometry_type: str
    source_feature_count: int
    declared_feature_count: int
    area_m2: float
    model_area_m2: float | None = None
    zero_cell_count: int | None = None
    partial_cell_count: int | None = None
    full_cell_count: int | None = None


@dataclass(frozen=True)
class DirectDistanceRow:
    """One source-to-analysis-cell observation in a projected metre CRS."""

    cell_id: str
    distance_m: float
    intersects: bool


@dataclass(frozen=True)
class DirectDistanceArtifact:
    """Complete direct-distance observations for one canonical layer."""

    layer_id: str
    resolution: int
    native_crs: str
    source_geometry_count: int
    source_part_count: int
    declared_feature_count: int
    rows: tuple[DirectDistanceRow, ...]


def _preview_error(code: str, message: str, error: Exception | None = None) -> GeometryPreviewError:
    failure = GeometryPreviewError(code, message)
    if error is not None:
        failure.__cause__ = error
    return failure


def _validate_buffer_contract(layer: LayerContract, distance: float) -> None:
    if layer.operation not in {
        "distance_exclusion",
        "hard_exclusion",
        "proximity_feasibility",
    }:
        raise GeometryPreviewError(
            "layer_operation_unsupported",
            f"Layer {layer.id!r} does not declare a distance-based operation.",
        )
    parameter = layer.parameters.get("buffer_m")
    if parameter is None or parameter.unit != "m":
        raise GeometryPreviewError(
            "buffer_contract_missing",
            f"Layer {layer.id!r} must declare a buffer_m parameter in metres.",
        )
    # Zero is a deliberate preview-only value: it exposes the dissolved source
    # footprint even when the analysis contract's first usable buffer is larger.
    if distance == 0:
        return
    try:
        parameter.validate_value(distance)
    except (TypeError, ValueError) as exc:
        raise _preview_error(
            "buffer_outside_contract",
            f"Layer {layer.id!r} does not allow a {distance:g} metre buffer.",
            exc,
        )


def _metric_crs(value: str) -> CRS:
    if not str(value or "").strip():
        raise GeometryPreviewError("native_crs_missing", "A native metric CRS is required.")
    try:
        crs = CRS.from_user_input(value)
    except Exception as exc:
        raise _preview_error(
            "native_crs_invalid",
            f"The native CRS {value!r} cannot be parsed.",
            exc,
        )
    if not crs.is_projected:
        raise GeometryPreviewError(
            "native_crs_not_projected",
            f"The native CRS {value!r} must be projected before metric buffering.",
        )
    horizontal_axes = crs.axis_info[:2]
    if len(horizontal_axes) != 2 or any(
        axis.unit_conversion_factor is None
        or not math.isclose(
            float(axis.unit_conversion_factor),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for axis in horizontal_axes
    ):
        raise GeometryPreviewError(
            "native_crs_not_metric",
            f"The native CRS {value!r} must use metres on both horizontal axes.",
        )
    return crs


def _buffer_distance(value: float) -> float:
    if isinstance(value, bool):
        raise GeometryPreviewError("buffer_invalid", "buffer_m must be a finite number.")
    try:
        distance = float(value)
    except (TypeError, ValueError) as exc:
        raise _preview_error(
            "buffer_invalid",
            "buffer_m must be a finite number.",
            exc,
        )
    if not math.isfinite(distance):
        raise GeometryPreviewError("buffer_invalid", "buffer_m must be a finite number.")
    if distance < 0:
        raise GeometryPreviewError("buffer_negative", "buffer_m must be zero or greater.")
    return distance


def _source_crs(payload: dict[str, Any], layer_id: str) -> CRS:
    declaration = payload.get("crs")
    if declaration is None:
        return SOURCE_CRS
    if not isinstance(declaration, dict) or declaration.get("type") != "name":
        raise GeometryPreviewError(
            "source_crs_invalid",
            f"Layer {layer_id!r} has an unsupported GeoJSON CRS declaration.",
        )
    properties = declaration.get("properties")
    name = properties.get("name") if isinstance(properties, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise GeometryPreviewError(
            "source_crs_invalid",
            f"Layer {layer_id!r} has an incomplete GeoJSON CRS declaration.",
        )
    try:
        crs = CRS.from_user_input(name)
    except Exception as exc:
        raise _preview_error(
            "source_crs_invalid",
            f"Layer {layer_id!r} has an unreadable GeoJSON CRS declaration.",
            exc,
        )
    if not crs.equals(WEB_CRS, ignore_axis_order=True):
        raise GeometryPreviewError(
            "source_crs_unsupported",
            f"Layer {layer_id!r} must use CRS84/EPSG:4326 source coordinates.",
        )
    return crs


def _geometry_family(geometry: BaseGeometry) -> str:
    geometry_type = geometry.geom_type.lower()
    if "point" in geometry_type:
        return "point"
    if "line" in geometry_type:
        return "line"
    if "polygon" in geometry_type:
        return "polygon"
    raise GeometryPreviewError(
        "geometry_family_unsupported",
        f"Unsupported source geometry type: {geometry.geom_type}.",
    )


def _raw_geometries(
    payload: dict[str, Any],
    layer_id: str,
    geometry_collection_policy: str,
) -> list[dict[str, Any]]:
    def expand_geometry(geometry: dict[str, Any]) -> list[dict[str, Any]]:
        if geometry.get("type") != "GeometryCollection":
            return [geometry]
        if geometry_collection_policy != "highest_dimension":
            return [geometry]
        expanded: list[dict[str, Any]] = []
        for child in geometry.get("geometries") or []:
            if not isinstance(child, dict):
                raise GeometryPreviewError(
                    "source_geometry_invalid",
                    f"Layer {layer_id!r} has an invalid collection member.",
                )
            expanded.extend(expand_geometry(child))
        return expanded

    payload_type = payload.get("type")
    if payload_type == "FeatureCollection":
        features = payload.get("features")
        if not isinstance(features, list) or not features:
            raise GeometryPreviewError(
                "source_empty",
                f"Layer {layer_id!r} has no source features.",
            )
        geometries: list[dict[str, Any]] = []
        for index, feature in enumerate(features):
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise GeometryPreviewError(
                    "source_feature_invalid",
                    f"Layer {layer_id!r} feature {index} is not a GeoJSON Feature.",
                )
            geometry = feature.get("geometry")
            if not isinstance(geometry, dict):
                raise GeometryPreviewError(
                    "source_geometry_missing",
                    f"Layer {layer_id!r} feature {index} has no geometry.",
                )
            geometries.extend(expand_geometry(geometry))
        return geometries
    if payload_type == "Feature":
        geometry = payload.get("geometry")
        if not isinstance(geometry, dict):
            raise GeometryPreviewError(
                "source_geometry_missing",
                f"Layer {layer_id!r} has no geometry.",
            )
        return expand_geometry(geometry)
    if isinstance(payload_type, str):
        return expand_geometry(payload)
    raise GeometryPreviewError(
        "source_geojson_invalid",
        f"Layer {layer_id!r} is not valid GeoJSON.",
    )


def _load_source_geometries(
    path: Path,
    *,
    layer_id: str,
    expected_family: str,
    geometry_collection_policy: str,
    geometry_validity_policy: str,
) -> tuple[list[BaseGeometry], CRS]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise _preview_error(
            "source_geojson_unreadable",
            f"Layer {layer_id!r} source GeoJSON cannot be read.",
            exc,
        )
    if not isinstance(payload, dict):
        raise GeometryPreviewError(
            "source_geojson_invalid",
            f"Layer {layer_id!r} source GeoJSON must be an object.",
        )
    source_crs = _source_crs(payload, layer_id)
    geometries: list[BaseGeometry] = []
    raw_geometries = _raw_geometries(
        payload,
        layer_id,
        geometry_collection_policy,
    )
    for index, raw_geometry in enumerate(raw_geometries):
        try:
            geometry = shape(raw_geometry)
        except Exception as exc:
            raise _preview_error(
                "source_geometry_invalid",
                f"Layer {layer_id!r} geometry {index} cannot be parsed.",
                exc,
            )
        if geometry.is_empty:
            raise GeometryPreviewError(
                "source_geometry_empty",
                f"Layer {layer_id!r} geometry {index} is empty.",
            )
        if not geometry.is_valid:
            if geometry_validity_policy != "make_valid":
                raise GeometryPreviewError(
                    "source_geometry_invalid",
                    f"Layer {layer_id!r} geometry {index} is invalid: "
                    f"{explain_validity(geometry)}.",
                )
            try:
                geometry = make_valid(geometry)
            except Exception as exc:
                raise _preview_error(
                    "source_geometry_repair_failed",
                    f"Layer {layer_id!r} geometry {index} could not be "
                    "repaired under its manifest policy.",
                    exc,
                )
            if geometry.is_empty or not geometry.is_valid:
                raise GeometryPreviewError(
                    "source_geometry_repair_failed",
                    f"Layer {layer_id!r} geometry {index} remained invalid "
                    "after its manifest-declared repair.",
                )
        family = _geometry_family(geometry)
        if family != expected_family:
            if geometry_collection_policy == "highest_dimension":
                dimensions = {"point": 0, "line": 1, "polygon": 2}
                if dimensions[family] < dimensions[expected_family]:
                    continue
            raise GeometryPreviewError(
                "source_geometry_family_mismatch",
                f"Layer {layer_id!r} geometry {index} is {family}; "
                f"the validated contract requires {expected_family}.",
            )
        geometries.append(geometry)
    return geometries, source_crs


def _ensure_usable_geometry(geometry: BaseGeometry, stage: str) -> None:
    if geometry.is_empty:
        raise GeometryPreviewError(
            "geometry_result_empty",
            f"The {stage} geometry is empty.",
        )
    if not geometry.is_valid:
        raise GeometryPreviewError(
            "geometry_result_invalid",
            f"The {stage} geometry is invalid: {explain_validity(geometry)}.",
        )
    if not all(math.isfinite(float(value)) for value in geometry.bounds):
        raise GeometryPreviewError(
            "geometry_result_nonfinite",
            f"The {stage} geometry has non-finite bounds.",
        )


def _repair_result_if_declared(
    geometry: BaseGeometry,
    stage: str,
    repair_declared: bool,
) -> BaseGeometry:
    if geometry.is_valid or not repair_declared:
        return geometry
    try:
        repaired = make_valid(geometry)
    except Exception as exc:
        raise _preview_error(
            "geometry_result_repair_failed",
            f"The {stage} geometry could not be repaired under the selected "
            "layers' manifest policy.",
            exc,
        )
    if repaired.is_empty or not repaired.is_valid:
        raise GeometryPreviewError(
            "geometry_result_repair_failed",
            f"The {stage} geometry remained invalid after its "
            "manifest-declared repair.",
        )
    return repaired


def _atomic_geometry_parts(
    geometry: BaseGeometry,
    expected_family: str,
) -> list[BaseGeometry]:
    """Explode multipart source geometry for indexed nearest-neighbour work."""

    family = _geometry_family(geometry)
    if family != expected_family:
        raise GeometryPreviewError(
            "source_geometry_family_mismatch",
            f"Direct-distance source is {family}; expected {expected_family}.",
        )
    parts = getattr(geometry, "geoms", None)
    if parts is None:
        return [geometry]
    atomic: list[BaseGeometry] = []
    for part in parts:
        atomic.extend(_atomic_geometry_parts(part, expected_family))
    return atomic


def _direct_distance_domain_geometries(
    domain: (
        AnalysisDomainContract
        | EligibleSurfaceContract
        | EligibleSurfaceRollupContract
    ),
    target_crs: CRS,
) -> dict[str, BaseGeometry]:
    """Load the exact manifest-declared source-resolution analysis geometry."""

    try:
        domain_path = resolve_source_path(domain.provider, domain.path)
        with domain_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise _preview_error(
            "analysis_domain_unreadable",
            "The direct-distance analysis domain cannot be read.",
            exc,
        )
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise GeometryPreviewError(
            "analysis_domain_invalid",
            "The direct-distance analysis domain must be a GeoJSON FeatureCollection.",
        )
    source_crs = _source_crs(payload, "analysis_domain")
    try:
        to_native = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    except Exception as exc:
        raise _preview_error(
            "analysis_domain_transform_failed",
            "The direct-distance analysis domain CRS cannot be transformed.",
            exc,
        )

    cells: dict[str, BaseGeometry] = {}
    features = payload.get("features")
    if not isinstance(features, list):
        raise GeometryPreviewError(
            "analysis_domain_invalid",
            "The direct-distance analysis domain has no feature list.",
        )
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise GeometryPreviewError(
                "analysis_domain_feature_invalid",
                f"Analysis-domain feature {index} is invalid.",
            )
        properties = feature.get("properties")
        cell_id = (
            str(properties.get(domain.id_field) or "").strip()
            if isinstance(properties, dict)
            else ""
        )
        if not cell_id:
            raise GeometryPreviewError(
                "analysis_domain_id_missing",
                f"Analysis-domain feature {index} has no {domain.id_field!r}.",
            )
        if cell_id in cells:
            raise GeometryPreviewError(
                "analysis_domain_id_duplicate",
                f"Analysis-domain cell {cell_id!r} is duplicated.",
            )
        try:
            if not h3.is_valid_cell(cell_id):
                raise ValueError("invalid H3 cell")
            actual_resolution = int(h3.get_resolution(cell_id))
        except Exception as exc:
            raise _preview_error(
                "analysis_domain_id_invalid",
                f"Analysis-domain id {cell_id!r} is not a valid H3 cell.",
                exc,
            )
        if actual_resolution != domain.resolution:
            raise GeometryPreviewError(
                "analysis_domain_resolution_mismatch",
                f"Analysis-domain cell {cell_id!r} is R{actual_resolution}; "
                f"expected R{domain.resolution}.",
            )
        raw_geometry = feature.get("geometry")
        if not isinstance(raw_geometry, dict):
            raise GeometryPreviewError(
                "analysis_domain_geometry_missing",
                f"Analysis-domain cell {cell_id!r} has no geometry.",
            )
        try:
            web_geometry = shape(raw_geometry)
            if _geometry_family(web_geometry) != "polygon":
                raise ValueError("analysis cell must be polygonal")
            _ensure_usable_geometry(web_geometry, f"analysis-domain cell {cell_id!r}")
            native_geometry = transform(to_native.transform, web_geometry)
            _ensure_usable_geometry(native_geometry, f"transformed analysis-domain cell {cell_id!r}")
        except GeometryPreviewError:
            raise
        except Exception as exc:
            raise _preview_error(
                "analysis_domain_geometry_invalid",
                f"Analysis-domain cell {cell_id!r} has invalid geometry.",
                exc,
            )
        cells[cell_id] = native_geometry
    if len(cells) != domain.expected_cell_count:
        raise GeometryPreviewError(
            "analysis_domain_count_mismatch",
            f"The direct-distance R{domain.resolution} domain has {len(cells)} "
            f"cells; expected {domain.expected_cell_count}.",
        )
    return cells


def build_direct_distance_artifact(
    layer: LayerContract,
    *,
    analysis_domain: AnalysisDomainContract,
    native_crs: str,
) -> DirectDistanceArtifact:
    """Measure one declared vector source directly against canonical cells.

    Distance follows the established artifact-export contract: shortest
    planar distance from each analysis cell's interior representative point to
    the manifest-declared source, plus an independent full-cell intersection
    flag. Multipart sources are indexed as atomic parts for bounded build time.
    Product runtime should consume the resulting deterministic CSV rather than
    repeating this geospatial build during Streamlit reruns.
    """

    if layer.operation not in {
        "distance_exclusion",
        "hard_exclusion",
        "proximity_feasibility",
    }:
        raise GeometryPreviewError(
            "layer_operation_unsupported",
            f"Layer {layer.id!r} does not declare a distance-based operation.",
        )
    target_crs = _metric_crs(native_crs)
    try:
        validated = validate_layer(layer)
    except Exception as exc:
        raise _preview_error(
            "layer_validation_failed",
            f"Layer {layer.id!r} failed source-contract validation: {exc}",
            exc,
        )
    if validated.geometry_family not in SUPPORTED_VECTOR_FAMILIES:
        raise GeometryPreviewError(
            "geometry_family_unsupported",
            f"Layer {layer.id!r} uses unsupported direct-distance family "
            f"{validated.geometry_family!r}.",
        )
    source_geometries, source_crs = _load_source_geometries(
        validated.assets.geojson_path,
        layer_id=layer.id,
        expected_family=validated.geometry_family,
        geometry_collection_policy=layer.source.geometry_collection_policy,
        geometry_validity_policy=layer.source.geometry_validity_policy,
    )
    try:
        to_native = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        native_sources = [
            transform(to_native.transform, geometry)
            for geometry in source_geometries
        ]
    except Exception as exc:
        raise _preview_error(
            "source_transform_failed",
            f"Layer {layer.id!r} could not be transformed to {native_crs!r}.",
            exc,
        )
    source_parts: list[BaseGeometry] = []
    for geometry in native_sources:
        _ensure_usable_geometry(geometry, f"transformed {layer.id!r} source")
        source_parts.extend(
            _atomic_geometry_parts(geometry, validated.geometry_family)
        )
    if not source_parts:
        raise GeometryPreviewError(
            "source_empty",
            f"Layer {layer.id!r} has no source geometry parts.",
        )
    for part in source_parts:
        _ensure_usable_geometry(part, f"atomic {layer.id!r} source")

    cells = _direct_distance_domain_geometries(analysis_domain, target_crs)
    try:
        source_index = STRtree(source_parts)
        rows: list[DirectDistanceRow] = []
        for cell_id in sorted(cells):
            cell_geometry = cells[cell_id]
            representative_point = cell_geometry.representative_point()
            nearest_index = int(source_index.nearest(representative_point))
            distance = float(
                representative_point.distance(source_parts[nearest_index])
            )
            if not math.isfinite(distance) or distance < 0:
                raise ValueError(f"invalid distance {distance!r}")
            intersects = bool(
                len(source_index.query(cell_geometry, predicate="intersects"))
            )
            rows.append(
                DirectDistanceRow(
                    cell_id=cell_id,
                    distance_m=distance,
                    intersects=intersects,
                )
            )
    except Exception as exc:
        raise _preview_error(
            "direct_distance_failed",
            f"Direct distances could not be built for layer {layer.id!r}.",
            exc,
        )
    return DirectDistanceArtifact(
        layer_id=layer.id,
        resolution=analysis_domain.resolution,
        native_crs=target_crs.to_string(),
        source_geometry_count=len(source_geometries),
        source_part_count=len(source_parts),
        declared_feature_count=validated.assets.feature_count,
        rows=tuple(rows),
    )


def build_vector_buffer_preview(
    layers: Iterable[LayerContract],
    *,
    native_crs: str,
    buffer_m: float,
) -> VectorBufferPreview:
    """Resolve, dissolve, buffer, and reproject canonical layer geometries.

    Every layer first passes the existing manifest/provider validation chain.
    Source GeoJSON must use CRS84/EPSG:4326 and ``native_crs`` must be a
    projected metre CRS. The result is never clipped: clipping will only be
    added when the repository has an explicit validated mask contract.
    """

    layer_list = tuple(layers)
    if not layer_list:
        raise GeometryPreviewError("layers_empty", "At least one layer is required.")
    layer_ids = tuple(layer.id for layer in layer_list)
    if len(layer_ids) != len(set(layer_ids)):
        raise GeometryPreviewError("layers_duplicate", "Layer ids must be unique.")

    target_crs = _metric_crs(native_crs)
    distance = _buffer_distance(buffer_m)
    native_geometries: list[BaseGeometry] = []
    source_feature_count = 0
    declared_feature_count = 0
    result_repair_declared = any(
        layer.source.geometry_validity_policy == "make_valid"
        for layer in layer_list
    )

    for layer in layer_list:
        _validate_buffer_contract(layer, distance)
        try:
            validated = validate_layer(layer)
        except Exception as exc:
            raise _preview_error(
                "layer_validation_failed",
                f"Layer {layer.id!r} failed source-contract validation: {exc}",
                exc,
            )
        if validated.geometry_family not in SUPPORTED_VECTOR_FAMILIES:
            raise GeometryPreviewError(
                "geometry_family_unsupported",
                f"Layer {layer.id!r} uses unsupported vector-preview family "
                f"{validated.geometry_family!r}.",
            )
        source_geometries, source_crs = _load_source_geometries(
            validated.assets.geojson_path,
            layer_id=layer.id,
            expected_family=validated.geometry_family,
            geometry_collection_policy=(
                layer.source.geometry_collection_policy
            ),
            geometry_validity_policy=(
                layer.source.geometry_validity_policy
            ),
        )
        try:
            to_native = Transformer.from_crs(
                source_crs,
                target_crs,
                always_xy=True,
            )
            transformed = [
                transform(to_native.transform, geometry)
                for geometry in source_geometries
            ]
        except Exception as exc:
            raise _preview_error(
                "source_transform_failed",
                f"Layer {layer.id!r} could not be transformed to {native_crs!r}.",
                exc,
            )
        for geometry in transformed:
            _ensure_usable_geometry(geometry, f"transformed {layer.id!r} source")
        native_geometries.extend(transformed)
        source_feature_count += len(source_geometries)
        declared_feature_count += validated.assets.feature_count

    try:
        dissolved = unary_union(native_geometries)
    except Exception as exc:
        raise _preview_error(
            "dissolve_failed",
            "The selected source geometries could not be dissolved.",
            exc,
        )
    dissolved = _repair_result_if_declared(
        dissolved,
        "dissolved source",
        result_repair_declared,
    )
    _ensure_usable_geometry(dissolved, "dissolved source")

    semantics: PreviewSemantics
    if distance == 0:
        native_result = dissolved
        semantics = "dissolved_source_footprint"
    else:
        try:
            native_result = dissolved.buffer(distance)
        except Exception as exc:
            raise _preview_error(
                "buffer_failed",
                f"The dissolved source could not be buffered by {distance:g} metres.",
                exc,
            )
        semantics = "metric_buffer"
    native_result = _repair_result_if_declared(
        native_result,
        semantics.replace("_", " "),
        result_repair_declared,
    )
    _ensure_usable_geometry(native_result, semantics.replace("_", " "))

    area_m2 = float(native_result.area)
    try:
        to_web = Transformer.from_crs(target_crs, WEB_CRS, always_xy=True)
        web_geometry = transform(to_web.transform, native_result)
    except Exception as exc:
        raise _preview_error(
            "web_transform_failed",
            "The preview could not be transformed to EPSG:4326.",
            exc,
        )
    web_geometry = _repair_result_if_declared(
        web_geometry,
        "EPSG:4326 preview",
        result_repair_declared,
    )
    _ensure_usable_geometry(web_geometry, "EPSG:4326 preview")

    canonical_native_crs = target_crs.to_string()
    properties = {
        "layer_ids": list(layer_ids),
        "native_crs": canonical_native_crs,
        "buffer_m": distance,
        "semantics": semantics,
    }
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": mapping(web_geometry),
            }
        ],
    }
    return VectorBufferPreview(
        geojson=geojson,
        layer_ids=layer_ids,
        native_crs=canonical_native_crs,
        buffer_m=distance,
        semantics=semantics,
        geometry_type=web_geometry.geom_type,
        source_feature_count=source_feature_count,
        declared_feature_count=declared_feature_count,
        area_m2=area_m2,
    )
