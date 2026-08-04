from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PORT_APPS = ROOT / "apps" / "v2_port" / "apps"
APP_PATH = ROOT / "apps" / "v2_port" / "potential_app.py"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
TRONDELAG_REGION_ID = "trondelag"
STANDARD_CANONICAL_GROUP_IDS = (
    "roads",
    "population",
    "nature",
    "culture",
    "grid_infrastructure",
)
WIND_SELECTION_STATE_KEY = "wind_builder_selected_layers"
WIND_PARAMS_STATE_KEY = "wind_builder_params"
WIND_EMPTY_SELECTION_STATE_KEY = "wind_empty_selection_active"
WIND_ANALYSIS_KEY_PREFIX = "wind_control__analysis__"
WIND_GROUP_KEY_PREFIX = "wind_control__group__"
WIND_LAYER_KEY_PREFIX = "wind_control__layer__"
WIND_VISUAL_SOURCE_KEY_PREFIX = "wind_control__visual_source__"
WIND_VISUAL_BUFFER_KEY_PREFIX = "wind_control__visual_buffer__"

for import_root in (ROOT, PORT_APPS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from acceptance_model.layers import (  # noqa: E402
    layer_status_table,
    load_registry,
)
from potential_model.map_rendering import build_layered_hex_map_html  # noqa: E402
from potential_model.manifests import load_region, v2_source_root  # noqa: E402
from potential_model.speedlocal_bridge import (  # noqa: E402
    culture_control_contract,
    default_wind_layer_selection,
    grid_control_contract,
    nature_control_contract,
    population_control_contract,
    public_wind_group_ids,
    roads_control_contract,
)
from speedlocal.catalogs import load_analysis  # noqa: E402


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
        if item.label == "Vind: genomsnittlig potential per analyscell"
    )
    if value == "-":
        raise AssertionError("Wind mean cell potential was not calculated")
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


def _app_failures(app: AppTest) -> tuple[list[str], list[str]]:
    return (
        [str(item.value) for item in app.exception],
        [str(item.value) for item in app.error],
    )


def _check_map_interaction_control(report: Report) -> None:
    map_html = build_layered_hex_map_html(
        [
            {
                "name": "Testlager",
                "feature_collection": {
                    "type": "FeatureCollection",
                    "features": [],
                },
            }
        ],
        center=[63.4, 10.4],
        zoom=7,
        map_state_key="interaction-control-test",
    )
    required_contract = (
        "map-interaction-control",
        "Panorera kartan",
        "Granska kartobjekt",
        "setInteractionMode(modeValue)",
        "map.dragging.enable()",
        "map.dragging.disable()",
        "setInteractionMode(interactionMode)",
        "storageKey('interaction-mode')",
        "__potentialMapSetInteractionMode",
        "map-pan-mode .leaflet-pane canvas",
        "map.closeTooltip()",
    )
    report.check(
        all(marker in map_html for marker in required_contract),
        "The map exposes a local QGIS-style pan/inspect control below zoom "
        "without a Streamlit rerun.",
        "The map pan/inspect control contract is incomplete: "
        + ", ".join(marker for marker in required_contract if marker not in map_html),
    )


def _element_ids(elements, prefix: str) -> set[str]:
    return {
        str(item.key)[len(prefix):]
        for item in elements
        if str(item.key or "").startswith(prefix)
    }


def _ready_public_ui_contract(
    region_id: str,
) -> tuple[set[str], set[str], set[str], set[str]]:
    registry_groups, registry_layers, registry_meta = load_registry(region_id)
    public_group_ids = set(public_wind_group_ids(region_id))
    manifest_public_group_ids = {
        "roads",
        "population",
        "nature",
        "culture",
        "grid_infrastructure",
    }
    legacy_public_group_ids = public_group_ids - manifest_public_group_ids
    roads_group = roads_control_contract(region_id)
    population_group = population_control_contract(region_id)
    nature_group = nature_control_contract(region_id)
    culture_group = culture_control_contract(region_id)
    grid_group = grid_control_contract(region_id)
    manifest_layer_ids = {
        layer.id
        for group in (
            roads_group,
            population_group,
            nature_group,
            culture_group,
            grid_group,
        )
        for layer in group.layers
    }
    status_frame = layer_status_table(registry_meta)
    status_by_layer = {
        str(row["layer_id"]): row.to_dict()
        for _, row in status_frame.iterrows()
    }

    def is_ready(layer_id: str) -> bool:
        status = status_by_layer.get(str(layer_id), {})
        return (
            bool(status.get("geojson_ready"))
            and bool(status.get("distance_ready"))
            and bool(status.get("source_exists"))
            and int(status.get("feature_count", 0) or 0) > 0
            and str(status.get("status", "")) == "ok"
        )

    ready_layer_ids = {
        str(layer_id)
        for layer_id, layer in registry_layers.items()
        if str(layer.group_id) in legacy_public_group_ids
        and str(layer_id) not in manifest_layer_ids
        and is_ready(str(layer_id))
    }
    ready_layer_ids.update(
        layer.id
        for group in (
            roads_group,
            population_group,
            nature_group,
            culture_group,
            grid_group,
        )
        for layer in group.layers
        if layer.ready
    )
    ready_group_ids = {
        str(registry_layers[layer_id].group_id)
        for layer_id in ready_layer_ids
        if layer_id in registry_layers
        and layer_id not in manifest_layer_ids
    }
    if any(layer.ready for layer in roads_group.layers):
        ready_group_ids.add("roads")
    if any(layer.ready for layer in population_group.layers):
        ready_group_ids.add("population")
    if any(layer.ready for layer in nature_group.layers):
        ready_group_ids.add("nature")
    if any(layer.ready for layer in culture_group.layers):
        ready_group_ids.add("culture")
    if any(layer.ready for layer in grid_group.layers):
        ready_group_ids.add("grid_infrastructure")
    public_layer_ids = {
        str(layer_id)
        for layer_id, layer in registry_layers.items()
        if str(layer.group_id) in legacy_public_group_ids
    }
    public_layer_ids.update(manifest_layer_ids)
    extra_group_ids = set(registry_groups) - public_group_ids - {"transport"}
    return (
        ready_group_ids,
        ready_layer_ids,
        public_layer_ids,
        extra_group_ids,
    )


