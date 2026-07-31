from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PORT_ROOT = ROOT / "apps" / "v2_port"
PORT_APPS = PORT_ROOT / "apps"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"

for import_root in (ROOT, PORT_ROOT, PORT_APPS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import potential_app as app  # noqa: E402
from acceptance_model.layers import load_registry  # noqa: E402
from acceptance_model.runtime_geometry import (  # noqa: E402
    _resolve_confined_artifact_path,
)


def _bornholm_diagnostic_runtime_result(
    region: dict[str, Any],
    params: dict[str, float],
    selection: dict[str, list[str]],
) -> dict[str, Any]:
    """Replay the frozen diagnostic fixture outside the product wind path."""
    payload = json.loads(
        app._wind_runtime_config_json(
            params,
            layer_selection=selection,
            region_id=str(region.get("region_id") or ""),
        )
    )
    groups = payload.get("groups") or {}
    roads = groups.pop("roads", None)
    if roads is not None:
        groups["transport"] = roads
    return app.run_geometry_runtime(
        json.dumps(payload, sort_keys=True, ensure_ascii=False),
        str(region.get("region_id") or ""),
    )


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        (self.passes if condition else self.failures).append(
            ok if condition else fail
        )

    def emit(self) -> int:
        print("Bornholm V1-derived V2 archive diagnostics")
        print("=" * 43)
        print("\nNOTICE")
        print(
            "These checks protect diagnostic provenance only. "
            "They do not establish product readiness or frozen-V2 parity."
        )
        print("\nBLOCKERS")
        if self.failures:
            for index, failure in enumerate(self.failures, start=1):
                print(f"{index}. FAIL {failure}")
        else:
            print("None")
        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")
        status = "FAIL" if self.failures else "PASS"
        print(
            f"\nRESULT: {status} "
            f"({len(self.passes)} passed, {len(self.failures)} diagnostic blocker(s))"
        )
        return 1 if self.failures else 0


def _geojson_nonempty(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "FeatureCollection"
        and bool(value.get("features"))
    )


def _check_path_confinement(report: Report) -> None:
    with tempfile.TemporaryDirectory(
        prefix="speedlocal-bornholm-diagnostic-confinement-"
    ) as value:
        test_root = Path(value)
        artifact_root = test_root / "artifacts"
        outside_root = test_root / "outside"
        artifact_root.mkdir()
        outside_root.mkdir()
        inside_file = artifact_root / "inside.json"
        outside_file = outside_root / "config.json"
        inside_file.write_text("{}", encoding="utf-8")
        outside_file.write_text("{}", encoding="utf-8")

        inside_resolves = (
            _resolve_confined_artifact_path(artifact_root, inside_file)
            == inside_file.resolve()
        )
        direct_escape_rejected = False
        try:
            _resolve_confined_artifact_path(artifact_root, outside_file)
        except ValueError:
            direct_escape_rejected = True

        symlink_escape_rejected = True
        linked_directory = artifact_root / "linked"
        try:
            linked_directory.symlink_to(outside_root, target_is_directory=True)
        except OSError:
            pass
        else:
            try:
                _resolve_confined_artifact_path(
                    artifact_root,
                    linked_directory / "config.json",
                )
            except ValueError:
                pass
            else:
                symlink_escape_rejected = False

        report.check(
            inside_resolves
            and direct_escape_rejected
            and symlink_escape_rejected,
            "Diagnostic artifact paths remain inside their declared root.",
            "Diagnostic artifact path confinement accepted an escape.",
        )


def main() -> int:
    report = Report()
    source_value = os.environ.get(V2_SOURCE_ROOT_ENV, "").strip()
    source_root = Path(source_value).expanduser() if source_value else None
    report.check(
        bool(source_root and source_root.is_dir()),
        "Frozen V2 diagnostic source root exists.",
        f"Frozen V2 diagnostic source root is unavailable: {source_root}",
    )
    if source_root is None or not source_root.is_dir():
        return report.emit()

    bornholm_region = app.load_region("bornholm")
    _, _, bornholm_registry = load_registry("bornholm")
    behavior_reference = bornholm_region.get("behavior_reference") or {}
    report.check(
        bornholm_region.get("status") == "onboarding"
        and not bool((bornholm_region.get("landing_card") or {}).get("enabled"))
        and behavior_reference.get("status") == "diagnostic_only"
        and behavior_reference.get("frozen_v2_parity") is False
        and bornholm_registry.get("_runtime_strategy") == "precomputed_polygon",
        "Bornholm is disabled and its polygon material is diagnostic only.",
        "Bornholm diagnostic classification or runtime strategy is invalid.",
    )

    _check_path_confinement(report)

    selection = app._reference_default_wind_layer_selection("bornholm")
    expected_fixtures = (
        (300.0, "frozen_default_roads_300m", 3.9),
        (400.0, "frozen_roads_400m", 3.3),
    )
    for road_distance, fixture_id, expected_share in expected_fixtures:
        params = app._reference_default_wind_params()
        params["road_distance_m"] = road_distance
        try:
            result = _bornholm_diagnostic_runtime_result(
                bornholm_region,
                params,
                selection,
            )
            frame = app._wind_runtime_hex_layer_frame(
                bornholm_region,
                result,
                9,
            )
        except Exception as exc:
            report.check(
                False,
                "",
                f"Bornholm diagnostic fixture {road_distance:.0f} m failed: {exc}",
            )
            continue
        groups = result.get("groups") or {}
        combined = result.get("combined") or {}
        report.check(
            result.get("validated_fixture_id") == fixture_id
            and abs(
                float(combined.get("land_share_pct", -1.0))
                - expected_share
            )
            <= 1e-9
            and set(groups)
            == {"culture", "protected", "settlement", "transport"}
            and _geojson_nonempty(combined.get("geojson"))
            and all(
                _geojson_nonempty(group.get("geojson"))
                for group in groups.values()
            )
            and not frame.empty
            and frame["potential_area_share_pct"].between(
                0.0,
                100.0,
                inclusive="neither",
            ).any(),
            f"Bornholm diagnostic fixture {fixture_id} retains "
            f"{expected_share:.1f}% with partial-area H3 cells.",
            f"Bornholm diagnostic fixture {fixture_id} drifted.",
        )

    invalid_params = app._reference_default_wind_params()
    invalid_params["road_distance_m"] = 425.0
    try:
        _bornholm_diagnostic_runtime_result(
            bornholm_region,
            invalid_params,
            selection,
        )
    except RuntimeError as exc:
        report.check(
            "saknas ett validerat fryst polygonresultat" in str(exc),
            "An undeclared Bornholm diagnostic combination fails closed.",
            f"Bornholm diagnostic rejection was unclear: {exc}",
        )
    else:
        report.check(
            False,
            "",
            "Bornholm accepted an undeclared diagnostic configuration.",
        )

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
