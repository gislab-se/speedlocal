from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PORT_APPS = ROOT / "apps" / "v2_port" / "apps"
APP_PATH = ROOT / "apps" / "v2_port" / "potential_app.py"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
ACTIVE_REGION_IDS = ("trondelag",)
ROAD_TEST_DISTANCE_M = {
    "trondelag": 1000,
}
EXPECTED_WIND_SHARE_PCT = {
    "trondelag": (6.7, 6.2),
}

for import_root in (ROOT, PORT_APPS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from potential_model.manifests import load_region, v2_source_root  # noqa: E402


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        if condition:
            self.passes.append(ok)
        else:
            self.failures.append(fail)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def emit(self) -> int:
        print("SpeedLocal V2 port app smoke test")
        print("=" * 33)
        print("\nBLOCKERS")
        if self.failures:
            for idx, failure in enumerate(self.failures, start=1):
                print(f"{idx}. FAIL {failure}")
        else:
            print("None")
        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")
        if self.notes:
            print("\nNOTES")
            for item in self.notes:
                print(f"- {item}")
        status = "FAIL" if self.failures else "PASS"
        print(f"\nRESULT: {status} ({len(self.passes)} passed, {len(self.failures)} blocker(s))")
        return 1 if self.failures else 0


def _by_key(elements, key: str):
    return next(item for item in elements if item.key == key)


def _wind_share_pct(app: AppTest) -> float:
    value = next(
        item.value
        for item in app.metric
        if item.label == "Vind: potentiell landandel"
    )
    if value == "-":
        raise AssertionError("Wind land share was not calculated")
    return float(str(value).rstrip("%").replace(",", "."))


def _safe_wind_share_pct(app: AppTest) -> tuple[float | None, str | None]:
    try:
        return _wind_share_pct(app), None
    except (AssertionError, StopIteration, TypeError, ValueError) as exc:
        return None, str(exc)


def _session_state_value(app: AppTest, key: str):
    try:
        return app.session_state[key]
    except (AttributeError, KeyError):
        return None


def _wind_apply_button(app: AppTest):
    return next(
        item
        for item in app.button
        if str(item.key).startswith(
            "FormSubmitter:wind_unified_group_controls-"
        )
    )


def _rendered_text(app: AppTest) -> str:
    values: list[str] = []
    for collection_name in (
        "caption",
        "error",
        "info",
        "markdown",
        "text",
        "warning",
    ):
        for element in getattr(app, collection_name):
            values.append(str(element.value))
    return "\n".join(values)


def _select_roads_large_only(app: AppTest) -> None:
    for checkbox in app.checkbox:
        key = str(checkbox.key or "")
        if key.startswith("wind_control__layer__") and not checkbox.disabled:
            checkbox.set_value(
                key == "wind_control__layer__roads_large"
            )
        elif key.startswith("wind_control__group__") and not checkbox.disabled:
            checkbox.set_value(False)


def _check_roads_large_slice(report: Report) -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = "trondelag"
    app.run(timeout=120)
    initial_exceptions = [str(item.value) for item in app.exception]
    initial_errors = [str(item.value) for item in app.error]
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            "trondelag: roads_large slice setup failed: "
            f"exceptions={initial_exceptions}, errors={initial_errors}",
        )
        return

    _select_roads_large_only(app)
    road_slider = _by_key(
        app.slider,
        "wind_control__analysis__transport",
    )
    road_slider.set_value(300)
    _wind_apply_button(app).click().run(timeout=120)
    first_exceptions = [str(item.value) for item in app.exception]
    first_errors = [str(item.value) for item in app.error]
    if first_exceptions or first_errors:
        report.check(
            False,
            "",
            "trondelag: applying the roads_large-only slice at 300 m failed: "
            f"exceptions={first_exceptions}, errors={first_errors}",
        )
        return

    selected = app.session_state["wind_builder_selected_layers"]
    first_share = _wind_share_pct(app)
    report.check(
        selected.get("transport") == ["roads_large"]
        and not any(
            layer_ids
            for group_id, layer_ids in selected.items()
            if group_id != "transport"
        )
        and abs(first_share - 96.9) <= 0.05,
        "trondelag: roads_large-only R7 renders the canonical 300 m "
        "result (96.9%).",
        "trondelag: roads_large-only 300 m state/result drifted: "
        f"selection={selected}, share={first_share:.3f}%.",
    )

    road_slider = _by_key(
        app.slider,
        "wind_control__analysis__transport",
    )
    road_slider.set_value(1000)
    _wind_apply_button(app).click().run(timeout=120)
    second_exceptions = [str(item.value) for item in app.exception]
    second_errors = [str(item.value) for item in app.error]
    if second_exceptions or second_errors:
        report.check(
            False,
            "",
            "trondelag: applying the roads_large-only slice at 1000 m failed: "
            f"exceptions={second_exceptions}, errors={second_errors}",
        )
        return
    second_share = _wind_share_pct(app)
    report.check(
        abs(second_share - 95.5) <= 0.05,
        "trondelag: roads_large-only R7 visibly reacts at 1000 m "
        "(95.5%).",
        "trondelag: roads_large-only 1000 m result drifted: "
        f"expected 95.5%, got {second_share:.3f}%.",
    )

    display_mode = _by_key(app.radio, "combined_h3_display_mode")
    display_mode.set_value("selected").run(timeout=120)
    display_exceptions = [str(item.value) for item in app.exception]
    display_errors = [str(item.value) for item in app.error]
    if display_exceptions or display_errors:
        report.check(
            False,
            "",
            "trondelag: switching to selected H3 resolution failed: "
            f"exceptions={display_exceptions}, errors={display_errors}",
        )
        return
    resolution_control = _by_key(app.radio, "combined_h3_resolution")
    report.check(
        len(resolution_control.options) == 3
        and all(
            any(str(option).startswith(f"R{resolution}") for option in resolution_control.options)
            for resolution in (7, 6, 5)
        ),
        "trondelag: the real V2 Final resolution control exposes R7/R6/R5.",
        "trondelag: the V2 Final resolution options drifted: "
        f"{resolution_control.options}.",
    )

    expected_resolution_shares = {
        1000: {6: 91.0, 5: 80.9},
        300: {6: 92.2, 5: 81.9},
    }
    for buffer_m, expected_shares in expected_resolution_shares.items():
        if buffer_m != 1000:
            road_slider = _by_key(
                app.slider,
                "wind_control__analysis__transport",
            )
            road_slider.set_value(buffer_m)
            _wind_apply_button(app).click().run(timeout=120)
            buffer_exceptions = [str(item.value) for item in app.exception]
            buffer_errors = [str(item.value) for item in app.error]
            if buffer_exceptions or buffer_errors:
                report.check(
                    False,
                    "",
                    f"trondelag: applying {buffer_m} m before the R6/R5 "
                    f"display checks failed: exceptions={buffer_exceptions}, "
                    f"errors={buffer_errors}",
                )
                return

        for resolution, expected_share in expected_shares.items():
            resolution_control = _by_key(app.radio, "combined_h3_resolution")
            resolution_control.set_value(resolution).run(timeout=120)
            resolution_exceptions = [str(item.value) for item in app.exception]
            resolution_errors = [str(item.value) for item in app.error]
            runtime_failure = (
                "Vindruntime kunde inte köras"
                in _rendered_text(app)
            )
            resolution_state = _session_state_value(
                app,
                "combined_h3_resolution",
            )
            resolution_share, share_error = _safe_wind_share_pct(app)
            report.check(
                not resolution_exceptions
                and not resolution_errors
                and not runtime_failure
                and resolution_state == resolution
                and resolution_share is not None
                and abs(resolution_share - expected_share) <= 0.05,
                f"trondelag: roads_large-only V2 Final builds the canonical "
                f"R{resolution} result at {buffer_m} m "
                f"({expected_share:.1f}%).",
                f"trondelag: R{resolution}/{buffer_m} m display failed: "
                f"exceptions={resolution_exceptions}, "
                f"errors={resolution_errors}, "
                f"runtime_failure={runtime_failure}, "
                f"state={resolution_state}, share={resolution_share}, "
                f"share_error={share_error}.",
            )