def _check_manifest_empty_start_and_public_controls(
    report: Report,
) -> None:
    region_id = TRONDELAG_REGION_ID
    try:
        analysis = load_analysis(region_id, "wind")
        manifest_selection = default_wind_layer_selection(region_id)
        (
            ready_group_ids,
            ready_layer_ids,
            public_layer_ids,
            extra_group_ids,
        ) = _ready_public_ui_contract(region_id)
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: manifest-driven UI contract could not load: {exc}",
        )
        return

    report.check(
        tuple(analysis.groups) == STANDARD_CANONICAL_GROUP_IDS
        and analysis.default_request is not None
        and analysis.default_request.selected_layer_ids == ()
        and not any(manifest_selection.values()),
        f"{region_id}: wind manifest declares the five standard groups and "
        "an empty startup request.",
        f"{region_id}: invalid startup contract: groups={analysis.groups}, "
        f"default_request={analysis.default_request}, "
        f"selection={manifest_selection}.",
    )

    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = region_id
    app.run(timeout=120)
    exceptions, errors = _app_failures(app)
    report.check(
        not exceptions and not errors,
        f"{region_id}: empty manifest-driven start renders without app errors.",
        f"{region_id}: empty start failed: exceptions={exceptions}, "
        f"errors={errors}.",
    )
    if exceptions or errors:
        return

    selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    empty_selection_active = _session_state_value(
        app,
        WIND_EMPTY_SELECTION_STATE_KEY,
    )
    wind_share, share_error = _safe_wind_share_pct(app)
    layer_controls = [
        item
        for item in app.checkbox
        if str(item.key or "").startswith(WIND_LAYER_KEY_PREFIX)
    ]
    group_controls = [
        item
        for item in app.checkbox
        if str(item.key or "").startswith(WIND_GROUP_KEY_PREFIX)
    ]
    report.check(
        isinstance(selected, dict)
        and not any(selected.values())
        and all(not bool(item.value) for item in layer_controls)
        and all(not bool(item.value) for item in group_controls)
        and empty_selection_active is True
        and wind_share is not None
        and abs(wind_share - 100.0) <= 0.05
        and "Inga aktiva filter" in _rendered_text(app),
        f"{region_id}: product starts with no filters and 100.0% unfiltered "
        "wind potential.",
        f"{region_id}: startup state drifted: selection={selected}, "
        f"empty_active={empty_selection_active}, share={wind_share}, "
        f"share_error={share_error}.",
    )

    rendered_group_ids = _element_ids(app.slider, WIND_ANALYSIS_KEY_PREFIX)
    rendered_layer_ids = _element_ids(app.checkbox, WIND_LAYER_KEY_PREFIX)
    enabled_layer_ids = {
        str(item.key)[len(WIND_LAYER_KEY_PREFIX):]
        for item in layer_controls
        if not item.disabled
    }
    rendered_group_toggle_ids = _element_ids(
        app.checkbox,
        WIND_GROUP_KEY_PREFIX,
    )
    extra_layer_ids = {
        str(layer_id)
        for layer_id, layer in load_registry(region_id)[1].items()
        if str(layer.group_id) in extra_group_ids
        and str(layer_id) not in public_layer_ids
    }
    report.check(
        rendered_group_ids == ready_group_ids
        and enabled_layer_ids == ready_layer_ids
        and rendered_layer_ids <= public_layer_ids
        and not (rendered_group_toggle_ids & extra_group_ids)
        and not (rendered_layer_ids & extra_layer_ids),
        f"{region_id}: UI exposes only ready controls from the five public "
        "groups.",
        f"{region_id}: public/ready UI drifted: rendered_groups="
        f"{sorted(rendered_group_ids)}, expected_groups="
        f"{sorted(ready_group_ids)}, enabled_layers="
        f"{sorted(enabled_layer_ids)}, expected_layers="
        f"{sorted(ready_layer_ids)}, extra_group_controls="
        f"{sorted(rendered_group_toggle_ids & extra_group_ids)}, "
        f"extra_layers={sorted(rendered_layer_ids & extra_layer_ids)}.",
    )

    try:
        road_slider = _by_key(
            app.slider,
            f"{WIND_ANALYSIS_KEY_PREFIX}roads",
        )
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: manifest-backed road slider is unavailable: {exc}",
        )
    else:
        report.check(
            not road_slider.disabled
            and int(road_slider.value) == 300
            and int(road_slider.min) == 100
            and int(road_slider.max) == 2000
            and int(road_slider.step) == 25,
            f"{region_id}: empty selection keeps the manifest-backed "
            "100/2000/25 road parameter contract available.",
            f"{region_id}: road parameter contract drifted: "
            f"disabled={road_slider.disabled}, value={road_slider.value}, "
            f"min={road_slider.min}, max={road_slider.max}, "
            f"step={road_slider.step}.",
        )

    try:
        population_slider = _by_key(
            app.slider,
            f"{WIND_ANALYSIS_KEY_PREFIX}population",
        )
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: manifest-backed population slider is "
            f"unavailable: {exc}",
        )
    else:
        report.check(
            not population_slider.disabled
            and int(population_slider.value) == 100
            and int(population_slider.min) == 100
            and int(population_slider.max) == 3000
            and int(population_slider.step) == 50,
            f"{region_id}: population uses the manifest-backed "
            "100/3000/50 parameter contract.",
            f"{region_id}: population parameter contract drifted: "
            f"disabled={population_slider.disabled}, "
            f"value={population_slider.value}, min={population_slider.min}, "
            f"max={population_slider.max}, step={population_slider.step}.",
        )

    try:
        nature_slider = _by_key(
            app.slider,
            f"{WIND_ANALYSIS_KEY_PREFIX}nature",
        )
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: manifest-backed nature slider is unavailable: {exc}",
        )
    else:
        report.check(
            not nature_slider.disabled
            and int(nature_slider.value) == 0
            and int(nature_slider.min) == 0
            and int(nature_slider.max) == 2000
            and int(nature_slider.step) == 50,
            f"{region_id}: nature uses the manifest-backed 0/2000/50 "
            "hard-exclusion buffer contract.",
            f"{region_id}: nature parameter contract drifted: "
            f"disabled={nature_slider.disabled}, value={nature_slider.value}, "
            f"min={nature_slider.min}, max={nature_slider.max}, "
            f"step={nature_slider.step}.",
        )

    try:
        culture_slider = _by_key(
            app.slider,
            f"{WIND_ANALYSIS_KEY_PREFIX}culture",
        )
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: manifest-backed culture slider is unavailable: "
            f"{exc}",
        )
    else:
        report.check(
            not culture_slider.disabled
            and int(culture_slider.value) == 0
            and int(culture_slider.min) == 0
            and int(culture_slider.max) == 1500
            and int(culture_slider.step) == 50,
            f"{region_id}: culture uses the manifest-backed 0/1500/50 "
            "hard-exclusion buffer contract.",
            f"{region_id}: culture parameter contract drifted: "
            f"disabled={culture_slider.disabled}, "
            f"value={culture_slider.value}, min={culture_slider.min}, "
            f"max={culture_slider.max}, step={culture_slider.step}.",
        )

    try:
        grid_slider = _by_key(
            app.slider,
            f"{WIND_ANALYSIS_KEY_PREFIX}grid_infrastructure",
        )
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: manifest-backed grid slider is unavailable: {exc}",
        )
    else:
        report.check(
            not grid_slider.disabled
            and int(grid_slider.value) == 2000
            and int(grid_slider.min) == 500
            and int(grid_slider.max) == 15000
            and int(grid_slider.step) == 250,
            f"{region_id}: grid infrastructure uses the manifest-backed "
            "500/15000/250 proximity-feasibility contract.",
            f"{region_id}: grid parameter contract drifted: "
            f"disabled={grid_slider.disabled}, value={grid_slider.value}, "
            f"min={grid_slider.min}, max={grid_slider.max}, "
            f"step={grid_slider.step}.",
        )

    mix_slider_key = f"energy_model_mix_solar_share_{region_id}"
    try:
        mix_slider = _by_key(app.slider, mix_slider_key)
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: continuous wind/solar mix control is unavailable: "
            f"{exc}",
        )
    else:
        report.check(
            not mix_slider.disabled
            and int(mix_slider.min) == 0
            and int(mix_slider.max) == 100
            and int(mix_slider.step) == 1,
            f"{region_id}: wind/solar mix exposes every integer allocation "
            "from 0 to 100 percent.",
            f"{region_id}: continuous mix control drifted: "
            f"disabled={mix_slider.disabled}, min={mix_slider.min}, "
            f"max={mix_slider.max}, step={mix_slider.step}.",
        )

    grid_layers = {
        layer.id: layer for layer in grid_control_contract(region_id).layers
    }
    population_layers = {
        layer.id: layer
        for layer in population_control_contract(region_id).layers
    }
    leisure_home_layer = population_layers.get("built_low_selection")
    report.check(
        leisure_home_layer is not None
        and int(leisure_home_layer.point_radius) == 4,
        f"{region_id}: the manifest renders leisure homes as compact 4 px "
        "source markers, not map-scale discs.",
        f"{region_id}: the leisure-home source marker radius drifted: "
        f"{None if leisure_home_layer is None else leisure_home_layer.point_radius}.",
    )
    report.check(
        leisure_home_layer is not None
        and leisure_home_layer.quality_flag == "caution"
        and "1 km-gridproxy" in leisure_home_layer.note,
        f"{region_id}: the manifest discreetly flags the coarse leisure-home "
        "grid proxy in the control and explains it in the tooltip.",
        f"{region_id}: the leisure-home quality flag or explanation drifted.",
    )
    turbine_layer = grid_layers.get("existing_wind_turbines")
    report.check(
        turbine_layer is not None and int(turbine_layer.point_radius) == 4,
        f"{region_id}: the manifest renders existing wind turbines as compact "
        "4 px source markers, not map-scale discs.",
        f"{region_id}: the existing-wind-turbine source marker radius drifted: "
        f"{None if turbine_layer is None else turbine_layer.point_radius}.",
    )

    visual_ids = (
        _element_ids(app.toggle, WIND_VISUAL_SOURCE_KEY_PREFIX)
        | _element_ids(app.toggle, WIND_VISUAL_BUFFER_KEY_PREFIX)
    )
    report.check(
        not visual_ids,
        f"{region_id}: map-review toggles stay hidden while no analysis "
        "layers are selected.",
        f"{region_id}: map-review toggles rendered for an empty selection: "
        f"{sorted(visual_ids)}.",
    )

    try:
        _select_road_layers(app, ("roads_large",))
        _wind_apply_button(app).click().run(timeout=120)
        _by_key(app.button, "wind_unified_reset_filters").click().run(
            timeout=120
        )
    except Exception as exc:
        report.check(
            False,
            "",
            f"{region_id}: Nollställ filter failed during interaction: {exc}",
        )
    else:
        reset_exceptions, reset_errors = _app_failures(app)
        reset_selection = _session_state_value(app, WIND_SELECTION_STATE_KEY)
        report.check(
            not reset_exceptions
            and not reset_errors
            and isinstance(reset_selection, dict)
            and not any(reset_selection.values())
            and _session_state_value(
                app,
                WIND_EMPTY_SELECTION_STATE_KEY,
            )
            is True,
            f"{region_id}: Nollställ filter clears instantiated wind "
            "widgets through a pre-rerun callback.",
            f"{region_id}: Nollställ filter did not return to the empty "
            f"state: selection={reset_selection}, exceptions="
            f"{reset_exceptions}, errors={reset_errors}.",
        )

    app.session_state["potential_start_default_version_trondelag"] = (
        "manifest_empty_selection_v6"
    )
    app.session_state[WIND_SELECTION_STATE_KEY] = {
        "settlement": ["built_centre"]
    }
    app.session_state["wind_control__analysis__settlement"] = 500
    app.session_state["wind_control__group__settlement"] = True
    app.run(timeout=120)
    migration_exceptions, migration_errors = _app_failures(app)
    migrated_selection = _session_state_value(
        app,
        WIND_SELECTION_STATE_KEY,
    )
    report.check(
        not migration_exceptions
        and not migration_errors
        and isinstance(migrated_selection, dict)
        and not any(migrated_selection.values())
        and _session_state_value(
            app,
            "potential_start_default_version_trondelag",
        )
        == "manifest_grid_group_v1"
        and not any(
            item.key == "wind_control__group__settlement"
            for item in app.checkbox
        )
        and any(
            item.key == "wind_control__analysis__population"
            for item in app.slider
        ),
        f"{region_id}: a pre-migration browser session resets once to the "
        "canonical population control without an app error.",
        f"{region_id}: stale settlement session migration failed: "
        f"selection={migrated_selection}, exceptions={migration_exceptions}, "
        f"errors={migration_errors}.",
    )


