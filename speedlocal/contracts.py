from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


STANDARD_GROUP_IDS = ("roads", "population", "nature", "culture", "grid_infrastructure")
SUPPORTED_GEOMETRY_FAMILIES = {"point", "line", "polygon", "grid"}
SUPPORTED_OPERATIONS = {"distance_exclusion", "hard_exclusion"}


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
    distance_h3_resolution: int | None = None
    distance_coverage: DistanceCoverageContract = field(
        default_factory=DistanceCoverageContract
    )

    def __post_init__(self) -> None:
        if self.geometry_collection_policy not in {
            "reject_mixed",
            "highest_dimension",
        }:
            raise ValueError(
                "geometry_collection_policy must be 'reject_mixed' or "
                "'highest_dimension'"
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
class AnalysisContract:
    id: str
    region_id: str
    groups: tuple[str, ...]
    layers: dict[str, LayerContract]
    default_request: DefaultRequestContract | None = None
    analysis_domain: AnalysisDomainContract | None = None
    ui: AnalysisUIContract | None = None


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
        ui=analysis_ui_contract(raw.get("ui")),
    )