def _check_missing_source_root(report: Report) -> None:
    configured = os.environ.pop(V2_SOURCE_ROOT_ENV, None)
    app = None
    try:
        app = AppTest.from_file(str(APP_PATH), default_timeout=120)
        app.query_params["region"] = "trondelag"
        app.run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"Missing V2 source root preflight could not run: {exc}",
        )
        return
    finally:
        if configured is not None:
            os.environ[V2_SOURCE_ROOT_ENV] = configured
    if app is None:
        return
    exceptions = [str(item.value) for item in app.exception]
    errors = [str(item.value) for item in app.error]
    report.check(
        not exceptions,
        "Missing V2 source root fails closed without an uncaught exception.",
        f"Missing V2 source root raised uncaught exceptions: {exceptions}",
    )
    report.check(
        len(errors) == 1 and V2_SOURCE_ROOT_ENV in errors[0],
        "Missing V2 source root renders one actionable configuration error.",
        f"Missing V2 source root rendered unexpected errors: {errors}",
    )


def main() -> int:
    report = Report()
    _check_missing_source_root(report)
    source_root = v2_source_root()
    report.note(f"{V2_SOURCE_ROOT_ENV}: {os.environ.get(V2_SOURCE_ROOT_ENV, '<not set>')}")
    report.check(APP_PATH.is_file(), "Quarantine app entrypoint exists.", f"Missing app: {APP_PATH}")
    report.check(
        bool(source_root and source_root.is_dir()),
        "V2 source root exists.",
        f"V2 source root does not exist: {source_root}",
    )
    if not APP_PATH.is_file() or source_root is None or not source_root.is_dir():
        return report.emit()

    for region_id in ACTIVE_REGION_IDS:
        test_road_distance = ROAD_TEST_DISTANCE_M[region_id]
        expected_before, expected_after = EXPECTED_WIND_SHARE_PCT[region_id]
        region = load_region(region_id)
        report.check(
            region.get("_v2_source_available") is True,
            f"{region_id}: detailed V2 source manifest is available.",
            f"{region_id}: detailed V2 source manifest is unavailable.",
        )
        app = AppTest.from_file(str(APP_PATH), default_timeout=120)
        app.query_params["region"] = region_id
        app.run(timeout=120)
        exceptions = [str(item.value) for item in app.exception]
        errors = [str(item.value) for item in app.error]
        report.check(
            not exceptions,
            f"{region_id}: app executes without uncaught exceptions.",
            f"{region_id}: uncaught exceptions: {exceptions}",
        )
        report.check(
            not errors,
            f"{region_id}: app renders without st.error output.",
            f"{region_id}: st.error output: {errors}",
        )
        report.check(
            len(app.button) > 0 and len(app.metric) > 0,
            f"{region_id}: interactive workspace elements render.",
            f"{region_id}: expected buttons and metrics did not render.",
        )
        if exceptions or errors:
            report.note(f"{region_id}: road interaction skipped because initial render failed.")
            continue

        try:
            road_slider = _by_key(app.slider, "wind_control__analysis__transport")
            medium_roads = _by_key(app.checkbox, "wind_control__layer__roads_medium")
            large_roads = _by_key(app.checkbox, "wind_control__layer__roads_large")
            apply_button = _wind_apply_button(app)
            before_share = _wind_share_pct(app)
        except Exception as exc:
            report.check(False, "", f"{region_id}: road controls/result are unavailable: {exc}")
            continue

        report.check(
            not road_slider.disabled
            and not medium_roads.disabled
            and not large_roads.disabled,
            f"{region_id}: medium/large road controls are enabled.",
            f"{region_id}: one or more road controls are disabled.",
        )
        report.check(
            int(road_slider.value) == 300
            and bool(medium_roads.value)
            and bool(large_roads.value),
            f"{region_id}: frozen-V2 road defaults render (300 m, medium + large).",
            f"{region_id}: unexpected road defaults: slider={road_slider.value}, "
            f"medium={medium_roads.value}, large={large_roads.value}.",
        )
        report.check(
            int(road_slider.min) == 100
            and int(road_slider.max) == 2000
            and int(road_slider.step) == 25,
            f"{region_id}: road slider reads its canonical 100/2000/25 "
            "contract.",
            f"{region_id}: unexpected road slider contract: "
            f"min={road_slider.min}, max={road_slider.max}, "
            f"step={road_slider.step}.",
        )
        report.check(
            abs(before_share - expected_before) <= 0.05,
            f"{region_id}: default wind share matches the accepted reviewed "
            "V2 Final baseline "
            f"({expected_before:.1f}%).",
            f"{region_id}: default wind share drifted from the accepted reviewed "
            f"V2 Final baseline: expected {expected_before:.1f}%, "
            f"got {before_share:.3f}%.",
        )

        road_slider.set_value(test_road_distance)
        apply_button.click().run(timeout=120)
        interaction_exceptions = [str(item.value) for item in app.exception]
        interaction_errors = [str(item.value) for item in app.error]
        report.check(
            not interaction_exceptions and not interaction_errors,
            f"{region_id}: applying a changed road buffer completes without app errors.",
            f"{region_id}: road interaction failed: "
            f"exceptions={interaction_exceptions}, errors={interaction_errors}",
        )
        if interaction_exceptions or interaction_errors:
            continue

        try:
            after_share = _wind_share_pct(app)
            applied_slider = _by_key(
                app.slider,
                "wind_control__analysis__transport",
            )
            applied_params = app.session_state["wind_builder_params"]
            applied_road_distance = float(applied_params["road_distance_m"])
        except Exception as exc:
            report.check(False, "", f"{region_id}: applied road result cannot be read: {exc}")
            continue

        report.check(
            int(applied_slider.value) == test_road_distance
            and applied_road_distance == float(test_road_distance),
            f"{region_id}: submitted {test_road_distance} m road buffer reaches applied state.",
            f"{region_id}: submitted road buffer was not applied: "
            f"slider={applied_slider.value}, state={applied_road_distance}.",
        )
        report.check(
            abs(after_share - expected_after) <= 0.05,
            f"{region_id}: changed-road result matches the accepted reviewed "
            "V2 Final baseline "
            f"({expected_after:.1f}%).",
            f"{region_id}: changed-road result drifted from the accepted reviewed "
            f"V2 Final baseline: expected {expected_after:.1f}%, "
            f"got {after_share:.3f}%.",
        )
        report.note(
            f"{region_id}: road buffer 300 -> {test_road_distance} m changed wind land share "
            f"{before_share:.3f}% -> {after_share:.3f}%."
        )
        report.note(f"{region_id}: {len(app.warning)} domain warning(s) rendered.")

    _check_disabled_bornholm_route(report)
    _check_roads_large_slice(report)
    return report.emit()