def _select_wind_group_layers(
    app: AppTest,
    group_id: str,
    layer_ids: tuple[str, ...],
) -> None:
    selected_layer_ids = set(layer_ids)
    for checkbox in app.checkbox:
        key = str(checkbox.key or "")
        if key.startswith("wind_control__layer__") and not checkbox.disabled:
            layer_id = key[len("wind_control__layer__"):]
            checkbox.set_value(layer_id in selected_layer_ids)
        elif key.startswith("wind_control__group__") and not checkbox.disabled:
            rendered_group_id = key[len("wind_control__group__"):]
            checkbox.set_value(rendered_group_id == str(group_id))


def _select_road_layers(app: AppTest, layer_ids: tuple[str, ...]) -> None:
    _select_wind_group_layers(app, "roads", layer_ids)


def _check_wind_map_review_toggles(
    report: Report,
    app: AppTest,
    expected_share: float,
    group_id: str = "roads",
    group_label: str = "roads",
) -> bool:
    baseline_selection = deepcopy(
        _session_state_value(app, WIND_SELECTION_STATE_KEY)
    )
    baseline_params = deepcopy(
        _session_state_value(app, WIND_PARAMS_STATE_KEY)
    )
    baseline_share, baseline_share_error = _safe_wind_share_pct(app)
    source_key = f"{WIND_VISUAL_SOURCE_KEY_PREFIX}{group_id}"
    buffer_key = f"{WIND_VISUAL_BUFFER_KEY_PREFIX}{group_id}"
    try:
        source_toggle = _by_key(app.toggle, source_key)
        buffer_toggle = _by_key(app.toggle, buffer_key)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: external {group_label} map-review toggles are "
            "unavailable: "
            f"{exc}",
        )
        return False

    report.check(
        not source_toggle.disabled and not buffer_toggle.disabled,
        f"trondelag: {group_label} source and manifest-backed buffer toggles render "
        "outside the analysis form.",
        "trondelag: source or buffer map-review toggle is disabled.",
    )
    if source_toggle.disabled or buffer_toggle.disabled:
        return False

    source_toggle.set_value(True).run(timeout=120)
    source_exceptions, source_errors = _app_failures(app)
    source_selection = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    source_params = _session_state_value(app, WIND_PARAMS_STATE_KEY)
    source_share, source_share_error = _safe_wind_share_pct(app)
    report.check(
        not source_exceptions
        and not source_errors
        and _session_state_value(app, source_key) is True
        and source_selection == baseline_selection
        and source_params == baseline_params
        and baseline_share is not None
        and source_share is not None
        and abs(baseline_share - expected_share) <= 0.05
        and abs(source_share - baseline_share) <= 0.001,
        "trondelag: source-map toggle changes only map-review state; "
        "analysis selection, parameters, and metric stay unchanged.",
        "trondelag: source-map toggle changed analysis state: "
        f"exceptions={source_exceptions}, errors={source_errors}, "
        f"selection={source_selection}, params_equal="
        f"{source_params == baseline_params}, baseline_share="
        f"{baseline_share}, source_share={source_share}, "
        f"share_errors={[baseline_share_error, source_share_error]}.",
    )
    if source_exceptions or source_errors:
        return False

    try:
        buffer_toggle = _by_key(app.toggle, buffer_key)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: buffer map-review toggle disappeared: {exc}",
        )
        return False
    buffer_toggle.set_value(True).run(timeout=120)
    buffer_exceptions, buffer_errors = _app_failures(app)
    buffer_selection = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    buffer_params = _session_state_value(app, WIND_PARAMS_STATE_KEY)
    buffer_share, buffer_share_error = _safe_wind_share_pct(app)
    report.check(
        not buffer_exceptions
        and not buffer_errors
        and _session_state_value(app, source_key) is True
        and _session_state_value(app, buffer_key) is True
        and buffer_selection == baseline_selection
        and buffer_params == baseline_params
        and baseline_share is not None
        and buffer_share is not None
        and abs(buffer_share - baseline_share) <= 0.001,
        "trondelag: buffer-map toggle changes only map-review state; "
        "analysis selection, parameters, and metric stay unchanged.",
        "trondelag: buffer-map toggle changed analysis state: "
        f"exceptions={buffer_exceptions}, errors={buffer_errors}, "
        f"selection={buffer_selection}, params_equal="
        f"{buffer_params == baseline_params}, baseline_share="
        f"{baseline_share}, buffer_share={buffer_share}, "
        f"share_error={buffer_share_error}.",
    )
    return not buffer_exceptions and not buffer_errors


