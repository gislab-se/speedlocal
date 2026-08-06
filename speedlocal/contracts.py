from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


STANDARD_GROUP_IDS = ("roads", "population", "nature", "culture", "grid_infrastructure")
SUPPORTED_GEOMETRY_FAMILIES = {"point", "line", "polygon", "grid"}
SUPPORTED_OPERATIONS = {
    "distance_exclusion",
    "hard_exclusion",
    "proximity_feasibility",
}


@dataclass(frozen=True)
class DistanceTargetCoverageContract:
    resolution: int
    target_cell_count: int
    covered_cell_count: int
    missing_cell_count: int
    outside_cell_count: int
    missing_ids_sha256: str
    outside_ids_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.resolution, bool) or not isinstance(
            self.resolution, int
        ):
            raise ValueError("Distance target resolution must be an integer")
        if self.resolution < 0 or self.resolution > 15:
            raise ValueError("Distance target resolution must be between 0 and 15")
        for field_name in (
            "target_cell_count",
            "covered_cell_count",
            "missing_cell_count",
            "outside_cell_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.target_cell_count != (
            self.covered_cell_count + self.missing_cell_count
        ):
            raise ValueError(
                "Distance target coverage must satisfy target = covered + missing"
            )
        for field_name in ("missing_ids_sha256", "outside_ids_sha256"):
            value = getattr(self, field_name)
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError(f"{field_name} must be a lowercase SHA256 digest")


@dataclass(frozen=True)
class DistanceCoverageContract:
    mode: str = "complete"
    missing_policy: str = "error"
    expected_source_row_count: int | None = None
    source_ids_sha256: str | None = None
    targets: dict[int, DistanceTargetCoverageContract] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in {"complete", "declared_sparse"}:
            raise ValueError(
                "Distance coverage mode must be 'complete' or 'declared_sparse'"
            )
        if self.missing_policy not in {"error", "zero_acceptance"}:
            raise ValueError(
                "Distance missing policy must be 'error' or 'zero_acceptance'"
            )
        if self.mode == "complete" and self.missing_policy != "error":
            raise ValueError("Complete distance coverage must use the error policy")
        row_count = self.expected_source_row_count
        if row_count is not None and (
            isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count <= 0
        ):
            raise ValueError(
                "expected_source_row_count must be a positive integer"
            )
        if self.source_ids_sha256 is not None and (
            len(self.source_ids_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.source_ids_sha256
            )
        ):
            raise ValueError("source_ids_sha256 must be a lowercase SHA256 digest")
        if self.mode == "declared_sparse":
            if self.missing_policy != "zero_acceptance":
                raise ValueError(
                    "Declared sparse distance coverage must use zero_acceptance"
                )
            if row_count is None or self.source_ids_sha256 is None:
                raise ValueError(
                    "Declared sparse distance coverage must pin source rows and ids"
                )
            if not self.targets:
                raise ValueError(
                    "Declared sparse distance coverage must declare target signatures"
                )
        if any(
            resolution != target.resolution
            for resolution, target in self.targets.items()
        ):
            raise ValueError("Distance target coverage keys must match resolutions")


