from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


STANDARD_GROUP_IDS = ("roads", "population", "nature", "culture", "grid_infrastructure")
SUPPORTED_GEOMETRY_FAMILIES = {"point", "line", "polygon", "grid"}
SUPPORTED_OPERATIONS = {"distance_exclusion"}


@dataclass(frozen=True)
class SourceContract:
    provider: str
    asset_manifest: str
    layer_id: str
    expected_geometry_families: tuple[str, ...]
    data_representation: str = "auto"
    source_geometry_required: bool = True


@dataclass(frozen=True)
class AnalysisDomainContract:
    provider: str
    path: str
    id_field: str
    cell_kind: str
    resolution: int
    expected_cell_count: int


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
class LayerContract:
    id: str
    label: str
    group_id: str
    source: SourceContract
    operation: str
    parameters: dict[str, ParameterContract] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisContract:
    id: str
    region_id: str
    groups: tuple[str, ...]
    layers: dict[str, LayerContract]
    analysis_domain: AnalysisDomainContract | None = None


def source_contract(raw: dict[str, Any]) -> SourceContract:
    return SourceContract(
        provider=str(raw["provider"]),
        asset_manifest=str(raw["asset_manifest"]),
        layer_id=str(raw["layer_id"]),
        expected_geometry_families=tuple(str(item) for item in raw["expected_geometry_families"]),
        data_representation=str(raw.get("data_representation") or "auto"),
        source_geometry_required=bool(raw.get("source_geometry_required", True)),
    )


def analysis_domain_contract(
    raw: dict[str, Any] | None,
) -> AnalysisDomainContract | None:
    if not raw:
        return None
    return AnalysisDomainContract(
        provider=str(raw["provider"]),
        path=str(raw["path"]),
        id_field=str(raw["id_field"]),
        cell_kind=str(raw["cell_kind"]),
        resolution=int(raw["resolution"]),
        expected_cell_count=int(raw["expected_cell_count"]),
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
        )
    return AnalysisContract(
        id=str(raw["analysis_id"]),
        region_id=str(raw["region_id"]),
        groups=tuple(str(item) for item in raw.get("groups") or []),
        layers=layers,
        analysis_domain=analysis_domain_contract(raw.get("analysis_domain")),
    )