def _check_roads_large_slice(report: Report) -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = "trondelag"
    app.run(timeout=120)
    initial_exceptions, initial_errors = _app_failures(app)
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            "trondelag: roads_large slice setup failed: "
            f"exceptions={initial_exceptions}, errors={initial_errors}",
        )
        return

    try:
        _select_road_layers(app, ("roads_large",))
        road_slider = _by_key(
            app.slider,
            "wind_control__analysis__roads",
        )
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: roads_large controls are unavailable: {exc}",
        )
        return
    road_slider.set_value(300)
    _wind_apply_button(app).click().run(timeout=120)
    first_exceptions, first_errors = _app_failures(app)
    if first_exceptions or first_errors:
        report.check(
            False,
            "",
            "trondelag: applying the roads_large-only slice at 300 m failed: "
            f"exceptions={first_exceptions}, errors={first_errors}",
        )
        return

    selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    first_share, first_share_error = _safe_wind_share_pct(app)
    report.check(
        isinstance(selected, dict)
        and selected.get("roads") == ["roads_large"]
        and not any(
            layer_ids
            for group_id, layer_ids in selected.items()
            if group_id != "roads"
        )
        and first_share is not None
        and abs(first_share - 96.9) <= 0.05,
        "trondelag: roads_large-only R7 renders the canonical 300 m "
        "result (96.9%).",
        "trondelag: roads_large-only 300 m state/result drifted: "
        f"selection={selected}, share={first_share}, "
        f"share_error={first_share_error}.",
    )
    if first_share is None:
        return

    _check_wind_map_review_toggles(report, app, expected_share=96.9)

    road_slider = _by_key(
        app.slider,
        "wind_control__analysis__roads",
    )
    road_slider.set_value(1000)
    _wind_apply_button(app).click().run(timeout=120)
    second_exceptions, second_errors = _app_failures(app)
    if second_exceptions or second_errors:
        report.check(
            False,
            "",
            "trondelag: applying the roads_large-only slice at 1000 m failed: "
            f"exceptions={second_exceptions}, errors={second_errors}",
        )
        return
    second_share, second_share_error = _safe_wind_share_pct(app)
    report.check(
        second_share is not None and abs(second_share - 95.5) <= 0.05,
        "trondelag: roads_large-only R7 visibly reacts at 1000 m "
        "(95.5%).",
        "trondelag: roads_large-only 1000 m result drifted: "
        f"expected 95.5%, got {second_share}, "
        f"share_error={second_share_error}.",
    )
    if second_share is None:
        return

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
                "wind_control__analysis__roads",
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