@dataclass(frozen=True)
class SourceContract:
    provider: str
    asset_manifest: str
    layer_id: str
    expected_geometry_families: tuple[str, ...]
    data_representation: str = "auto"
    source_geometry_required: bool = True
    geometry_collection_policy: str = "reject_mixed"
    geometry_validity_policy: str = "reject_invalid"
    distance_provider: str | None = None
    distance_path: str | None = None
    distance_h3_resolution: int | None = None
    distance_coverage: DistanceCoverageContract = field(
        default_factory=DistanceCoverageContract
    )

    def __post_init__(self) -> None:
        if (self.distance_provider is None) != (self.distance_path is None):
            raise ValueError(
                "distance_provider and distance_path must be declared together"
            )
        if self.distance_provider is not None and (
            not self.distance_provider.strip() or not str(self.distance_path).strip()
        ):
            raise ValueError(
                "distance_provider and distance_path must not be blank"
            )
        if self.geometry_collection_policy not in {
            "reject_mixed",
            "highest_dimension",
        }:
            raise ValueError(
                "geometry_collection_policy must be 'reject_mixed' or "
                "'highest_dimension'"
            )
        if self.geometry_validity_policy not in {
            "reject_invalid",
            "make_valid",
        }:
            raise ValueError(
                "geometry_validity_policy must be 'reject_invalid' or "
                "'make_valid'"
            )
        resolution = self.distance_h3_resolution
        if resolution is not None:
            if isinstance(resolution, bool) or not isinstance(resolution, int):
                raise ValueError("distance_h3_resolution must be an integer")
            if resolution < 0 or resolution > 15:
                raise ValueError(
                    "distance_h3_resolution must be between 0 and 15"
                )


@dataclass(frozen=True)
class AnalysisDomainRollupContract:
    provider: str
    path: str
    id_field: str
    area_field: str
    area_unit: str
    resolution: int
    expected_cell_count: int


@dataclass(frozen=True)
class AnalysisDomainContract:
    provider: str
    path: str
    id_field: str
    area_field: str
    area_unit: str
    cell_kind: str
    resolution: int
    expected_cell_count: int
    rollups: dict[int, AnalysisDomainRollupContract] = field(default_factory=dict)


@dataclass(frozen=True)
class ParameterContract:
    id: str
    value_type: str
    unit: str | None
    default: float
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None

    def __post_init__(self) -> None:
        if self.value_type != "number":
            raise ValueError(f"Unsupported parameter type for {self.id}: {self.value_type}")
        values = {
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
        }
        for label, value in values.items():
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{self.id} {label} must be finite")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError(f"{self.id} minimum must be <= maximum")
        if self.minimum is not None and self.default < self.minimum:
            raise ValueError(f"{self.id} default must be >= {self.minimum}")
        if self.maximum is not None and self.default > self.maximum:
            raise ValueError(f"{self.id} default must be <= {self.maximum}")
        if self.step is not None:
            if self.step <= 0:
                raise ValueError(f"{self.id} step must be > 0")
            self._validate_step_alignment(self.default, "default")
            if self.maximum is not None:
                self._validate_step_alignment(self.maximum, "maximum")

    def _validate_step_alignment(self, number: float, label: str) -> None:
        if self.step is None:
            return
        origin = self.minimum if self.minimum is not None else 0.0
        step_count = (number - origin) / self.step
        if not math.isclose(step_count, round(step_count), rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"{self.id} {label} must align to step {self.step} from {origin}"
            )

    def validate_value(self, value: Any) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{self.id} must be a finite number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{self.id} must be a finite number")
        if self.minimum is not None and number < self.minimum:
            raise ValueError(f"{self.id} must be >= {self.minimum}")
        if self.maximum is not None and number > self.maximum:
            raise ValueError(f"{self.id} must be <= {self.maximum}")
        return number


@dataclass(frozen=True)
class GroupUIContract:
    id: str
    label: str
    analysis_label: str
    interpretation: str
    expanded_by_default: bool
    blend_default: int
    group_color: str


@dataclass(frozen=True)
class LayerUIContract:
    note: str
    source_color: str
    point_radius: int
    quality_flag: str | None


@dataclass(frozen=True)
class AnalysisUIContract:
    groups: dict[str, GroupUIContract]


@dataclass(frozen=True)
class LayerContract:
    id: str
    label: str
    group_id: str
    source: SourceContract
    operation: str
    parameters: dict[str, ParameterContract] = field(default_factory=dict)
    ui: LayerUIContract | None = None


@dataclass(frozen=True)
class DefaultRequestContract:
    selected_layer_ids: tuple[str, ...]


@dataclass(frozen=True)
class AreaResultContract:
    technology: str
    applicable_group_ids: tuple[str, ...]
    restriction_combination: str
    operation_order: str
    denominator: str
    geometry_semantics: str