def _check_disabled_bornholm_route(report: Report) -> None:
    bornholm = load_region("bornholm")
    behavior_reference = bornholm.get("behavior_reference") or {}
    report.check(
        bornholm.get("status") == "onboarding"
        and not bool((bornholm.get("landing_card") or {}).get("enabled"))
        and behavior_reference.get("status") == "diagnostic_only"
        and behavior_reference.get("frozen_v2_parity") is False,
        "Bornholm is cataloged for onboarding and excluded from V2 parity.",
        "Bornholm is not safely classified as disabled onboarding.",
    )

    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = "bornholm"
    app.run(timeout=120)
    bornholm_exceptions = [str(item.value) for item in app.exception]
    bornholm_errors = [str(item.value) for item in app.error]
    try:
        bornholm_button = _by_key(app.button, "select_region_bornholm")
        trondelag_button = _by_key(app.button, "select_region_trondelag")
    except Exception as exc:
        report.check(
            False,
            "",
            f"Bornholm onboarding landing controls are unavailable: {exc}",
        )
        return
    workspace_metrics = [
        item for item in app.metric
        if item.label == "Vind: potentiell landandel"
    ]
    report.check(
        not bornholm_exceptions
        and not bornholm_errors
        and bornholm_button.disabled
        and not trondelag_button.disabled
        and not workspace_metrics,
        "A direct Bornholm URL fails closed on the landing page with no workspace result.",
        "A direct Bornholm URL exposed an active workspace or invalid landing state: "
        f"exceptions={bornholm_exceptions}, errors={bornholm_errors}, "
        f"bornholm_disabled={bornholm_button.disabled}, metrics={len(workspace_metrics)}.",
    )

    app.query_params["region"] = "trondelag"
    app.run(timeout=120)
    trondelag_exceptions = [str(item.value) for item in app.exception]
    trondelag_errors = [str(item.value) for item in app.error]
    report.check(
        not trondelag_exceptions
        and not trondelag_errors
        and abs(_wind_share_pct(app) - 6.7) <= 0.05,
        "Trondelag remains directly routable after the disabled Bornholm probe.",
        "Trondelag did not render after the disabled Bornholm probe: "
        f"exceptions={trondelag_exceptions}, errors={trondelag_errors}.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