def _check_canonical_road_selection(
    report: Report,
    layer_ids: tuple[str, ...],
    expected_shares: dict[int, dict[int, float]],
) -> None:
    selection_label = "+".join(layer_ids)
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = "trondelag"
    app.run(timeout=120)
    initial_exceptions, initial_errors = _app_failures(app)
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            f"trondelag: {selection_label} setup failed: "
            f"exceptions={initial_exceptions}, errors={initial_errors}",
        )
        return

    try:
        _select_road_layers(app, layer_ids)
        road_slider = _by_key(
            app.slider,
            "wind_control__analysis__roads",
        )
        road_slider.set_value(300)
        _wind_apply_button(app).click().run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: {selection_label} controls failed: {exc}",
        )
        return

    first_exceptions, first_errors = _app_failures(app)
    selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    first_share, first_share_error = _safe_wind_share_pct(app)
    expected_first_share = expected_shares[300][7]
    report.check(
        not first_exceptions
        and not first_errors
        and isinstance(selected, dict)
        and selected.get("roads") == list(layer_ids)
        and not any(
            selected_layer_ids
            for group_id, selected_layer_ids in selected.items()
            if group_id != "roads"
        )
        and first_share is not None
        and abs(first_share - expected_first_share) <= 0.05,
        f"trondelag: {selection_label} is canonical in the real R7 app at "
        f"300 m ({expected_first_share:.1f}%).",
        f"trondelag: {selection_label} R7/300 m drifted: selection="
        f"{selected}, share={first_share}, share_error={first_share_error}, "
        f"exceptions={first_exceptions}, errors={first_errors}.",
    )
    if first_share is None or first_exceptions or first_errors:
        return

    if len(layer_ids) > 1:
        _check_wind_map_review_toggles(
            report,
            app,
            expected_share=expected_first_share,
        )

    try:
        display_mode = _by_key(app.radio, "combined_h3_display_mode")
        display_mode.set_value("selected").run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: {selection_label} resolution mode failed: {exc}",
        )
        return

    for buffer_m, resolution_expectations in expected_shares.items():
        road_slider = _by_key(
            app.slider,
            "wind_control__analysis__roads",
        )
        road_slider.set_value(buffer_m)
        _wind_apply_button(app).click().run(timeout=120)
        buffer_exceptions, buffer_errors = _app_failures(app)
        if buffer_exceptions or buffer_errors:
            report.check(
                False,
                "",
                f"trondelag: {selection_label}/{buffer_m} m failed: "
                f"exceptions={buffer_exceptions}, errors={buffer_errors}",
            )
            return

        for resolution, expected_share in resolution_expectations.items():
            resolution_control = _by_key(
                app.radio,
                "combined_h3_resolution",
            )
            resolution_control.set_value(resolution).run(timeout=120)
            resolution_exceptions, resolution_errors = _app_failures(app)
            resolution_share, share_error = _safe_wind_share_pct(app)
            runtime_failure = "Vindruntime kunde inte köras" in _rendered_text(app)
            report.check(
                not resolution_exceptions
                and not resolution_errors
                and not runtime_failure
                and resolution_share is not None
                and abs(resolution_share - expected_share) <= 0.05,
                f"trondelag: {selection_label} builds canonical R{resolution} "
                f"at {buffer_m} m ({expected_share:.1f}%).",
                f"trondelag: {selection_label} R{resolution}/{buffer_m} m "
                f"drifted: share={resolution_share}, "
                f"share_error={share_error}, runtime_failure="
                f"{runtime_failure}, exceptions={resolution_exceptions}, "
                f"errors={resolution_errors}.",
            )