@dataclass(frozen=True)
class PopulationCountSourceContract:
    provider: str
    path: str
    sha256: str
    format: str
    h3_id_field: str
    value_field: str
    source_h3_resolution: int
    analysis_h3_resolution: int
    aggregation: str
    expected_row_count: int
    expected_total: float
    accounting_total_policy: str
    expected_analysis_domain_totals: dict[int, float]
    semantics: str

    def __post_init__(self) -> None:
        for field_name in (
            "provider",
            "path",
            "sha256",
            "format",
            "h3_id_field",
            "value_field",
            "aggregation",
            "accounting_total_policy",
            "semantics",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(
                    f"Population count source {field_name} must not be blank"
                )
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.sha256
        ):
            raise ValueError(
                "Population count source sha256 must be a lowercase SHA256 digest"
            )
        if self.format != "csv":
            raise ValueError("Population count source format must be 'csv'")
        for field_name in (
            "source_h3_resolution",
            "analysis_h3_resolution",
        ):
            resolution = getattr(self, field_name)
            if isinstance(resolution, bool) or not isinstance(resolution, int):
                raise ValueError(
                    f"Population count source {field_name} must be an integer"
                )
            if resolution < 0 or resolution > 15:
                raise ValueError(
                    f"Population count source {field_name} must be between 0 and 15"
                )
        if self.analysis_h3_resolution > self.source_h3_resolution:
            raise ValueError(
                "Population count analysis resolution must not be finer than "
                "its source resolution"
            )
        if self.aggregation != "sum_to_analysis_then_parent_rollup":
            raise ValueError(
                "Population count source aggregation must be "
                "'sum_to_analysis_then_parent_rollup'"
            )
        if self.accounting_total_policy != "source_total_before_domain_clip":
            raise ValueError(
                "Population count accounting_total_policy must be "
                "'source_total_before_domain_clip'"
            )
        if (
            isinstance(self.expected_row_count, bool)
            or not isinstance(self.expected_row_count, int)
            or self.expected_row_count <= 0
        ):
            raise ValueError(
                "Population count source expected_row_count must be positive"
            )
        if not math.isfinite(self.expected_total) or self.expected_total <= 0:
            raise ValueError(
                "Population count source expected_total must be positive and finite"
            )
        if self.analysis_h3_resolution not in self.expected_analysis_domain_totals:
            raise ValueError(
                "Population count source must declare the canonical "
                "analysis-domain total"
            )
        for resolution, total in self.expected_analysis_domain_totals.items():
            if (
                isinstance(resolution, bool)
                or not isinstance(resolution, int)
                or resolution < 0
                or resolution > self.analysis_h3_resolution
            ):
                raise ValueError(
                    "Population count expected-domain resolutions must be "
                    "valid rollups of the analysis resolution"
                )
            if (
                not math.isfinite(total)
                or total <= 0
                or total > self.expected_total
            ):
                raise ValueError(
                    "Population count expected analysis-domain totals must "
                    "be positive and no greater than the source total"
                )