def _check_population_slice(report: Report) -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = TRONDELAG_REGION_ID
    app.run(timeout=120)
    initial_exceptions, initial_errors = _app_failures(app)
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            "trondelag: population slice setup failed: "
            f"exceptions={initial_exceptions}, errors={initial_errors}",
        )
        return

    checkbox_by_key = {
        str(item.key or ""): str(item.label)
        for item in app.checkbox
    }
    population_layer_labels = {
        "wind_control__layer__population_points": "Befolkning 250 m-rutor",
        "wind_control__layer__built_centre": "Bebyggelsekärnor",
        "wind_control__layer__built_low_selection": (
            "Fritidshus :orange[:material/warning:]"
        ),
    }
    expander_labels = {
        str(getattr(item, "label", ""))
        for item in getattr(app, "expander", [])
    }
    rendered_population_layer_order = [
        str(item.key or "")
        for item in app.checkbox
        if str(item.key or "") in population_layer_labels
    ]
    report.check(
        all(
            checkbox_by_key.get(key) == label
            for key, label in population_layer_labels.items()
        )
        and "wind_control__group__population" not in checkbox_by_key
        and "Fler datakällor" in expander_labels
        and rendered_population_layer_order
        == list(population_layer_labels),
        "trondelag: the population control exposes its manifest primary "
        "source directly, keeps two manifest optional sources under Fler "
        "datakällor, and has no redundant group checkbox.",
        "trondelag: the simplified population control drifted: "
        f"checkboxes={checkbox_by_key}, order="
        f"{rendered_population_layer_order}, "
        f"expanders={sorted(expander_labels)}.",
    )

    try:
        _select_wind_group_layers(
            app,
            "population",
            ("population_points",),
        )
        population_slider = _by_key(
            app.slider,
            "wind_control__analysis__population",
        )
        population_slider.set_value(100)
        _wind_apply_button(app).click().run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: population controls failed: {exc}",
        )
        return

    first_exceptions, first_errors = _app_failures(app)
    selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    first_share, first_share_error = _safe_wind_share_pct(app)
    report.check(
        not first_exceptions
        and not first_errors
        and isinstance(selected, dict)
        and selected.get("population") == ["population_points"]
        and not any(
            selected_layer_ids
            for group_id, selected_layer_ids in selected.items()
            if group_id != "population"
        )
        and first_share is not None
        and abs(first_share - 70.7) <= 0.05,
        "trondelag: population_points renders the canonical R7 result at "
        "100 m (70.7%).",
        "trondelag: population_points R7/100 m drifted: "
        f"selection={selected}, share={first_share}, "
        f"share_error={first_share_error}, exceptions={first_exceptions}, "
        f"errors={first_errors}.",
    )
    if first_share is None or first_exceptions or first_errors:
        return

    if not _check_wind_map_review_toggles(
        report,
        app,
        expected_share=70.7,
        group_id="population",
        group_label="population",
    ):
        return

    population_slider = _by_key(
        app.slider,
        "wind_control__analysis__population",
    )
    population_slider.set_value(1000)
    _wind_apply_button(app).click().run(timeout=120)
    second_exceptions, second_errors = _app_failures(app)
    second_share, second_share_error = _safe_wind_share_pct(app)
    report.check(
        not second_exceptions
        and not second_errors
        and second_share is not None
        and abs(second_share - 63.2) <= 0.05,
        "trondelag: population_points visibly reacts at 1000 m (63.2%).",
        "trondelag: population_points R7/1000 m drifted: "
        f"share={second_share}, share_error={second_share_error}, "
        f"exceptions={second_exceptions}, errors={second_errors}.",
    )

    try:
        _select_wind_group_layers(
            app,
            "population",
            (
                "population_points",
                "built_centre",
                "built_low_selection",
            ),
        )
        population_slider = _by_key(
            app.slider,
            "wind_control__analysis__population",
        )
        population_slider.set_value(500)
        _wind_apply_button(app).click().run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: combined population controls failed: {exc}",
        )
        return
    combined_exceptions, combined_errors = _app_failures(app)
    combined_selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    combined_share, combined_share_error = _safe_wind_share_pct(app)
    report.check(
        not combined_exceptions
        and not combined_errors
        and isinstance(combined_selected, dict)
        and combined_selected.get("population")
        == ["population_points", "built_centre", "built_low_selection"]
        and combined_share is not None
        and abs(combined_share - 47.2) <= 0.05,
        "trondelag: the grid, polygon, and point population sources combine "
        "canonically in the real R7 app at 500 m (47.2%).",
        "trondelag: combined population source behavior drifted: "
        f"selection={combined_selected}, share={combined_share}, "
        f"share_error={combined_share_error}, exceptions="
        f"{combined_exceptions}, errors={combined_errors}.",
    )


def _check_nature_slice(report: Report) -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = TRONDELAG_REGION_ID
    app.run(timeout=120)
    initial_exceptions, initial_errors = _app_failures(app)
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            "trondelag: nature slice setup failed: "
            f"exceptions={initial_exceptions}, errors={initial_errors}",
        )
        return

    checkbox_by_key = {
        str(item.key or ""): str(item.label)
        for item in app.checkbox
    }
    report.check(
        checkbox_by_key.get("wind_control__layer__protected_areas")
        == "Naturvernområden"
        and "wind_control__group__nature" not in checkbox_by_key
        and "wind_control__group__protected" not in checkbox_by_key,
        "trondelag: nature exposes its single manifest source directly "
        "without a redundant or legacy group checkbox.",
        "trondelag: simplified nature control drifted: "
        f"checkboxes={checkbox_by_key}.",
    )

    try:
        _select_wind_group_layers(app, "nature", ("protected_areas",))
        nature_slider = _by_key(
            app.slider,
            "wind_control__analysis__nature",
        )
        nature_slider.set_value(0)
        _wind_apply_button(app).click().run(timeout=120)
    except Exception as exc:
        report.check(False, "", f"trondelag: nature controls failed: {exc}")
        return

    first_exceptions, first_errors = _app_failures(app)
    selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    first_share, first_share_error = _safe_wind_share_pct(app)
    report.check(
        not first_exceptions
        and not first_errors
        and isinstance(selected, dict)
        and selected.get("nature") == ["protected_areas"]
        and not any(
            layer_ids
            for group_id, layer_ids in selected.items()
            if group_id != "nature"
        )
        and first_share is not None
        and abs(first_share - 71.2) <= 0.05,
        "trondelag: protected_areas renders canonical binary R7 behavior at "
        "0 m (71.2%).",
        "trondelag: protected_areas R7/0 m drifted: "
        f"selection={selected}, share={first_share}, "
        f"share_error={first_share_error}, exceptions={first_exceptions}, "
        f"errors={first_errors}.",
    )
    if first_share is None or first_exceptions or first_errors:
        return

    if not _check_wind_map_review_toggles(
        report,
        app,
        expected_share=71.2,
        group_id="nature",
        group_label="nature",
    ):
        return

    nature_slider = _by_key(
        app.slider,
        "wind_control__analysis__nature",
    )
    nature_slider.set_value(2000)
    _wind_apply_button(app).click().run(timeout=120)
    try:
        _by_key(
            app.radio,
            "combined_h3_display_mode",
        ).set_value("selected").run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: nature resolution mode failed: {exc}",
        )
        return
    expected_by_resolution = {7: 60.2, 6: 40.8, 5: 12.9}
    observed: dict[int, float | None] = {}
    resolution_errors: list[str] = []
    for resolution, expected_share in expected_by_resolution.items():
        _by_key(app.radio, "combined_h3_resolution").set_value(
            resolution
        ).run(timeout=120)
        exceptions, errors = _app_failures(app)
        share, share_error = _safe_wind_share_pct(app)
        observed[resolution] = share
        if (
            exceptions
            or errors
            or share is None
            or abs(share - expected_share) > 0.05
        ):
            resolution_errors.append(
                f"R{resolution}: share={share}, share_error={share_error}, "
                f"exceptions={exceptions}, errors={errors}"
            )
    report.check(
        not resolution_errors,
        "trondelag: the 2000 m nature hard exclusion uses canonical "
        "R7/R6/R5 behavior (60.2/40.8/12.9%).",
        "trondelag: nature R7/R6/R5 behavior drifted: "
        f"observed={observed}, errors={resolution_errors}.",
    )


def _check_culture_slice(report: Report) -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = TRONDELAG_REGION_ID
    app.run(timeout=120)
    initial_exceptions, initial_errors = _app_failures(app)
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            "trondelag: culture slice setup failed: "
            f"exceptions={initial_exceptions}, errors={initial_errors}",
        )
        return

    checkbox_by_key = {
        str(item.key or ""): str(item.label)
        for item in app.checkbox
    }
    report.check(
        checkbox_by_key.get(
            "wind_control__layer__cultural_preservation"
        )
        == "Kulturmiljöer och kulturminnen"
        and checkbox_by_key.get(
            "wind_control__layer__valuable_cultural_environment"
        )
        == "Värdefulla kulturlandskap"
        and "wind_control__group__culture" not in checkbox_by_key,
        "trondelag: culture exposes both manifest sources directly without "
        "the redundant group checkbox.",
        "trondelag: simplified culture control drifted: "
        f"checkboxes={checkbox_by_key}.",
    )

    culture_layer_ids = (
        "cultural_preservation",
        "valuable_cultural_environment",
    )
    try:
        _select_wind_group_layers(app, "culture", culture_layer_ids)
        culture_slider = _by_key(
            app.slider,
            "wind_control__analysis__culture",
        )
        culture_slider.set_value(0)
        _wind_apply_button(app).click().run(timeout=120)
    except Exception as exc:
        report.check(False, "", f"trondelag: culture controls failed: {exc}")
        return

    first_exceptions, first_errors = _app_failures(app)
    selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    first_share, first_share_error = _safe_wind_share_pct(app)
    report.check(
        not first_exceptions
        and not first_errors
        and isinstance(selected, dict)
        and selected.get("culture") == list(culture_layer_ids)
        and not any(
            layer_ids
            for group_id, layer_ids in selected.items()
            if group_id != "culture"
        )
        and first_share is not None
        and abs(first_share - 88.9) <= 0.05,
        "trondelag: both culture sources render canonical binary R7 "
        "behavior at 0 m (88.9%).",
        "trondelag: combined culture R7/0 m drifted: "
        f"selection={selected}, share={first_share}, "
        f"share_error={first_share_error}, exceptions={first_exceptions}, "
        f"errors={first_errors}.",
    )
    if first_share is None or first_exceptions or first_errors:
        return

    if not _check_wind_map_review_toggles(
        report,
        app,
        expected_share=88.9,
        group_id="culture",
        group_label="culture",
    ):
        return

    culture_slider = _by_key(
        app.slider,
        "wind_control__analysis__culture",
    )
    culture_slider.set_value(1500)
    _wind_apply_button(app).click().run(timeout=120)
    try:
        _by_key(
            app.radio,
            "combined_h3_display_mode",
        ).set_value("selected").run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: culture resolution mode failed: {exc}",
        )
        return
    expected_by_resolution = {7: 87.2, 6: 79.0, 5: 56.2}
    observed: dict[int, float | None] = {}
    resolution_errors: list[str] = []
    for resolution, expected_share in expected_by_resolution.items():
        _by_key(app.radio, "combined_h3_resolution").set_value(
            resolution
        ).run(timeout=120)
        exceptions, errors = _app_failures(app)
        share, share_error = _safe_wind_share_pct(app)
        observed[resolution] = share
        if (
            exceptions
            or errors
            or share is None
            or abs(share - expected_share) > 0.05
        ):
            resolution_errors.append(
                f"R{resolution}: share={share}, share_error={share_error}, "
                f"exceptions={exceptions}, errors={errors}"
            )
    report.check(
        not resolution_errors,
        "trondelag: the 1500 m culture hard exclusion uses canonical "
        "R7/R6/R5 behavior (87.2/79.0/56.2%).",
        "trondelag: culture R7/R6/R5 behavior drifted: "
        f"observed={observed}, errors={resolution_errors}.",
    )