@dataclass(frozen=True)
class RooftopSolarYieldContract:
    method: str
    specific_yield_kwh_per_kwp: float
    module_efficiency_stc_fraction: float
    expected_kwh_per_m2: float
    pvgis_version: str
    radiation_database: str
    data_period: str
    pv_technology: str
    mounting_place: str
    slope_deg: float
    aspect_deg: float
    system_loss_pct: float
    use_horizon: bool
    site_aggregation: str
    sample_site_count: int
    reference_urls: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.method != "pvgis_specific_yield_times_stc_efficiency":
            raise ValueError("Unsupported rooftop-solar annual-yield method")
        for field_name in (
            "specific_yield_kwh_per_kwp",
            "module_efficiency_stc_fraction",
            "expected_kwh_per_m2",
            "slope_deg",
            "aspect_deg",
            "system_loss_pct",
        ):
            value = getattr(self, field_name)
            if not math.isfinite(value):
                raise ValueError(
                    f"Rooftop-solar annual yield {field_name} must be finite"
                )
        if self.specific_yield_kwh_per_kwp <= 0:
            raise ValueError(
                "Rooftop-solar specific yield must be positive"
            )
        if not 0 < self.module_efficiency_stc_fraction <= 1:
            raise ValueError(
                "Rooftop-solar module efficiency must be in (0, 1]"
            )
        if self.expected_kwh_per_m2 <= 0:
            raise ValueError(
                "Rooftop-solar expected kWh per m2 must be positive"
            )
        derived_kwh_per_m2 = (
            self.specific_yield_kwh_per_kwp
            * self.module_efficiency_stc_fraction
        )
        if not math.isclose(
            self.expected_kwh_per_m2,
            derived_kwh_per_m2,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError(
                "Rooftop-solar expected kWh per m2 does not match its "
                "specific yield and module efficiency"
            )
        if not 0 <= self.slope_deg <= 90:
            raise ValueError("Rooftop-solar slope must be between 0 and 90")
        if not -180 <= self.aspect_deg <= 180:
            raise ValueError(
                "Rooftop-solar aspect must be between -180 and 180"
            )
        if not 0 <= self.system_loss_pct < 100:
            raise ValueError(
                "Rooftop-solar system loss must be in [0, 100)"
            )
        for field_name in (
            "pvgis_version",
            "radiation_database",
            "data_period",
            "pv_technology",
            "mounting_place",
            "site_aggregation",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(
                    f"Rooftop-solar annual yield {field_name} must not be blank"
                )
        if (
            isinstance(self.sample_site_count, bool)
            or not isinstance(self.sample_site_count, int)
            or self.sample_site_count <= 0
        ):
            raise ValueError(
                "Rooftop-solar sample_site_count must be positive"
            )
        if not self.reference_urls or any(
            not str(value).strip() for value in self.reference_urls
        ):
            raise ValueError(
                "Rooftop-solar annual yield must declare reference URLs"
            )


@dataclass(frozen=True)
class RooftopSolarAccountingContract:
    cap_at_solar_target: bool
    affects_geographic_potential: bool
    adds_establishment_candidates: bool


@dataclass(frozen=True)
class RooftopSolarMapReviewContract:
    canonical_group_id: str
    layer_ids: tuple[str, ...]
    buffer_value_source: str

    def __post_init__(self) -> None:
        if not self.canonical_group_id.strip():
            raise ValueError(
                "Rooftop-solar map-review group must not be blank"
            )
        if not self.layer_ids or any(
            not layer_id.strip() for layer_id in self.layer_ids
        ):
            raise ValueError(
                "Rooftop-solar map review must declare non-blank layers"
            )
        if len(set(self.layer_ids)) != len(self.layer_ids):
            raise ValueError(
                "Rooftop-solar map-review layers must be unique"
            )
        if self.buffer_value_source != "canonical_layer_default":
            raise ValueError(
                "Rooftop-solar map-review buffer must use the canonical "
                "layer default"
            )


@dataclass(frozen=True)
class RooftopSolarContract:
    status: str
    technology_key: str
    population_source: PopulationCountSourceContract
    map_review: RooftopSolarMapReviewContract
    panel_area_m2_per_person: ParameterContract
    annual_yield: RooftopSolarYieldContract
    accounting: RooftopSolarAccountingContract


@dataclass(frozen=True)
class DistributedGenerationContract:
    rooftop_solar: RooftopSolarContract | None = None


@dataclass(frozen=True)
class AnalysisContract:
    id: str
    region_id: str
    groups: tuple[str, ...]
    layers: dict[str, LayerContract]
    default_request: DefaultRequestContract | None = None
    analysis_domain: AnalysisDomainContract | None = None
    area_result: AreaResultContract | None = None
    ui: AnalysisUIContract | None = None
    distributed_generation: DistributedGenerationContract | None = None


def distance_coverage_contract(raw: dict[str, Any] | None) -> DistanceCoverageContract:
    if not raw:
        return DistanceCoverageContract()
    targets: dict[int, DistanceTargetCoverageContract] = {}
    for item in raw.get("targets") or []:
        resolution = item["resolution"]
        if isinstance(resolution, bool) or not isinstance(resolution, int):
            raise ValueError("Distance target resolution must be an integer")
        if resolution in targets:
            raise ValueError(
                f"Distance coverage contains duplicate R{resolution} targets"
            )
        targets[resolution] = DistanceTargetCoverageContract(
            resolution=resolution,
            target_cell_count=item["target_cell_count"],
            covered_cell_count=item["covered_cell_count"],
            missing_cell_count=item["missing_cell_count"],
            outside_cell_count=item["outside_cell_count"],
            missing_ids_sha256=str(item["missing_ids_sha256"]).lower(),
            outside_ids_sha256=str(item["outside_ids_sha256"]).lower(),
        )
    return DistanceCoverageContract(
        mode=str(raw.get("mode") or "complete"),
        missing_policy=str(raw.get("missing_policy") or "error"),
        expected_source_row_count=raw.get("expected_source_row_count"),
        source_ids_sha256=(
            str(raw["source_ids_sha256"]).lower()
            if raw.get("source_ids_sha256") is not None
            else None
        ),
        targets=targets,
    )


def source_contract(raw: dict[str, Any]) -> SourceContract:
    distance_h3_resolution = raw.get("distance_h3_resolution")
    return SourceContract(
        provider=str(raw["provider"]),
        asset_manifest=str(raw["asset_manifest"]),
        layer_id=str(raw["layer_id"]),
        expected_geometry_families=tuple(str(item) for item in raw["expected_geometry_families"]),
        data_representation=str(raw.get("data_representation") or "auto"),
        source_geometry_required=bool(raw.get("source_geometry_required", True)),
        geometry_collection_policy=str(
            raw.get("geometry_collection_policy") or "reject_mixed"
        ),
        geometry_validity_policy=str(
            raw.get("geometry_validity_policy") or "reject_invalid"
        ),
        distance_provider=(
            str(raw["distance_provider"])
            if raw.get("distance_provider") is not None
            else None
        ),
        distance_path=(
            str(raw["distance_path"])
            if raw.get("distance_path") is not None
            else None
        ),
        distance_h3_resolution=distance_h3_resolution,
        distance_coverage=distance_coverage_contract(raw.get("distance_coverage")),
    )


def analysis_domain_contract(
    raw: dict[str, Any] | None,
) -> AnalysisDomainContract | None:
    if not raw:
        return None
    rollups: dict[int, AnalysisDomainRollupContract] = {}
    for item in raw.get("rollups") or []:
        raw_resolution = item["resolution"]
        if isinstance(raw_resolution, bool) or not isinstance(raw_resolution, int):
            raise ValueError(
                "Analysis-domain rollup resolution must be an integer"
            )
        resolution = raw_resolution
        if resolution in rollups:
            raise ValueError(
                f"Analysis domain contains duplicate R{resolution} rollups"
            )
        rollups[resolution] = AnalysisDomainRollupContract(
            provider=str(item["provider"]),
            path=str(item["path"]),
            id_field=str(item["id_field"]),
            area_field=str(item.get("area_field") or ""),
            area_unit=str(item.get("area_unit") or ""),
            resolution=resolution,
            expected_cell_count=int(item["expected_cell_count"]),
        )
    return AnalysisDomainContract(
        provider=str(raw["provider"]),
        path=str(raw["path"]),
        id_field=str(raw["id_field"]),
        area_field=str(raw.get("area_field") or ""),
        area_unit=str(raw.get("area_unit") or ""),
        cell_kind=str(raw["cell_kind"]),
        resolution=int(raw["resolution"]),
        expected_cell_count=int(raw["expected_cell_count"]),
        rollups=rollups,
    )


def parameter_contract(parameter_id: str, raw: dict[str, Any]) -> ParameterContract:
    return ParameterContract(
        id=parameter_id,
        value_type=str(raw["type"]),
        unit=str(raw["unit"]) if raw.get("unit") else None,
        default=float(raw["default"]),
        minimum=float(raw["minimum"]) if raw.get("minimum") is not None else None,
        maximum=float(raw["maximum"]) if raw.get("maximum") is not None else None,
        step=float(raw["step"]) if raw.get("step") is not None else None,
    )


def group_ui_contract(raw: dict[str, Any]) -> GroupUIContract:
    return GroupUIContract(
        id=str(raw["id"]),
        label=str(raw["label"]),
        analysis_label=str(raw["analysis_label"]),
        interpretation=str(raw["interpretation"]),
        expanded_by_default=bool(raw.get("expanded_by_default", False)),
        blend_default=int(raw.get("blend_default", 50)),
        group_color=str(raw["group_color"]),
    )


def layer_ui_contract(raw: dict[str, Any] | None) -> LayerUIContract | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Layer ui must be an object")
    return LayerUIContract(
        note=str(raw["note"]),
        source_color=str(raw["source_color"]),
        point_radius=int(raw.get("point_radius", 4)),
        quality_flag=(
            str(raw["quality_flag"])
            if raw.get("quality_flag") is not None
            else None
        ),
    )


def analysis_ui_contract(
    raw: dict[str, Any] | None,
) -> AnalysisUIContract | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Analysis ui must be an object")
    groups: dict[str, GroupUIContract] = {}
    for item in raw.get("groups") or []:
        group = group_ui_contract(item)
        if group.id in groups:
            raise ValueError(
                f"Analysis ui contains duplicate group descriptor: {group.id}"
            )
        groups[group.id] = group
    return AnalysisUIContract(groups=groups)


def default_request_contract(
    raw: dict[str, Any] | None,
) -> DefaultRequestContract | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Analysis default_request must be an object")
    if "selected_layer_ids" not in raw:
        raise ValueError(
            "Analysis default_request must declare selected_layer_ids"
        )
    selected_layer_ids = raw["selected_layer_ids"]
    if not isinstance(selected_layer_ids, list):
        raise ValueError(
            "Analysis default_request selected_layer_ids must be a list"
        )
    return DefaultRequestContract(
        selected_layer_ids=tuple(str(item) for item in selected_layer_ids),
    )


def area_result_contract(
    raw: dict[str, Any] | None,
) -> AreaResultContract | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Analysis area_result must be an object")
    applicable_group_ids = raw.get("applicable_group_ids")
    if not isinstance(applicable_group_ids, list):
        raise ValueError(
            "Analysis area_result applicable_group_ids must be a list"
        )
    return AreaResultContract(
        technology=str(raw["technology"]),
        applicable_group_ids=tuple(str(item) for item in applicable_group_ids),
        restriction_combination=str(raw["restriction_combination"]),
        operation_order=str(raw["operation_order"]),
        denominator=str(raw["denominator"]),
        geometry_semantics=str(raw["geometry_semantics"]),
    )


def population_count_source_contract(
    raw: dict[str, Any],
) -> PopulationCountSourceContract:
    if not isinstance(raw, dict):
        raise ValueError("Population count source must be an object")
    for field_name in (
        "source_h3_resolution",
        "analysis_h3_resolution",
        "expected_row_count",
    ):
        if isinstance(raw.get(field_name), bool) or not isinstance(
            raw.get(field_name), int
        ):
            raise ValueError(
                f"Population count source {field_name} must be an integer"
            )
    expected_total = raw.get("expected_total")
    if isinstance(expected_total, bool) or not isinstance(
        expected_total, (int, float)
    ):
        raise ValueError(
            "Population count source expected_total must be numeric"
        )
    raw_domain_totals = raw.get("expected_analysis_domain_totals")
    if not isinstance(raw_domain_totals, list) or not raw_domain_totals:
        raise ValueError(
            "Population count source expected_analysis_domain_totals must "
            "be a non-empty list"
        )
    domain_totals: dict[int, float] = {}
    for item in raw_domain_totals:
        if not isinstance(item, dict):
            raise ValueError(
                "Population count expected-domain total must be an object"
            )
        resolution = item.get("resolution")
        total = item.get("total")
        if isinstance(resolution, bool) or not isinstance(resolution, int):
            raise ValueError(
                "Population count expected-domain resolution must be an integer"
            )
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            raise ValueError(
                "Population count expected-domain total must be numeric"
            )
        if resolution in domain_totals:
            raise ValueError(
                f"Duplicate population expected-domain R{resolution} total"
            )
        domain_totals[resolution] = float(total)
    return PopulationCountSourceContract(
        provider=str(raw["provider"]),
        path=str(raw["path"]),
        sha256=str(raw["sha256"]),
        format=str(raw["format"]),
        h3_id_field=str(raw["h3_id_field"]),
        value_field=str(raw["value_field"]),
        source_h3_resolution=raw["source_h3_resolution"],
        analysis_h3_resolution=raw["analysis_h3_resolution"],
        aggregation=str(raw["aggregation"]),
        expected_row_count=raw["expected_row_count"],
        expected_total=float(expected_total),
        accounting_total_policy=str(raw["accounting_total_policy"]),
        expected_analysis_domain_totals=domain_totals,
        semantics=str(raw["semantics"]),
    )


def rooftop_solar_yield_contract(
    raw: dict[str, Any],
) -> RooftopSolarYieldContract:
    if not isinstance(raw, dict):
        raise ValueError("Rooftop-solar annual yield must be an object")
    references = raw.get("reference_urls")
    if not isinstance(references, list):
        raise ValueError(
            "Rooftop-solar annual yield reference_urls must be a list"
        )
    numeric_fields = (
        "specific_yield_kwh_per_kwp",
        "module_efficiency_stc_fraction",
        "expected_kwh_per_m2",
        "slope_deg",
        "aspect_deg",
        "system_loss_pct",
    )
    for field_name in numeric_fields:
        if isinstance(raw.get(field_name), bool) or not isinstance(
            raw.get(field_name), (int, float)
        ):
            raise ValueError(
                f"Rooftop-solar annual yield {field_name} must be numeric"
            )
    sample_site_count = raw.get("sample_site_count")
    if isinstance(sample_site_count, bool) or not isinstance(
        sample_site_count, int
    ):
        raise ValueError(
            "Rooftop-solar sample_site_count must be an integer"
        )
    if not isinstance(raw.get("use_horizon"), bool):
        raise ValueError(
            "Rooftop-solar use_horizon must be an explicit boolean"
        )
    return RooftopSolarYieldContract(
        method=str(raw["method"]),
        specific_yield_kwh_per_kwp=float(
            raw["specific_yield_kwh_per_kwp"]
        ),
        module_efficiency_stc_fraction=float(
            raw["module_efficiency_stc_fraction"]
        ),
        expected_kwh_per_m2=float(raw["expected_kwh_per_m2"]),
        pvgis_version=str(raw["pvgis_version"]),
        radiation_database=str(raw["radiation_database"]),
        data_period=str(raw["data_period"]),
        pv_technology=str(raw["pv_technology"]),
        mounting_place=str(raw["mounting_place"]),
        slope_deg=float(raw["slope_deg"]),
        aspect_deg=float(raw["aspect_deg"]),
        system_loss_pct=float(raw["system_loss_pct"]),
        use_horizon=raw["use_horizon"],
        site_aggregation=str(raw["site_aggregation"]),
        sample_site_count=sample_site_count,
        reference_urls=tuple(str(value) for value in references),
    )


def rooftop_solar_accounting_contract(
    raw: dict[str, Any],
) -> RooftopSolarAccountingContract:
    if not isinstance(raw, dict):
        raise ValueError("Rooftop-solar accounting must be an object")
    required = (
        "cap_at_solar_target",
        "affects_geographic_potential",
        "adds_establishment_candidates",
    )
    if any(not isinstance(raw.get(key), bool) for key in required):
        raise ValueError(
            "Rooftop-solar accounting flags must be explicit booleans"
        )
    return RooftopSolarAccountingContract(
        cap_at_solar_target=raw["cap_at_solar_target"],
        affects_geographic_potential=raw[
            "affects_geographic_potential"
        ],
        adds_establishment_candidates=raw[
            "adds_establishment_candidates"
        ],
    )


def rooftop_solar_map_review_contract(
    raw: dict[str, Any],
) -> RooftopSolarMapReviewContract:
    if not isinstance(raw, dict):
        raise ValueError("Rooftop-solar map_review must be an object")
    layer_ids = raw.get("layer_ids")
    if not isinstance(layer_ids, list):
        raise ValueError(
            "Rooftop-solar map-review layer_ids must be a list"
        )
    return RooftopSolarMapReviewContract(
        canonical_group_id=str(raw["canonical_group_id"]),
        layer_ids=tuple(str(value) for value in layer_ids),
        buffer_value_source=str(raw["buffer_value_source"]),
    )


def distributed_generation_contract(
    raw: dict[str, Any] | None,
) -> DistributedGenerationContract | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Analysis distributed_generation must be an object")
    rooftop_raw = raw.get("rooftop_solar")
    if rooftop_raw is None:
        return DistributedGenerationContract()
    if not isinstance(rooftop_raw, dict):
        raise ValueError("Analysis rooftop_solar must be an object")
    panel_area_raw = rooftop_raw.get("panel_area_m2_per_person")
    if not isinstance(panel_area_raw, dict):
        raise ValueError(
            "Rooftop-solar panel_area_m2_per_person must be an object"
        )
    for field_name in ("default", "minimum", "maximum", "step"):
        if isinstance(panel_area_raw.get(field_name), bool) or not isinstance(
            panel_area_raw.get(field_name), (int, float)
        ):
            raise ValueError(
                "Rooftop-solar panel-area parameter values must be numeric"
            )
    return DistributedGenerationContract(
        rooftop_solar=RooftopSolarContract(
            status=str(rooftop_raw["status"]),
            technology_key=str(rooftop_raw["technology_key"]),
            population_source=population_count_source_contract(
                rooftop_raw["population_source"]
            ),
            map_review=rooftop_solar_map_review_contract(
                rooftop_raw["map_review"]
            ),
            panel_area_m2_per_person=parameter_contract(
                "panel_area_m2_per_person",
                panel_area_raw,
            ),
            annual_yield=rooftop_solar_yield_contract(
                rooftop_raw["annual_yield"]
            ),
            accounting=rooftop_solar_accounting_contract(
                rooftop_raw["accounting"]
            ),
        )
    )


def analysis_contract(raw: dict[str, Any]) -> AnalysisContract:
    layers: dict[str, LayerContract] = {}
    for item in raw.get("layers") or []:
        layer_id = str(item["id"])
        layers[layer_id] = LayerContract(
            id=layer_id,
            label=str(item["label"]),
            group_id=str(item["group_id"]),
            source=source_contract(item["source"]),
            operation=str(item["operation"]),
            parameters={
                str(key): parameter_contract(str(key), value)
                for key, value in (item.get("parameters") or {}).items()
            },
            ui=layer_ui_contract(item.get("ui")),
        )
    return AnalysisContract(
        id=str(raw["analysis_id"]),
        region_id=str(raw["region_id"]),
        groups=tuple(str(item) for item in raw.get("groups") or []),
        layers=layers,
        default_request=default_request_contract(raw.get("default_request")),
        analysis_domain=analysis_domain_contract(raw.get("analysis_domain")),
        area_result=area_result_contract(raw.get("area_result")),
        ui=analysis_ui_contract(raw.get("ui")),
        distributed_generation=distributed_generation_contract(
            raw.get("distributed_generation")
        ),
    )