def _check_grid_infrastructure_slice(report: Report) -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = TRONDELAG_REGION_ID
    app.run(timeout=120)
    initial_exceptions, initial_errors = _app_failures(app)
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            "trondelag: grid-infrastructure slice setup failed: "
            f"exceptions={initial_exceptions}, errors={initial_errors}",
        )
        return

    checkbox_by_key = {
        str(item.key or ""): str(item.label)
        for item in app.checkbox
    }
    grid_layer_ids = (
        "high_voltage_lines",
        "underground_cables",
        "existing_wind_turbines",
    )
    report.check(
        checkbox_by_key.get("wind_control__layer__high_voltage_lines")
        == "Högspänningsledningar"
        and checkbox_by_key.get("wind_control__layer__underground_cables")
        == "Markkablar"
        and checkbox_by_key.get("wind_control__layer__existing_wind_turbines")
        == "Befintliga vindkraftverk"
        and "wind_control__group__grid_infrastructure" not in checkbox_by_key
        and "wind_control__group__electrical" not in checkbox_by_key,
        "trondelag: grid infrastructure exposes all three manifest sources "
        "directly without a legacy or redundant group checkbox.",
        "trondelag: simplified grid control drifted: "
        f"checkboxes={checkbox_by_key}.",
    )

    try:
        _select_wind_group_layers(
            app,
            "grid_infrastructure",
            grid_layer_ids,
        )
        grid_slider = _by_key(
            app.slider,
            "wind_control__analysis__grid_infrastructure",
        )
        grid_slider.set_value(2000)
        _wind_apply_button(app).click().run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: grid-infrastructure controls failed: {exc}",
        )
        return

    first_exceptions, first_errors = _app_failures(app)
    selected = _session_state_value(app, WIND_SELECTION_STATE_KEY)
    first_share, first_share_error = _safe_wind_share_pct(app)
    report.check(
        not first_exceptions
        and not first_errors
        and isinstance(selected, dict)
        and selected.get("grid_infrastructure") == list(grid_layer_ids)
        and not any(
            layer_ids
            for group_id, layer_ids in selected.items()
            if group_id != "grid_infrastructure"
        )
        and first_share is not None
        and abs(first_share - 39.5) <= 0.05,
        "trondelag: all three grid sources render canonical R7 proximity "
        "feasibility at 2000 m (39.5%).",
        "trondelag: combined grid R7/2000 m drifted: "
        f"selection={selected}, share={first_share}, "
        f"share_error={first_share_error}, exceptions={first_exceptions}, "
        f"errors={first_errors}.",
    )
    if first_share is None or first_exceptions or first_errors:
        return

    if not _check_wind_map_review_toggles(
        report,
        app,
        expected_share=39.5,
        group_id="grid_infrastructure",
        group_label="grid infrastructure",
    ):
        return

    grid_slider = _by_key(
        app.slider,
        "wind_control__analysis__grid_infrastructure",
    )
    grid_slider.set_value(15000)
    _wind_apply_button(app).click().run(timeout=120)
    try:
        _by_key(
            app.radio,
            "combined_h3_display_mode",
        ).set_value("selected").run(timeout=120)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: grid resolution mode failed: {exc}",
        )
        return
    expected_by_resolution = {7: 79.0, 6: 85.4, 5: 90.5}
    observed: dict[int, float | None] = {}
    resolution_errors: list[str] = []
    for resolution, expected_share in expected_by_resolution.items():
        _by_key(app.radio, "combined_h3_resolution").set_value(
            resolution
        ).run(timeout=120)
        exceptions, errors = _app_failures(app)
        share, share_error = _safe_wind_share_pct(app)
        observed[resolution] = share
        if (
            exceptions
            or errors
            or share is None
            or abs(share - expected_share) > 0.05
        ):
            resolution_errors.append(
                f"R{resolution}: share={share}, share_error={share_error}, "
                f"exceptions={exceptions}, errors={errors}"
            )
    report.check(
        not resolution_errors,
        "trondelag: the 15000 m grid proximity operation uses canonical "
        "R7/R6/R5 behavior (79.0/85.4/90.5%).",
        "trondelag: grid R7/R6/R5 behavior drifted: "
        f"observed={observed}, errors={resolution_errors}.",
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
    _check_map_interaction_control(report)
    _check_missing_source_root(report)
    source_root = v2_source_root()
    report.note(f"{V2_SOURCE_ROOT_ENV}: {os.environ.get(V2_SOURCE_ROOT_ENV, '<not set>')}")
    report.check(
        APP_PATH.is_file(),
        "V2 Final app entrypoint exists.",
        f"Missing app: {APP_PATH}",
    )
    report.check(
        bool(source_root and source_root.is_dir()),
        "V2 source root exists.",
        f"V2 source root does not exist: {source_root}",
    )
    if not APP_PATH.is_file() or source_root is None or not source_root.is_dir():
        return report.emit()

    region = load_region(TRONDELAG_REGION_ID)
    report.check(
        region.get("_v2_source_available") is True,
        "trondelag: detailed V2 source manifest is available.",
        "trondelag: detailed V2 source manifest is unavailable.",
    )
    _check_manifest_empty_start_and_public_controls(report)
    _check_continuous_mix_control(report)
    _check_disabled_bornholm_route(report)
    _check_roads_large_slice(report)
    _check_canonical_road_selection(
        report,
        ("roads_medium",),
        {
            300: {7: 76.8, 6: 55.0, 5: 31.2},
            1000: {7: 69.6, 6: 50.7, 5: 29.5},
        },
    )
    _check_canonical_road_selection(
        report,
        ("roads_medium", "roads_large"),
        {
            300: {7: 75.0, 6: 52.3, 5: 27.1},
            1000: {7: 67.4, 6: 47.9, 5: 25.5},
        },
    )
    _check_population_slice(report)
    _check_nature_slice(report)
    _check_culture_slice(report)
    _check_grid_infrastructure_slice(report)
    return report.emit()


def _check_continuous_mix_control(report: Report) -> None:
    region_id = TRONDELAG_REGION_ID
    mix_slider_key = f"energy_model_mix_solar_share_{region_id}"
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.query_params["region"] = region_id
    app.run(timeout=120)
    initial_exceptions, initial_errors = _app_failures(app)
    if initial_exceptions or initial_errors:
        report.check(
            False,
            "",
            "trondelag: continuous mix probe could not start: "
            f"exceptions={initial_exceptions}, errors={initial_errors}.",
        )
        return
    try:
        mix_slider = _by_key(app.slider, mix_slider_key)
    except Exception as exc:
        report.check(
            False,
            "",
            f"trondelag: continuous mix probe could not find the slider: {exc}",
        )
        return

    endpoint_results: list[tuple[int, list[str], list[str], bool]] = []
    for solar_share_pct, expected_text in [
        (0, "Energimix: 100% vind / 0% sol."),
        (50, "Energimix: 50% vind / 50% sol."),
        (100, "Energimix: 0% vind / 100% sol."),
    ]:
        mix_slider.set_value(solar_share_pct)
        app.run(timeout=120)
        exceptions, errors = _app_failures(app)
        rendered_text = _rendered_text(app)
        endpoint_results.append(
            (
                solar_share_pct,
                exceptions,
                errors,
                expected_text in rendered_text,
            )
        )
        mix_slider = _by_key(app.slider, mix_slider_key)

    report.check(
        all(
            not exceptions and not errors and rendered_match
            for _, exceptions, errors, rendered_match in endpoint_results
        ),
        "trondelag: the real app executes 0/100, 50/50, and 100/0 "
        "wind/solar allocations and renders the selected mix without errors.",
        "trondelag: a real-app mix endpoint failed: "
        f"{endpoint_results}.",
    )


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
        if item.label == "Vind: genomsnittlig potential per analyscell"
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
    trondelag_exceptions, trondelag_errors = _app_failures(app)
    trondelag_share, share_error = _safe_wind_share_pct(app)
    trondelag_selection = _session_state_value(
        app,
        WIND_SELECTION_STATE_KEY,
    )
    report.check(
        not trondelag_exceptions
        and not trondelag_errors
        and isinstance(trondelag_selection, dict)
        and not any(trondelag_selection.values())
        and trondelag_share is not None
        and abs(trondelag_share - 100.0) <= 0.05,
        "Trondelag remains directly routable with its empty 100.0% startup "
        "after the disabled Bornholm probe.",
        "Trondelag did not render after the disabled Bornholm probe: "
        f"exceptions={trondelag_exceptions}, errors={trondelag_errors}, "
        f"selection={trondelag_selection}, share={trondelag_share}, "
        f"share_error={share_error}.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
