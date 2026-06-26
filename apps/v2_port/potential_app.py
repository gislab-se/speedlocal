from __future__ import annotations

from collections import deque
import hashlib
import html
from io import StringIO
import h3
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import pandas as pd
import streamlit as st

try:
    import streamlit.components.v1 as components
except Exception:
    components = None


ROOT = Path(__file__).resolve().parent
APPS_DIR = ROOT / "apps"
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from potential_model.geometry import geometry_for_hex, load_h3_display_geometries  # noqa: E402
import potential_model.landscape as landscape_model  # noqa: E402
from potential_model.manifests import (  # noqa: E402
    default_region_id,
    load_linked_manifest,
    load_region,
    list_regions,
    read_manifest,
    resolve_region_path,
    resolve_repo_path,
)
from potential_model.region_status import (  # noqa: E402
    available_h3_resolutions as region_available_h3_resolutions,
    load_region_context,
    region_data_status_rows,
)
from potential_model.map_rendering import build_layered_hex_map_html  # noqa: E402
from potential_model.energy_modeling import (  # noqa: E402
    AREA_SCENARIO_LABELS,
    AREA_SCENARIO_ORDER,
    allocate_wind_area_from_core_hexes,
    build_times_summary,
    calculate_area_demand,
    h3_hex_area_km2,
    load_area_demand_bundle,
    load_energy_model_inputs,
    planning_scenario_label,
    planning_scenarios,
    scenario_display_label,
    select_planning_mix,
)
from potential_model.potential import (  # noqa: E402
    potential_by_landscape,
    potential_feature_collection,
    potential_summary,
    rollup_frame_for_entry,
    rollup_potential_frame,
    solar_capacity_frame,
    solar_capacity_summary,
)
from potential_model.social_acceptance import (  # noqa: E402
    DEFAULT_SCENARIO_ID as SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID,
    acceptance_value_column as social_acceptance_value_column,
    acceptance_layer as social_acceptance_layer,
    acceptance_scenario_label as social_acceptance_scenario_label,
    acceptance_scenarios as social_acceptance_scenarios,
    load_acceptance_frame as load_social_acceptance_frame,
)
from potential_model.wind_acceptance import (  # noqa: E402
    GROUP_LABELS,
    GROUP_PARAM_MAP,
    SOURCE_RESOLUTION as WIND_SOURCE_RESOLUTION,
    WIND_GROUP_LAYER_DEFAULTS,
    normalize_group_layer_map,
    runtime_combined_hex_frame,
    wind_acceptance_group_summary,
    wind_acceptance_potential_frame,
    wind_acceptance_rollup_frame,
    wind_candidate_summary,
    wind_vector_feature_collection,
)
from acceptance_model.layers import (  # noqa: E402
    distance_table_for_layer,
    layer_status_table as acceptance_layer_status_table,
    load_registry as load_acceptance_registry,
    ordered_groups,
    ordered_layers,
    source_geojson_for_layer,
)
from acceptance_model.runtime_geometry import run_geometry_runtime  # noqa: E402
from acceptance_model.i18n import (  # noqa: E402
    group_analysis_label,
    group_interpretation,
    group_label,
    layer_label,
    layer_note,
    ui_text,
)


CLUSTER_COLORS = landscape_model.CLUSTER_COLORS
FACTOR_STOPS = landscape_model.FACTOR_STOPS
cluster_summary = landscape_model.cluster_summary
factor_columns = landscape_model.factor_columns
factor_label = landscape_model.factor_label
cluster_label = landscape_model.cluster_label
feature_collection_for_frame = landscape_model.feature_collection_for_frame
landscape_frame_for_resolution = landscape_model.landscape_frame_for_resolution
landscape_source_resolution = landscape_model.landscape_source_resolution
landscape_type_feature_collection_for_frame = landscape_model.landscape_type_feature_collection_for_frame
load_cluster_profile = landscape_model.load_cluster_profile
load_factor_scores = landscape_model.load_factor_scores
load_run_summary = landscape_model.load_run_summary


def landscape_type_display_colors(manifest: dict[str, Any] | None = None) -> dict[str, str]:
    color_func = getattr(landscape_model, "landscape_type_display_colors", None)
    if callable(color_func):
        return color_func(manifest)

    # Backward compatibility for deployments where potential_app.py is newer than landscape.py.
    colors = dict(getattr(landscape_model, "V10_TYPE_COLORS", {}))
    if not manifest:
        return colors

    manifest_colors = manifest.get("landscape_type_colors") or {}
    manifest_labels = manifest.get("landscape_type_labels") or {}
    for key, value in manifest_colors.items():
        colors.setdefault(str(key), str(value))
    for key in manifest_labels:
        colors.setdefault(str(key), "#999999")
    return colors


PAGE_TITLE = "Sol- och vindpotential"
APP_RELEASE_STAGE = "BETA"
APP_RELEASE_NOTE = "Utvecklingsversion - inte färdig produkt"
APP_LANGUAGE_KEY = "potential_app_language"
APP_LANGUAGES = {
    "da_no": "Danska/Norska",
    "sv": "Svenska",
    "en": "English",
}
APP_LANGUAGE_BUTTONS = {
    "da_no": "DA/NO",
    "sv": "SV",
    "en": "EN",
}
MAP_VIEW_RESET_TOKEN_KEY = "potential_map_view_reset_token"
MAP_STATE_VERSION = "establishment-start-v6"
LEFT_PANEL_OPEN_KEY = "potential_left_panel_open"
RIGHT_PANEL_OPEN_KEY = "potential_right_panel_open"
RIGHT_PANEL_WIDTH_KEY = "potential_right_panel_width_pct"
RIGHT_PANEL_WIDTH_DEFAULT_VERSION_KEY = "potential_right_panel_width_default_version"
RIGHT_PANEL_WIDTH_DEFAULT_VERSION = "map_balance_v2"
RIGHT_PANEL_WIDTH_DEFAULT = 42.0
RIGHT_PANEL_WIDTH_LEGACY_DEFAULTS = (34.0, 60.0, 66.0)
PERFORMANCE_HISTORY_KEY = "potential_performance_history_v1"
UI_ONLY_RERUN_KEY = "potential_ui_only_rerun"
UI_ONLY_RERUN_REASON_KEY = "potential_ui_only_rerun_reason"
WORKSPACE_RENDER_CACHE_KEY = "potential_workspace_render_cache_v2"
WORKSPACE_CALCULATION_VERSION = "lablab_landscape_ui_v1"
TUTORIAL_FORCE_OPEN_KEY = "potential_tutorial_force_open"
TUTORIAL_FORCE_OPEN_TOKEN_KEY = "potential_tutorial_force_open_token"
TUTORIAL_STORAGE_KEY = "potential_tutorial_trondelag_v2_dismissed"
# Kept only so shared registry helpers can resolve the Trondelag layer registry.
REGION_SELECT_KEY = "potential_selected_region_id"
REGION_LANDING_VIEW = "landing"
DEFAULT_REGION_ID = default_region_id()
WIND_LAYER_SELECTION_KEY = "wind_builder_selected_layers"
WIND_RUNTIME_OVERLAY_KEY = "wind_builder_runtime_overlay_enabled"
SOLAR_APPLIED_CONFIG_KEY = "solar_applied_config"
START_DEFAULT_VERSION_KEY = "potential_start_default_version"
START_DEFAULT_VERSION = "trondelag_decision_default_v5"
WIND_EMPTY_SELECTION_ACTIVE_KEY = "wind_empty_selection_active"
WIND_CONTROL_LANGUAGE = "sv"
WIND_RUNTIME_BASE_RESOLUTION = 10
WIND_LANDSCAPE_POTENTIAL_LABEL = "Landskapspotential Vind"
WIND_POTENTIAL_HEX_LABEL = "Landskapspotential Vind hexagon"
WIND_ESTABLISHMENT_LAYER_LABEL = "Potentiell etableringsyta Vind"
COMBINED_ESTABLISHMENT_LAYER_LABEL = "Potentiell etableringsyta"
SCENARIO_ALLOCATION_LAYER_LABEL = "Scenariofördelning i etableringshex"
SOLAR_LANDSCAPE_POTENTIAL_LABEL = "Landskapspotential Sol"
SOLAR_SMALL_SCALE_LABEL = "Småskalig anläggning på tak"
SOLAR_LARGE_SCALE_LABEL = "Storskalig anläggning på land"
SOLAR_POTENTIAL_POLYGON_LABEL = "Landskapspotential Sol polygon"
SOLAR_POTENTIAL_HEX_LABEL = "Landskapspotential Sol hexagon"
SOLAR_ESTABLISHMENT_LAYER_LABEL = "Potentiell etableringsyta Sol"
OUTSIDE_LP_NEED_LAYER_LABEL = "Ytbehov utanför landskapets potential"
OUTSIDE_LP_NEED_DISPLAY_MIN_KM2 = 0.005
SOLAR_POPULATION_SOURCE_LABEL = "Sol källa: Befolkningsunderlag"
SOLAR_POPULATION_BUFFER_LABEL = "Solbuffert: Befolkningsunderlag"
PROTECTED_NATURE_LABEL = "Skyddad natur"
SOLAR_PROTECTED_SOURCE_LABEL = f"Sol källa: {PROTECTED_NATURE_LABEL}"
SOLAR_PROTECTED_BUFFER_LABEL = f"Solbuffert: {PROTECTED_NATURE_LABEL}"
WIND_SETTLEMENT_GROUP_ID = "settlement"
WIND_SETTLEMENT_GROUP_LABEL = "Befolkning och bebyggelse"
WIND_POPULATION_SOURCE_LAYER_ID = "population_points"
WIND_CULTURE_GROUP_ID = "culture"
WIND_CULTURE_GROUP_LABEL = "kulturmiljöer"
WIND_REINDEER_GROUP_ID = "reindeer"
WIND_REINDEER_GROUP_LABEL = "rennäring / reindrift"
SOLAR_PROTECTED_GROUP_ID = "protected"
SOLAR_PROTECTED_LAYER_IDS = tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_PROTECTED_GROUP_ID, []))
SOLAR_ROAD_GROUP_ID = "transport"
SOLAR_ELECTRICAL_GROUP_ID = "electrical"
SOLAR_CULTURE_GROUP_ID = "culture"
SOLAR_REINDEER_GROUP_ID = "reindeer"
SOLAR_COASTAL_GROUP_ID = "coastal"
WIND_ESTABLISHMENT_INTERSECTION_BLOCK_GROUP_IDS = {SOLAR_COASTAL_GROUP_ID}
SOLAR_LAND_USE_GROUP_ID = "land_use"
SOLAR_FOREST_LAYER_ID = "forest_land_cover"
SOLAR_FILTER_GROUP_SPECS: dict[str, dict[str, Any]] = {
    SOLAR_PROTECTED_GROUP_ID: {
        "label": PROTECTED_NATURE_LABEL,
        "source_label": SOLAR_PROTECTED_SOURCE_LABEL,
        "buffer_label": SOLAR_PROTECTED_BUFFER_LABEL,
        "layer_ids": SOLAR_PROTECTED_LAYER_IDS,
        "active_key": "large_protected_active",
        "layer_ids_key": "large_protected_layer_ids",
        "buffer_key": "protected_buffer_m",
        "draft_active_key": "solar_draft_protected_active",
        "draft_buffer_key": "solar_draft_protected_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 2000.0,
        "buffer_step_m": 50.0,
        "source_color": "#16a34a",
        "buffer_color": "#16a34a",
        "caption": f"{PROTECTED_NATURE_LABEL} används som avdrag i storskalig solpotential.",
    },
    SOLAR_LAND_USE_GROUP_ID: {
        "label": "Markanvändning: skog",
        "source_label": "Sol källa: skog",
        "buffer_label": "Solavdrag: skog",
        "layer_ids": (SOLAR_FOREST_LAYER_ID,),
        "default_layer_ids": (SOLAR_FOREST_LAYER_ID,),
        "layer_ids_key": "large_land_use_layer_ids",
        "active_key": "large_land_use_active",
        "buffer_key": "forest_buffer_m",
        "draft_active_key": "solar_draft_land_use_active",
        "draft_buffer_key": "solar_draft_forest_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 1000.0,
        "buffer_step_m": 50.0,
        "source_color": "#166534",
        "buffer_color": "#14532d",
        "active_help": (
            "Tar bort markdekke/arealdekke skog från storskalig solpotential med samma polygon-, buffert- och H3-aggregeringslogik som skyddad natur och kultur."
        ),
        "caption": "Skogsfiltret ligger separat från skyddad natur och bygger på N500 markdekke där `objtype = Skog`.",
    },
    SOLAR_ROAD_GROUP_ID: {
        "label": "Vägar",
        "source_label": "Sol källa: Vägar",
        "buffer_label": "Solbuffert: Vägar",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_ROAD_GROUP_ID, [])),
        "active_key": "large_road_active",
        "layer_ids_key": "large_road_layer_ids",
        "buffer_key": "road_buffer_m",
        "draft_active_key": "solar_draft_road_active",
        "draft_buffer_key": "solar_draft_road_buffer_m",
        "buffer_default_m": 100.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 500.0,
        "buffer_step_m": 25.0,
        "source_color": "#b45309",
        "buffer_color": "#f97316",
        "caption": "Vägfiltret prövar respektavstånd till större vägar och allmänna vägstråk.",
    },
    SOLAR_ELECTRICAL_GROUP_ID: {
        "label": "Elinfrastruktur / nätanslutning",
        "source_label": "Sol källa: Elinfrastruktur",
        "buffer_label": "Sol nära nät: Elinfrastruktur",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_ELECTRICAL_GROUP_ID, [])),
        "active_key": "large_electrical_active",
        "layer_ids_key": "large_electrical_layer_ids",
        "buffer_key": "solar_grid_max_distance_m",
        "draft_active_key": "solar_draft_electrical_active",
        "draft_buffer_key": "solar_draft_grid_max_distance_m",
        "buffer_default_m": 2000.0,
        "buffer_min_m": 500.0,
        "buffer_max_m": 15000.0,
        "buffer_step_m": 250.0,
        "source_color": "#0f766e",
        "buffer_color": "#14b8a6",
        "effect": "feasibility",
        "slider_label": "Max avstånd till elinfrastruktur",
        "slider_help": "Yta räknas som storskalig solpotential bara inom valt avstånd till valda nätobjekt.",
        "active_help": f"Valda nätlager används som positiv närhetsregel i {SOLAR_LARGE_SCALE_LABEL}.",
        "buffer_legend_label": "Inom maxavstånd till elinfrastruktur",
        "caption": "Nära nät används som en positiv mask: yta räknas som solpotential bara inom valt avstånd till elinfrastruktur.",
    },
    SOLAR_CULTURE_GROUP_ID: {
        "label": "Kulturmiljö",
        "source_label": "Sol källa: Kulturmiljö",
        "buffer_label": "Solbuffert: Kulturmiljö",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_CULTURE_GROUP_ID, [])),
        "active_key": "large_culture_active",
        "layer_ids_key": "large_culture_layer_ids",
        "buffer_key": "culture_buffer_m",
        "draft_active_key": "solar_draft_culture_active",
        "draft_buffer_key": "solar_draft_culture_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 1500.0,
        "buffer_step_m": 50.0,
        "source_color": "#9333ea",
        "buffer_color": "#a855f7",
        "caption": "Kulturmiljöfiltret tar bort ytor som träffar valda kulturmiljölager och eventuell buffert.",
    },
    SOLAR_REINDEER_GROUP_ID: {
        "label": "Rennäring / reindrift",
        "source_label": "Sol källa: Rennäring",
        "buffer_label": "Solbuffert: Rennäring",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_REINDEER_GROUP_ID, [])),
        "active_key": "large_reindeer_active",
        "layer_ids_key": "large_reindeer_layer_ids",
        "buffer_key": "reindeer_buffer_m",
        "draft_active_key": "solar_draft_reindeer_active",
        "draft_buffer_key": "solar_draft_reindeer_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 5000.0,
        "buffer_step_m": 100.0,
        "source_color": "#be4952",
        "buffer_color": "#dc645d",
        "caption": "Rennäringsfiltret tar bort ytor som träffar valda reindriftslager och eventuell buffert.",
    },
    SOLAR_COASTAL_GROUP_ID: {
        "label": "Strandskydd / kust",
        "source_label": "Sol källa: Strandskydd / kust",
        "buffer_label": "Solbuffert: Strandskydd / kust",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_COASTAL_GROUP_ID, [])),
        "default_layer_ids": ("strand_protection",),
        "active_key": "large_coastal_active",
        "layer_ids_key": "large_coastal_layer_ids",
        "buffer_key": "coastal_buffer_m",
        "draft_active_key": "solar_draft_coastal_active",
        "draft_buffer_key": "solar_draft_coastal_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 1000.0,
        "buffer_step_m": 50.0,
        "source_color": "#0e7490",
        "buffer_color": "#06b6d4",
        "caption": "Strandskydd och kustzon kan användas som ett försiktigt kustnära avdrag.",
    },
}
SOLAR_FILTER_GROUP_IDS = tuple(SOLAR_FILTER_GROUP_SPECS)
DEFAULT_WIND_ESTABLISHMENT_LAYER_SELECTION = {
    group_id: (
        [WIND_POPULATION_SOURCE_LAYER_ID]
        if group_id == WIND_SETTLEMENT_GROUP_ID
        else list(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_ROAD_GROUP_ID, []))
        if group_id == SOLAR_ROAD_GROUP_ID
        else []
        if group_id == SOLAR_ELECTRICAL_GROUP_ID
        else ["protected_areas"]
        if group_id == SOLAR_PROTECTED_GROUP_ID
        else [
            layer_id
            for layer_id in ("cultural_preservation", "valuable_cultural_environment")
            if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(WIND_CULTURE_GROUP_ID, [])
        ]
        if group_id == WIND_CULTURE_GROUP_ID
        else [
            layer_id
            for layer_id in ("reindeer_grazing_merged",)
            if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(WIND_REINDEER_GROUP_ID, [])
        ]
        if group_id == WIND_REINDEER_GROUP_ID
        else []
    )
    for group_id in WIND_GROUP_LAYER_DEFAULTS
}
DEFAULT_WIND_ADVANCED_LAYER_SELECTION = {
    WIND_SETTLEMENT_GROUP_ID: [WIND_POPULATION_SOURCE_LAYER_ID],
    SOLAR_PROTECTED_GROUP_ID: list(SOLAR_PROTECTED_LAYER_IDS),
    WIND_CULTURE_GROUP_ID: list(WIND_GROUP_LAYER_DEFAULTS.get(WIND_CULTURE_GROUP_ID, [])),
    WIND_REINDEER_GROUP_ID: list(WIND_GROUP_LAYER_DEFAULTS.get(WIND_REINDEER_GROUP_ID, [])),
}
SOLAR_VISUAL_SOURCE_GROUPS_KEY = "visible_source_groups"
SOLAR_VISUAL_BUFFER_GROUPS_KEY = "visible_buffer_groups"
SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID = "small_population"
SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID = "large_population"
DEFAULT_SOLAR_APPLIED_CONFIG = {
    "small_population_active": False,
    "large_unfiltered_land_active": False,
    "large_scale_active": True,
    "large_population_active": True,
    "large_protected_layer_ids": ["protected_areas"],
    "large_protected_active": True,
    "large_land_use_layer_ids": [SOLAR_FOREST_LAYER_ID],
    "large_land_use_active": False,
    "large_road_layer_ids": list(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_ROAD_GROUP_ID, [])),
    "large_road_active": True,
    "large_electrical_layer_ids": [
        layer_id
        for layer_id in ("high_voltage_lines", "underground_cables")
        if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_ELECTRICAL_GROUP_ID, [])
    ],
    "large_electrical_active": False,
    "large_culture_layer_ids": [
        layer_id
        for layer_id in ("cultural_preservation", "valuable_cultural_environment")
        if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_CULTURE_GROUP_ID, [])
    ],
    "large_culture_active": True,
    "large_reindeer_layer_ids": [
        layer_id
        for layer_id in ("reindeer_grazing_merged",)
        if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_REINDEER_GROUP_ID, [])
    ],
    "large_reindeer_active": True,
    "large_coastal_layer_ids": [],
    "large_coastal_active": False,
    "panel_area_m2_per_person": 10.0,
    "population_buffer_m": 500.0,
    "protected_buffer_m": 250.0,
    "forest_buffer_m": 0.0,
    "road_buffer_m": 300.0,
    "solar_grid_max_distance_m": 2000.0,
    "culture_buffer_m": 100.0,
    "reindeer_buffer_m": 100.0,
    "coastal_buffer_m": 0.0,
    SOLAR_VISUAL_SOURCE_GROUPS_KEY: [],
    SOLAR_VISUAL_BUFFER_GROUPS_KEY: [],
}
ENERGY_PROPOSAL_LAYER_LABEL = WIND_ESTABLISHMENT_LAYER_LABEL
WIND_AUTO_RESOLUTION_MIN_ZOOM: dict[int, int] = {10: 11, 9: 9, 8: 7, 7: 5, 6: 0}
REGIONAL_PIPELINE_ROOT = Path(os.environ.get("REGIONAL_LANDSCAPE_PIPELINE_ROOT", r"C:\gislab\regional-landscape-pipeline"))
SOLAR_V1_POPULATION_LAYER_PATH = (
    REGIONAL_PIPELINE_ROOT
    / "outputs"
    / "bornholm"
    / "bornholm_v1_higher_h3_local_sprickdal"
    / "layers"
    / "01_fastboendebefolkningmapinfo.csv"
)
SOLAR_V1_POPULATION_COUNT_COLUMN = "fastboendebefolkningmapinfo_count"
EML_PROVIDER_URL = "https://energymodellinglab.com/"
IVL_PROVIDER_URL = "https://www.ivl.se/"
SOCIAL_ACCEPTANCE_IMPACT_TINT_COLOR = "#991b1b"
SOCIAL_ACCEPTANCE_LOW_THRESHOLD = 0.4
SOCIAL_ACCEPTANCE_HIGH_THRESHOLD = 0.7

APP_TRANSLATIONS: dict[str, dict[str, str]] = {
    "sv": {},
    "da_no": {
        "Sol- och vindpotential": "Sol- og vindpotentiale",
        "Danska/Norska": "Dansk/Norsk",
        "Svenska": "Svensk",
        "English": "Engelsk",
        "Språk": "Sprog/Språk",
        "Visa guide": "Vis guide",
        "Öppna en kort genomgång av Trøndelag-vyn.": "Åbn en kort gennemgang af Trøndelag-visningen.",
        "Föregående": "Forrige",
        "Nästa": "Næste",
        "Hoppa över": "Spring over",
        "Pausa": "Pause",
        "Fortsätt guide": "Fortsæt guide",
        "Testa detta": "Prøv dette",
        "Klart": "Klart",
        "Stäng": "Luk",
        "Klar": "Færdig",
        "Öppna inte automatiskt igen": "Åbn ikke automatisk igen",
        "Region": "Region",
        "Scenarier": "Scenarier",
        "Scenario": "Scenario",
        "Lager": "Lag",
        "Geografier": "Geografier",
        "Landskap": "Landskab",
        "Landskapstyper": "Landskabstyper",
        "Landskapstrukturer": "Landskabsstrukturer",
        "Landskapsfaktorer": "Landskabsfaktorer",
        "Faktor": "Faktor",
        "H3-upplösning": "H3-oppløsning",
        "H3-rollup": "H3-rollup",
        "Hexvisning": "Hexvisning",
        "Vald upplösning": "Valgt oppløsning",
        "Zoomanpassad upplösning": "Zoomtilpasset oppløsning",
        "Snabb visning: vald upplösning": "Hurtig visning: valgt oppløsning",
        "Panelbredd": "Panelbredde",
        "Visa/dölj kontext": "Vis/skjul kontekst",
        "Karta": "Kort/Kart",
        "Etableringsyta": "Etableringsareal",
        "Regionstatus": "Regionstatus",
        "Nästa datapaket": "Neste datapakke",
        "Data och metod": "Data og metode",
        "Aktiva beräkningar": "Aktive beregninger",
        "Beräkning och datakvalitet": "Beregning og datakvalitet",
        "Energimodellering": "Energimodellering",
        "Social acceptans": "Social accept",
        "Visa social acceptans": "Vis social accept",
        "Visa social acceptanslager": "Vis socialt acceptlag",
        "Acceptanspåverkan": "Acceptpåvirkning",
        "Kommer i augusti": "Kommer i august",
        "Levereras av EML": "Leveres af EML",
        "Levereras av IVL": "Leveres af IVL",
        "Landskapspotential Vind": "Landskabspotentiale Vind",
        "Landskapspotential Sol": "Landskabspotentiale Sol",
        "Småskalig anläggning på tak": "Småskala anlæg på tag",
        "Storskalig anläggning på land": "Storskala anlæg på land",
        "Potentiell etableringsyta": "Potentielt etableringsareal",
        "Scenariofördelning i etableringshex": "Scenariefordeling i etableringshex",
        "Ytbehov utanför landskapets potential": "Arealbehov udenfor landskabets potentiale",
        "Befolkning": "Befolkning",
        "Befolkningspunkter": "Befolkningspunkter",
        "Panelyta per person": "Panelareal per person",
        "Avstånd till befolkning": "Afstand til befolkning",
        "Använd ändringar": "Anvend ændringer",
        "Energimix": "Energimix",
        "Visa föreslagen etableringsyta": "Vis foreslået etableringsareal",
        "Sammanfattning": "Sammenfatning",
        "Vind/sol och landskapspåverkan": "Vind/sol og landskabspåvirkning",
        "Så läses tabellen": "Sådan læses tabellen",
        "Potentialfördelning per landskapstyp": "Potentialefordeling per landskabstype",
        "Avancerade inställningar": "Avancerede indstillinger",
        "Avancerade kartinställningar": "Avancerede kortindstillinger",
        "Vindandel": "Vindandel",
        "Solandel": "Solandel",
        "Total energi": "Samlet energi",
        "Debug och prestanda": "Debug og ydeevne",
        "Manifest och tekniska sökvägar": "Manifest og tekniske stier",
        "Visning och enheter": "Visning og enheder",
        "Hexdetaljer och kartmarkörer": "Hexdetaljer og kortmarkører",
        "Urval och ytdetaljer": "Udvalg og arealdetaljer",
        "Prestanda": "Ydeevne",
        "Landskapsanalys": "Landskabsanalyse",
        "Lager som visas": "Lag som vises",
        "Kärnområden": "Kerneområder",
        "Inga lager är tända.": "Ingen lag er tændt.",
        "Alla grundmanifest och H3-geometrier finns.": "Alle grundmanifest og H3-geometrier findes.",
        "Data saknas för vissa lager/funktioner. Det är okej i detta läge.": "Data mangler for visse lag/funktioner. Det er okay i denne fase.",
        "Inga regionmanifest hittades.": "Ingen regionmanifest fundet.",
        "planerad": "planlagt",
        "På": "På",
    },
    "en": {
        "Sol- och vindpotential": "Solar and Wind Potential",
        "Danska/Norska": "Danish/Norwegian",
        "Svenska": "Swedish",
        "English": "English",
        "Språk": "Language",
        "Visa guide": "Show guide",
        "Öppna en kort genomgång av Trøndelag-vyn.": "Open a short walkthrough of the Trøndelag view.",
        "Föregående": "Previous",
        "Nästa": "Next",
        "Hoppa över": "Skip",
        "Pausa": "Pause",
        "Fortsätt guide": "Resume guide",
        "Testa detta": "Try this",
        "Klart": "Done",
        "Stäng": "Close",
        "Klar": "Done",
        "Öppna inte automatiskt igen": "Do not open automatically again",
        "Region": "Region",
        "Scenarier": "Scenarios",
        "Scenario": "Scenario",
        "Lager": "Layers",
        "Geografier": "Geographies",
        "Landskap": "Landscape",
        "Landskapstyper": "Landscape Types",
        "Landskapstrukturer": "Landscape Structures",
        "Landskapsfaktorer": "Landscape Factors",
        "Faktor": "Factor",
        "H3-upplösning": "H3 Resolution",
        "H3-rollup": "H3 Rollup",
        "Hexvisning": "Hex Display",
        "Vald upplösning": "Selected resolution",
        "Zoomanpassad upplösning": "Zoom-adaptive resolution",
        "Snabb visning: vald upplösning": "Fast display: selected resolution",
        "Panelbredd": "Panel width",
        "Visa/dölj kontext": "Show/hide context",
        "Karta": "Map",
        "Etableringsyta": "Establishment Area",
        "Regionstatus": "Region Status",
        "Nästa datapaket": "Next Data Package",
        "Data och metod": "Data and Method",
        "Aktiva beräkningar": "Active Calculations",
        "Beräkning och datakvalitet": "Calculation and Data Quality",
        "Energimodellering": "Energy Modelling",
        "Social acceptans": "Social Acceptance",
        "Visa social acceptans": "Show social acceptance",
        "Visa social acceptanslager": "Show social acceptance layer",
        "Acceptanspåverkan": "Acceptance impact",
        "Kommer i augusti": "Coming in August",
        "Levereras av EML": "Provided by EML",
        "Levereras av IVL": "Provided by IVL",
        "Landskapspotential Vind": "Landscape Potential Wind",
        "Landskapspotential Sol": "Landscape Potential Solar",
        "Småskalig anläggning på tak": "Small-scale rooftop installation",
        "Storskalig anläggning på land": "Large-scale ground installation",
        "Potentiell etableringsyta": "Potential Establishment Area",
        "Scenariofördelning i etableringshex": "Scenario Allocation in Establishment Hexes",
        "Ytbehov utanför landskapets potential": "Area Demand Outside Landscape Potential",
        "Befolkning": "Population",
        "Befolkningspunkter": "Population points",
        "Panelyta per person": "Panel area per person",
        "Avstånd till befolkning": "Distance to population",
        "Använd ändringar": "Apply changes",
        "Energimix": "Energy mix",
        "Visa föreslagen etableringsyta": "Show proposed establishment area",
        "Sammanfattning": "Summary",
        "Vind/sol och landskapspåverkan": "Wind/Solar and Landscape Impact",
        "Så läses tabellen": "How to read the table",
        "Potentialfördelning per landskapstyp": "Potential distribution by landscape type",
        "Avancerade inställningar": "Advanced Settings",
        "Avancerade kartinställningar": "Advanced Map Settings",
        "Vindandel": "Wind Share",
        "Solandel": "Solar Share",
        "Total energi": "Total Energy",
        "Debug och prestanda": "Debug and Performance",
        "Manifest och tekniska sökvägar": "Manifests and Technical Paths",
        "Visning och enheter": "Display and Units",
        "Hexdetaljer och kartmarkörer": "Hex Details and Map Markers",
        "Urval och ytdetaljer": "Selection and Area Details",
        "Prestanda": "Performance",
        "Landskapsanalys": "Landscape Analysis",
        "Lager som visas": "Visible Layers",
        "Kärnområden": "Core Areas",
        "Inga lager är tända.": "No layers are enabled.",
        "Alla grundmanifest och H3-geometrier finns.": "All base manifests and H3 geometries are available.",
        "Data saknas för vissa lager/funktioner. Det är okej i detta läge.": "Data is missing for some layers/functions. That is okay at this stage.",
        "Inga regionmanifest hittades.": "No region manifests found.",
        "planerad": "planned",
        "På": "On",
    },
}


def _language() -> str:
    value = str(st.session_state.get(APP_LANGUAGE_KEY, "sv"))
    return value if value in APP_LANGUAGES else "sv"


def _t(text: str, **kwargs: Any) -> str:
    translated = APP_TRANSLATIONS.get(_language(), {}).get(str(text), str(text))
    return translated.format(**kwargs) if kwargs else translated


def _wind_control_language() -> str:
    return "en" if _language() == "en" else "sv"


def _render_language_switcher(panel: Any | None = None) -> None:
    target = panel or st.sidebar
    current = _language()
    target.divider()
    target.caption(f"{_t('Språk')}: {_t(APP_LANGUAGES[current])}")
    cols = target.columns(3)
    for idx, (code, label) in enumerate(APP_LANGUAGES.items()):
        if cols[idx].button(
            APP_LANGUAGE_BUTTONS.get(code, _t(label)),
            key=f"app_language_{code}",
            type="secondary",
            disabled=code == current,
            help=_t(label),
        ):
            st.session_state[APP_LANGUAGE_KEY] = code
            _request_ui_only_rerun("språk")
            st.rerun()


def _trondelag_tutorial_available(region: dict[str, Any]) -> bool:
    return str(region.get("region_id", "") or "").lower() == "trondelag"


def _render_tutorial_launcher(region: dict[str, Any], panel: Any | None = None) -> bool:
    if not _trondelag_tutorial_available(region):
        return False

    target = panel or st.sidebar
    target.divider()
    clicked = target.button(
        _t("Visa guide"),
        key="potential_tutorial_open_button",
        help=_t("Öppna en kort genomgång av Trøndelag-vyn."),
        width="stretch",
    )
    if clicked:
        st.session_state[TUTORIAL_FORCE_OPEN_KEY] = True
        st.session_state[TUTORIAL_FORCE_OPEN_TOKEN_KEY] = int(st.session_state.get(TUTORIAL_FORCE_OPEN_TOKEN_KEY, 0) or 0) + 1
    return bool(st.session_state.pop(TUTORIAL_FORCE_OPEN_KEY, False))


def _tutorial_text(key: str, **kwargs: Any) -> str:
    texts = {
        "sv": {
            "prototype_title": "Hitta potential för ny vind och sol",
            "prototype_body": (
                "Det här är en prototyp som hjälper dig att utforska var ny vind- och solenergi kan passa. "
                "Du kan pröva olika energibehov och se hur landskap, avstånd och social acceptans påverkar möjliga etableringar, "
                "så att viktiga vägval blir lättare att förstå."
            ),
            "geography_title": "Börja med geografin",
            "geography_body": (
                "Startläget visar analysens resultat: den potentiella etableringsytan för vind och sol. "
                "Alla GIS-lager som används i analysen visas inte i kartan från start, men de kan öppnas under avancerade inställningar "
                "när du vill se vilka antaganden som påverkar ytan."
            ),
            "energy_title": "Koppla yta till energi",
            "energy_body": (
                "Energimixen i huvudytan låter dig pröva balansen mellan vind och sol. Energimodelleringen översätter valt scenario till ett ytanspråk."
            ),
            "scenario_title": "Energiscenario och markintensitet",
            "scenario_body": (
                "Energiscenario styr hur mycket energi som ska testas i modellen. Markintensitet styr hur mycket mark som behövs per TWh "
                "och kan väljas låg, mellan eller hög oberoende av energiscenariot. Därför kan du till exempel testa hög energinivå "
                "med mellan markintensitet."
            ),
            "acceptance_title": "Lägg till social acceptans",
            "acceptance_body": (
                "Social acceptans hjälper dig förstå var potentialen kan vara mer eller mindre realistisk utifrån landskapets användning, "
                "värden och möjliga konflikter. I Trøndelag är detta syntetiskt testdata, inte färdiga IVL-resultat."
            ),
            "acceptance_suggestion": (
                "Dra i reglaget Acceptanspåverkan och följ hur energilandskapet förändras i kartan och i tabellen till höger."
            ),
            "establishment_body": (
                "Kartan visar den sammanvägda etableringspotentialen: grön betyder både vind och sol, gul bara sol, blå bara vind och röd ej lämpligt. "
                "Det är potential utifrån de geografiska antaganden och filter som är aktiva just nu."
            ),
            "allocation_body": (
                "Scenariofördelningen visar var modellens vind- och solyta placeras inom den möjliga etableringsytan. "
                "Mörkare teknikfärger visar scenariots placering. Där både vind och sol kan använda samma hex syns samnyttjande i modellen."
            ),
            "outside_body": (
                "Ytbehov utanför landskapets potential visar schematisk vind- eller solyta som behövs när scenariot inte ryms i den beräknade potentialen. "
                "Det gör skillnaden mellan landskapets möjliga yta och scenariots efterfrågan synlig."
            ),
            "green_title": "Startläget är försiktigt",
            "green_body": (
                "Kartan startar med ett restriktivt potentialläge så att antaganden och bortval syns direkt. "
                "Grönt betyder möjligt enligt nuvarande filter, inte ett färdigt rekommenderat område."
            ),
            "wind_solar_title": "Vind och sol styrs under Geografier",
            "wind_solar_body": (
                "Under Geografier finns Landskapspotential Vind och Landskapspotential Sol. Där kan du ändra de förvalda filtren, buffertarna och nätantagandena. "
                "Analysen använder valen även när GIS-lagren är dolda i kartan."
            ),
            "wind_apply_title": "Ändra vindantaganden och använd dem",
            "wind_apply_body": (
                "Öppna vindpotentialen om du vill ändra startlägets filter, till exempel Befolkning och bebyggelse eller vägar. "
                "Klicka sedan Använd ändringar för att räkna om kartan och resultatet med de valda antagandena."
            ),
            "action_open_geography_todo": "Öppna Geografier och Landskap för att se vilka antaganden som formar kartan.",
            "action_open_geography_done": "Bra, nu är landskapsvalen synliga. Fortsätt med energimodelleringen eller testa egna filter.",
            "action_open_wind_todo": "Öppna vind- och solpotentialen för att se vilka antaganden du kan ändra.",
            "action_open_wind_done": "Bra, nu är potentialkontrollerna synliga. Testa ett filter eller fortsätt till omräkningen.",
            "action_apply_wind_todo": "Klicka på Använd ändringar när du vill räkna om kartan och resultatet med filtervalen.",
            "action_apply_wind_done": "Bra, appen har fått en apply-signal. Kontrollera kartan och resultatpanelen innan du går vidare.",
            "table_title": "Läs resultatet i tabellen",
            "table_body": (
                "Tabellen visar om energimixen ryms inom den beräknade potentialen. Totalraden är en tekniksumma: samma fysiska hex kan räknas för både vind och sol när ytan kan samnyttjas."
            ),
            "right_geographies_title": "Geografier visar antagandena",
            "right_geographies_body": (
                "Här sammanfattas vilka GIS-lager och filter som formar kartan, till exempel befolkning, vägar, naturvärden och kulturmiljöer."
            ),
            "landscape_distribution_title": "Potential per landskapstyp",
            "landscape_distribution_body": (
                "De två expandrarna visar hur vind- och solpotentialen fördelas mellan landskapstyper. Det hjälper dig se vilken typ av landskap potentialen hamnar i."
            ),
            "reopen_title": "Du kan alltid öppna guiden igen",
            "reopen_body": (
                "Starta om den korta guiden med Visa guide. Kryssa i Öppna inte automatiskt igen om du vill att appen ska hoppa över introduktionen nästa gång."
            ),
        },
        "en": {
            "prototype_title": "Find potential for new wind and solar",
            "prototype_body": (
                "This prototype helps you explore where new wind and solar energy may fit. "
                "You can test energy needs and see how landscape, distances and social acceptance affect possible establishments, "
                "so important choices become easier to understand."
            ),
            "geography_title": "Start with geography",
            "geography_body": (
                "The starting point shows the analysis result: the potential establishment area for wind and solar. "
                "Not every GIS layer used in the analysis is shown on the map by default, but they can be opened under advanced settings "
                "when you want to see which assumptions shape the area."
            ),
            "energy_title": "Connect area to energy",
            "energy_body": (
                "The energy mix control in the main view lets you test the balance between wind and solar. Energy modelling translates the selected scenario into an area claim."
            ),
            "scenario_title": "Energy scenario and land intensity",
            "scenario_body": (
                "The energy scenario controls how much energy is tested in the model. Land intensity controls how much land is needed per TWh "
                "and can be low, medium or high independently of the energy scenario. For example, you can test a high energy level "
                "with medium land intensity."
            ),
            "acceptance_title": "Add social acceptance",
            "acceptance_body": (
                "Social acceptance helps you understand where the potential may be more or less realistic given landscape use, "
                "values and possible conflicts. In Trøndelag this is synthetic test data, not finished IVL results."
            ),
            "acceptance_suggestion": (
                "Drag the Acceptance impact slider and watch how the energy landscape changes on the map and in the table to the right."
            ),
            "establishment_body": (
                "The map shows the combined establishment potential: green means both wind and solar, yellow solar only, blue wind only and red not suitable. "
                "It is the potential under the geographic assumptions and filters that are active right now."
            ),
            "allocation_body": (
                "The scenario allocation shows where the model places wind and solar area within the possible establishment area. "
                "Darker technology colours show the scenario placement. Where wind and solar can use the same hex, the model shows shared use."
            ),
            "outside_body": (
                "Area demand outside landscape potential shows schematic wind or solar area needed when the scenario does not fit inside the calculated potential. "
                "It makes the gap between possible landscape area and scenario demand visible."
            ),
            "green_title": "The starting point is cautious",
            "green_body": (
                "The map starts in a restrictive potential mode so assumptions and exclusions are visible immediately. "
                "Green means possible under the current filters, not a final recommended area."
            ),
            "wind_solar_title": "Wind and solar are controlled under Geographies",
            "wind_solar_body": (
                "Under Geographies you will find Landscape Potential Wind and Landscape Potential Solar. This is where you can change the preset filters, buffers and grid assumptions. "
                "The analysis uses those choices even when the GIS layers are hidden on the map."
            ),
            "wind_apply_title": "Change wind assumptions and apply them",
            "wind_apply_body": (
                "Open wind potential if you want to change the starting filters, for example Population and settlement or roads. "
                "Then click Apply changes to recalculate the map and result using the selected assumptions."
            ),
            "action_open_geography_todo": "Open Geographies and Landscape to see which assumptions shape the map.",
            "action_open_geography_done": "Good, the landscape choices are visible. Continue with energy modelling or try your own filters.",
            "action_open_wind_todo": "Open wind and solar potential to see which assumptions you can change.",
            "action_open_wind_done": "Good, the potential controls are visible. Try a filter or continue to recalculation.",
            "action_apply_wind_todo": "Click Apply changes when you want to recalculate the map and result using the filter choices.",
            "action_apply_wind_done": "Good, the app received an apply signal. Check the map and result panel before continuing.",
            "table_title": "Read the result table",
            "table_body": (
                "The table shows whether the energy mix fits within the calculated potential. The total row is a technology sum: the same physical hex can count for both wind and solar when the area can be shared."
            ),
            "right_geographies_title": "Geographies show the assumptions",
            "right_geographies_body": (
                "This section summarizes which GIS layers and filters shape the map, such as population, roads, nature values and cultural environments."
            ),
            "landscape_distribution_title": "Potential by landscape type",
            "landscape_distribution_body": (
                "The two expanders show how wind and solar potential are distributed across landscape types. This helps you see which kinds of landscape the potential falls within."
            ),
            "reopen_title": "You can always open the guide again",
            "reopen_body": (
                "Restart the short guide with Show guide. Tick Do not open automatically again if you want the app to skip the introduction next time."
            ),
        },
        "da_no": {
            "prototype_title": "Find potentiale for ny vind og sol",
            "prototype_body": (
                "Denne prototype hjælper dig med at udforske, hvor ny vind- og solenergi kan passe. "
                "Du kan teste energibehov og se hvordan landskab, afstande og social accept påvirker mulige etableringer, "
                "så vigtige valg bliver lettere at forstå."
            ),
            "geography_title": "Begynd med geografien",
            "geography_body": (
                "Startpunktet viser analysens resultat: det potentielle etableringsareal for vind og sol. "
                "Ikke alle GIS-lag, der bruges i analysen, vises på kortet fra start, men de kan åbnes under avancerede indstillinger, "
                "når du vil se hvilke antagelser der påvirker arealet."
            ),
            "energy_title": "Kobl areal til energi",
            "energy_body": (
                "Energimix-kontrollen i hovedvisningen lader dig teste balancen mellem vind og sol. Energimodelleringen oversætter valgt scenarie til et arealkrav."
            ),
            "scenario_title": "Energiscenarie og markintensitet",
            "scenario_body": (
                "Energiscenariet styrer hvor meget energi der testes i modellen. Markintensitet styrer hvor meget areal der behøves per TWh "
                "og kan vælges lav, mellem eller høj uafhængigt af energiscenariet. Derfor kan du for eksempel teste et højt energiniveau "
                "med mellem markintensitet."
            ),
            "acceptance_title": "Tilføj social accept",
            "acceptance_body": (
                "Social accept hjælper dig med at forstå hvor potentialet kan være mere eller mindre realistisk ud fra landskabets anvendelse, "
                "værdier og mulige konflikter. I Trøndelag er dette syntetiske testdata, ikke færdige IVL-resultater."
            ),
            "acceptance_suggestion": (
                "Træk i skyderen Acceptpåvirkning og følg hvordan energilandskabet ændrer sig på kortet og i tabellen til højre."
            ),
            "establishment_body": (
                "Kortet viser det samlede etableringspotentiale: grøn betyder både vind og sol, gul kun sol, blå kun vind og rød ikke egnet. "
                "Det er potentialet ud fra de geografiske antagelser og filtre som er aktive lige nu."
            ),
            "allocation_body": (
                "Scenariefordelingen viser hvor modellen placerer vind- og solareal inden for den mulige etableringsflade. "
                "Mørkere teknikfarver viser scenariets placering. Hvor vind og sol kan bruge samme hex, viser modellen samnyttelse."
            ),
            "outside_body": (
                "Arealbehov udenfor landskabets potentiale viser skematisk vind- eller solareal som behøves, når scenariet ikke kan rummes i det beregnede potentiale. "
                "Det gør forskellen mellem landskabets mulige areal og scenariets efterspørgsel synlig."
            ),
            "green_title": "Startpunktet er forsigtigt",
            "green_body": (
                "Kortet starter i en restriktiv potentialtilstand, så antagelser og fravalg ses direkte. "
                "Grøn betyder muligt med nuværende filtre, ikke et færdigt anbefalet område."
            ),
            "wind_solar_title": "Vind og sol styres under Geografier",
            "wind_solar_body": (
                "Under Geografier findes Landskabspotentiale Vind og Landskabspotentiale Sol. Her kan du ændre de forvalgte filtre, buffere og netantagelser. "
                "Analysen bruger valgene, selv når GIS-lagene er skjult på kortet."
            ),
            "wind_apply_title": "Ændr vindantagelser og anvend dem",
            "wind_apply_body": (
                "Åbn vindpotentialet, hvis du vil ændre startfiltrene, for eksempel Befolkning og bebyggelse eller veje. "
                "Klik derefter Använd ändringar for at beregne kortet og resultatet igen med de valgte antagelser."
            ),
            "action_open_geography_todo": "Åbn Geografier og Landskab for at se hvilke antagelser som former kortet.",
            "action_open_geography_done": "Godt, nu er landskabsvalgene synlige. Fortsæt med energimodelleringen eller test egne filtre.",
            "action_open_wind_todo": "Åbn vind- og solpotentialet for at se hvilke antagelser du kan ændre.",
            "action_open_wind_done": "Godt, nu er potentialekontrollerne synlige. Test et filter eller fortsæt til genberegningen.",
            "action_apply_wind_todo": "Klik på Använd ändringar når du vil beregne kortet og resultatet igen med filtervalgene.",
            "action_apply_wind_done": "Godt, appen har fået et apply-signal. Kontrollér kortet og resultatpanelet før du går videre.",
            "table_title": "Læs resultatet i tabellen",
            "table_body": (
                "Tabellen viser om energimixet kan rummes inden for det beregnede potentiale. Totalrækken er en teknologisum: samme fysiske hex kan tælle for både vind og sol, når arealet kan deles."
            ),
            "right_geographies_title": "Geografier viser antagelserne",
            "right_geographies_body": (
                "Her sammenfattes hvilke GIS-lag og filtre der former kortet, for eksempel befolkning, veje, naturværdier og kulturmiljøer."
            ),
            "landscape_distribution_title": "Potentiale per landskabstype",
            "landscape_distribution_body": (
                "De to expandere viser hvordan vind- og solpotentialet fordeles mellem landskabstyper. Det hjælper dig med at se hvilken type landskab potentialet havner i."
            ),
            "reopen_title": "Du kan altid åbne guiden igen",
            "reopen_body": (
                "Start den korte guide igen med Vis guide. Marker Åbn ikke automatisk igen hvis du vil have appen til at springe introduktionen over næste gang."
            ),
        },
    }
    language_texts = texts.get(_language(), texts["sv"])
    value = language_texts.get(str(key), texts["sv"].get(str(key), str(key)))
    return value.format(**kwargs) if kwargs else value


def _trondelag_tutorial_steps(region: dict[str, Any]) -> list[dict[str, Any]]:
    region_label = str(region.get("display_name", "Trondelag") or "Trondelag")
    geography_label = _t("Geografier")
    landscape_label = _t("Landskap")
    wind_label = _t(WIND_LANDSCAPE_POTENTIAL_LABEL)
    solar_label = _t(SOLAR_LANDSCAPE_POTENTIAL_LABEL)
    guide_label = _t("Visa guide")
    wind_apply_label = ui_text("apply_changes", _wind_control_language())
    return [
        {
            "selector": ".workspace-header",
            "title": _tutorial_text("prototype_title"),
            "body": _tutorial_text("prototype_body", region_label=region_label),
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("geography_title"),
            "body": _tutorial_text("geography_body"),
            "openTexts": [geography_label, landscape_label],
            "showActionStatus": False,
            "action": {
                "kind": "detailsOpen",
                "texts": [geography_label, landscape_label],
                "todo": _tutorial_text("action_open_geography_todo"),
                "done": _tutorial_text("action_open_geography_done"),
            },
        },
        {
            "anchor": "energy-mix",
            "title": _tutorial_text("energy_title"),
            "body": _tutorial_text("energy_body"),
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("scenario_title"),
            "body": _tutorial_text("scenario_body"),
            "openTexts": [_t("Energimodellering")],
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("acceptance_title"),
            "body": _tutorial_text("acceptance_body"),
            "suggestion": _tutorial_text("acceptance_suggestion"),
            "openTexts": [_t("Social acceptans")],
        },
        {
            "anchor": "map",
            "target": "iframeLegendSection",
            "legendSectionTitle": COMBINED_ESTABLISHMENT_LAYER_LABEL,
            "fallbackTarget": "iframeSelector",
            "iframeSelectors": [".map-legend"],
            "scrollWindowToTarget": True,
            "title": _t(COMBINED_ESTABLISHMENT_LAYER_LABEL),
            "body": _tutorial_text("establishment_body"),
        },
        {
            "anchor": "map",
            "target": "iframeLegendSection",
            "legendSectionTitle": SCENARIO_ALLOCATION_LAYER_LABEL,
            "fallbackTarget": "iframeSelector",
            "iframeSelectors": [".map-legend"],
            "scrollWindowToTarget": True,
            "title": _t(SCENARIO_ALLOCATION_LAYER_LABEL),
            "mapLayers": [SCENARIO_ALLOCATION_LAYER_LABEL],
            "body": _tutorial_text("allocation_body"),
        },
        {
            "anchor": "map",
            "target": "iframeLegendSection",
            "legendSectionTitle": OUTSIDE_LP_NEED_LAYER_LABEL,
            "fallbackTarget": "iframeSelector",
            "iframeSelectors": [".map-legend"],
            "scrollWindowToTarget": True,
            "mapLayers": [OUTSIDE_LP_NEED_LAYER_LABEL],
            "title": _t(OUTSIDE_LP_NEED_LAYER_LABEL),
            "body": _tutorial_text("outside_body"),
        },
        {
            "anchor": "map",
            "target": "iframeGreenArea",
            "fallbackTarget": "nextIframe",
            "closeAllExpanders": True,
            "sidebarScrollTop": True,
            "scrollWindowToTarget": True,
            "stableHighlight": True,
            "title": _tutorial_text("green_title"),
            "body": _tutorial_text("green_body"),
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("wind_solar_title"),
            "body": _tutorial_text("wind_solar_body"),
            "closeAllExpanders": True,
            "sidebarScrollTop": True,
            "openTexts": [geography_label],
            "highlightTexts": [wind_label, solar_label],
            "action": {
                "kind": "detailsOpen",
                "texts": [wind_label, solar_label],
                "todo": _tutorial_text("action_open_wind_todo"),
                "done": _tutorial_text("action_open_wind_done"),
            },
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("wind_apply_title"),
            "body": _tutorial_text("wind_apply_body"),
            "closeAllExpanders": True,
            "sidebarScrollTop": True,
            "openTexts": [geography_label, wind_label, WIND_SETTLEMENT_GROUP_LABEL],
            "scrollToText": wind_apply_label,
            "scrollAlign": 0.58,
            "highlightTexts": [wind_apply_label],
            "action": {
                "kind": "buttonClick",
                "id": "wind_apply",
                "text": wind_apply_label,
                "todo": _tutorial_text("action_apply_wind_todo"),
                "done": _tutorial_text("action_apply_wind_done"),
            },
        },
        {
            "selector": ".change-table-wrap",
            "anchor": "right-panel",
            "scrollWindowToTarget": True,
            "title": _tutorial_text("table_title"),
            "body": _tutorial_text("table_body"),
        },
        {
            "selector": "[data-potential-tutorial-anchor=\"right-geographies\"]",
            "scrollWindowToTarget": True,
            "title": _tutorial_text("right_geographies_title"),
            "body": _tutorial_text("right_geographies_body"),
        },
        {
            "selector": "[data-potential-tutorial-anchor=\"landscape-distribution\"]",
            "scrollWindowToTarget": True,
            "title": _tutorial_text("landscape_distribution_title"),
            "body": _tutorial_text("landscape_distribution_body"),
        },
        {
            "target": "buttonText",
            "buttonText": guide_label,
            "closeAllExpanders": True,
            "title": _tutorial_text("reopen_title"),
            "body": _tutorial_text("reopen_body"),
        },
    ]


def _render_tutorial_component(region: dict[str, Any], force_open: bool = False) -> None:
    if not _trondelag_tutorial_available(region):
        return
    if components is None:
        if force_open:
            st.warning("Guiden kräver Streamlit components och kan inte visas i den här miljön.")
        return

    payload = json.dumps(
        {
            "forceOpen": bool(force_open),
            "openToken": int(st.session_state.get(TUTORIAL_FORCE_OPEN_TOKEN_KEY, 0) or 0),
            "storageKey": TUTORIAL_STORAGE_KEY,
            "steps": _trondelag_tutorial_steps(region),
            "labels": {
                "previous": _t("Föregående"),
                "next": _t("Nästa"),
                "skip": _t("Hoppa över"),
                "pause": _t("Pausa"),
                "resume": _t("Fortsätt guide"),
                "close": _t("Stäng"),
                "done": _t("Klar"),
                "actionTodo": _t("Testa detta"),
                "actionDone": _t("Klart"),
                "doNotAutoOpen": _t("Öppna inte automatiskt igen"),
                "step": "Steg" if _language() != "en" else "Step",
                "of": "av" if _language() != "en" else "of",
            },
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    component_html = """
<div id="potential-tutorial-component-root" aria-hidden="true"></div>
<script>
(() => {
  const payload = __PAYLOAD__;
  let parentWindow;
  let parentDocument;
  try {
    parentWindow = window.parent;
    parentDocument = parentWindow.document;
  } catch (error) {
    return;
  }
  if (!parentWindow || !parentDocument || !Array.isArray(payload.steps) || payload.steps.length === 0) {
    return;
  }

  const storage = (() => {
    try {
      return parentWindow.localStorage;
    } catch (error) {
      try {
        return window.localStorage;
      } catch (innerError) {
        return null;
      }
    }
  })();

  const progressKey = `${payload.storageKey}:progress`;
  const pausedKey = `${payload.storageKey}:paused`;
  const actionKey = `${payload.storageKey}:actions`;
  const shouldAutoOpen = !storage || storage.getItem(payload.storageKey) !== "1";
  const hasPausedProgress = storage && storage.getItem(pausedKey) === "1";
  if (!payload.forceOpen && !shouldAutoOpen && !hasPausedProgress) {
    return;
  }

  if (typeof parentWindow.__potentialTutorialCleanup === "function") {
    parentWindow.__potentialTutorialCleanup();
  }

  const styleId = "potential-tutorial-style";
  const existingStyle = parentDocument.getElementById(styleId);
  const style = existingStyle || parentDocument.createElement("style");
  style.id = styleId;
  style.textContent = `
      #potential-tutorial-root {
        position: fixed;
        inset: 0;
        z-index: 2147483000;
        pointer-events: none;
        font-family: "Source Sans Pro", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      #potential-tutorial-root .pt-dim {
        display: none;
      }
      #potential-tutorial-root .pt-highlight {
        position: fixed;
        border: 2px solid #f8fafc;
        box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.82), 0 14px 34px rgba(15, 23, 42, 0.28);
        border-radius: 8px;
        pointer-events: none;
        transition: top 140ms ease, left 140ms ease, width 140ms ease, height 140ms ease;
        z-index: 1;
      }
      #potential-tutorial-root .pt-popover {
        position: fixed;
        width: min(360px, calc(100vw - 32px));
        max-height: calc(100vh - 32px);
        overflow: auto;
        border: 1px solid rgba(15, 23, 42, 0.14);
        border-radius: 8px;
        background: #ffffff;
        color: #111827;
        box-shadow: 0 18px 50px rgba(15, 23, 42, 0.26);
        padding: 0.95rem;
        pointer-events: auto;
        z-index: 2;
      }
      #potential-tutorial-root .pt-topline {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.35rem;
      }
      #potential-tutorial-root .pt-count {
        color: #4b5563;
        font-size: 0.78rem;
        font-weight: 700;
      }
      #potential-tutorial-root .pt-close {
        width: 2rem;
        height: 2rem;
        border: 0;
        border-radius: 6px;
        background: #f3f4f6;
        color: #111827;
        cursor: pointer;
        font-size: 1.05rem;
        line-height: 1;
      }
      #potential-tutorial-root h2 {
        margin: 0 0 0.42rem 0;
        color: #111827;
        font-size: 1.05rem;
        line-height: 1.22;
        letter-spacing: 0;
      }
      #potential-tutorial-root p {
        margin: 0;
        color: #374151;
        font-size: 0.92rem;
        line-height: 1.42;
      }
      #potential-tutorial-root .pt-action-status {
        margin-top: 0.72rem;
        border: 1px solid rgba(22, 101, 52, 0.18);
        border-radius: 6px;
        background: #f0fdf4;
        color: #166534;
        padding: 0.55rem 0.65rem;
        font-size: 0.84rem;
        line-height: 1.32;
      }
      #potential-tutorial-root .pt-action-status[data-state="todo"] {
        border-color: rgba(146, 64, 14, 0.18);
        background: #fffbeb;
        color: #92400e;
      }
      #potential-tutorial-root .pt-checkbox {
        display: flex;
        align-items: flex-start;
        gap: 0.48rem;
        margin: 0.82rem 0 0.9rem 0;
        color: #374151;
        font-size: 0.86rem;
        line-height: 1.25;
      }
      #potential-tutorial-root .pt-checkbox input {
        width: 1rem;
        height: 1rem;
        margin-top: 0.05rem;
      }
      #potential-tutorial-root .pt-actions {
        display: flex;
        justify-content: space-between;
        gap: 0.45rem;
        flex-wrap: wrap;
      }
      #potential-tutorial-root button {
        font: inherit;
      }
      #potential-tutorial-root .pt-button {
        min-height: 2rem;
        border: 1px solid rgba(15, 23, 42, 0.16);
        border-radius: 6px;
        background: #ffffff;
        color: #111827;
        padding: 0.38rem 0.65rem;
        cursor: pointer;
        font-size: 0.86rem;
        font-weight: 650;
      }
      #potential-tutorial-root .pt-button:disabled {
        cursor: not-allowed;
        opacity: 0.45;
      }
      #potential-tutorial-root .pt-button-primary {
        border-color: #166534;
        background: #166534;
        color: #ffffff;
      }
      #potential-tutorial-resume {
        position: fixed;
        right: 18px;
        bottom: 74px;
        z-index: 2147483001;
        min-height: 2.35rem;
        border: 1px solid rgba(22, 101, 52, 0.26);
        border-radius: 6px;
        background: #166534;
        color: #ffffff;
        box-shadow: 0 12px 32px rgba(15, 23, 42, 0.24);
        cursor: pointer;
        font: 650 0.9rem "Source Sans Pro", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        padding: 0.48rem 0.78rem;
      }
      @media (max-width: 680px) {
        #potential-tutorial-root .pt-popover {
          left: 16px !important;
          right: 16px !important;
          width: auto;
        }
      }
    `;
  if (!existingStyle) {
    parentDocument.head.appendChild(style);
  }

  const root = parentDocument.createElement("div");
  root.id = "potential-tutorial-root";
  const stableHighlightCache = parentWindow.__potentialTutorialStableHighlightCache || new Map();
  parentWindow.__potentialTutorialStableHighlightCache = stableHighlightCache;
  root.innerHTML = `
    <div class="pt-dim" data-dim="top"></div>
    <div class="pt-dim" data-dim="left"></div>
    <div class="pt-dim" data-dim="right"></div>
    <div class="pt-dim" data-dim="bottom"></div>
    <div class="pt-highlight"></div>
    <section class="pt-popover" role="dialog" aria-live="polite" aria-label="Tutorial">
      <div class="pt-topline">
        <div class="pt-count"></div>
        <button type="button" class="pt-close" aria-label="${payload.labels.close}">&times;</button>
      </div>
      <h2></h2>
      <p></p>
      <div class="pt-action-status" hidden></div>
      <label class="pt-checkbox">
        <input type="checkbox" />
        <span></span>
      </label>
      <div class="pt-actions">
        <span>
          <button type="button" class="pt-button pt-skip"></button>
          <button type="button" class="pt-button pt-pause"></button>
        </span>
        <span>
          <button type="button" class="pt-button pt-prev"></button>
          <button type="button" class="pt-button pt-button-primary pt-next"></button>
        </span>
      </div>
    </section>
  `;
  parentDocument.body.appendChild(root);

  const dims = {
    top: root.querySelector('[data-dim="top"]'),
    left: root.querySelector('[data-dim="left"]'),
    right: root.querySelector('[data-dim="right"]'),
    bottom: root.querySelector('[data-dim="bottom"]'),
  };
  const highlight = root.querySelector(".pt-highlight");
  const popover = root.querySelector(".pt-popover");
  const count = root.querySelector(".pt-count");
  const title = root.querySelector("h2");
  const body = root.querySelector("p");
  const actionStatus = root.querySelector(".pt-action-status");
  const remember = root.querySelector(".pt-checkbox input");
  const rememberLabel = root.querySelector(".pt-checkbox span");
  const closeButton = root.querySelector(".pt-close");
  const skipButton = root.querySelector(".pt-skip");
  const pauseButton = root.querySelector(".pt-pause");
  const prevButton = root.querySelector(".pt-prev");
  const nextButton = root.querySelector(".pt-next");
  let index = 0;
  let activeTarget = null;
  let resumeButton = null;
  let actionInterval = null;
  if (payload.forceOpen && storage) {
    storage.removeItem(pausedKey);
    storage.removeItem(progressKey);
    storage.removeItem(actionKey);
  }
  if (storage) {
    const savedIndex = Number.parseInt(storage.getItem(progressKey) || "", 10);
    if (Number.isFinite(savedIndex)) {
      index = Math.min(Math.max(savedIndex, 0), payload.steps.length - 1);
    }
  }

  rememberLabel.textContent = payload.labels.doNotAutoOpen;
  skipButton.textContent = payload.labels.skip;
  pauseButton.textContent = payload.labels.pause;
  prevButton.textContent = payload.labels.previous;
  if (storage && storage.getItem(payload.storageKey) === "1") {
    remember.checked = true;
  }

  const cleanup = () => {
    parentWindow.removeEventListener("resize", updatePosition);
    parentWindow.removeEventListener("scroll", updatePosition, true);
    parentDocument.removeEventListener("keydown", onKeyDown, true);
    parentDocument.removeEventListener("click", onDocumentClick, true);
    if (actionInterval) {
      parentWindow.clearInterval(actionInterval);
    }
    if (resumeButton && resumeButton.parentNode) {
      resumeButton.parentNode.removeChild(resumeButton);
    }
    if (root.parentNode) {
      root.parentNode.removeChild(root);
    }
    parentWindow.__potentialTutorialCleanup = null;
  };

  const persistPreference = () => {
    if (!storage) {
      return;
    }
    if (remember.checked) {
      storage.setItem(payload.storageKey, "1");
    } else {
      storage.removeItem(payload.storageKey);
    }
  };

  const saveProgress = () => {
    if (storage) {
      storage.setItem(progressKey, String(index));
    }
  };

  const close = () => {
    persistPreference();
    if (storage) {
      storage.removeItem(pausedKey);
      storage.removeItem(progressKey);
      storage.removeItem(actionKey);
    }
    cleanup();
  };

  const showResumeButton = () => {
    if (resumeButton && resumeButton.parentNode) {
      return;
    }
    resumeButton = parentDocument.createElement("button");
    resumeButton.id = "potential-tutorial-resume";
    resumeButton.type = "button";
    resumeButton.textContent = payload.labels.resume;
    resumeButton.addEventListener("click", resume);
    parentDocument.body.appendChild(resumeButton);
  };

  const hideResumeButton = () => {
    if (resumeButton && resumeButton.parentNode) {
      resumeButton.parentNode.removeChild(resumeButton);
    }
    resumeButton = null;
  };

  const pause = () => {
    saveProgress();
    if (storage) {
      storage.setItem(pausedKey, "1");
    }
    root.style.display = "none";
    showResumeButton();
  };

  const resume = () => {
    if (storage) {
      storage.removeItem(pausedKey);
    }
    hideResumeButton();
    root.style.display = "";
    render();
  };

  const markerFor = (anchor) => {
    if (!anchor) {
      return null;
    }
    return parentDocument.querySelector(`[data-potential-tutorial-anchor="${anchor}"]`) || parentDocument.getElementById(anchor);
  };

  const resolveSelector = (selector) => {
    if (!selector) {
      return null;
    }
    try {
      return parentDocument.querySelector(selector);
    } catch (error) {
      return null;
    }
  };

  const iframeForContainer = (container) => {
    if (!container) {
      return null;
    }
    return container.tagName && container.tagName.toLowerCase() === "iframe"
      ? container
      : container.querySelector("iframe");
  };

  const visibleMapFrames = () => Array.from(parentDocument.querySelectorAll("iframe"))
    .map((iframe) => {
      const container = iframe.closest('div[data-testid="stIFrame"]') || iframe;
      const rect = container.getBoundingClientRect();
      const visibleLeft = Math.max(0, rect.left);
      const visibleTop = Math.max(0, rect.top);
      const visibleRight = Math.min(parentWindow.innerWidth, rect.right);
      const visibleBottom = Math.min(parentWindow.innerHeight, rect.bottom);
      const visibleArea = Math.max(0, visibleRight - visibleLeft) * Math.max(0, visibleBottom - visibleTop);
      return { iframe, container, rect, visibleArea };
    })
    .filter((item) => (
      item.rect.width > 220 &&
      item.rect.height > 220 &&
      item.visibleArea > 50000 &&
      !item.container.closest('section[data-testid="stSidebar"]')
    ))
    .sort((a, b) => b.visibleArea - a.visibleArea);

  const findNextIframe = (anchor) => {
    const marker = markerFor(anchor);
    const frames = visibleMapFrames();
    if (!frames.length) {
      return null;
    }
    if (!marker) {
      return frames[0].container;
    }
    const markerTop = marker.getBoundingClientRect().top;
    const afterMarker = frames
      .filter((item) => item.rect.top >= markerTop - 24)
      .sort((a, b) => b.visibleArea - a.visibleArea);
    return (afterMarker[0] || frames[0]).container;
  };

  const normalizedText = (value) => String(value || "").replace(/\s+/g, " ").trim().toLowerCase();
  const rightPanelScope = () => parentDocument.querySelector('div[data-testid="column"]:has(#right-panel-content-anchor)') || parentDocument;
  const scopeForStep = (step) => (step && step.scope === "rightPanel" ? rightPanelScope() : parentDocument);
  const isVisible = (node) => {
    if (!node || !node.getBoundingClientRect) {
      return false;
    }
    const rect = node.getBoundingClientRect();
    return rect.width > 2 && rect.height > 2;
  };

  const virtualRect = (rectProvider) => ({
    __virtual: true,
    getBoundingClientRect: rectProvider,
  });

  const combineRects = (nodes) => {
    const rects = nodes
      .filter((node) => node && (node.__virtual || isVisible(node)))
      .map((node) => node.getBoundingClientRect());
    if (!rects.length) {
      return null;
    }
    return virtualRect(() => {
      const liveRects = nodes
        .filter((node) => node && (node.__virtual || isVisible(node)))
        .map((node) => node.getBoundingClientRect());
      const source = liveRects.length ? liveRects : rects;
      const left = Math.min(...source.map((rect) => rect.left));
      const top = Math.min(...source.map((rect) => rect.top));
      const right = Math.max(...source.map((rect) => rect.right));
      const bottom = Math.max(...source.map((rect) => rect.bottom));
      return { left, top, right, bottom, width: right - left, height: bottom - top };
    });
  };

  const iframeElementTarget = (iframe, element) => {
    if (!iframe || !element || !isVisible(element)) {
      return null;
    }
    return virtualRect(() => {
      const frameRect = iframe.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      const left = frameRect.left + rect.left;
      const top = frameRect.top + rect.top;
      const right = left + rect.width;
      const bottom = top + rect.height;
      return { left, top, right, bottom, width: rect.width, height: rect.height };
    });
  };

  const iframeDocumentForStep = (step) => {
    const frameContainer = findNextIframe(step.anchor);
    const iframe = iframeForContainer(frameContainer);
    try {
      return iframe && iframe.contentDocument ? { iframe, doc: iframe.contentDocument } : null;
    } catch (error) {
      return null;
    }
  };

  const activateMapLayersForStep = (step) => {
    const layerNames = Array.isArray(step.mapLayers) ? step.mapLayers : [];
    if (!layerNames.length) {
      return;
    }
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo || !iframeInfo.iframe || !iframeInfo.iframe.contentWindow) {
      return;
    }
    const mapWindow = iframeInfo.iframe.contentWindow;
    const setter = mapWindow.__potentialMapSetOverlayVisibility;
    if (typeof setter !== "function") {
      return;
    }
    layerNames.forEach((layerName) => {
      try {
        setter(String(layerName), true);
      } catch (error) {
        // The guide can still highlight the legend if the map is re-rendering.
      }
    });
  };

  const findIframeSelectorTarget = (step) => {
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo) {
      return null;
    }
    const selectors = Array.isArray(step.iframeSelectors) ? step.iframeSelectors : [];
    for (const selector of selectors) {
      try {
        const element = iframeInfo.doc.querySelector(selector);
        const target = iframeElementTarget(iframeInfo.iframe, element);
        if (target) {
          return target;
        }
      } catch (error) {
        continue;
      }
    }
    return null;
  };

  const findIframeLegendSectionTarget = (step) => {
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo) {
      return null;
    }
    const wanted = normalizedText(step.legendSectionTitle);
    if (!wanted) {
      return null;
    }
    const sections = Array.from(iframeInfo.doc.querySelectorAll(".map-legend-section"));
    const heading = sections.find((node) => normalizedText(node.textContent) === wanted);
    if (!heading) {
      return null;
    }
    const legend = heading.closest(".map-legend");
    if (legend && legend.scrollHeight > legend.clientHeight + 4) {
      legend.scrollTop = Math.max(0, heading.offsetTop - 8);
    }
    const nodes = [heading];
    let next = heading.nextElementSibling;
    while (next && !next.classList.contains("map-legend-section")) {
      if (next.classList.contains("map-legend-row")) {
        nodes.push(next);
      }
      next = next.nextElementSibling;
    }
    const target = combineRects(nodes);
    if (!target) {
      return null;
    }
    return virtualRect(() => {
      const frameRect = iframeInfo.iframe.getBoundingClientRect();
      const rect = target.getBoundingClientRect();
      const left = frameRect.left + rect.left;
      const top = frameRect.top + rect.top;
      const right = left + rect.width;
      const bottom = top + rect.height;
      return { left, top, right, bottom, width: rect.width, height: rect.height };
    });
  };

  const findGreenMapAreaTarget = (step) => {
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo) {
      return null;
    }
    return virtualRect(() => {
      const frameRect = iframeInfo.iframe.getBoundingClientRect();
      const width = Math.min(parentWindow.innerWidth * 0.24, 520, Math.max(24, frameRect.width - 24));
      const height = Math.min(parentWindow.innerHeight * 0.35, 460, Math.max(24, frameRect.height - 24));
      const preferredLeft = parentWindow.innerWidth * 0.38;
      const preferredTop = parentWindow.innerHeight * 0.48;
      const left = Math.min(Math.max(preferredLeft, frameRect.left + 12), frameRect.right - width - 12);
      const top = Math.min(Math.max(preferredTop, frameRect.top + 12), frameRect.bottom - height - 12);
      const right = left + width;
      const bottom = top + height;
      return { left, top, right, bottom, width: right - left, height: bottom - top };
    });
  };

  const findExpanderForLabel = (label, scope = parentDocument) => {
    const wanted = normalizedText(label);
    if (!wanted) {
      return null;
    }
    const searchScope = scope || parentDocument;
    const details = Array.from(searchScope.querySelectorAll("details"));
    const matches = details.filter((node) => {
      const summary = node.querySelector("summary");
      const text = normalizedText(summary ? summary.textContent : node.textContent);
      return text === wanted || text.includes(wanted);
    });
    return (
      matches.find((node) => isVisible(node) && node.closest('section[data-testid="stSidebar"]')) ||
      matches.find((node) => isVisible(node)) ||
      matches.find((node) => node.closest('section[data-testid="stSidebar"]')) ||
      matches[0] ||
      null
    );
  };

  const findButtonByText = (label, scope = parentDocument) => {
    const wanted = normalizedText(label);
    if (!wanted) {
      return null;
    }
    const searchScope = scope || parentDocument;
    return Array.from(searchScope.querySelectorAll("button")).find((button) => {
      const text = normalizedText(button.textContent);
      return isVisible(button) && (text === wanted || text.includes(wanted));
    }) || null;
  };

  const findTextBlockByText = (label, scope = parentDocument) => {
    const wanted = normalizedText(label);
    if (!wanted) {
      return null;
    }
    const searchScope = scope || parentDocument;
    return Array.from(searchScope.querySelectorAll("h1,h2,h3,h4,h5,h6,summary,p,li")).find((node) => {
      const text = normalizedText(node.textContent);
      return isVisible(node) && (text === wanted || text.includes(wanted));
    }) || null;
  };

  const findElementByText = (label, scope = parentDocument) => (
    findExpanderForLabel(label, scope) || findButtonByText(label, scope) || findTextBlockByText(label, scope)
  );

  const actionIdentity = (action) => String((action && (action.id || action.text)) || "");

  const readActionState = () => {
    if (!storage) {
      return {};
    }
    try {
      const value = JSON.parse(storage.getItem(actionKey) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (error) {
      return {};
    }
  };

  const markActionDone = (action) => {
    const id = actionIdentity(action);
    if (!storage || !id) {
      return;
    }
    const actions = readActionState();
    actions[id] = true;
    storage.setItem(actionKey, JSON.stringify(actions));
  };

  const actionIsComplete = (action) => {
    if (!action || !action.kind) {
      return false;
    }
    if (action.kind === "detailsOpen") {
      const labels = Array.isArray(action.texts) ? action.texts : [];
      return labels.length > 0 && labels.every((label) => {
        const match = findExpanderForLabel(label);
        return Boolean(match && match.open);
      });
    }
    if (action.kind === "buttonClick") {
      const actions = readActionState();
      return Boolean(actions[actionIdentity(action)]);
    }
    return false;
  };

  const updateActionStatus = () => {
    const step = payload.steps[index] || {};
    const action = step.action || null;
    if (!action && step.showActionStatus !== false && step.suggestion) {
      actionStatus.hidden = false;
      actionStatus.dataset.state = "todo";
      actionStatus.textContent = `${payload.labels.actionTodo}: ${step.suggestion || ""}`;
      return;
    }
    if (!action || step.showActionStatus === false) {
      actionStatus.hidden = true;
      actionStatus.textContent = "";
      return;
    }
    const complete = actionIsComplete(action);
    actionStatus.hidden = false;
    actionStatus.dataset.state = complete ? "done" : "todo";
    const prefix = complete ? payload.labels.actionDone : payload.labels.actionTodo;
    const message = complete ? action.done : action.todo;
    actionStatus.textContent = `${prefix}: ${message || ""}`;
  };

  const onDocumentClick = (event) => {
    const target = event.target && event.target.closest
      ? event.target.closest("button,[role='button'],summary,label,input")
      : null;
    const clickedText = normalizedText(
      target ? (target.textContent || target.getAttribute("aria-label") || target.value || "") : ""
    );
    if (clickedText) {
      payload.steps.forEach((step) => {
        const action = step.action || null;
        if (!action || action.kind !== "buttonClick") {
          return;
        }
        const wanted = normalizedText(action.text);
        if (wanted && (clickedText === wanted || clickedText.includes(wanted))) {
          markActionDone(action);
        }
      });
    }
    parentWindow.setTimeout(updateActionStatus, 120);
  };

  const combinedTextTarget = (labels, scope = parentDocument) => {
    const nodes = (Array.isArray(labels) ? labels : [])
      .map((label) => findElementByText(label, scope))
      .filter(Boolean);
    return combineRects(nodes);
  };

  const firstStepExpander = (step) => {
    const labels = Array.isArray(step.openTexts) ? step.openTexts.map(normalizedText).filter(Boolean) : [];
    for (const label of labels) {
      const match = findExpanderForLabel(label);
      if (match) {
        return match;
      }
    }
    return null;
  };

  const openExpandersForStep = (step) => {
    const labels = Array.isArray(step.openTexts) ? step.openTexts.map(normalizedText).filter(Boolean) : [];
    if (!labels.length) {
      return;
    }
    labels.forEach((label) => {
      const match = findExpanderForLabel(label);
      if (match && !match.open) {
        match.open = true;
        match.dispatchEvent(new Event("toggle", { bubbles: true }));
      }
    });
  };

  const closeSidebarExpanders = () => {
    const sidebar = parentDocument.querySelector('section[data-testid="stSidebar"]');
    const scope = sidebar || parentDocument;
    Array.from(scope.querySelectorAll("details")).forEach((node) => {
      if (node.open) {
        node.open = false;
        node.dispatchEvent(new Event("toggle", { bubbles: true }));
      }
    });
  };

  const sidebarScrollContainers = () => {
    const sidebar = parentDocument.querySelector('section[data-testid="stSidebar"]');
    if (!sidebar) {
      return [];
    }
    const candidates = [sidebar, ...Array.from(sidebar.querySelectorAll("*"))].filter((node) => {
      const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
      if (!rect || rect.height < 80) {
        return false;
      }
      const style = parentWindow.getComputedStyle(node);
      return (
        node.scrollHeight > node.clientHeight + 8 &&
        ["auto", "scroll", "overlay"].includes(style.overflowY)
      );
    });
    return candidates.length ? candidates : [sidebar];
  };

  const setSidebarScrollTop = (top = 0) => {
    sidebarScrollContainers().forEach((node) => {
      node.scrollTop = top;
    });
  };

  const scrollSidebarToElement = (element, align = 0.5) => {
    if (!element || !element.getBoundingClientRect) {
      return;
    }
    sidebarScrollContainers().forEach((node) => {
      if (!node.contains(element)) {
        return;
      }
      const containerRect = node.getBoundingClientRect();
      const elementRect = element.getBoundingClientRect();
      const desiredTop = containerRect.top + containerRect.height * clamp(align, 0.1, 0.9);
      node.scrollTop += elementRect.top - desiredTop;
    });
  };

  const scrollSidebarToText = (label, align = 0.5) => {
    const target = findElementByText(label);
    if (target) {
      scrollSidebarToElement(target, align);
    }
  };

  const scrollTargetIntoViewport = (target) => {
    if (!target || !target.getBoundingClientRect) {
      return;
    }
    const rect = target.getBoundingClientRect();
    const margin = 24;
    let deltaY = 0;
    if (rect.bottom > parentWindow.innerHeight - margin) {
      deltaY = rect.bottom - parentWindow.innerHeight + margin;
    } else if (rect.top < margin) {
      deltaY = rect.top - margin;
    }
    if (Math.abs(deltaY) > 1) {
      parentWindow.scrollBy(0, deltaY);
      const sidebar = parentDocument.querySelector('section[data-testid="stSidebar"]');
      const candidates = [
        parentDocument.scrollingElement,
        parentDocument.documentElement,
        parentDocument.body,
        ...Array.from(parentDocument.querySelectorAll("*")),
      ].filter((node, index, nodes) => {
        if (!node || nodes.indexOf(node) !== index || (sidebar && sidebar.contains(node))) {
          return false;
        }
        const nodeRect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
        return (
          nodeRect &&
          nodeRect.height > 200 &&
          node.scrollHeight > node.clientHeight + 8
        );
      });
      candidates.forEach((node) => {
        node.scrollTop += deltaY;
      });
    }
  };

  const resolveTarget = (step) => {
    if (step.target === "iframeSelector") {
      return findIframeSelectorTarget(step) || (step.fallbackTarget === "nextIframe" ? findNextIframe(step.anchor) : null);
    }
    if (step.target === "iframeLegendSection") {
      return findIframeLegendSectionTarget(step) || (step.fallbackTarget === "iframeSelector" ? findIframeSelectorTarget(step) : null);
    }
    if (step.target === "iframeGreenArea") {
      return findGreenMapAreaTarget(step) || (step.fallbackTarget === "nextIframe" ? findNextIframe(step.anchor) : null);
    }
    if (step.target === "buttonText") {
      return findButtonByText(step.buttonText);
    }
    if (Array.isArray(step.highlightTexts)) {
      const textTarget = combinedTextTarget(step.highlightTexts, scopeForStep(step));
      if (textTarget) {
        return textTarget;
      }
    }
    if (step.target === "nextIframe") {
      return findNextIframe(step.anchor);
    }
    const stepExpander = firstStepExpander(step);
    if (stepExpander) {
      return stepExpander;
    }
    const selected = resolveSelector(step.selector);
    if (selected) {
      return selected;
    }
    const marker = markerFor(step.anchor);
    if (!marker) {
      return null;
    }
    return (
      marker.closest("section[data-testid='stSidebar']") ||
      marker.closest("div[data-testid='column']") ||
      marker.closest("div[data-testid='stVerticalBlock']") ||
      marker.closest("div[data-testid='stElementContainer']") ||
      marker.parentElement
    );
  };

  const setBox = (node, top, left, width, height) => {
    node.style.top = `${Math.max(0, top)}px`;
    node.style.left = `${Math.max(0, left)}px`;
    node.style.width = `${Math.max(0, width)}px`;
    node.style.height = `${Math.max(0, height)}px`;
  };

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  function updatePosition() {
    const viewportWidth = parentWindow.innerWidth;
    const viewportHeight = parentWindow.innerHeight;
    let top = 72;
    let left = 24;
    let width = Math.min(420, viewportWidth - 48);
    let height = 160;

    if (activeTarget && (activeTarget.__virtual || parentDocument.body.contains(activeTarget))) {
      const rect = activeTarget.getBoundingClientRect();
      const pad = 8;
      top = clamp(rect.top - pad, 8, viewportHeight - 24);
      left = clamp(rect.left - pad, 8, viewportWidth - 24);
      width = clamp(rect.width + pad * 2, 24, viewportWidth - left - 8);
      height = clamp(rect.height + pad * 2, 24, viewportHeight - top - 8);
    }

    const seamOverlap = 2;
    const holeTop = Math.floor(top);
    const holeLeft = Math.floor(left);
    const holeRight = Math.ceil(left + width);
    const holeBottom = Math.ceil(top + height);
    const holeWidth = Math.max(0, holeRight - holeLeft);
    const holeHeight = Math.max(0, holeBottom - holeTop);
    setBox(dims.top, 0, 0, viewportWidth, holeTop + seamOverlap);
    setBox(dims.left, Math.max(0, holeTop - seamOverlap), 0, holeLeft + seamOverlap, holeHeight + seamOverlap * 2);
    setBox(
      dims.right,
      Math.max(0, holeTop - seamOverlap),
      Math.max(0, holeRight - seamOverlap),
      viewportWidth - holeRight + seamOverlap,
      holeHeight + seamOverlap * 2
    );
    setBox(
      dims.bottom,
      Math.max(0, holeBottom - seamOverlap),
      0,
      viewportWidth,
      viewportHeight - holeBottom + seamOverlap
    );
    setBox(highlight, holeTop, holeLeft, holeWidth, holeHeight);

    const popoverWidth = Math.min(360, viewportWidth - 32);
    const popoverHeight = popover.offsetHeight || 240;
    let popoverLeft = left + width + 16;
    if (popoverLeft + popoverWidth > viewportWidth - 16) {
      popoverLeft = left - popoverWidth - 16;
    }
    if (popoverLeft < 16) {
      popoverLeft = clamp(left + 8, 16, viewportWidth - popoverWidth - 16);
    }
    let popoverTop = clamp(top + 8, 16, viewportHeight - popoverHeight - 16);
    if (viewportWidth <= 680) {
      popoverLeft = 16;
      popoverTop = clamp(top + height + 12, 16, viewportHeight - popoverHeight - 16);
    }
    popover.style.left = `${popoverLeft}px`;
    popover.style.top = `${popoverTop}px`;
  }

  const render = () => {
    const step = payload.steps[index];
    if (step.closeAllExpanders) {
      closeSidebarExpanders();
    }
    openExpandersForStep(step);
    if (step.sidebarScrollTop) {
      setSidebarScrollTop(0);
    }
    if (step.scrollToText) {
      scrollSidebarToText(step.scrollToText, Number(step.scrollAlign || 0.5));
    }
    activateMapLayersForStep(step);
    activeTarget = resolveTarget(step);
    if (step.scrollWindowToTarget) {
      scrollTargetIntoViewport(activeTarget);
      activeTarget = resolveTarget(step);
    }
    if (step.stableHighlight && activeTarget && activeTarget.getBoundingClientRect) {
      const key = `${index}:${step.title || ""}`;
      const viewport = `${parentWindow.innerWidth}x${parentWindow.innerHeight}`;
      const cached = stableHighlightCache.get(key);
      if (cached && cached.viewport === viewport) {
        const cachedRect = cached.rect;
        activeTarget = virtualRect(() => ({ ...cachedRect }));
      } else {
        const rect = activeTarget.getBoundingClientRect();
        const stableRect = {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        };
        stableHighlightCache.set(key, { viewport, rect: stableRect });
        activeTarget = virtualRect(() => ({ ...stableRect }));
      }
    }
    title.textContent = step.title || "";
    body.textContent = step.body || "";
    saveProgress();
    updateActionStatus();
    count.textContent = `${payload.labels.step} ${index + 1} ${payload.labels.of} ${payload.steps.length}`;
    prevButton.disabled = index === 0;
    nextButton.textContent = index === payload.steps.length - 1 ? payload.labels.done : payload.labels.next;
    if (activeTarget && typeof activeTarget.scrollIntoView === "function") {
      try {
        activeTarget.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
      } catch (error) {
        activeTarget.scrollIntoView();
      }
    }
    parentWindow.setTimeout(updatePosition, 180);
    parentWindow.requestAnimationFrame(updatePosition);
    nextButton.focus({ preventScroll: true });
  };

  const go = (delta) => {
    index = clamp(index + delta, 0, payload.steps.length - 1);
    render();
  };

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      if (index === payload.steps.length - 1) {
        close();
      } else {
        go(1);
      }
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      go(-1);
    }
  };

  closeButton.addEventListener("click", close);
  skipButton.addEventListener("click", close);
  pauseButton.addEventListener("click", pause);
  prevButton.addEventListener("click", () => go(-1));
  nextButton.addEventListener("click", () => {
    if (index === payload.steps.length - 1) {
      close();
    } else {
      go(1);
    }
  });
  parentWindow.addEventListener("resize", updatePosition);
  parentWindow.addEventListener("scroll", updatePosition, true);
  parentDocument.addEventListener("keydown", onKeyDown, true);
  parentDocument.addEventListener("click", onDocumentClick, true);
  actionInterval = parentWindow.setInterval(updateActionStatus, 800);
  parentWindow.__potentialTutorialCleanup = cleanup;

  if (payload.forceOpen && storage) {
    storage.removeItem(pausedKey);
  }
  if (!payload.forceOpen && storage && storage.getItem(pausedKey) === "1") {
    root.style.display = "none";
    showResumeButton();
  } else {
    parentWindow.setTimeout(render, 350);
  }
})();
</script>
""".replace("__PAYLOAD__", payload)
    components.html(component_html, height=0)


def _request_ui_only_rerun(reason: str) -> None:
    st.session_state[UI_ONLY_RERUN_KEY] = True
    st.session_state[UI_ONLY_RERUN_REASON_KEY] = str(reason)


def _ui_only_rerun_requested() -> bool:
    return bool(st.session_state.get(UI_ONLY_RERUN_KEY, False))


def _ui_only_rerun_reason() -> str:
    return str(st.session_state.get(UI_ONLY_RERUN_REASON_KEY, "visning"))


def _clear_ui_only_rerun() -> None:
    st.session_state[UI_ONLY_RERUN_KEY] = False
    st.session_state[UI_ONLY_RERUN_REASON_KEY] = ""


def _workspace_calculation_fingerprint(
    region: dict[str, Any],
    scenario_state: dict[str, Any],
    h3_resolution: int,
    analysis_h3_resolution: int,
    zoom_family_enabled: bool,
    show_user_solar: bool,
    show_solar_v1: bool,
    show_user_wind: bool,
    show_v10: bool,
    show_pdf_types: bool,
    show_cluster: bool,
    show_factor: bool,
    show_social_acceptance: bool,
    social_acceptance_scenario: str,
    social_acceptance_impact_pct: float,
    social_acceptance_allocation_priority_pct: float,
    selected_factor: str,
    applied_solar_config: dict[str, Any],
    solar_params: dict[str, Any],
    solar_large_filter_configs: list[dict[str, Any]],
    wind_selected_layers: dict[str, list[str]],
    wind_ui_params: dict[str, Any],
    wind_visual_options: dict[str, Any],
    energy_model_state: dict[str, Any],
) -> str:
    """Hash the calculation inputs, deliberately excluding UI language."""
    payload = {
        "calculation_version": WORKSPACE_CALCULATION_VERSION,
        "region_id": str(region.get("region_id", "region")),
        "scenario": scenario_state.get("scenario"),
        "h3_resolution": int(h3_resolution),
        "analysis_h3_resolution": int(analysis_h3_resolution),
        "zoom_family_enabled": bool(zoom_family_enabled),
        "show_user_solar": bool(show_user_solar),
        "show_solar_v1": bool(show_solar_v1),
        "show_user_wind": bool(show_user_wind),
        "show_landscape_types": bool(show_v10),
        "show_landscape_pdf_types": bool(show_pdf_types),
        "show_landscape_structures": bool(show_cluster),
        "show_landscape_factors": bool(show_factor),
        "show_social_acceptance": bool(show_social_acceptance),
        "social_acceptance_scenario": str(social_acceptance_scenario),
        "social_acceptance_impact_pct": float(social_acceptance_impact_pct),
        "social_acceptance_allocation_priority_pct": float(social_acceptance_allocation_priority_pct),
        "selected_factor": str(selected_factor),
        "applied_solar_config": applied_solar_config,
        "solar_params": solar_params,
        "solar_large_filter_configs": solar_large_filter_configs,
        "wind_selected_layers": normalize_group_layer_map(wind_selected_layers),
        "wind_ui_params": wind_ui_params,
        "wind_visual_options": wind_visual_options,
        "energy_debug_run_id": energy_model_state.get("debug_run_id"),
        "energy_available": bool(energy_model_state.get("available")),
        "energy_show_proposal": bool(energy_model_state.get("show_proposal")),
        "energy_placement_mode": energy_model_state.get("placement_mode"),
    }
    return _short_hash(payload)


def _cached_workspace_payload(fingerprint: str) -> dict[str, Any] | None:
    cached = st.session_state.get(WORKSPACE_RENDER_CACHE_KEY)
    if not isinstance(cached, dict):
        return None
    if str(cached.get("fingerprint", "")) != str(fingerprint):
        return None
    return cached


def _invalidate_workspace_cache(reason: str = "") -> None:
    st.session_state.pop(WORKSPACE_RENDER_CACHE_KEY, None)
    _clear_ui_only_rerun()
    if reason:
        st.session_state["workspace_cache_invalidated_reason"] = str(reason)


WIND_SHARE_CLASS_SPECS: list[dict[str, Any]] = [
    {"id": "share_0", "label": "0%", "max_pct": 0.0, "legend_label": "0%", "base_color": "#d7301f", "core_color": "#7f0000"},
    {"id": "share_1", "label": ">0-5%", "max_pct": 5.0, "legend_label": "<=5%", "base_color": "#ef4444", "core_color": "#991b1b"},
    {"id": "share_2", "label": ">5-10%", "max_pct": 10.0, "legend_label": None, "base_color": "#f87171", "core_color": "#b91c1c"},
    {"id": "share_3", "label": ">10-15%", "max_pct": 15.0, "legend_label": None, "base_color": "#fecaca", "core_color": "#ef4444"},
    {"id": "share_4", "label": ">15-25%", "max_pct": 25.0, "legend_label": "~25%", "base_color": "#dbeafe", "core_color": "#93c5fd"},
    {"id": "share_5", "label": ">25-35%", "max_pct": 35.0, "legend_label": None, "base_color": "#bfdbfe", "core_color": "#60a5fa"},
    {"id": "share_6", "label": ">35-50%", "max_pct": 50.0, "legend_label": "~50%", "base_color": "#93c5fd", "core_color": "#3b82f6"},
    {"id": "share_7", "label": ">50-65%", "max_pct": 65.0, "legend_label": None, "base_color": "#60a5fa", "core_color": "#2563eb"},
    {"id": "share_8", "label": ">65-80%", "max_pct": 80.0, "legend_label": None, "base_color": "#2563eb", "core_color": "#1d4ed8"},
    {"id": "share_9", "label": ">80-100%", "max_pct": 100.0, "legend_label": "100%", "base_color": "#1d4ed8", "core_color": "#1e3a8a"},
]
ESTABLISHMENT_CLASS_SPECS: dict[str, dict[str, str]] = {
    "not_suitable": {"label": "Inte lämplig", "color": "#991b1b", "stroke": "#fee2e2"},
    "wind_only": {"label": "Endast vind", "color": "#2563eb", "stroke": "#dbeafe"},
    "solar_only": {"label": "Endast sol", "color": "#facc15", "stroke": "#fef3c7"},
    "wind_and_solar": {"label": "Vind och sol", "color": "#15803d", "stroke": "#dcfce7"},
}
SOLAR_CONTROL_GROUPS: list[dict[str, Any]] = [
    {
        "id": "open_landscape",
        "label": "Robusta öppna landskap",
        "caption": "Plus för öppna, jämna och storskaliga produktionslandskap.",
        "params": ["everyday_matrix_bonus"],
    },
    {
        "id": "grid",
        "label": "Elinfrastruktur",
        "caption": "Plus för teknisk logik nära elnät och transformatorstationer.",
        "params": ["grid_access_bonus"],
    },
    {
        "id": "settlement",
        "label": "Bebyggelse och rekreation",
        "caption": "Minus där bebyggelse, tät struktur och vardagslandskap ökar konflikt.",
        "params": ["settlement_penalty", "population_buffer_m"],
    },
    {
        "id": "protected",
        "label": "Skyddad natur och habitat",
        "caption": "Minus för skog, habitatkärnor och skyddade naturmiljöer.",
        "params": ["protected_penalty"],
    },
    {
        "id": "coast",
        "label": "Kust och öppna strandmiljöer",
        "caption": "Minus för kustnära landskap där solparker kan få visuell kontakt med kustlinjen.",
        "params": ["coastal_penalty"],
    },
    {
        "id": "terrain",
        "label": "Terräng, dalar och utsikt",
        "caption": "Minus för relief, sprickdalar, sluttningar och visuellt känsliga lägen.",
        "params": ["terrain_penalty"],
    },
]
SOLAR_PARAM_CONTROLS: dict[str, dict[str, Any]] = {
    "base_score": {
        "label": "Basnivå",
        "min": 30.0,
        "max": 75.0,
        "step": 1.0,
        "help": "Startpoäng innan landskapsvillkor läggs till.",
    },
    "grid_access_bonus": {
        "label": "Elanslutningslogik",
        "min": 0.0,
        "max": 20.0,
        "step": 1.0,
        "help": "Förberedd lagerbaserad kontroll för närhet till elnät och transformatorstationer.",
    },
    "everyday_matrix_bonus": {
        "label": "Öppet produktionslandskap",
        "min": 0.0,
        "max": 30.0,
        "step": 1.0,
        "help": "Förberedd kontroll för öppna produktionslandskap som kan bära storskalig sol.",
    },
    "coastal_penalty": {
        "label": "Buffert kust/strand",
        "min": 0.0,
        "max": 35.0,
        "step": 1.0,
        "help": "Förberedd lagerbaserad kontroll för kustzon och strandskydd.",
    },
    "terrain_penalty": {
        "label": "Terrängavgränsning",
        "min": 0.0,
        "max": 35.0,
        "step": 1.0,
        "help": "Förberedd kontroll för relief, sprickdalar och visuellt känsliga lägen.",
    },
    "protected_penalty": {
        "label": "Buffert skyddad natur",
        "min": 0.0,
        "max": 40.0,
        "step": 1.0,
        "help": "Förberedd lagerbaserad kontroll för skyddade områden, skog och habitat.",
    },
    "settlement_penalty": {
        "label": "Bebyggelseavgränsning",
        "min": 0.0,
        "max": 35.0,
        "step": 1.0,
        "help": "Förberedd lagerbaserad kontroll för bebyggelse och tät struktur.",
    },
    "population_buffer_m": {
        "label": "Avstånd till befolkning",
        "min": 100.0,
        "max": 500.0,
        "step": 25.0,
        "help": "Totalt avstånd från befolkningspunkter. Källan är redan en 100 m visningsbuffert, så appen lägger bara till avståndet över 100 m.",
    },
}


def _map_view_reset_token() -> int:
    try:
        return int(st.session_state.get(MAP_VIEW_RESET_TOKEN_KEY, 0))
    except Exception:
        return 0


def _init_panel_state() -> None:
    st.session_state.setdefault(LEFT_PANEL_OPEN_KEY, True)
    st.session_state.setdefault(RIGHT_PANEL_OPEN_KEY, True)
    if RIGHT_PANEL_WIDTH_KEY not in st.session_state:
        st.session_state[RIGHT_PANEL_WIDTH_KEY] = RIGHT_PANEL_WIDTH_DEFAULT
    elif st.session_state.get(RIGHT_PANEL_WIDTH_DEFAULT_VERSION_KEY) != RIGHT_PANEL_WIDTH_DEFAULT_VERSION:
        try:
            current_width = float(st.session_state.get(RIGHT_PANEL_WIDTH_KEY, RIGHT_PANEL_WIDTH_DEFAULT) or RIGHT_PANEL_WIDTH_DEFAULT)
        except Exception:
            current_width = RIGHT_PANEL_WIDTH_DEFAULT
        if any(abs(current_width - legacy_default) < 0.01 for legacy_default in RIGHT_PANEL_WIDTH_LEGACY_DEFAULTS):
            st.session_state[RIGHT_PANEL_WIDTH_KEY] = RIGHT_PANEL_WIDTH_DEFAULT
    st.session_state[RIGHT_PANEL_WIDTH_DEFAULT_VERSION_KEY] = RIGHT_PANEL_WIDTH_DEFAULT_VERSION


def _right_panel_width_pct() -> float:
    try:
        value = float(st.session_state.get(RIGHT_PANEL_WIDTH_KEY, RIGHT_PANEL_WIDTH_DEFAULT) or RIGHT_PANEL_WIDTH_DEFAULT)
    except Exception:
        value = RIGHT_PANEL_WIDTH_DEFAULT
    return max(0.0, min(100.0, value))


def _render_right_panel_width_control(panel: Any | None = None) -> None:
    target = panel or st
    target.caption(_t("Panelbredd"))
    target.slider(
        _t("Panelbredd"),
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key=RIGHT_PANEL_WIDTH_KEY,
        format="%.0f%%",
        label_visibility="collapsed",
        on_change=_request_ui_only_rerun,
        args=("panelbredd",),
    )
    target.caption(
        {
            "en": "0% makes the panel minimal. 100% gives almost the full workspace to the panel.",
            "da_no": "0% gør panelet minimalt. 100% giver næsten hele arbejdsfladen til panelet.",
        }.get(_language(), "0% gör panelen minimal. 100% ger nästan hela arbetsytan till panelen.")
    )


def _toggle_panel(key: str) -> None:
    was_open = bool(st.session_state.get(key, True))
    st.session_state[key] = not was_open
    if key == RIGHT_PANEL_OPEN_KEY and was_open is False and _right_panel_width_pct() <= 0.0:
        st.session_state[RIGHT_PANEL_WIDTH_KEY] = RIGHT_PANEL_WIDTH_DEFAULT
    _request_ui_only_rerun("panel")


def _panel_shell() -> tuple[Any | None, Any | None]:
    _init_panel_state()
    left_open = bool(st.session_state.get(LEFT_PANEL_OPEN_KEY, True))
    right_open = bool(st.session_state.get(RIGHT_PANEL_OPEN_KEY, True))
    left_width = "min(20rem, 28vw)"
    right_width = "min(20rem, 28vw)"
    left_padding = f"calc({left_width} + 1.25rem)" if left_open else "1.5rem"
    right_padding = f"calc({right_width} + 1.25rem)" if right_open else "1.5rem"
    left_toggle_left = f"calc({left_width} + 0.45rem)" if left_open else "0.65rem"
    right_toggle_right = f"calc({right_width} + 0.45rem)" if right_open else "0.65rem"

    panel_css = f"""
        <style>
        div[data-testid="stAppViewContainer"] section.main .block-container,
        div[data-testid="stAppViewContainer"] .main .block-container {{
          max-width: none;
          padding-left: {left_padding};
          padding-right: {right_padding};
          padding-top: 0.7rem;
        }}
        div[data-testid="column"]:has(#left-panel-content-anchor) {{
          position: fixed !important;
          top: 0;
          left: 0;
          bottom: 0;
          width: {left_width} !important;
          min-width: {left_width} !important;
          max-width: {left_width} !important;
          flex: 0 0 {left_width} !important;
          z-index: 999;
          overflow-y: auto;
          overflow-x: hidden;
          background: rgb(244, 246, 249);
          border-right: 1px solid rgba(49, 51, 63, 0.16);
          padding: 3.3rem 1.05rem 2rem 1.05rem !important;
        }}
        div[data-testid="column"]:has(#right-panel-content-anchor) {{
          position: fixed !important;
          top: 0;
          right: 0;
          bottom: 0;
          width: {right_width} !important;
          min-width: {right_width} !important;
          max-width: {right_width} !important;
          flex: 0 0 {right_width} !important;
          z-index: 999;
          overflow-y: auto;
          overflow-x: hidden;
          background: rgb(244, 246, 249);
          border-left: 1px solid rgba(49, 51, 63, 0.16);
          padding: 3.3rem 1.05rem 2rem 1.05rem !important;
        }}
        div[data-testid="column"]:has(#left-panel-content-anchor) #left-panel-content-anchor,
        div[data-testid="column"]:has(#right-panel-content-anchor) #right-panel-content-anchor {{
          display: none;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor),
        div[data-testid="column"]:has(#right-panel-toggle-anchor) {{
          min-width: 1.75rem !important;
          width: 1.75rem !important;
          max-width: 1.75rem !important;
          flex: 0 0 1.75rem !important;
          padding-left: 0 !important;
          padding-right: 0 !important;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"],
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] {{
          position: fixed;
          top: 0.65rem;
          z-index: 1001;
          width: 1.75rem;
          margin: 0 !important;
          padding: 0 !important;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] {{
          left: {left_toggle_left};
        }}
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] {{
          right: {right_toggle_right};
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] button,
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] button {{
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 1.75rem;
          min-width: 1.75rem;
          height: 1.75rem;
          min-height: 1.75rem;
          padding: 0;
          border: 0;
          border-radius: 0.25rem;
          background: rgba(255, 255, 255, 0.72);
          box-shadow: 0 1px 4px rgba(15, 23, 42, 0.15);
          color: rgba(49, 51, 63, 0.68);
          font-size: 1rem;
          font-weight: 700;
          line-height: 1;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] button:hover,
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] button:hover {{
          background: rgba(255, 255, 255, 0.95);
          color: rgba(49, 51, 63, 0.9);
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] p,
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] p {{
          margin: 0;
          line-height: 1;
        }}
        .workspace-header {{
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 1rem;
          margin: 0.1rem 0 0.45rem 0;
        }}
        .workspace-header h1 {{
          font-size: 1.42rem;
          line-height: 1.15;
          margin: 0;
        }}
        .workspace-title-row {{
          display: flex;
          align-items: center;
          gap: 0.55rem;
          flex-wrap: wrap;
        }}
        .workspace-beta-badge {{
          display: inline-flex;
          align-items: center;
          min-height: 1.35rem;
          padding: 0.16rem 0.45rem;
          border-radius: 0.28rem;
          background: #7f1d1d;
          color: #fff;
          font-size: 0.72rem;
          font-weight: 700;
          letter-spacing: 0;
        }}
        .workspace-beta-note {{
          margin-top: 0.18rem;
          color: rgba(127, 29, 29, 0.88);
          font-size: 0.82rem;
          font-weight: 600;
        }}
        .workspace-eyebrow {{
          color: rgba(49, 51, 63, 0.68);
          font-size: 0.86rem;
          margin-bottom: 0.25rem;
        }}
        .workspace-pill {{
          border: 1px solid rgba(49, 51, 63, 0.16);
          border-radius: 8px;
          padding: 0.45rem 0.65rem;
          background: rgba(255, 255, 255, 0.72);
          color: rgba(49, 51, 63, 0.78);
          font-size: 0.86rem;
          white-space: nowrap;
        }}
        div[data-testid="stIFrame"] {{
          max-width: min(1320px, 100%);
          margin-left: auto !important;
          margin-right: auto !important;
          border: 1px solid rgba(49, 51, 63, 0.18);
          border-radius: 6px;
          overflow: hidden;
          box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
          background: #fff;
        }}
        div[data-testid="stIFrame"] iframe {{
          width: 100% !important;
        }}
        </style>
        """
    st.markdown(panel_css, unsafe_allow_html=True)

    left_col, left_toggle_col, right_toggle_col, right_col = st.columns([1, 0.05, 0.05, 1], gap="small")
    with left_toggle_col:
        st.markdown('<span id="left-panel-toggle-anchor"></span>', unsafe_allow_html=True)
        st.button(
            "<" if left_open else ">",
            key="left_panel_edge_toggle",
            help="Visa/dölj kartlager",
            on_click=_toggle_panel,
            args=(LEFT_PANEL_OPEN_KEY,),
        )
    with right_toggle_col:
        st.markdown('<span id="right-panel-toggle-anchor"></span>', unsafe_allow_html=True)
        st.button(
            ">" if right_open else "<",
            key="right_panel_edge_toggle",
            help=_t("Visa/dölj kontext"),
            on_click=_toggle_panel,
            args=(RIGHT_PANEL_OPEN_KEY,),
        )

    left_panel = None
    right_panel = None
    if left_open:
        with left_col:
            st.markdown('<span id="left-panel-content-anchor"></span>', unsafe_allow_html=True)
            left_panel = st.container()
    if right_open:
        with right_col:
            st.markdown('<span id="right-panel-content-anchor"></span>', unsafe_allow_html=True)
            right_panel = st.container()
    return left_panel, right_panel


def _workspace_shell() -> tuple[Any | None, Any, Any | None]:
    _init_panel_state()
    right_open = bool(st.session_state.get(RIGHT_PANEL_OPEN_KEY, True))
    right_panel_width_pct = _right_panel_width_pct()
    if not right_open:
        main_ratio = 1.0
        right_ratio = 0.035
    elif right_panel_width_pct <= 0.0:
        main_ratio = 1.0
        right_ratio = 0.035
    elif right_panel_width_pct >= 99.5:
        main_ratio = 0.015
        right_ratio = 1.0
    else:
        main_ratio = max(0.015, 100.0 - right_panel_width_pct)
        right_ratio = max(0.035, right_panel_width_pct)
    panel_css = """
        <style>
        div[data-testid="stAppViewContainer"] section.main .block-container,
        div[data-testid="stAppViewContainer"] .main .block-container {
          max-width: none;
          padding: 0.75rem 0.9rem 1rem 0.9rem;
        }
        .workspace-header {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 1rem;
          margin: 0.1rem 0 0.45rem 0;
        }
        .workspace-header h1 {
          font-size: 1.42rem;
          line-height: 1.15;
          margin: 0;
        }
        .workspace-title-row {
          display: flex;
          align-items: center;
          gap: 0.55rem;
          flex-wrap: wrap;
        }
        .workspace-beta-badge {
          display: inline-flex;
          align-items: center;
          min-height: 1.35rem;
          padding: 0.16rem 0.45rem;
          border-radius: 0.28rem;
          background: #7f1d1d;
          color: #fff;
          font-size: 0.72rem;
          font-weight: 700;
          letter-spacing: 0;
        }
        .workspace-beta-note {
          margin-top: 0.18rem;
          color: rgba(127, 29, 29, 0.88);
          font-size: 0.82rem;
          font-weight: 600;
        }
        .workspace-eyebrow {
          color: rgba(49, 51, 63, 0.68);
          font-size: 0.86rem;
          margin-bottom: 0.25rem;
        }
        .workspace-pill {
          border: 1px solid rgba(49, 51, 63, 0.16);
          border-radius: 8px;
          padding: 0.45rem 0.65rem;
          background: rgba(255, 255, 255, 0.72);
          color: rgba(49, 51, 63, 0.78);
          font-size: 0.86rem;
          white-space: nowrap;
        }
        div[data-testid="stIFrame"] {
          max-width: 100%;
          margin-left: auto !important;
          margin-right: auto !important;
          border: 1px solid rgba(49, 51, 63, 0.18);
          border-radius: 6px;
          overflow: hidden;
          box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
          background: #fff;
        }
        div[data-testid="stIFrame"] iframe {
          width: 100% !important;
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor) {
          resize: horizontal;
          overflow: auto;
          border-left: 1px solid rgba(49, 51, 63, 0.14);
          padding-left: 0.75rem !important;
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor)::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          bottom: 0;
          width: 0.55rem;
          cursor: ew-resize;
          background: linear-gradient(90deg, rgba(15, 23, 42, 0.12), rgba(15, 23, 42, 0));
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] {
          width: 1.75rem;
          margin: 0 !important;
          padding: 0 !important;
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 1.75rem;
          min-width: 1.75rem;
          height: 1.75rem;
          min-height: 1.75rem;
          padding: 0;
          border-radius: 0.25rem;
          background: rgba(255, 255, 255, 0.86);
          box-shadow: 0 1px 4px rgba(15, 23, 42, 0.15);
          color: rgba(49, 51, 63, 0.78);
          font-weight: 700;
        }
        div[data-testid="column"]:has(#right-panel-content-anchor) div[data-testid="stDataFrame"],
        div[data-testid="column"]:has(#right-panel-content-anchor) div[data-testid="stTable"] {
          overflow-x: auto;
        }
        div[data-testid="column"]:has(#right-panel-content-anchor) [data-testid="stMetricValue"] {
          font-size: clamp(1.15rem, 1.6vw, 1.75rem);
          line-height: 1.1;
        }
        </style>
        """
    st.markdown(panel_css, unsafe_allow_html=True)

    main_col, right_col = st.columns([main_ratio, right_ratio], gap="medium")
    left_panel = st.sidebar

    right_panel = None
    with right_col:
        st.markdown('<span id="right-panel-toggle-anchor"></span>', unsafe_allow_html=True)
        st.button(
            ">" if right_open else "<",
            key="right_panel_edge_toggle",
            help="Visa/dölj kontext",
            on_click=_toggle_panel,
            args=(RIGHT_PANEL_OPEN_KEY,),
        )
        if right_open and right_panel_width_pct > 0.0:
            right_panel = st.container(border=True)
            with right_panel:
                st.markdown('<span id="right-panel-content-anchor"></span>', unsafe_allow_html=True)

    return left_panel, main_col, right_panel


def _query_param_value(key: str) -> str | None:
    try:
        value = st.query_params.get(key)
    except Exception:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value not in {None, ""} else None


def _set_query_param(key: str, value: str) -> None:
    try:
        st.query_params[key] = value
    except Exception:
        return


def _clear_query_param(key: str) -> None:
    try:
        del st.query_params[key]
    except Exception:
        return


def _region_sort_key(region: dict[str, Any]) -> tuple[int, str]:
    card = region.get("landing_card") or {}
    try:
        order = int(card.get("sort_order", 999))
    except Exception:
        order = 999
    return order, str(region.get("display_name", region.get("region_id", "")))


def _landing_regions() -> list[dict[str, Any]]:
    return sorted(
        [region for region in list_regions() if isinstance(region.get("landing_card"), dict)],
        key=_region_sort_key,
    )


def _region_lookup() -> dict[str, dict[str, Any]]:
    return {str(region.get("region_id", "")).lower(): region for region in _landing_regions()}


def _region_card_enabled(region: dict[str, Any]) -> bool:
    card = region.get("landing_card") or {}
    if "enabled" in card:
        return bool(card.get("enabled"))
    return str(region.get("status", "")).lower() in {"active", "ready", "app_ready"}


def _selected_region_id() -> str | None:
    regions = _region_lookup()
    query_region = _query_param_value("region")
    if query_region and query_region.lower() in regions and _region_card_enabled(regions[query_region.lower()]):
        return str(regions[query_region.lower()].get("region_id"))

    session_region = st.session_state.get(REGION_SELECT_KEY)
    if session_region and str(session_region).lower() in regions and _region_card_enabled(regions[str(session_region).lower()]):
        return str(regions[str(session_region).lower()].get("region_id"))
    return None


def _should_show_region_landing() -> bool:
    if _query_param_value("view") == REGION_LANDING_VIEW:
        return True
    return _selected_region_id() is None


def _reset_session_for_region(region_id: str) -> None:
    for key in [
        WORKSPACE_RENDER_CACHE_KEY,
        "combined_h3_resolution",
        "combined_h3_display_mode",
        "workspace_cache_invalidated_reason",
    ]:
        st.session_state.pop(key, None)
    st.session_state[MAP_VIEW_RESET_TOKEN_KEY] = int(st.session_state.get(MAP_VIEW_RESET_TOKEN_KEY, 0) or 0) + 1


def _select_region(region_id: str) -> None:
    previous = str(st.session_state.get(REGION_SELECT_KEY, "") or "")
    if previous.lower() != str(region_id).lower():
        _reset_session_for_region(str(region_id))
    st.session_state[REGION_SELECT_KEY] = str(region_id)
    _set_query_param("region", str(region_id))
    _clear_query_param("view")
    st.rerun()


def _open_region_landing() -> None:
    _set_query_param("view", REGION_LANDING_VIEW)
    st.rerun()


def _render_region_landing() -> None:
    _render_language_switcher(st.sidebar)
    regions = _landing_regions()
    if not regions:
        st.error(_t("Inga regionmanifest hittades."))
        return

    st.markdown(
        """
        <style>
        .region-landing {
          max-width: 1180px;
          margin: 0 auto;
          padding: 1.5rem 0 2.5rem;
        }
        .region-landing h1 {
          font-size: clamp(2.2rem, 4vw, 4rem);
          line-height: 1.02;
          margin-bottom: 0.6rem;
        }
        .region-landing p {
          max-width: 780px;
          color: rgba(49, 51, 63, 0.78);
          font-size: 1.04rem;
          line-height: 1.55;
        }
        .region-card-meta {
          color: rgba(49, 51, 63, 0.68);
          font-size: 0.88rem;
          line-height: 1.35;
          margin-bottom: 0.45rem;
        }
        </style>
        <div class="region-landing">
          <h1>Sol- och vindpotential</h1>
          <p>
            Välj region för att öppna analysvyn. Regionkorten läses från manifest,
            så nya regioner kan läggas till genom en regionkatalog utan ändringar i den gemensamma appkoden.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for start in range(0, len(regions), 3):
        cols = st.columns(3, gap="medium")
        for col, region in zip(cols, regions[start : start + 3]):
            with col.container(border=True):
                card = region.get("landing_card") or {}
                title = str(card.get("title") or region.get("display_name") or region.get("region_id"))
                subtitle = str(card.get("subtitle") or region.get("country") or "")
                description = str(card.get("description") or region.get("runtime_note") or "")
                badge = str(card.get("badge") or region.get("status") or "")
                enabled = _region_card_enabled(region)
                region_id = str(region.get("region_id"))
                st.subheader(title)
                meta = " · ".join(part for part in [badge, subtitle] if part)
                if meta:
                    st.markdown(f'<div class="region-card-meta">{html.escape(meta)}</div>', unsafe_allow_html=True)
                if description:
                    st.caption(description)
                st.caption(f"CRS: {region.get('native_crs', 'TBD')} · H3: {', '.join(f'R{int(value)}' for value in region.get('available_h3_resolutions') or []) or 'saknas'}")
                if st.button(
                    "Öppna analys",
                    key=f"select_region_{region_id}",
                    disabled=not enabled,
                    width="stretch",
                ):
                    _select_region(region_id)


def _active_region() -> dict[str, Any]:
    region_id = _selected_region_id() or DEFAULT_REGION_ID
    try:
        region = load_region(region_id)
    except Exception as exc:
        if str(region_id).lower() != DEFAULT_REGION_ID:
            st.warning(f"Regionen {region_id} kunde inte laddas, öppnar {DEFAULT_REGION_ID}.")
            region = load_region(DEFAULT_REGION_ID)
        else:
            st.error(f"Regionmanifest kunde inte laddas: {exc}")
            st.stop()
    st.session_state[REGION_SELECT_KEY] = str(region.get("region_id", region_id))
    return region


def _render_region_switcher(region: dict[str, Any]) -> None:
    st.sidebar.caption(f"{_t('Region')}: {region.get('display_name', region.get('region_id'))}")
    if st.sidebar.button("Byt region", key="potential_region_landing_button", width="stretch"):
        _open_region_landing()


def _scenario_sidebar(region: dict[str, Any]) -> dict[str, Any]:
    scenario_manifest = load_linked_manifest(region, "scenario_manifest")
    st.sidebar.divider()
    st.sidebar.header(_t("Scenarier"))

    if scenario_manifest is None:
        st.sidebar.caption({"en": "Scenario manifest is missing for the selected region.", "da_no": "Scenariomanifest mangler for valgt region."}.get(_language(), "Scenariomanifest saknas för vald region."))
        return {"scenario": None, "manifest": None}

    levels = scenario_manifest.get("scenario_levels") or []
    selected = None
    if levels:
        default_level = _highest_option_id(tuple(str(level) for level in levels))
        selected = st.sidebar.radio(
            _t("Scenario"),
            options=levels,
            index=levels.index(default_level) if default_level in levels else 0,
            format_func=lambda value: {"low": "Låg", "medium": "Mellan", "high": "Hög"}.get(value, str(value)),
        )
    st.sidebar.caption(f"Scenario-set: {scenario_manifest.get('scenario_set_id', '-')}")
    st.sidebar.caption(f"{_t('Lager')}: {len(scenario_manifest.get('layers') or [])}")
    if not scenario_manifest.get("layers"):
        st.sidebar.caption("Scenariofiler kopplas in senare.")
    return {"scenario": selected, "manifest": scenario_manifest}


def _scenario_state(region: dict[str, Any], panel: Any | None = None) -> dict[str, Any]:
    scenario_manifest = load_linked_manifest(region, "scenario_manifest")
    if scenario_manifest is None:
        if panel is not None:
            panel.caption({"en": "Scenario manifest is missing for the selected region.", "da_no": "Scenariomanifest mangler for valgt region."}.get(_language(), "Scenariomanifest saknas för vald region."))
        return {"scenario": None, "manifest": None}

    levels = scenario_manifest.get("scenario_levels") or []
    selected = None
    if levels:
        region_id = region.get("region_id", "region")
        scenario_key = f"potential_scenario_{region_id}"
        energy_scenario_key = f"energy_model_planning_scenario_{region_id}"
        default_level = _highest_option_id(tuple(str(level) for level in levels)) or levels[0]
        energy_scenario = st.session_state.get(energy_scenario_key)
        if panel is None and energy_scenario in levels:
            st.session_state[scenario_key] = energy_scenario
        if st.session_state.get(scenario_key) not in levels:
            st.session_state[scenario_key] = default_level
        if panel is None:
            selected = st.session_state.get(scenario_key)
        else:
            selected = panel.radio(
                _t("Scenario"),
                options=levels,
                key=scenario_key,
                format_func=lambda value: {"low": "Låg", "medium": "Mellan", "high": "Hög"}.get(value, str(value)),
            )
    if panel is not None:
        panel.caption(f"Scenario-set: {scenario_manifest.get('scenario_set_id', '-')}")
        panel.caption(f"{_t('Lager')}: {len(scenario_manifest.get('layers') or [])}")
        if not scenario_manifest.get("layers"):
            panel.caption("Scenariofiler kopplas in senare.")
    return {"scenario": selected, "manifest": scenario_manifest}


@st.cache_data(show_spinner=False)
def _cached_energy_inputs(manifest_json: str, root_str: str) -> tuple[pd.DataFrame, dict[str, str], str]:
    manifest = json.loads(manifest_json)
    inputs = load_energy_model_inputs(manifest, Path(root_str))
    return inputs.times_rows, inputs.scenario_descriptions, inputs.source_status


@st.cache_data(show_spinner=False)
def _cached_area_demand(manifest_json: str, root_str: str) -> dict[str, Any]:
    manifest = json.loads(manifest_json)
    bundle = load_area_demand_bundle(manifest, Path(root_str))
    return {
        "factors_by_scenario": bundle.factors_by_scenario,
        "scenario_table": bundle.scenario_table,
        "observation_table": bundle.observation_table,
        "warning_table": bundle.warning_table,
        "local_reference_table": bundle.local_reference_table,
        "references": bundle.references,
        "rules_text": bundle.rules_text,
        "source_path": bundle.source_path,
    }


def _energy_model_manifest_json(scenario_manifest: dict[str, Any] | None) -> str:
    return json.dumps(scenario_manifest or {}, sort_keys=True, ensure_ascii=False)


def _technology_to_times_map(scenario_manifest: dict[str, Any] | None) -> dict[str, str]:
    area_cfg = (((scenario_manifest or {}).get("energy_model") or {}).get("area_demand") or {})
    mapping = area_cfg.get("times_technology_map") or {}
    result: dict[str, str] = {}
    for times_tech, rule in mapping.items():
        energy_key = str((rule or {}).get("energy_key", "")).strip()
        if energy_key:
            result[energy_key] = str(times_tech)
    return result or {"wind": "NRG_WIN", "solar": "NRG_SOL"}


def _area_scenario_label(scenario_id: str) -> str:
    labels = {"low": "Låg", "mid": "Mellan", "high": "Hög"}
    return labels.get(str(scenario_id), AREA_SCENARIO_LABELS.get(str(scenario_id), str(scenario_id)))


def _highest_option_id(option_ids: list[str] | tuple[str, ...]) -> str:
    clean_ids = [str(value) for value in option_ids if str(value)]
    for preferred in ("high", "hog", "hög", "hoj", "høj"):
        if preferred in clean_ids:
            return preferred
    return clean_ids[-1] if clean_ids else ""


def _planning_scenario_option_label(option: dict[str, Any] | None) -> str:
    option = option or {}
    label = planning_scenario_label(option)
    try:
        energy_scale = float(option.get("energy_scale", 1.0) or 1.0)
    except Exception:
        energy_scale = 1.0
    return f"{label} · {energy_scale:g}x energi"


def _energy_key_label(energy_key: str) -> str:
    return {"wind": "Vind", "solar": "Sol"}.get(str(energy_key), str(energy_key))


def _area_intensity_factor_table(scenario_table: pd.DataFrame) -> pd.DataFrame:
    if scenario_table.empty:
        return pd.DataFrame(columns=["Teknik", "Låg", "Mellan", "Hög"])
    rows: list[dict[str, object]] = []
    for energy_key in ("wind", "solar"):
        match = scenario_table[scenario_table["energy_key"].astype(str) == energy_key]
        if match.empty:
            continue
        row = match.iloc[0]
        rows.append(
            {
                "Teknik": _energy_key_label(energy_key),
                "Låg": float(row["low_km2_per_twh"]),
                "Mellan": float(row["mid_km2_per_twh"]),
                "Hög": float(row["high_km2_per_twh"]),
            }
        )
    return pd.DataFrame(rows)


def _area_intensity_cap_notes(scenario_table: pd.DataFrame) -> list[str]:
    if scenario_table.empty or "cap_note" not in scenario_table.columns:
        return []
    notes: list[str] = []
    for _, row in scenario_table.iterrows():
        note = str(row.get("cap_note", "") or "").strip()
        if note:
            notes.append(f"{_energy_key_label(str(row.get('energy_key', '')))}: {note}")
    return notes


def _energy_mix_share(mix: pd.DataFrame, energy_key: str) -> float:
    if mix.empty or "energy_key" not in mix.columns or "value_twh" not in mix.columns:
        return 0.0
    values = pd.to_numeric(
        mix.loc[mix["energy_key"].astype(str) == str(energy_key), "value_twh"],
        errors="coerce",
    ).fillna(0.0)
    return float(values.sum())


def _balance_wind_solar_mix(mix: pd.DataFrame, solar_share_pct: float) -> pd.DataFrame:
    adjusted = mix.copy()
    if adjusted.empty or "energy_key" not in adjusted.columns or "value_twh" not in adjusted.columns:
        return adjusted

    solar_share = max(0.0, min(100.0, float(solar_share_pct))) / 100.0
    wind_twh = _energy_mix_share(adjusted, "wind")
    solar_twh = _energy_mix_share(adjusted, "solar")
    total_twh = wind_twh + solar_twh
    if total_twh <= 0:
        return adjusted

    targets = {"solar": total_twh * solar_share, "wind": total_twh * (1.0 - solar_share)}
    for energy_key, target_twh in targets.items():
        mask = adjusted["energy_key"].astype(str) == energy_key
        current_twh = float(pd.to_numeric(adjusted.loc[mask, "value_twh"], errors="coerce").fillna(0.0).sum())
        if not mask.any():
            new_row = {
                "scenario": adjusted["scenario"].iloc[0] if "scenario" in adjusted.columns and not adjusted.empty else "",
                "year": adjusted["year"].iloc[0] if "year" in adjusted.columns and not adjusted.empty else "",
                "energy_key": energy_key,
                "value_twh": target_twh,
            }
            adjusted = pd.concat([adjusted, pd.DataFrame([new_row])], ignore_index=True, sort=False)
        elif current_twh > 0:
            adjusted.loc[mask, "value_twh"] = pd.to_numeric(adjusted.loc[mask, "value_twh"], errors="coerce").fillna(0.0) * (target_twh / current_twh)
        else:
            first_idx = adjusted.index[mask][0]
            adjusted.loc[mask, "value_twh"] = 0.0
            adjusted.loc[first_idx, "value_twh"] = target_twh
    return adjusted.reset_index(drop=True)


def _energy_mix_state_key(region: dict[str, Any]) -> str:
    return f"energy_model_mix_solar_share_{region.get('region_id', 'region')}"


def _energy_mix_solar_share_from_session(region: dict[str, Any]) -> tuple[str, float]:
    mix_key = _energy_mix_state_key(region)
    mix_default_key = f"{mix_key}_default_50_applied"
    if not bool(st.session_state.get(mix_default_key, False)):
        st.session_state[mix_key] = 50
        st.session_state[mix_default_key] = True
    st.session_state.setdefault(mix_key, 50)
    try:
        solar_share_pct = float(st.session_state.get(mix_key, 50) or 0.0)
    except Exception:
        solar_share_pct = 50.0
    return mix_key, max(0.0, min(100.0, solar_share_pct))


def _render_energy_mix_card(panel: Any, region: dict[str, Any], energy_model_state: dict[str, Any]) -> None:
    if not isinstance(energy_model_state, dict) or not energy_model_state.get("available"):
        return
    mix_key = str(energy_model_state.get("mix_key") or _energy_mix_state_key(region))
    try:
        current_solar_share_pct = float(st.session_state.get(mix_key, energy_model_state.get("solar_share_pct", 50)) or 0.0)
    except Exception:
        current_solar_share_pct = 50.0
    current_solar_share_pct = max(0.0, min(100.0, current_solar_share_pct))
    wind_share_pct = 100.0 - current_solar_share_pct
    native_total_twh = float(energy_model_state.get("native_total_twh", 0.0) or 0.0)
    native_solar_share_pct = float(energy_model_state.get("native_solar_share_pct", 50.0) or 0.0)

    panel.markdown('<span data-potential-tutorial-anchor="energy-mix"></span>', unsafe_allow_html=True)
    with panel.container(border=True):
        st.markdown("**Energimix**")
        st.caption(
            "Pröva hur samma energimängd fördelas mellan vind och sol. Kartan och resultatpanelen räknas om när reglaget ändras."
        )
        slider_value = float(
            st.slider(
                _t("Energimix"),
                min_value=0,
                max_value=100,
                step=5,
                key=mix_key,
                format="%d%% sol",
                help=(
                    "Balans mellan sol och vind i valt framtidsscenario. "
                    "När solandelen ökar minskar vindandelen med samma totalenergi, och tvärtom."
                ),
            )
        )
        wind_share_pct = 100.0 - slider_value
        mix_cols = st.columns(3)
        mix_cols[0].metric(_t("Vindandel"), f"{wind_share_pct:.0f}%")
        mix_cols[1].metric(_t("Solandel"), f"{slider_value:.0f}%")
        mix_cols[2].metric(_t("Total energi"), f"{native_total_twh:.2f} TWh")
        st.caption(
            f"Energimix: {wind_share_pct:.0f}% vind / {slider_value:.0f}% sol. "
            f"Ursprunglig TIMES-mix: {100.0 - native_solar_share_pct:.0f}% vind / {native_solar_share_pct:.0f}% sol."
        )


def _render_hex_area_card(
    area_by_scenario: dict[str, float],
    hex_area: float,
    selected_scenario: str,
    scenario_order: list[str] | tuple[str, ...] | None = None,
    label_func: Any | None = None,
) -> None:
    scenario_order = list(scenario_order or AREA_SCENARIO_ORDER)
    label_func = label_func or _area_scenario_label
    max_area = max([0.0, *[float(value or 0.0) for value in area_by_scenario.values()]])
    max_hex = max(1, int(math.ceil(max_area / max(hex_area, 1e-9))))
    symbol_scale = max(1, int(math.ceil(max_hex / 54)))
    rows: list[str] = []
    for scenario_id in scenario_order:
        area = float(area_by_scenario.get(scenario_id, 0.0) or 0.0)
        needed_hex = int(math.ceil(area / max(hex_area, 1e-9))) if area > 0 else 0
        symbols = max(1, int(math.ceil(needed_hex / symbol_scale))) if needed_hex else 0
        active = scenario_id == selected_scenario
        color = "#1f7a3f" if active else "#9ca3af"
        bg = "rgba(31,122,63,0.08)" if active else "rgba(255,255,255,0.55)"
        hexes = "".join(
            f"<span style='display:inline-block;width:0.58rem;height:0.52rem;margin:0.035rem;background:{color};clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);'></span>"
            for _ in range(min(symbols, 54))
        )
        if symbols > 54:
            hexes += "<span style='font-size:0.72rem;color:#6b7280;margin-left:0.2rem;'>+</span>"
        rows.append(
            "<div style='padding:0.45rem 0.5rem;border:1px solid rgba(49,51,63,0.14);"
            f"background:{bg};border-radius:6px;margin:0.32rem 0;'>"
            f"<div style='display:flex;justify-content:space-between;gap:0.5rem;font-size:0.82rem;font-weight:650;'>"
            f"<span>{label_func(scenario_id)}</span><span>{area:.2f} km²</span></div>"
            f"<div style='font-size:0.75rem;color:#6b7280;margin:0.1rem 0 0.25rem;'>~{needed_hex} hex</div>"
            f"<div style='line-height:0.55rem;'>{hexes}</div>"
            "</div>"
        )
    st.markdown(
        "<div style='font-size:0.82rem;font-weight:650;margin-bottom:0.25rem;'>Ytbehov som hex</div>"
        + "".join(rows)
        + f"<div style='font-size:0.74rem;color:#6b7280;margin-top:0.3rem;'>1 symbol ≈ {symbol_scale} hex i vald H3-upplösning.</div>",
        unsafe_allow_html=True,
    )


def _render_energy_modeling_panel(
    region: dict[str, Any],
    scenario_state: dict[str, Any],
    h3_resolution: int,
    panel: Any,
) -> dict[str, Any]:
    scenario_manifest = scenario_state.get("manifest")
    if not scenario_manifest or not (scenario_manifest.get("energy_model") or {}):
        with panel.expander("Scenarier", expanded=False):
            return _scenario_state(region, st) | {"available": False}

    manifest_json = _energy_model_manifest_json(scenario_manifest)
    state: dict[str, Any] = {"available": False, "manifest": scenario_manifest}
    try:
        times_rows, scenario_descriptions, source_status = _cached_energy_inputs(manifest_json, str(ROOT))
        area_payload = _cached_area_demand(manifest_json, str(ROOT))
    except Exception as exc:
        panel.warning(f"Energimodellering kunde inte laddas: {exc}")
        panel.caption("Kontrollera DuckDB/AreaDemand-sökvägar, schema i manifestet och Pythonpaketen duckdb/openpyxl.")
        return state

    scenario_totals, mix = build_times_summary(times_rows)
    if not scenario_totals:
        panel.warning("DuckDB gav inga konfigurerade vind-/solrader.")
        return state

    planning_options = planning_scenarios(scenario_manifest)
    planning_by_id = {str(option.get("id")): option for option in planning_options if option.get("id")}
    planning_ids = [str(option.get("id")) for option in planning_options if option.get("id")]
    if not planning_ids:
        panel.warning("Manifestet saknar planeringsscenarier.")
        return state

    planning_cfg = ((scenario_manifest.get("energy_model") or {}).get("planning") or {})
    region_id = region.get("region_id", "region")
    scenario_key = f"energy_model_planning_scenario_{region_id}"
    potential_scenario_key = f"potential_scenario_{region_id}"
    default_planning_id = str(
        st.session_state.get(scenario_key)
        or st.session_state.get(potential_scenario_key)
        or scenario_state.get("scenario")
        or _highest_option_id(tuple(planning_ids))
        or planning_cfg.get("default_scenario")
        or "medium"
    )
    if default_planning_id not in planning_by_id:
        default_planning_id = _highest_option_id(tuple(planning_ids)) or planning_ids[0]
    if st.session_state.get(scenario_key) not in planning_ids:
        st.session_state[scenario_key] = default_planning_id
    planning_id = panel.selectbox(
        {"en": "Energy scenario", "da_no": "Energiscenario"}.get(_language(), "Energiscenario"),
        options=planning_ids,
        key=scenario_key,
        format_func=lambda value: _planning_scenario_option_label(planning_by_id.get(str(value), {"id": value})),
    )
    scenario_levels = scenario_manifest.get("scenario_levels") or []
    if str(planning_id) in scenario_levels:
        st.session_state[potential_scenario_key] = str(planning_id)
    selected_planning = planning_by_id[str(planning_id)]
    selected_planning_label = planning_scenario_label(selected_planning)
    source_scenario = str(selected_planning.get("source_scenario", "")).strip()
    planning_year = int(selected_planning.get("planning_year", planning_cfg.get("planning_year", 2050)) or 2050)
    energy_scale = float(selected_planning.get("energy_scale", 1.0) or 1.0)
    area_scenario_key = f"energy_model_area_scenario_{region_id}"
    default_area_scenario_id = _highest_option_id(tuple(AREA_SCENARIO_ORDER)) or str(selected_planning.get("area_demand_scenario", "mid") or "mid")
    if default_area_scenario_id not in AREA_SCENARIO_ORDER:
        default_area_scenario_id = "mid"
    if st.session_state.get(area_scenario_key) not in AREA_SCENARIO_ORDER:
        st.session_state[area_scenario_key] = default_area_scenario_id
    area_scenario_id = str(
        panel.selectbox(
            {"en": "Land intensity", "da_no": "Arealintensitet"}.get(_language(), "Markintensitet"),
            options=list(AREA_SCENARIO_ORDER),
            key=area_scenario_key,
            format_func=_area_scenario_label,
        )
    )
    source_label = scenario_display_label(source_scenario, scenario_descriptions) if source_scenario else "-"
    scenario_table = pd.DataFrame(area_payload.get("scenario_table", pd.DataFrame()))
    intensity_table = _area_intensity_factor_table(scenario_table)
    if not intensity_table.empty:
        panel.dataframe(intensity_table.round(2), width="stretch", hide_index=True, height=108)
        panel.caption("Markintensitet i km²/TWh. Värdena bygger på AreaDemand och manifeststyrda caps.")

    panel.caption(
        "Dummy/prototypdata: energiscenario styr TWh och energiskala. "
        "Markintensitet styr ytbehov i km²/TWh oberoende av energiscenariot."
    )
    panel.caption(
        f"Valt: {_planning_scenario_option_label(selected_planning)} · markintensitet {_area_scenario_label(area_scenario_id)} · "
        f"modellkälla: {source_label}, {planning_year}"
    )

    st.session_state.pop(f"energy_model_placement_{region.get('region_id', 'region')}", None)
    placement_mode = "auto"

    selected_mix = select_planning_mix(mix, selected_planning)
    if selected_mix.empty:
        panel.warning(
            f"Planeringsscenariot pekar på {source_scenario or '-'} {planning_year}, men de raderna finns inte i DuckDB."
        )
        return state

    native_wind_twh = _energy_mix_share(selected_mix, "wind")
    native_solar_twh = _energy_mix_share(selected_mix, "solar")
    native_total_twh = native_wind_twh + native_solar_twh
    native_solar_share_pct = (native_solar_twh / native_total_twh * 100.0) if native_total_twh > 0 else 50.0
    mix_key, solar_share_pct = _energy_mix_solar_share_from_session(region)
    wind_share_pct = 100.0 - solar_share_pct
    selected_mix = _balance_wind_solar_mix(selected_mix, solar_share_pct)

    technology_to_times = _technology_to_times_map(scenario_manifest)
    area_bundle_obj = type(
        "AreaBundleShim",
        (),
        {"factors_by_scenario": area_payload["factors_by_scenario"]},
    )()
    area_demand = calculate_area_demand(selected_mix, area_bundle_obj, str(area_scenario_id), technology_to_times)
    area_demand["Teknik"] = area_demand["energy_key"].map(_energy_key_label)
    hex_area = h3_hex_area_km2(int(h3_resolution))

    planning = ((scenario_manifest.get("energy_model") or {}).get("planning") or {})
    primary_technology = str(planning.get("primary_technology", "wind"))
    primary_row = area_demand[area_demand["energy_key"].astype(str) == primary_technology]
    primary_area_need = float(primary_row["area_need_km2"].fillna(0.0).sum()) if not primary_row.empty else 0.0
    primary_twh = float(primary_row["twh"].fillna(0.0).sum()) if not primary_row.empty else 0.0
    primary_factor = float(primary_row["km2_per_twh"].dropna().iloc[0]) if not primary_row["km2_per_twh"].dropna().empty else math.nan
    solar_row = area_demand[area_demand["energy_key"].astype(str) == "solar"]
    wind_row = area_demand[area_demand["energy_key"].astype(str) == "wind"]
    solar_area_need = float(solar_row["area_need_km2"].fillna(0.0).sum()) if not solar_row.empty else 0.0
    solar_twh = float(solar_row["twh"].fillna(0.0).sum()) if not solar_row.empty else 0.0
    solar_factor = float(solar_row["km2_per_twh"].dropna().iloc[0]) if not solar_row.empty and not solar_row["km2_per_twh"].dropna().empty else math.nan
    wind_area_need = float(wind_row["area_need_km2"].fillna(0.0).sum()) if not wind_row.empty else 0.0
    wind_twh = float(wind_row["twh"].fillna(0.0).sum()) if not wind_row.empty else 0.0
    wind_factor = float(wind_row["km2_per_twh"].dropna().iloc[0]) if not wind_row.empty and not wind_row["km2_per_twh"].dropna().empty else math.nan

    panel.caption(
        "Ytbehovet beräknas från valt energiscenario och vald markintensitet. "
        "De fulla siffrorna visas i högerpanelens tabeller och under Beräkning och datakvalitet."
    )

    show_key = f"energy_model_show_proposal_{region.get('region_id', 'region')}"
    show_proposal = panel.checkbox(_t("Visa föreslagen etableringsyta"), value=True, key=show_key)

    with panel.expander(_t("Beräkning och datakvalitet"), expanded=False):
        calc_df = area_demand[["Teknik", "twh", "km2_per_twh", "area_need_km2"]].rename(
            columns={"twh": "TWh", "km2_per_twh": "km²/TWh", "area_need_km2": "km²"}
        )
        st.dataframe(calc_df.round(3), width="stretch", hide_index=True)
        st.caption(source_status)
        st.caption(f"AreaDemand: {area_payload.get('source_path', '-')}")
        local_reference_table = pd.DataFrame(area_payload.get("local_reference_table", pd.DataFrame()))
        if not local_reference_table.empty:
            st.caption(
                "Nedre Bornholm-sektionen i AreaDemand.xlsx läses som lokal referens. "
                "Den visas för transparens men styr inte scenarierna förrän manifestet väljer den som faktor."
            )
            st.dataframe(local_reference_table.round(4), width="stretch", hide_index=True, height=180)
        warning_table = pd.DataFrame(area_payload.get("warning_table", pd.DataFrame()))
        if not warning_table.empty:
            st.warning("AreaDemand innehåller datakvalitetsvarningar eller manifeststyrda caps.")
            st.dataframe(warning_table, width="stretch", hide_index=True, height=180)
        if not scenario_table.empty:
            cap_notes = _area_intensity_cap_notes(scenario_table)
            if cap_notes:
                st.info("Manifeststyrda caps: " + " · ".join(cap_notes))
            st.dataframe(scenario_table.round(3), width="stretch", hide_index=True)

    debug_payload = {
        "scenario": str(planning_id),
        "source_scenario": source_scenario,
        "source_year": int(planning_year),
        "energy_scale": round(float(energy_scale), 6),
        "area_scenario_id": str(area_scenario_id),
        "wind_share_pct": round(float(wind_share_pct), 3),
        "solar_share_pct": round(float(solar_share_pct), 3),
        "wind_area_need_km2": round(float(wind_area_need), 6),
        "solar_area_need_km2": round(float(solar_area_need), 6),
        "wind_twh": round(float(wind_twh), 6),
        "solar_twh": round(float(solar_twh), 6),
    }
    state.update(
        {
            "available": True,
            "debug_run_id": _short_hash(debug_payload),
            "debug_payload": debug_payload,
            "scenario": str(planning_id),
            "scenario_label": selected_planning_label,
            "source_scenario": source_scenario,
            "source_scenario_label": source_label,
            "source_year": int(planning_year),
            "energy_scale": energy_scale,
            "area_scenario_id": str(area_scenario_id),
            "area_scenario_label": _area_scenario_label(str(area_scenario_id)),
            "placement_mode": str(placement_mode),
            "show_proposal": bool(show_proposal),
            "area_demand": area_demand,
            "primary_technology": primary_technology,
            "primary_area_need_km2": primary_area_need,
            "primary_twh": primary_twh,
            "primary_km2_per_twh": primary_factor,
            "wind_share_pct": wind_share_pct,
            "solar_share_pct": solar_share_pct,
            "mix_key": mix_key,
            "native_total_twh": native_total_twh,
            "native_wind_share_pct": 100.0 - native_solar_share_pct,
            "native_solar_share_pct": native_solar_share_pct,
            "wind_area_need_km2": wind_area_need,
            "wind_km2_per_twh": wind_factor,
            "solar_area_need_km2": solar_area_need,
            "solar_km2_per_twh": solar_factor,
            "wind_twh": wind_twh,
            "solar_twh": solar_twh,
            "hex_area_km2": hex_area,
            "h3_resolution": int(h3_resolution),
            "auto_min_potential_share_pct": float(planning.get("auto_min_potential_share_pct", 65.0)),
            "source_status": source_status,
            "area_warnings": pd.DataFrame(area_payload.get("warning_table", pd.DataFrame())),
        }
    )
    return state


def _render_region_scenario_panel(panel: Any | None) -> tuple[dict[str, Any], dict[str, Any]]:
    region = _active_region()
    if panel is None:
        return region, _scenario_state(region, None)

    with panel.expander(_t("Scenarier"), expanded=False):
        scenario_state = _scenario_state(region, st)
    return region, scenario_state


def _metric_header(region: dict[str, Any], scenario_state: dict[str, Any], h3_resolution: int | None = None) -> None:
    st.title(f"{_t(PAGE_TITLE)} · {APP_RELEASE_STAGE}")
    st.caption(
        {
            "en": f"{APP_RELEASE_STAGE}: development version, not a finished product. Regional v0 for scenarios, {_t(SOLAR_LANDSCAPE_POTENTIAL_LABEL)}, {_t(WIND_LANDSCAPE_POTENTIAL_LABEL)} and landscape analysis.",
            "da_no": f"{APP_RELEASE_STAGE}: udviklingsversion, ikke et færdigt produkt. Regional v0 for scenarier, {_t(SOLAR_LANDSCAPE_POTENTIAL_LABEL)}, {_t(WIND_LANDSCAPE_POTENTIAL_LABEL)} og landskabsanalyse.",
        }.get(_language(), f"{APP_RELEASE_STAGE}: {APP_RELEASE_NOTE}. Regional v0 för scenarier, {SOLAR_LANDSCAPE_POTENTIAL_LABEL}, {WIND_LANDSCAPE_POTENTIAL_LABEL} och landskapsanalys.")
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(_t("Region"), str(region.get("display_name", region.get("region_id"))))
    c2.metric(_t("Scenario"), str(scenario_state.get("scenario") or "-"))
    c3.metric({"en": "Nominal scale", "da_no": "Nominel skala"}.get(_language(), "Nominell skala"), str(region.get("nominal_scale", "TBD")))
    c4.metric("CRS", str(region.get("native_crs", "TBD")))
    shown_resolution = h3_resolution or region.get("default_h3_resolution")
    c5.metric("H3", "TBD" if shown_resolution in {None, ""} else f"R{shown_resolution}")


def _workspace_header(region: dict[str, Any], scenario_state: dict[str, Any], h3_resolution: int | None = None) -> None:
    shown_resolution = h3_resolution or region.get("default_h3_resolution")
    h3_label = "TBD" if shown_resolution in {None, ""} else f"R{shown_resolution}"
    region_label = str(region.get("display_name", region.get("region_id")))
    scenario_label = str(scenario_state.get("scenario") or "-")
    st.markdown(
        f"""
        <div class="workspace-header" data-potential-tutorial-anchor="workspace-header">
          <div>
            <div class="workspace-eyebrow">{region_label} · scenario {scenario_label} · H3 {h3_label}</div>
            <div class="workspace-title-row">
              <h1>{_t(PAGE_TITLE)}</h1>
              <span class="workspace-beta-badge">{APP_RELEASE_STAGE}</span>
            </div>
            <div class="workspace-beta-note">{APP_RELEASE_NOTE}</div>
          </div>
          <div class="workspace-pill">CRS: {region.get("native_crs", "TBD")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _load_context(region: dict[str, Any]) -> dict[str, Any]:
    return load_region_context(region)


def _social_acceptance_manifest(region: dict[str, Any]) -> dict[str, Any] | None:
    manifest = load_linked_manifest(region, "social_acceptance_manifest")
    if manifest is not None:
        return manifest
    if str(region.get("region_id", "") or "").lower() != "trondelag":
        return None
    fallback_path = resolve_repo_path(
        "apps/potential_model/manifests/social_acceptance/trondelag_synthetic_acceptance_v0.json"
    )
    if fallback_path is None or not fallback_path.exists():
        return None
    manifest = read_manifest(str(fallback_path)).copy()
    manifest["_manifest_path"] = str(fallback_path)
    return manifest


def _social_acceptance_state_key(region: dict[str, Any]) -> str:
    return f"social_acceptance_scenario_{region.get('region_id', 'region')}"


def _social_acceptance_impact_state_key(region: dict[str, Any]) -> str:
    return f"social_acceptance_impact_pct_{region.get('region_id', 'region')}"


def _social_acceptance_allocation_priority_state_key(region: dict[str, Any]) -> str:
    return f"social_acceptance_allocation_priority_pct_{region.get('region_id', 'region')}"


def _social_acceptance_impact_pct(region: dict[str, Any]) -> float:
    try:
        value = float(st.session_state.get(_social_acceptance_impact_state_key(region), 0.0) or 0.0)
    except Exception:
        value = 0.0
    value = int(round(max(0.0, min(100.0, value))))
    st.session_state[_social_acceptance_impact_state_key(region)] = value
    return float(value)


def _social_acceptance_allocation_priority_pct(region: dict[str, Any]) -> float:
    try:
        value = float(st.session_state.get(_social_acceptance_allocation_priority_state_key(region), 0.0) or 0.0)
    except Exception:
        value = 0.0
    value = int(round(max(0.0, min(100.0, value))))
    st.session_state[_social_acceptance_allocation_priority_state_key(region)] = value
    return float(value)


def _social_acceptance_scenario(region: dict[str, Any], manifest: dict[str, Any] | None) -> str:
    options = [scenario["id"] for scenario in social_acceptance_scenarios(manifest)]
    default = SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID if SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID in options else options[0]
    state_key = _social_acceptance_state_key(region)
    if st.session_state.get(state_key) not in options:
        st.session_state[state_key] = default
    return str(st.session_state.get(state_key))


def _available_h3_resolutions(region: dict[str, Any]) -> list[int]:
    return region_available_h3_resolutions(region)


def _preferred_h3_resolution(region: dict[str, Any], preferred: int = 10) -> int:
    available = _available_h3_resolutions(region)
    return int(preferred) if int(preferred) in available else int(available[0])


def _coerce_h3_resolution_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        text = str(value).strip().upper()
        if text.startswith("R"):
            text = text[1:].strip()
        try:
            return int(text)
        except Exception:
            return None


def _session_h3_resolution(region: dict[str, Any], state_key: str, preferred_hint: int) -> int:
    preferred = _preferred_h3_resolution(region, preferred_hint)
    available = _available_h3_resolutions(region)
    value = _coerce_h3_resolution_value(st.session_state.get(state_key, preferred))
    if value in available:
        if st.session_state.get(state_key) != value:
            st.session_state[state_key] = value
        return int(value)
    st.session_state[state_key] = int(preferred)
    return int(preferred)


def _analysis_h3_resolution(region: dict[str, Any], preferred: int | None = None) -> int:
    available = _available_h3_resolutions(region)
    try:
        default_resolution = int(region.get("default_h3_resolution") or 9)
    except Exception:
        default_resolution = 9
    if default_resolution in available:
        return int(default_resolution)
    if preferred is not None and int(preferred) in available:
        return int(preferred)
    return _preferred_h3_resolution(region, default_resolution)


def _h3_display_geometry_path(region: dict[str, Any], resolution: int) -> str | None:
    geometry_paths = region.get("h3_display_geometries") or {}
    path_value = geometry_paths.get(str(resolution))
    path = resolve_repo_path(path_value) if path_value else None
    if path is None or not path.exists():
        return None
    return str(path)


@st.cache_data(show_spinner=False)
def _h3_display_hex_ids(display_geometry_path: str) -> frozenset[str]:
    return frozenset(load_h3_display_geometries(display_geometry_path))


def _h3_option_label(region: dict[str, Any], resolution: int) -> str:
    counts = region.get("h3_display_geometry_counts") or {}
    count_value = counts.get(str(resolution)) if isinstance(counts, dict) else None
    if count_value is not None:
        try:
            count_int = int(count_value)
            return f"R{resolution} ({count_int} landceller)"
        except Exception:
            return f"R{resolution} ({count_value} landceller)"
    return f"R{resolution}"


def _opacity_key(key_prefix: str) -> str:
    return f"{key_prefix}_vector_opacity"


def _current_opacity(key_prefix: str) -> float:
    try:
        opacity = float(st.session_state.get(_opacity_key(key_prefix), 0.78))
    except Exception:
        opacity = 0.78
    return max(0.1, min(0.9, opacity))


def _hex_opacity_key(key_prefix: str, opacity_key: str) -> str:
    safe_key = "".join(ch if ch.isalnum() else "_" for ch in str(opacity_key))
    return f"{key_prefix}_hex_opacity_{safe_key}"


def _hex_opacity_value(key_prefix: str, opacity_key: str, default: float = 0.78) -> float:
    try:
        opacity = float(st.session_state.get(_hex_opacity_key(key_prefix, opacity_key), default))
    except Exception:
        opacity = default
    return max(0.1, min(0.9, opacity))


def _render_opacity_control(key_prefix: str) -> None:
    st.session_state[_opacity_key(key_prefix)] = _current_opacity(key_prefix)
    control_left, control_center, control_right = st.columns([0.22, 0.56, 0.22], gap="small")
    with control_center:
        st.slider(
            "Opacitet polygoner och linjer",
            min_value=0.1,
            max_value=0.9,
            step=0.05,
            key=_opacity_key(key_prefix),
            help="0.1 är nästan genomskinligt. 0.9 är nästan helt fyllt.",
            on_change=_request_ui_only_rerun,
            args=("opacitet",),
        )


def _hex_opacity_controls(layers: list[dict[str, Any]], key_prefix: str) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for layer in layers:
        if str(layer.get("layer_kind", "")) != "hex":
            continue
        if layer.get("default_visible") is False:
            continue
        family_key = str(layer.get("opacity_family") or layer.get("control_name") or layer.get("name"))
        if family_key in families:
            continue
        families[family_key] = {
            "key": family_key,
            "label": str(layer.get("opacity_label") or layer.get("control_name") or layer.get("name")),
            "default": float(layer.get("fill_opacity", 0.78) or 0.78),
        }

    if not families:
        return []

    st.caption("Opacitet hexlager")
    for family in families.values():
        control_key = _hex_opacity_key(key_prefix, family["key"])
        st.session_state[control_key] = _hex_opacity_value(key_prefix, family["key"], family["default"])
        st.slider(
            family["label"],
            min_value=0.1,
            max_value=0.9,
            step=0.05,
            key=control_key,
            help=f"Styr opaciteten för hexlagret {family['label']}. 0.1 är nästan genomskinligt, 0.9 nästan helt fyllt.",
            on_change=_request_ui_only_rerun,
            args=("hexopacitet",),
        )
    return list(families.values())


def _apply_layer_opacity_state(layers: list[dict[str, Any]], key_prefix: str) -> list[dict[str, Any]]:
    adjusted_layers: list[dict[str, Any]] = []
    for layer in layers:
        spec = dict(layer)
        if str(spec.get("layer_kind", "")) == "hex":
            family_key = str(spec.get("opacity_family") or spec.get("control_name") or spec.get("name"))
            spec["fill_opacity"] = _hex_opacity_value(key_prefix, family_key, float(spec.get("fill_opacity", 0.78) or 0.78))
            if str(spec.get("fill_opacity_property", "")) == "fill_opacity":
                spec.pop("fill_opacity_property", None)
        adjusted_layers.append(spec)
    return adjusted_layers


def _layer_control_rows(layers: list[dict[str, Any]], key_prefix: str) -> list[dict[str, Any]]:
    rows_by_control: dict[str, dict[str, Any]] = {}
    for layer in layers:
        control_name = str(layer.get("control_name") or layer.get("name") or "Lager")
        kind = str(layer.get("layer_kind") or "lager")
        resolution = layer.get("auto_resolution")
        row = rows_by_control.setdefault(
            control_name,
            {
                "lager": control_name,
                "typ": "Hex" if kind == "hex" else "Polygon/linje" if kind == "vector" else kind.title(),
                "visning": "",
                "opacitet": "",
            },
        )
        if kind == "hex":
            family_key = str(layer.get("opacity_family") or control_name)
            row["opacitet"] = f"{_hex_opacity_value(key_prefix, family_key, float(layer.get('fill_opacity', 0.78) or 0.78)):.2f}"
        elif not row["opacitet"]:
            row["opacitet"] = f"{_current_opacity(key_prefix):.2f}"
        if resolution is not None:
            values = str(row["visning"]).split(", ") if row["visning"] else []
            label = f"R{int(resolution)}"
            if label not in values:
                values.append(label)
            row["visning"] = ", ".join(values)
        elif not row["visning"]:
            row["visning"] = "Direkt"
    return list(rows_by_control.values())


def _count_enabled(*values: bool) -> int:
    return sum(1 for value in values if bool(value))


def _perf_start() -> float:
    return time.perf_counter()


def _add_perf_timing(performance_log: list[dict[str, Any]], step: str, started_at: float, detail: str = "") -> None:
    performance_log.append(
        {
            "steg": step,
            "tid_s": round(max(0.0, time.perf_counter() - float(started_at)), 3),
            "detalj": detail,
        }
    )


def _calculation_progress_steps(
    show_user_solar: bool,
    show_solar_v1: bool,
    show_user_wind: bool,
    energy_model_state: dict[str, Any],
    show_landscape_layers: bool,
    show_social_acceptance: bool = False,
) -> list[str]:
    steps: list[str] = []
    if show_user_solar:
        steps.append("Sol storskalig")
    if show_solar_v1:
        steps.append("Sol småskalig")
    if show_user_solar or show_solar_v1:
        steps.append("Sol samlad etablering")
    if show_user_wind:
        steps.append("Vindpotential och vindetablering")
    if (
        energy_model_state.get("available")
        and energy_model_state.get("show_proposal")
        and energy_model_state.get("placement_mode") == "auto"
    ):
        steps.append("Gemensam etableringsyta")
        steps.append("Etableringsstatistik")
    if show_landscape_layers:
        steps.append("Landskapslager")
    if show_social_acceptance:
        steps.append("Social acceptans")
    steps.append("Karta HTML och rendering")
    return steps


def _median_seconds(values: list[float]) -> float | None:
    clean = sorted(float(value) for value in values if float(value) > 0)
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return float(clean[midpoint])
    return float((clean[midpoint - 1] + clean[midpoint]) / 2.0)


def _performance_history_bucket(region: dict[str, Any], h3_resolution: int, zoom_family_enabled: bool) -> str:
    mode = "zoom" if bool(zoom_family_enabled) else "fast"
    return f"{region.get('region_id', 'region')}:R{int(h3_resolution)}:{mode}"


def _performance_step_estimates(bucket: str, steps: list[str]) -> dict[str, float]:
    history = st.session_state.get(PERFORMANCE_HISTORY_KEY)
    if not isinstance(history, dict):
        return {}
    estimates: dict[str, float] = {}
    global_history = history.get("global") if isinstance(history.get("global"), dict) else {}
    bucket_history = history.get(bucket) if isinstance(history.get(bucket), dict) else {}
    for step in steps:
        specific_values = bucket_history.get(step) if isinstance(bucket_history, dict) else None
        global_values = global_history.get(step) if isinstance(global_history, dict) else None
        median = _median_seconds([float(value) for value in specific_values]) if isinstance(specific_values, list) else None
        if median is None and isinstance(global_values, list):
            median = _median_seconds([float(value) for value in global_values])
        if median is not None:
            estimates[step] = median
    return estimates


def _record_performance_history(bucket: str, performance_log: list[dict[str, Any]]) -> None:
    if not performance_log:
        return
    history = st.session_state.get(PERFORMANCE_HISTORY_KEY)
    if not isinstance(history, dict):
        history = {}
    for scope in ("global", bucket):
        scope_history = history.setdefault(scope, {})
        if not isinstance(scope_history, dict):
            scope_history = {}
            history[scope] = scope_history
        for row in performance_log:
            step = str(row.get("steg", ""))
            if not step:
                continue
            try:
                seconds = float(row.get("tid_s", 0.0) or 0.0)
            except Exception:
                continue
            if seconds <= 0:
                continue
            values = scope_history.setdefault(step, [])
            if not isinstance(values, list):
                values = []
                scope_history[step] = values
            values.append(round(seconds, 3))
            del values[:-12]
    st.session_state[PERFORMANCE_HISTORY_KEY] = history


def _estimated_remaining_text(steps: list[str], completed: set[str], estimates: dict[str, float]) -> str:
    remaining = [step for step in steps if step not in completed]
    estimated_remaining = sum(float(estimates.get(step, 0.0) or 0.0) for step in remaining)
    known_count = sum(1 for step in remaining if step in estimates)
    if known_count <= 0:
        return "Ingen historik ännu; mäter denna körning."
    suffix = "" if known_count == len(remaining) else " plus omätta steg"
    return f"Beräknad kvarvarande tid: ca {estimated_remaining:.1f} s{suffix}."


def _start_calculation_progress(steps: list[str], estimates: dict[str, float] | None = None) -> dict[str, Any] | None:
    if not steps:
        return None
    estimates = estimates or {}
    estimated_total = sum(float(estimates.get(step, 0.0) or 0.0) for step in steps)
    estimate_text = (
        f"Historik: brukar ta ca {estimated_total:.1f} s för kända steg."
        if estimated_total > 0
        else "Ingen historik ännu; mäter denna körning."
    )
    status = st.status("Beräknar karta och potential...", expanded=False)
    with status:
        progress_bar = st.progress(0, text=f"0/{len(steps)} steg klara. {estimate_text}")
        st.caption("Progressen uppdateras först när ett faktiskt beräkningsblock är färdigt. Kvarvarande tid bygger bara på tidigare uppmätta körningar.")
    return {
        "status": status,
        "bar": progress_bar,
        "steps": list(steps),
        "estimates": dict(estimates),
        "completed": set(),
        "started_at": time.perf_counter(),
    }


def _safe_status_update(status: Any, **kwargs: Any) -> None:
    update = getattr(status, "update", None)
    if not callable(update):
        return
    try:
        update(**kwargs)
    except Exception:
        return


def _advance_calculation_progress(progress: dict[str, Any] | None, step: str) -> None:
    if not progress:
        return
    steps = list(progress.get("steps") or [])
    if step not in steps:
        return
    completed = progress.setdefault("completed", set())
    completed.add(step)
    done = sum(1 for item in steps if item in completed)
    total = max(1, len(steps))
    elapsed = max(0.0, time.perf_counter() - float(progress.get("started_at", time.perf_counter())))
    percent = int(round(done / total * 100.0))
    remaining_text = _estimated_remaining_text(steps, completed, progress.get("estimates") if isinstance(progress.get("estimates"), dict) else {})
    progress["bar"].progress(percent, text=f"{done}/{total} steg klara: {step} ({elapsed:.1f} s). {remaining_text}")
    _safe_status_update(progress.get("status"), label=f"Beräknar karta och potential... {done}/{total} steg klara", state="running", expanded=False)


def _finish_calculation_progress(progress: dict[str, Any] | None, performance_log: list[dict[str, Any]]) -> None:
    if not progress:
        return
    elapsed = max(0.0, time.perf_counter() - float(progress.get("started_at", time.perf_counter())))
    slowest = max(performance_log, key=lambda row: float(row.get("tid_s", 0.0) or 0.0)) if performance_log else None
    suffix = f" Längsta steg: {slowest.get('steg')} {float(slowest.get('tid_s', 0.0) or 0.0):.1f} s." if slowest else ""
    progress["bar"].progress(100, text=f"Klart på {elapsed:.1f} s.{suffix}")
    _safe_status_update(progress.get("status"), label=f"Beräkning klar på {elapsed:.1f} s", state="complete", expanded=False)


def _performance_diagnostic_rows(performance_log: list[dict[str, Any]], estimates: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in performance_log:
        step = str(row.get("steg", ""))
        actual = float(row.get("tid_s", 0.0) or 0.0)
        expected = estimates.get(step)
        rows.append(
            {
                "steg": step,
                "tid_s": round(actual, 3),
                "historisk_median_s": round(float(expected), 3) if expected is not None else None,
                "avvikelse_s": round(actual - float(expected), 3) if expected is not None else None,
                "detalj": str(row.get("detalj", "")),
            }
        )
    return sorted(rows, key=lambda item: float(item.get("tid_s", 0.0) or 0.0), reverse=True)


def _short_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:10]


def _feature_count(feature_collection: dict[str, Any] | None) -> int:
    if not isinstance(feature_collection, dict):
        return 0
    features = feature_collection.get("features")
    return len(features) if isinstance(features, list) else 0


def _map_layer_debug_rows(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for layer in layers:
        rows.append(
            {
                "lager": str(layer.get("control_name") or layer.get("name") or "Lager"),
                "namn": str(layer.get("name") or "-"),
                "typ": str(layer.get("layer_kind") or "-"),
                "features": _feature_count(layer.get("feature_collection")),
                "default": "på" if layer.get("default_visible", True) is not False else "av",
                "z": int(layer.get("z_index", 0) or 0),
            }
        )
    return rows


def _preview_labels(labels: list[str], limit: int = 3) -> str:
    clean = [str(label) for label in labels if str(label)]
    if not clean:
        return ""
    suffix = "..." if len(clean) > int(limit) else ""
    return ", ".join(clean[: int(limit)]) + suffix


def _wind_group_display_label(groups: dict[str, Any], group_id: str) -> str:
    if str(group_id) == WIND_SETTLEMENT_GROUP_ID:
        return WIND_SETTLEMENT_GROUP_LABEL
    if str(group_id) == SOLAR_PROTECTED_GROUP_ID:
        return PROTECTED_NATURE_LABEL
    group = groups.get(str(group_id))
    if group is None:
        return GROUP_LABELS.get(str(group_id), str(group_id))
    return group_label(group, WIND_CONTROL_LANGUAGE, group.label)


def _geography_filter_notes(
    *,
    show_user_wind: bool,
    wind_selected_layers: dict[str, list[str]],
    wind_ui_params: dict[str, Any],
    wind_unfiltered_land: bool,
    show_user_solar: bool,
    show_solar_v1: bool,
    solar_large_population_active: bool,
    solar_large_unfiltered_land_active: bool,
    solar_params: dict[str, Any],
    solar_large_filter_configs: list[dict[str, Any]],
    solar_v1_area_m2_per_person: float,
) -> list[str]:
    notes: list[str] = []
    selected_wind = normalize_group_layer_map(wind_selected_layers or {})
    if show_user_wind:
        if wind_unfiltered_land or not any(selected_wind.values()):
            notes.append("Vind: inga avgränsande lager är valda, så vindpotentialen används som ett öppet startläge.")
        else:
            groups, layers, _ = load_acceptance_registry()
            for group in ordered_groups():
                group_id = str(group.id)
                layer_ids = [str(layer_id) for layer_id in selected_wind.get(group_id, [])]
                if not layer_ids:
                    continue
                threshold_key = GROUP_PARAM_MAP.get(group_id)
                threshold_m = (
                    float(wind_ui_params.get(threshold_key, group.analysis_default_m))
                    if threshold_key
                    else float(group.analysis_default_m)
                )
                selected_labels = [
                    layer_label(layers[layer_id], WIND_CONTROL_LANGUAGE, layers[layer_id].label)
                    for layer_id in layer_ids
                    if layer_id in layers
                ]
                layer_text = _preview_labels(selected_labels)
                effect_text = "maxavstånd" if str(group.analysis_kind) == "proximity_feasibility" else "buffert/avstånd"
                source_text = f" ({layer_text})" if layer_text else ""
                notes.append(
                    f"Vind: {_wind_group_display_label(groups, group_id)} använder {len(layer_ids)} källager med {threshold_m:.0f} m {effect_text}{source_text}."
                )

    if show_user_solar:
        has_solar_filters = bool(solar_large_population_active or solar_large_filter_configs)
        if solar_large_population_active:
            notes.append(
                f"Sol: befolkning begränsar storskalig sol med {float(solar_params.get('population_buffer_m', 250.0) or 250.0):.0f} m avstånd från Trøndelag 250 m befolkningsrutproxy."
            )
        for filter_config in solar_large_filter_configs:
            group_id = str(filter_config.get("group_id", ""))
            spec = SOLAR_FILTER_GROUP_SPECS.get(group_id, {})
            label = str(spec.get("label", filter_config.get("label", group_id)))
            layer_ids = list(filter_config.get("layer_ids") or [])
            layer_labels = [str(value) for value in (filter_config.get("layer_labels") or [])]
            layer_text = _preview_labels(layer_labels)
            source_text = f" ({layer_text})" if layer_text else ""
            distance_m = float(filter_config.get("buffer_m", 0.0) or 0.0)
            if str(filter_config.get("effect", spec.get("effect", "exclusion"))) == "feasibility":
                notes.append(f"Sol: {label} kräver närhet inom {distance_m:.0f} m från {len(layer_ids)} källager{source_text}.")
            else:
                notes.append(f"Sol: {label} drar av yta med {distance_m:.0f} m buffert från {len(layer_ids)} källager{source_text}.")
        if not has_solar_filters and solar_large_unfiltered_land_active:
            notes.append("Sol: storskalig sol använder landskapsunderlaget utan aktiva avdragsfilter.")

    if show_solar_v1:
        notes.append(
            f"Sol: småskalig takschablon använder {float(solar_v1_area_m2_per_person or 0.0):.0f} m² panelyta per person."
        )

    return notes


def _geography_effect_notes(energy_model_state: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    solar_filter_impact = energy_model_state.get("solar_filter_impact") if isinstance(energy_model_state, dict) else None
    if isinstance(solar_filter_impact, dict) and int(solar_filter_impact.get("active_filter_count", 0) or 0) > 0:
        removed_area = float(solar_filter_impact.get("removed_area_km2", 0.0) or 0.0)
        removed_share = float(solar_filter_impact.get("removed_share_pct", 0.0) or 0.0)
        if removed_area > 1e-6:
            notes.append(
                f"Solfiltereffekt: {_format_area_primary(removed_area, 'km²')} tas bort från den storskaliga solbasen ({removed_share:.1f}%)."
            )
        else:
            notes.append("Solfilter är aktiva men tar inte bort någon mätbar yta med nuvarande inställningar.")
    return notes


def _establishment_color_summary_text(stats: dict[str, Any] | None) -> str:
    if not isinstance(stats, dict):
        return ""
    values = {
        "gröna": int(stats.get("wind_and_solar_hex_count", 0) or 0),
        "blå": int(stats.get("wind_only_hex_count", 0) or 0),
        "gula": int(stats.get("solar_only_hex_count", 0) or 0),
        "röda": int(stats.get("red_hex_count", 0) or 0),
    }
    total = int(stats.get("total_hex_count", 0) or 0)
    if total <= 0:
        total = sum(values.values())
    if total <= 0:
        return ""
    parts = [
        f"{_count_text(count)} {label} ({count / max(total, 1) * 100.0:.1f}%)"
        for label, count in values.items()
    ]
    black_count = int(stats.get("black_hex_count", 0) or 0)
    suffix = f" Svarta schematiska fält: {_count_text(black_count)}." if black_count > 0 else ""
    return f"Färgfördelning i kartan: {', '.join(parts)} av {_count_text(total)} hexagoner.{suffix}"


def _render_geography_user_summary(map_state: dict[str, Any]) -> None:
    st.caption(
        "Kartan visar hur aktiva geografiska antaganden formar möjlig etableringsyta och hur scenariot placeras i landskapet."
    )
    filter_notes = [str(note) for note in (map_state.get("geography_filter_notes") or []) if str(note)]
    if filter_notes:
        st.markdown("\n".join(f"- {note}" for note in filter_notes))
    else:
        st.caption("Inga aktiva geografiska filter kunde sammanfattas för den senaste kartkörningen.")
    color_text = _establishment_color_summary_text(map_state.get("establishment_hex_stats"))
    if color_text:
        st.caption(color_text)
    for note in [str(value) for value in (map_state.get("geography_effect_notes") or []) if str(value)]:
        st.caption(note)


def _protected_group_label() -> str:
    return PROTECTED_NATURE_LABEL


def _settlement_group_label() -> str:
    return WIND_SETTLEMENT_GROUP_LABEL


def _apply_wind_layer_selection_state(layer_selection: dict[str, list[str]]) -> dict[str, list[str]]:
    selected = normalize_group_layer_map(layer_selection)
    st.session_state[WIND_LAYER_SELECTION_KEY] = selected
    for layer in ordered_layers():
        st.session_state[_wind_control_key("layer", layer.id)] = bool(layer.id in selected.get(layer.group_id, []))
    st.session_state[_wind_control_key("group", WIND_SETTLEMENT_GROUP_ID)] = bool(
        selected.get(WIND_SETTLEMENT_GROUP_ID)
    )
    st.session_state[_wind_control_key("group", WIND_CULTURE_GROUP_ID)] = bool(
        selected.get(WIND_CULTURE_GROUP_ID)
    )
    st.session_state[_wind_control_key("group", WIND_REINDEER_GROUP_ID)] = bool(
        selected.get(WIND_REINDEER_GROUP_ID)
    )
    st.session_state[_wind_control_key("group", SOLAR_PROTECTED_GROUP_ID)] = bool(
        selected.get(SOLAR_PROTECTED_GROUP_ID)
    )
    return selected


def _region_start_default_key(region: dict[str, Any]) -> str:
    region_id = str(region.get("region_id", "region") or "region")
    return f"{START_DEFAULT_VERSION_KEY}_{region_id}"


def _ensure_default_start_state(region: dict[str, Any], force: bool = False) -> None:
    start_default_key = _region_start_default_key(region)
    if not force and st.session_state.get(start_default_key) == START_DEFAULT_VERSION:
        return
    _apply_reference_default_wind_to_controls()
    for group_id in WIND_GROUP_LAYER_DEFAULTS:
        st.session_state[_wind_control_key("visual_source", str(group_id))] = False
        st.session_state[_wind_control_key("visual_buffer", str(group_id))] = False
    st.session_state[WIND_EMPTY_SELECTION_ACTIVE_KEY] = False
    default_solar_config = dict(DEFAULT_SOLAR_APPLIED_CONFIG)
    st.session_state[SOLAR_APPLIED_CONFIG_KEY] = default_solar_config
    region_id = str(region.get("region_id", "region") or "region")
    st.session_state[f"potential_scenario_{region_id}"] = "high"
    st.session_state[f"energy_model_planning_scenario_{region_id}"] = "high"
    st.session_state[f"energy_model_area_scenario_{region_id}"] = "high"
    default_display_resolution = int(region.get("default_display_h3_resolution") or region.get("default_h3_resolution") or 8)
    st.session_state["combined_h3_resolution"] = _preferred_h3_resolution(region, default_display_resolution)
    st.session_state["combined_h3_display_mode"] = "zoom_family"
    st.session_state["show_landscape_v10"] = False
    st.session_state["show_landscape_pdf_types"] = False
    st.session_state["show_landscape_cluster"] = False
    st.session_state["show_landscape_factor"] = False
    st.session_state["show_social_acceptance"] = False
    st.session_state[_social_acceptance_state_key(region)] = SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID
    st.session_state[_social_acceptance_impact_state_key(region)] = 0
    st.session_state[_social_acceptance_allocation_priority_state_key(region)] = 0
    st.session_state["show_solar_v1"] = bool(default_solar_config.get("small_population_active", False))
    st.session_state["show_user_solar"] = bool(default_solar_config.get("large_scale_active", True))
    st.session_state["solar_draft_small_population_active"] = bool(default_solar_config.get("small_population_active", False))
    st.session_state["solar_draft_large_population_active"] = bool(default_solar_config.get("large_population_active", False))
    st.session_state["solar_draft_area_m2_per_person"] = float(default_solar_config.get("panel_area_m2_per_person", 10.0) or 10.0)
    st.session_state["solar_draft_population_buffer_m"] = float(default_solar_config.get("population_buffer_m", 250.0) or 250.0)
    for group_id in _solar_visual_group_order():
        st.session_state[_solar_visual_control_key("source", group_id)] = False
        st.session_state[_solar_visual_control_key("buffer", group_id)] = False
    for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
        configured_layer_ids = {
            str(layer_id)
            for layer_id in default_solar_config.get(str(spec["layer_ids_key"]), [])
        }
        st.session_state[str(spec["draft_active_key"])] = bool(default_solar_config.get(str(spec["active_key"]), False))
        st.session_state[str(spec["draft_buffer_key"])] = float(
            default_solar_config.get(str(spec["buffer_key"]), spec.get("buffer_default_m", 0.0)) or 0.0
        )
        for layer_id in spec.get("layer_ids") or []:
            st.session_state[_solar_filter_layer_control_key(group_id, str(layer_id))] = str(layer_id) in configured_layer_ids
    st.session_state[start_default_key] = START_DEFAULT_VERSION


def _solar_filter_spec(group_id: str) -> dict[str, Any]:
    return SOLAR_FILTER_GROUP_SPECS[str(group_id)]


def _solar_filter_layer_ids(group_id: str) -> tuple[str, ...]:
    return tuple(str(layer_id) for layer_id in (_solar_filter_spec(group_id).get("layer_ids") or ()))


def _solar_default_filter_layer_ids(group_id: str) -> tuple[str, ...]:
    spec = _solar_filter_spec(group_id)
    requested = spec.get("default_layer_ids")
    if requested is None:
        requested = spec.get("layer_ids")
    allowed = set(_solar_filter_layer_ids(group_id))
    return tuple(str(layer_id) for layer_id in (requested or ()) if str(layer_id) in allowed)


def _solar_filter_layer_control_key(group_id: str, layer_id: str) -> str:
    if str(group_id) == SOLAR_PROTECTED_GROUP_ID:
        return _solar_protected_layer_control_key(str(layer_id))
    return f"solar_draft_{group_id}_layer__{layer_id}"


def _solar_visual_control_key(kind: str, group_id: str) -> str:
    return f"solar_draft_visual_{kind}__{group_id}"


def _solar_visual_config_key(kind: str) -> str:
    return SOLAR_VISUAL_SOURCE_GROUPS_KEY if str(kind) == "source" else SOLAR_VISUAL_BUFFER_GROUPS_KEY


def _solar_visual_group_order() -> tuple[str, ...]:
    return (
        SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
        SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID,
        *SOLAR_FILTER_GROUP_IDS,
    )


def _solar_visible_group_ids(config: dict[str, Any], kind: str) -> list[str]:
    raw = config.get(_solar_visual_config_key(kind), [])
    if isinstance(raw, dict):
        requested = {str(group_id) for group_id, enabled in raw.items() if bool(enabled)}
    elif isinstance(raw, (list, tuple, set)):
        requested = {str(group_id) for group_id in raw}
    else:
        requested = set()
    return [group_id for group_id in _solar_visual_group_order() if group_id in requested]


def _solar_visual_enabled(config: dict[str, Any], kind: str, group_id: str) -> bool:
    return str(group_id) in set(_solar_visible_group_ids(config, kind))


def _solar_visible_group_ids_from_session(kind: str) -> list[str]:
    return [
        group_id
        for group_id in _solar_visual_group_order()
        if bool(st.session_state.get(_solar_visual_control_key(kind, group_id), False))
    ]


def _solar_control_selected_filter_layer_ids(config: dict[str, Any], group_id: str) -> list[str]:
    spec = _solar_filter_spec(group_id)
    active_key = str(spec["active_key"])
    if active_key in config and not bool(config.get(active_key, False)):
        return []
    raw_ids = config.get(str(spec["layer_ids_key"]))
    if isinstance(raw_ids, (list, tuple, set)):
        requested = [str(layer_id) for layer_id in raw_ids]
    elif bool(config.get(str(spec["active_key"]), False)):
        requested = list(_solar_default_filter_layer_ids(group_id))
    else:
        requested = []
    return list(_solar_available_filter_layer_ids(group_id, requested))


def _solar_control_selected_protected_layer_ids(config: dict[str, Any]) -> list[str]:
    return _solar_control_selected_filter_layer_ids(config, SOLAR_PROTECTED_GROUP_ID)


def _solar_filter_layer_labels(layer_ids: list[str] | tuple[str, ...]) -> list[str]:
    _, layers, _ = load_acceptance_registry()
    labels: list[str] = []
    for layer_id in layer_ids:
        layer_spec = layers.get(str(layer_id))
        if layer_spec is None:
            labels.append(str(layer_id))
            continue
        labels.append(layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label))
    return labels


def _solar_active_filter_configs(config: dict[str, Any]) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for group_id in SOLAR_FILTER_GROUP_IDS:
        spec = _solar_filter_spec(group_id)
        layer_ids = _solar_control_selected_filter_layer_ids(config, group_id)
        if not layer_ids:
            continue
        active.append(
            {
                "group_id": group_id,
                "layer_ids": layer_ids,
                "layer_labels": _solar_filter_layer_labels(layer_ids),
                "buffer_m": float(config.get(str(spec["buffer_key"]), spec.get("buffer_default_m", 0.0)) or 0.0),
                "label": str(spec["label"]),
                "effect": str(spec.get("effect", "exclusion")),
            }
        )
    return active


def _solar_large_scale_is_active(
    base_active: bool,
    population_active: bool,
    protected_layer_ids: list[str] | tuple[str, ...],
) -> bool:
    _ = base_active
    _ = population_active
    _ = protected_layer_ids
    return True


def _solar_protected_layer_control_key(layer_id: str) -> str:
    return f"solar_draft_protected_layer__{layer_id}"


def _solar_default_filter_config_values(config: dict[str, Any] | None = None) -> dict[str, Any]:
    source = config if isinstance(config, dict) else {}
    values: dict[str, Any] = {}
    for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
        layer_ids = _solar_control_selected_filter_layer_ids(source, group_id) if source else []
        values[str(spec["layer_ids_key"])] = layer_ids
        values[str(spec["active_key"])] = bool(layer_ids)
        values[str(spec["buffer_key"])] = float(
            source.get(str(spec["buffer_key"]), spec.get("buffer_default_m", 0.0)) or 0.0
        )
    return values


def _initial_solar_config_from_session() -> dict[str, Any]:
    if not any(
        key in st.session_state
        for key in [
            "show_solar_v1",
            "show_user_solar",
            "solar_large_scale_active",
            "solar_large_population_active",
            "solar_draft_small_population_active",
        ]
    ):
        return dict(DEFAULT_SOLAR_APPLIED_CONFIG)
    selected_filter_ids: dict[str, list[str]] = {}
    for group_id in SOLAR_FILTER_GROUP_IDS:
        selected_filter_ids[group_id] = [
            layer_id
            for layer_id in _solar_filter_layer_ids(group_id)
            if bool(st.session_state.get(_solar_filter_layer_control_key(group_id, layer_id), False))
        ]
    selected_protected_ids = selected_filter_ids.get(SOLAR_PROTECTED_GROUP_ID, [])
    large_scale_base_active = True
    large_population_active = bool(st.session_state.get("solar_large_population_active", False))
    large_scale_active = _solar_large_scale_is_active(
        large_scale_base_active,
        large_population_active,
        selected_protected_ids,
    )
    config = {
        "small_population_active": bool(st.session_state.get("show_solar_v1", False))
        and bool(st.session_state.get("solar_small_population_active", True)),
        "large_unfiltered_land_active": False,
        "large_scale_active": large_scale_active,
        "large_population_active": large_population_active,
        "large_protected_layer_ids": selected_protected_ids,
        "large_protected_active": bool(selected_protected_ids),
        "panel_area_m2_per_person": float(st.session_state.get("solar_v1_area_m2_per_person", 10.0) or 10.0),
        "population_buffer_m": float(st.session_state.get("solar_builder_population_buffer_m", 250.0) or 250.0),
        "protected_buffer_m": float(st.session_state.get("solar_builder_protected_buffer_m", 0.0) or 0.0),
        SOLAR_VISUAL_SOURCE_GROUPS_KEY: _solar_visible_group_ids_from_session("source"),
        SOLAR_VISUAL_BUFFER_GROUPS_KEY: _solar_visible_group_ids_from_session("buffer"),
    }
    for group_id, layer_ids in selected_filter_ids.items():
        spec = _solar_filter_spec(group_id)
        config[str(spec["layer_ids_key"])] = list(layer_ids)
        config[str(spec["active_key"])] = bool(layer_ids)
        config[str(spec["buffer_key"])] = float(
            st.session_state.get(str(spec["draft_buffer_key"]), spec.get("buffer_default_m", 0.0)) or 0.0
        )
    return config


def _solar_config_from_session() -> dict[str, Any]:
    config = st.session_state.get(SOLAR_APPLIED_CONFIG_KEY)
    if not isinstance(config, dict):
        config = _initial_solar_config_from_session()
        st.session_state[SOLAR_APPLIED_CONFIG_KEY] = dict(config)
    filter_values = _solar_default_filter_config_values(config)
    protected_layer_ids = list(filter_values.get("large_protected_layer_ids", []))
    large_scale_base_active = True
    large_population_active = bool(config.get("large_population_active", False))
    large_scale_active = _solar_large_scale_is_active(
        large_scale_base_active,
        large_population_active,
        protected_layer_ids,
    )
    normalized = {
        "small_population_active": bool(config.get("small_population_active", False)),
        "large_unfiltered_land_active": bool(config.get("large_unfiltered_land_active", False)),
        "large_scale_active": large_scale_active,
        "large_population_active": large_population_active,
        "large_protected_layer_ids": protected_layer_ids,
        "large_protected_active": bool(protected_layer_ids),
        "panel_area_m2_per_person": float(config.get("panel_area_m2_per_person", 10.0) or 0.0),
        "population_buffer_m": float(config.get("population_buffer_m", 250.0) or 250.0),
        "protected_buffer_m": float(config.get("protected_buffer_m", 0.0) or 0.0),
        SOLAR_VISUAL_SOURCE_GROUPS_KEY: _solar_visible_group_ids(config, "source"),
        SOLAR_VISUAL_BUFFER_GROUPS_KEY: _solar_visible_group_ids(config, "buffer"),
    }
    normalized.update(filter_values)
    return normalized


def _prime_solar_draft_state(config: dict[str, Any]) -> None:
    st.session_state.setdefault("solar_draft_small_population_active", bool(config.get("small_population_active", False)))
    st.session_state.setdefault("solar_draft_large_population_active", bool(config.get("large_population_active", False)))
    st.session_state.setdefault("solar_draft_area_m2_per_person", float(config.get("panel_area_m2_per_person", 10.0) or 10.0))
    st.session_state.setdefault("solar_draft_population_buffer_m", float(config.get("population_buffer_m", 250.0) or 250.0))
    visible_source_groups = set(_solar_visible_group_ids(config, "source"))
    visible_buffer_groups = set(_solar_visible_group_ids(config, "buffer"))
    for group_id in _solar_visual_group_order():
        st.session_state.setdefault(_solar_visual_control_key("source", group_id), group_id in visible_source_groups)
        st.session_state.setdefault(_solar_visual_control_key("buffer", group_id), group_id in visible_buffer_groups)
    for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
        selected_layer_ids = set(_solar_control_selected_filter_layer_ids(config, group_id))
        default_layer_ids = set(_solar_default_filter_layer_ids(group_id))
        st.session_state.setdefault(
            str(spec["draft_buffer_key"]),
            float(config.get(str(spec["buffer_key"]), spec.get("buffer_default_m", 0.0)) or 0.0),
        )
        for layer_id in _solar_filter_layer_ids(group_id):
            st.session_state.setdefault(
                _solar_filter_layer_control_key(group_id, layer_id),
                layer_id in selected_layer_ids or (not selected_layer_ids and layer_id in default_layer_ids),
            )
        st.session_state.setdefault(str(spec["draft_active_key"]), bool(selected_layer_ids))


def _solar_draft_config_from_session() -> dict[str, Any]:
    large_scale_base_active = True
    large_population_active = bool(st.session_state.get("solar_draft_large_population_active", False))
    filter_values: dict[str, Any] = {}
    for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
        active = bool(st.session_state.get(str(spec["draft_active_key"]), False))
        layer_ids = (
            [
                layer_id
                for layer_id in _solar_filter_layer_ids(group_id)
                if bool(st.session_state.get(_solar_filter_layer_control_key(group_id, layer_id), False))
            ]
            if active
            else []
        )
        if active and not layer_ids:
            layer_ids = list(_solar_default_filter_layer_ids(group_id))
        layer_ids = list(_solar_available_filter_layer_ids(group_id, layer_ids))
        filter_values[str(spec["layer_ids_key"])] = layer_ids
        filter_values[str(spec["active_key"])] = bool(layer_ids)
        filter_values[str(spec["buffer_key"])] = float(
            st.session_state.get(str(spec["draft_buffer_key"]), spec.get("buffer_default_m", 0.0)) or 0.0
        )
    protected_layer_ids = list(filter_values.get("large_protected_layer_ids", []))
    config = {
        "small_population_active": bool(st.session_state.get("solar_draft_small_population_active", False)),
        "large_unfiltered_land_active": False,
        "large_scale_active": _solar_large_scale_is_active(
            large_scale_base_active,
            large_population_active,
            protected_layer_ids,
        ),
        "large_population_active": large_population_active,
        "large_protected_layer_ids": protected_layer_ids,
        "large_protected_active": bool(protected_layer_ids),
        "panel_area_m2_per_person": float(st.session_state.get("solar_draft_area_m2_per_person", 10.0) or 0.0),
        "population_buffer_m": float(st.session_state.get("solar_draft_population_buffer_m", 250.0) or 250.0),
        "protected_buffer_m": float(st.session_state.get("solar_draft_protected_buffer_m", 0.0) or 0.0),
        SOLAR_VISUAL_SOURCE_GROUPS_KEY: _solar_visible_group_ids_from_session("source"),
        SOLAR_VISUAL_BUFFER_GROUPS_KEY: _solar_visible_group_ids_from_session("buffer"),
    }
    config.update(filter_values)
    return config


def _render_solar_filter_control(group_id: str) -> list[str]:
    spec = _solar_filter_spec(group_id)
    label = str(spec["label"])
    selected_layer_ids: list[str] = []
    with st.expander(label, expanded=False):
        active = st.checkbox(
            f"Använd {label}",
            key=str(spec["draft_active_key"]),
            help=str(spec.get("active_help") or f"Valda lager används som avdrag i {SOLAR_LARGE_SCALE_LABEL}."),
        )
        options = _solar_filter_layer_options(group_id)
        with st.expander("Avancerade inställningar", expanded=False):
            st.caption(f"Välj vilka del-lager som ingår i {label}.")
            for option in options:
                layer_id = str(option["id"])
                checked = st.checkbox(
                    str(option["label"]),
                    key=_solar_filter_layer_control_key(group_id, layer_id),
                    disabled=not bool(option["ready"]),
                    help=str(option.get("message", "") or ""),
                )
                if active and checked and bool(option["ready"]):
                    selected_layer_ids.append(layer_id)
            st.caption("Kartvisning: valda lager används i analysen även när källa och buffert är dolda på kartan.")
            st.checkbox(
                "Visa källa i kartan",
                key=_solar_visual_control_key("source", group_id),
                disabled=not bool(options),
            )
            st.checkbox(
                "Visa buffert i kartan",
                key=_solar_visual_control_key("buffer", group_id),
                disabled=not bool(options),
            )
        if not options:
            st.caption(f"Inga lager hittades för {label.lower()} i acceptansregistret.")
        elif not active:
            st.caption(f"{label} används inte i solpotentialen.")
        elif not selected_layer_ids:
            st.caption(f"{label} behöver minst ett del-lager för att användas.")
        else:
            st.caption(str(spec.get("caption", "")))
        st.slider(
            str(spec.get("slider_label") or f"Buffert {label.lower()}"),
            min_value=float(spec.get("buffer_min_m", 0.0)),
            max_value=float(spec.get("buffer_max_m", 1000.0)),
            step=float(spec.get("buffer_step_m", 50.0)),
            key=str(spec["draft_buffer_key"]),
            help=str(spec.get("slider_help") or "0 m tar bort själva källgeometrin. Högre värden lägger till buffert."),
        )
    return selected_layer_ids


def _has_selected_wind_layers(layer_selection: dict[str, list[str]] | None = None) -> bool:
    selected = normalize_group_layer_map(_selected_wind_layers() if layer_selection is None else layer_selection)
    return any(len(layer_ids) > 0 for layer_ids in selected.values())


def _wind_empty_selection_is_active(layer_selection: dict[str, list[str]] | None = None) -> bool:
    return bool(st.session_state.get(WIND_EMPTY_SELECTION_ACTIVE_KEY, False)) and not _has_selected_wind_layers(layer_selection)


def _wind_potential_is_active(layer_selection: dict[str, list[str]] | None = None) -> bool:
    return _has_selected_wind_layers(layer_selection) or _wind_empty_selection_is_active(layer_selection)


def _map_panel_controls(region: dict[str, Any], key_prefix: str, panel: Any | None = None) -> tuple[int, bool, float, bool, int]:
    available = _available_h3_resolutions(region)
    state_key = f"{key_prefix}_h3_resolution"
    display_mode_key = f"{key_prefix}_h3_display_mode"
    try:
        preferred_hint = int(region.get("default_display_h3_resolution") or 9)
    except Exception:
        preferred_hint = 9
    current_value = _session_h3_resolution(region, state_key, preferred_hint)

    display_modes = ["selected", "zoom_family"]
    current_display_mode = str(st.session_state.get(display_mode_key, "zoom_family"))
    if current_display_mode not in display_modes:
        current_display_mode = "zoom_family"
        if display_mode_key in st.session_state:
            del st.session_state[display_mode_key]

    zoom_family_base = _zoom_family_base_resolution(region)
    family_resolutions = _zoom_family_resolutions(region)
    zoom_family_available = len({int(value) for value in family_resolutions}) > 1
    if not zoom_family_available and current_display_mode == "zoom_family":
        current_display_mode = "selected"
        st.session_state[display_mode_key] = "selected"
    display_modes_for_resolution = ["selected", "zoom_family"] if zoom_family_available else ["selected"]

    if panel is not None:
        panel.markdown(f"**{_t('H3-upplösning')}**")
        display_mode_index = display_modes_for_resolution.index(current_display_mode)
        display_mode = panel.radio(
            _t("Hexvisning"),
            options=display_modes_for_resolution,
            index=display_mode_index,
            format_func=lambda value: {
                "selected": _t("Vald upplösning"),
                "zoom_family": _t("Zoomanpassad upplösning"),
            }.get(str(value), str(value)),
            horizontal=False,
            key=display_mode_key,
        )
        if display_mode is None:
            display_mode = current_display_mode
        zoom_family_enabled = display_mode == "zoom_family"
        if zoom_family_enabled:
            h3_resolution = zoom_family_base
            if st.session_state.get(state_key) != int(h3_resolution):
                st.session_state[state_key] = int(h3_resolution)
        else:
            h3_index = available.index(current_value)
            h3_resolution = panel.radio(
                _t("H3-rollup"),
                options=available,
                index=h3_index,
                format_func=lambda value: _h3_option_label(region, value),
                horizontal=False,
                key=state_key,
            )
            if h3_resolution is None:
                h3_resolution = current_value
        panel.markdown("[Läs mer om H3-upplösningar](https://h3geo.org/).")
    else:
        h3_resolution = current_value
        zoom_family_enabled = (
            current_display_mode == "zoom_family"
            and zoom_family_available
        )
        if zoom_family_enabled:
            h3_resolution = zoom_family_base

    return int(h3_resolution), bool(zoom_family_enabled), _current_opacity(key_prefix), True, _map_view_reset_token()


def _filter_frame_to_display_geometries(frame: pd.DataFrame, display_geometry_path: str | None) -> pd.DataFrame:
    if not display_geometry_path or "hex_id" not in frame.columns:
        return frame
    visible_hex_ids = _h3_display_hex_ids(display_geometry_path)
    return frame[frame["hex_id"].astype(str).isin(visible_hex_ids)].copy()


def _display_family_resolutions(region: dict[str, Any], preferred_resolution: int) -> list[int]:
    preferred = int(preferred_resolution)
    available = [value for value in _available_h3_resolutions(region) if int(value) <= preferred]
    return available or [preferred]


def _zoom_family_base_resolution(region: dict[str, Any]) -> int:
    available = _available_h3_resolutions(region)
    try:
        default_resolution = int(region.get("default_display_h3_resolution") or region.get("default_h3_resolution") or max(available))
    except Exception:
        default_resolution = max(available)
    return _preferred_h3_resolution(region, default_resolution)


def _zoom_family_resolutions(region: dict[str, Any]) -> list[int]:
    return _display_family_resolutions(region, _zoom_family_base_resolution(region))


def _hex_display_rule(region: dict[str, Any], selected_resolution: int, zoom_family_enabled: bool) -> dict[str, str]:
    selected = _zoom_family_base_resolution(region) if bool(zoom_family_enabled) else int(selected_resolution)
    family_resolutions = _zoom_family_resolutions(region) if bool(zoom_family_enabled) else _display_family_resolutions(region, selected)
    min_resolution = min(int(value) for value in family_resolutions) if family_resolutions else selected
    if not bool(zoom_family_enabled):
        return {
            "selected_label": f"R{selected}",
            "display_label": f"R{selected}",
            "mode_label": "Snabb",
            "item_note": f"Snabb hexvisning i R{selected}.",
        }
    if min_resolution == selected:
        return {
            "selected_label": f"R{selected}",
            "display_label": f"R{selected}",
            "mode_label": "Fast",
            "item_note": f"Hexvisning i R{selected}.",
        }
    return {
        "selected_label": f"R{selected}",
        "display_label": f"R{selected} till R{min_resolution}",
        "mode_label": "Zoomanpassad",
        "item_note": f"Hexvisning zoomanpassas från R{selected} till R{min_resolution}.",
    }


def _hex_family_layers(
    region: dict[str, Any],
    selected_resolution: int,
    zoom_family_enabled: bool,
    family_key: str,
    control_name: str,
    build_layer: Any,
    family_resolutions: list[int] | None = None,
) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    selected_for_map = _zoom_family_base_resolution(region) if bool(zoom_family_enabled) else int(selected_resolution)
    resolutions = (
        [int(value) for value in family_resolutions]
        if family_resolutions is not None
        else (
            _zoom_family_resolutions(region)
            if bool(zoom_family_enabled)
            else [int(selected_resolution)]
        )
    )
    for resolution in resolutions:
        layer = build_layer(int(resolution))
        if layer is None:
            continue
        layer["name"] = f"{control_name} R{int(resolution)}"
        layer["control_name"] = control_name
        layer["auto_resolution_group"] = str(family_key)
        layer["auto_resolution"] = int(resolution)
        layer["selected_resolution"] = int(selected_for_map)
        layer["lock_selected_resolution"] = not bool(zoom_family_enabled)
        layers.append(layer)
    return layers


def _class_breaks(solar_rules: dict[str, Any]) -> list[dict[str, Any]]:
    return list((solar_rules.get("score_model") or {}).get("class_breaks") or [])


def _solar_rollup_entry(potential_manifest: dict[str, Any], resolution: int) -> dict[str, Any] | None:
    for entry in potential_manifest.get("h3_rollups") or []:
        if entry.get("technology") == "solar" and int(entry.get("h3_resolution", -1)) == int(resolution):
            return entry
    return None


def _default_solar_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    potential_manifest: dict[str, Any],
    solar_rules: dict[str, Any],
    resolution: int,
) -> pd.DataFrame:
    display_rules = _solar_rules_with_display_palette(solar_rules)
    source_resolution = landscape_source_resolution(landscape_manifest)
    entry = _solar_rollup_entry(potential_manifest, resolution)
    if entry is not None and int(entry.get("source_resolution", -1)) == source_resolution:
        frame = rollup_frame_for_entry(entry)
        class_colors = {
            str(item.get("id")): str(item.get("color", "#999999"))
            for item in _class_breaks(display_rules)
        }
        if "solar_class" in frame.columns:
            frame = frame.copy()
            frame["solar_color"] = frame["solar_class"].astype(str).map(class_colors).fillna(frame.get("solar_color", "#999999"))
    else:
        frame = rollup_potential_frame(
            solar_capacity_frame(landscape_manifest, display_rules),
            resolution,
            _class_breaks(display_rules),
            "solar",
            source_resolution=source_resolution,
        )
    return _filter_frame_to_display_geometries(frame, _h3_display_geometry_path(region, resolution))


def _custom_solar_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    solar_rules: dict[str, Any],
    resolution: int,
    params: dict[str, float],
) -> pd.DataFrame:
    rules = _solar_rules_from_params(solar_rules, params)
    base = solar_capacity_frame(landscape_manifest, rules)
    frame = rollup_potential_frame(base, resolution, _class_breaks(rules), "solar", source_resolution=landscape_source_resolution(landscape_manifest))
    return _filter_frame_to_display_geometries(frame, _h3_display_geometry_path(region, resolution))


def _solar_v1_class(area_m2: float) -> dict[str, str]:
    value = max(0.0, float(area_m2 or 0.0))
    if value <= 0:
        return {"id": "none", "label": "0 m2", "color": "#991b1b"}
    if value <= 25:
        return {"id": "very_low", "label": ">0-25 m2", "color": "#f87171"}
    if value <= 100:
        return {"id": "low", "label": "25-100 m2", "color": "#fef08a"}
    if value <= 250:
        return {"id": "medium", "label": "100-250 m2", "color": "#fde047"}
    if value <= 1000:
        return {"id": "high", "label": "250-1 000 m2", "color": "#facc15"}
    return {"id": "very_high", "label": ">1 000 m2", "color": "#ca8a04"}


def _solar_v1_legend_items() -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for value in [10, 50, 150, 500, 1500]:
        item = _solar_v1_class(float(value))
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append({"label": item["label"], "color": item["color"]})
    return items


@st.cache_data(show_spinner=False)
def _population_count_frame_for_resolution(
    path_str: str,
    target_resolution: int,
    count_column: str = SOLAR_V1_POPULATION_COUNT_COLUMN,
) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame(columns=["hex_id", "population"])
    raw = pd.read_csv(path)
    if "hex_id" not in raw.columns or count_column not in raw.columns:
        return pd.DataFrame(columns=["hex_id", "population"])

    work = raw[["hex_id", count_column]].copy()
    work["hex_id"] = work["hex_id"].astype(str)
    work["population"] = pd.to_numeric(work[count_column], errors="coerce").fillna(0.0).clip(lower=0.0)
    work = work[["hex_id", "population"]]
    source_resolutions: list[int] = []
    for value in work["hex_id"].dropna().astype(str).head(250):
        try:
            source_resolutions.append(int(h3.get_resolution(value)))
        except Exception:
            continue
    if not source_resolutions:
        return pd.DataFrame(columns=["hex_id", "population"])
    source_resolution = int(pd.Series(source_resolutions).mode().iloc[0])
    target_resolution = int(target_resolution)

    if target_resolution == source_resolution:
        return work.groupby("hex_id", as_index=False)["population"].sum()
    if target_resolution < source_resolution:
        out = work.copy()
        out["hex_id"] = out["hex_id"].map(lambda value: h3.cell_to_parent(str(value), target_resolution))
        return out.groupby("hex_id", as_index=False)["population"].sum()

    rows: list[dict[str, Any]] = []
    for row in work.itertuples(index=False):
        try:
            children = sorted(h3.cell_to_children(str(row.hex_id), target_resolution))
        except Exception:
            children = []
        if not children:
            continue
        population_share = float(row.population) / float(len(children))
        rows.extend({"hex_id": str(child), "population": population_share} for child in children)
    if not rows:
        return pd.DataFrame(columns=["hex_id", "population"])
    return pd.DataFrame(rows).groupby("hex_id", as_index=False)["population"].sum()


def _trondelag_population_proxy_unit_count(registry_meta: dict[str, Any]) -> float | None:
    try:
        geojson = source_geojson_for_layer(registry_meta, WIND_POPULATION_SOURCE_LAYER_ID)
    except Exception:
        geojson = None
    features = geojson.get("features") if isinstance(geojson, dict) else []
    if not features:
        return None
    for feature in features:
        props = feature.get("properties") if isinstance(feature, dict) else {}
        if not isinstance(props, dict):
            continue
        value = props.get("source_feature_count")
        try:
            count = float(value)
        except Exception:
            continue
        if count > 0:
            return count
    return None


def _trondelag_population_proxy_resolution_m(region: dict[str, Any]) -> float:
    catalog = load_linked_manifest(region, "parameter_buffer_catalog") or load_linked_manifest(region, "parameter_buffers") or {}
    runtime = catalog.get("runtime_rendering") if isinstance(catalog, dict) else {}
    population = runtime.get("population_buffer") if isinstance(runtime, dict) else {}
    try:
        return float(population.get("proxy_resolution_m") or 250.0) if isinstance(population, dict) else 250.0
    except Exception:
        return 250.0


def _trondelag_population_proxy_count_frame(region: dict[str, Any], target_resolution: int) -> pd.DataFrame:
    catalog = load_linked_manifest(region, "parameter_buffer_catalog") or load_linked_manifest(region, "parameter_buffers") or {}
    runtime = catalog.get("runtime_rendering") if isinstance(catalog, dict) else {}
    population = runtime.get("population_buffer") if isinstance(runtime, dict) else {}
    if not isinstance(population, dict):
        return pd.DataFrame(columns=["hex_id", "population"])
    path = resolve_region_path(region, population.get("population_h3_counts_csv"))
    if path is None or not path.exists():
        return pd.DataFrame(columns=["hex_id", "population"])
    count_column = str(population.get("population_count_column") or "population")
    return _population_count_frame_for_resolution(str(path), int(target_resolution), count_column)


def _solar_v1_population_count_frame(region: dict[str, Any], target_resolution: int) -> pd.DataFrame:
    if str(region.get("region_id", "")).lower() == "trondelag":
        return _trondelag_population_proxy_count_frame(region, int(target_resolution))
    return _population_count_frame_for_resolution(str(SOLAR_V1_POPULATION_LAYER_PATH), int(target_resolution))


def _solar_v1_population_source_available(region: dict[str, Any]) -> bool:
    if str(region.get("region_id", "")).lower() == "trondelag":
        return not _trondelag_population_proxy_count_frame(region, int(region.get("default_h3_resolution") or 7)).empty
    return SOLAR_V1_POPULATION_LAYER_PATH.exists()


def _solar_v1_population_source_status(region: dict[str, Any]) -> str:
    if str(region.get("region_id", "")).lower() == "trondelag":
        return (
            "Befolkningsunderlag: Trondelag 250 m befolkningsrute-/centroidproxy. "
            "Småskalig sol använder personantalet i rutorna, inte individuella personpunkter."
        )
    if SOLAR_V1_POPULATION_LAYER_PATH.exists():
        return (
            f"Befolkningsunderlag: {SOLAR_V1_POPULATION_LAYER_PATH} "
            "(regional-landscape-pipeline, H3 R10)."
        )
    return (
        f"Befolkningsunderlag saknas: {SOLAR_V1_POPULATION_LAYER_PATH}. "
        "Sätt REGIONAL_LANDSCAPE_PIPELINE_ROOT om regional-landscape-pipeline ligger på annan plats."
    )


def _solar_v1_panel_area_label(region: dict[str, Any]) -> str:
    return _t("Panelyta per person")


def _solar_v1_formula_text(region: dict[str, Any], panel_area_m2_per_person: float) -> str:
    if str(region.get("region_id", "")).lower() == "trondelag":
        return (
            "Småskalig solyta beräknas som befolkning i 250 m-rutor per hex "
            f"× {float(panel_area_m2_per_person or 0.0):.0f} m2/person."
        )
    return (
        "Småskalig solyta beräknas som befolkning per hex "
        f"× {float(panel_area_m2_per_person or 0.0):.0f} m2/person."
    )


def _solar_v1_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
    panel_area_m2_per_person: float,
) -> pd.DataFrame:
    columns = [
        "hex_id",
        "class_km",
        "landscape_type",
        "population",
        "solar_v1_area_m2",
        "solar_v1_area_km2",
        "solar_v1_score",
        "solar_v1_class",
        "solar_v1_class_label",
        "solar_v1_color",
        "solar_v1_population_label",
    ]
    resolution = int(resolution)
    display_geometry_path = _h3_display_geometry_path(region, resolution)
    landscape = _landscape_frame(region, landscape_manifest, resolution)
    if landscape.empty:
        return pd.DataFrame(columns=columns)
    population = _solar_v1_population_count_frame(region, resolution)
    frame = landscape[["hex_id", "class_km", "landscape_type"]].copy()
    frame = frame.merge(population, on="hex_id", how="left")
    frame["population"] = pd.to_numeric(frame["population"], errors="coerce").fillna(0.0).clip(lower=0.0)
    frame["solar_v1_area_m2"] = frame["population"] * max(0.0, float(panel_area_m2_per_person or 0.0))
    frame["solar_v1_area_km2"] = frame["solar_v1_area_m2"] / 1_000_000.0
    max_area = float(frame["solar_v1_area_m2"].max() or 0.0)
    if max_area > 0:
        frame["solar_v1_score"] = (frame["solar_v1_area_m2"].map(math.log1p) / math.log1p(max_area) * 100.0).clip(lower=0.0, upper=100.0).round(1)
    else:
        frame["solar_v1_score"] = 0.0
    classes = [_solar_v1_class(float(value)) for value in frame["solar_v1_area_m2"]]
    frame["solar_v1_class"] = [item["id"] for item in classes]
    frame["solar_v1_class_label"] = [item["label"] for item in classes]
    frame["solar_v1_color"] = [item["color"] for item in classes]
    frame["solar_v1_population_label"] = (
        "personer (250 m-rutor)" if str(region.get("region_id", "")).lower() == "trondelag" else "personer"
    )
    return _filter_frame_to_display_geometries(frame, display_geometry_path).reindex(columns=columns)


@st.cache_data(show_spinner=False)
def _solar_v1_feature_collection(frame_json: str, target_resolution: int) -> dict[str, Any]:
    frame = pd.read_json(StringIO(frame_json), orient="records")
    if frame.empty:
        return {"type": "FeatureCollection", "features": []}
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        hex_id = str(row.hex_id)
        area_m2 = float(getattr(row, "solar_v1_area_m2", 0.0) or 0.0)
        if area_m2 <= 0:
            continue
        population_label = str(getattr(row, "solar_v1_population_label", "personer") or "personer")
        try:
            source_resolution = int(h3.get_resolution(hex_id))
        except Exception:
            source_resolution = int(target_resolution)
        child_resolution = min(15, max(int(target_resolution), source_resolution) + 1)
        try:
            display_hex = str(h3.cell_to_center_child(hex_id, child_resolution))
        except Exception:
            display_hex = hex_id
        geometry = _h3_polygon_geometry(display_hex)
        if geometry is None:
            continue
        population = float(getattr(row, "population", 0.0) or 0.0)
        popup = (
            f"<strong>{hex_id}</strong><br>"
            f"{SOLAR_SMALL_SCALE_LABEL}: {area_m2:.0f} m2<br>"
            f"{population_label}: {population:.1f}<br>"
            f"Landskapstyp: {int(row.class_km)} - {row.landscape_type}<br>"
            "Visas som liten schablonhex, inte som faktisk takpolygon."
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "display_hex_id": display_hex,
                    "score": float(getattr(row, "solar_v1_score", 0.0) or 0.0),
                    "class": str(getattr(row, "solar_v1_class", "none")),
                    "class_label": str(getattr(row, "solar_v1_class_label", "0 m2")),
                    "fill": str(getattr(row, "solar_v1_color", "#fde68a")),
                    "stroke": "#7c2d12",
                    "stroke_weight": 0.55,
                    "fill_opacity": 0.9,
                    "tooltip_title": f"{SOLAR_SMALL_SCALE_LABEL}: {area_m2:.0f} m2",
                    "tooltip_body": f"Schablon från {population_label} per hex",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _solar_v1_layer(
    name: str,
    frame: pd.DataFrame,
    target_resolution: int,
) -> dict[str, Any]:
    if frame.empty:
        map_frame = pd.DataFrame(
            columns=[
                "hex_id",
                "class_km",
                "landscape_type",
                "population",
                "solar_v1_area_m2",
                "solar_v1_score",
                "solar_v1_class",
                "solar_v1_class_label",
                "solar_v1_color",
                "solar_v1_population_label",
            ]
        )
    else:
        map_frame = frame[
            [
                "hex_id",
                "class_km",
                "landscape_type",
                "population",
                "solar_v1_area_m2",
                "solar_v1_score",
                "solar_v1_class",
                "solar_v1_class_label",
                "solar_v1_color",
                "solar_v1_population_label",
            ]
        ].copy()
    return {
        "name": name,
        "feature_collection": _solar_v1_feature_collection(map_frame.to_json(orient="records", force_ascii=False), int(target_resolution)),
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "stroke_weight_property": "stroke_weight",
        "legend_items": _solar_v1_legend_items(),
        "legend_id": "solar_v1_schematic",
        "legend_title": "Småskalig solyta (schablon)",
        "default_visible": True,
        "stroke": True,
        "stroke_opacity": 0.82,
        "fill_opacity": 0.9,
        "weight": 0.55,
        "z_index": 530,
        "layer_kind": "hex",
        "opacity_family": name,
        "opacity_label": name,
    }


def _solar_score_class(score: float) -> dict[str, str]:
    value = max(0.0, min(100.0, float(score or 0.0)))
    if value <= 0:
        return {"id": "none", "label": "0%", "color": "#991b1b"}
    if value < 25:
        return {"id": "low", "label": "0-25%", "color": "#f87171"}
    if value < 50:
        return {"id": "medium_low", "label": "25-50%", "color": "#fef08a"}
    if value < 75:
        return {"id": "medium_high", "label": "50-75%", "color": "#facc15"}
    return {"id": "high", "label": "75-100%", "color": "#ca8a04"}


def _solar_score_legend_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in [0, 10, 35, 60, 90]:
        item = _solar_score_class(float(value))
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append({"label": item["label"], "color": item["color"]})
    return items


def _h3_edge_length_m(resolution: int) -> float:
    try:
        return float(h3.average_hexagon_edge_length(int(resolution), unit="m"))
    except Exception:
        return 75.0


def _population_buffer_ring_count(resolution: int, buffer_m: float) -> int:
    edge_m = max(1.0, _h3_edge_length_m(int(resolution)))
    return max(1, int(math.ceil(max(0.0, float(buffer_m or 0.0)) / edge_m)))


def _append_unique_layer(layers: list[dict[str, Any]], layer: dict[str, Any] | None) -> None:
    if layer is None:
        return
    source_layer_id = str(layer.get("source_layer_id", "") or "")
    if source_layer_id and any(str(existing.get("source_layer_id", "") or "") == source_layer_id for existing in layers):
        return
    buffer_layer_id = str(layer.get("buffer_layer_id", "") or "")
    if buffer_layer_id and any(str(existing.get("buffer_layer_id", "") or "") == buffer_layer_id for existing in layers):
        return
    name = str(layer.get("name", ""))
    if name and not source_layer_id and not buffer_layer_id and any(str(existing.get("name", "")) == name for existing in layers):
        return
    layers.append(layer)


def _layer_visible_by_default(layer: dict[str, Any] | None) -> dict[str, Any] | None:
    if layer is None:
        return None
    visible_layer = dict(layer)
    visible_layer["default_visible"] = True
    return visible_layer


def _dedupe_layers(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    seen_names: set[str] = set()
    for layer in layers:
        source_layer_id = str(layer.get("source_layer_id", "") or "")
        if source_layer_id:
            if source_layer_id in seen_source_ids:
                continue
            seen_source_ids.add(source_layer_id)
        buffer_layer_id = str(layer.get("buffer_layer_id", "") or "")
        if buffer_layer_id:
            if buffer_layer_id in seen_source_ids:
                continue
            seen_source_ids.add(buffer_layer_id)
        name = str(layer.get("name", "") or "")
        if name:
            if not source_layer_id and not buffer_layer_id and name in seen_names:
                continue
            seen_names.add(name)
        deduped.append(layer)
    return deduped


def _solar_population_source_layer() -> dict[str, Any] | None:
    groups, layers, registry_meta = load_acceptance_registry()
    _ = groups
    layer_spec = layers.get(WIND_POPULATION_SOURCE_LAYER_ID)
    if layer_spec is None:
        return None
    geojson = source_geojson_for_layer(registry_meta, WIND_POPULATION_SOURCE_LAYER_ID)
    if not geojson:
        return None
    source_color = _rgb_to_hex(layer_spec.source_color)
    source_label = f"Sol källa: {layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label)}"
    return {
        "name": source_label,
        "source_layer_id": f"solar:{WIND_POPULATION_SOURCE_LAYER_ID}",
        "feature_collection": geojson,
        "fill_property": "fill",
        "legend_items": [],
        "legend_id": "solar_population_source",
        "legend_title": "",
        "default_visible": True,
        "stroke_color": source_color,
        "fill_color": source_color,
        "stroke_opacity": 0.85,
        "fill_opacity": 0.28,
        "weight": 1.2,
        "point_radius": int(layer_spec.point_radius),
        "use_global_opacity": False,
        "layer_kind": "vector",
    }


def _solar_population_runtime_result(buffer_m: float) -> dict[str, Any] | None:
    try:
        config = {
            "groups": {
                "settlement": {
                    "active_layer_ids": [WIND_POPULATION_SOURCE_LAYER_ID],
                    "analysis_value_m": int(round(float(buffer_m or 0.0))),
                }
            }
        }
        return run_geometry_runtime(json.dumps(config, sort_keys=True, ensure_ascii=False))
    except Exception:
        return None


def _solar_population_buffer_geojson(buffer_m: float) -> dict[str, Any] | None:
    runtime_result = _solar_population_runtime_result(float(buffer_m or 0.0))
    runtime_group = (runtime_result or {}).get("groups", {}).get("settlement") if isinstance(runtime_result, dict) else None
    if not isinstance(runtime_group, dict):
        return None
    geojson = runtime_group.get("geojson")
    return geojson if isinstance(geojson, dict) else None


TRONDELAG_POPULATION_BUFFER_DEFAULTS = {
    "render_mode": "dissolved_polygon_proxy",
    "source_layer_id": WIND_POPULATION_SOURCE_LAYER_ID,
    "proxy_resolution_m": 250,
    "cache_filename_template": "population_points_buffer_{buffer_m}m.geojson",
    "user_facing_note": "Trondelag population uses dissolved 250 m grid-cell proxy polygons derived from centroids, not individual population points.",
}


def _trondelag_population_buffer_config(region: dict[str, Any]) -> dict[str, Any]:
    manifest = load_linked_manifest(region, "parameter_buffer_catalog") or load_linked_manifest(region, "parameter_buffers") or {}
    runtime_rendering = manifest.get("runtime_rendering") if isinstance(manifest, dict) else {}
    config = (runtime_rendering or {}).get("population_buffer") if isinstance(runtime_rendering, dict) else {}
    merged = dict(TRONDELAG_POPULATION_BUFFER_DEFAULTS)
    if isinstance(config, dict):
        merged.update(config)
    return merged


def _trondelag_population_buffer_config_path(region: dict[str, Any], config: dict[str, Any], key: str) -> Path | None:
    path_value = config.get(key)
    path = resolve_region_path(region, str(path_value)) if path_value else None
    if path is not None:
        return path
    return None


def _trondelag_population_proxy_rds_path(region: dict[str, Any]) -> Path | None:
    config = _trondelag_population_buffer_config(region)
    return _trondelag_population_buffer_config_path(region, config, "source_rds")


def _trondelag_population_buffer_script_path(region: dict[str, Any]) -> Path | None:
    config = _trondelag_population_buffer_config(region)
    return _trondelag_population_buffer_config_path(region, config, "render_script")


def _trondelag_population_buffer_cache_path(region: dict[str, Any], buffer_m: float) -> Path | None:
    config = _trondelag_population_buffer_config(region)
    cache_dir = _trondelag_population_buffer_config_path(region, config, "cache_dir")
    if cache_dir is None:
        return None
    buffer_value = int(round(max(0.0, float(buffer_m or 0.0))))
    template = str(config.get("cache_filename_template") or TRONDELAG_POPULATION_BUFFER_DEFAULTS["cache_filename_template"])
    try:
        filename = template.format(
            buffer_m=buffer_value,
            source_layer_id=str(config.get("source_layer_id") or WIND_POPULATION_SOURCE_LAYER_ID),
        )
    except Exception:
        filename = f"population_points_buffer_{buffer_value}m.geojson"
    return cache_dir / filename


def _trondelag_population_proxy_resolution_m(region: dict[str, Any]) -> int:
    config = _trondelag_population_buffer_config(region)
    try:
        return int(config.get("proxy_resolution_m") or 250)
    except Exception:
        return 250


@st.cache_data(show_spinner=False)
def _load_trondelag_population_buffer_geojson(
    buffer_value_m: int,
    source_path_str: str,
    source_mtime_ns: int,
    script_path_str: str,
    script_mtime_ns: int,
    output_path_str: str,
) -> dict[str, Any] | None:
    _ = source_mtime_ns, script_mtime_ns
    output_path = Path(output_path_str)
    source_path = Path(source_path_str)
    script_path = Path(script_path_str)
    newest_source_mtime = max(source_path.stat().st_mtime, script_path.stat().st_mtime)
    if not output_path.exists() or output_path.stat().st_mtime < newest_source_mtime:
        try:
            subprocess.run(
                [
                    "Rscript",
                    str(script_path),
                    str(ROOT),
                    str(int(buffer_value_m)),
                    str(output_path),
                    str(source_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except Exception:
            return None
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _trondelag_population_buffer_geojson(region: dict[str, Any], buffer_m: float) -> dict[str, Any] | None:
    source_path = _trondelag_population_proxy_rds_path(region)
    script_path = _trondelag_population_buffer_script_path(region)
    if not source_path or not script_path or not source_path.exists() or not script_path.exists():
        return None
    buffer_value = int(round(max(0.0, float(buffer_m or 0.0))))
    output_path = _trondelag_population_buffer_cache_path(region, float(buffer_value))
    if output_path is None:
        return None
    return _load_trondelag_population_buffer_geojson(
        buffer_value,
        str(source_path),
        int(source_path.stat().st_mtime_ns),
        str(script_path),
        int(script_path.stat().st_mtime_ns),
        str(output_path),
    )


def _trondelag_population_buffer_polygon_layer(
    region: dict[str, Any],
    buffer_m: float,
    prefix: str = "Buffert",
    context_key: str = "shared",
) -> dict[str, Any] | None:
    _, layers, _ = load_acceptance_registry()
    layer_spec = layers.get(WIND_POPULATION_SOURCE_LAYER_ID)
    if layer_spec is None:
        return None
    geojson = _trondelag_population_buffer_geojson(region, float(buffer_m or 0.0))
    features = geojson.get("features") if isinstance(geojson, dict) else None
    if not isinstance(features, list) or not features:
        return None
    label = layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label)
    buffer_value = float(buffer_m or 0.0)
    proxy_resolution_m = _trondelag_population_proxy_resolution_m(region)
    for feature in features:
        props = feature.setdefault("properties", {})
        props["fill"] = "#14b8a6"
        props["stroke"] = "#0f766e"
        props["fill_opacity"] = 0.22
        props["tooltip_title"] = f"{prefix}: {label}"
        props["tooltip_body"] = f"{buffer_value:.0f} m från upplöst {proxy_resolution_m} m befolkningsrutproxy"
        props["popup"] = (
            f"<strong>{prefix}: {label}</strong><br>"
            f"Buffert: {buffer_value:.0f} m<br>"
            f"Källa: {proxy_resolution_m} m befolkningsrutor härledda från centroider. "
            "Bufferten är en dissolvad polygon, inte individuella befolkningspunkter."
        )
    return {
        "name": f"{prefix}: {label}",
        "buffer_layer_id": f"{context_key}:{WIND_POPULATION_SOURCE_LAYER_ID}:polygon_buffer:{int(round(buffer_value))}",
        "feature_collection": geojson,
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "legend_items": [{"label": f"{buffer_value:.0f} m från {proxy_resolution_m} m befolkningsrutor", "color": "#14b8a6"}],
        "legend_id": f"population_polygon_buffer_{int(round(buffer_value))}",
        "legend_title": "",
        "default_visible": True,
        "stroke_color": "#0f766e",
        "fill_color": "#14b8a6",
        "stroke_opacity": 0.55,
        "fill_opacity": 0.22,
        "weight": 0.65,
        "point_radius": 4,
        "use_global_opacity": False,
        "z_index": 456,
        "layer_kind": "vector",
        "opacity_family": f"{prefix}: {label}",
        "opacity_label": f"{prefix}: {label}",
    }


def _solar_population_buffer_frame(
    region: dict[str, Any],
    target_resolution: int,
    buffer_m: float,
) -> pd.DataFrame:
    if float(buffer_m or 0.0) <= 0:
        return pd.DataFrame(columns=["hex_id", "population_buffer_m", "buffer_ring_count"])
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "population_buffer_m", "buffer_ring_count"])
    if str(region.get("region_id", "")).lower() == "trondelag":
        share = _population_buffer_share_frame(region, int(target_resolution), float(buffer_m or 0.0))
        if share.empty:
            return pd.DataFrame(columns=["hex_id", "population_buffer_m", "buffer_ring_count", "buffer_share_pct"])
        share = share.rename(columns={"filter_buffer_share_pct": "buffer_share_pct"})
        share["population_buffer_m"] = float(buffer_m or 0.0)
        share["buffer_ring_count"] = 0
        return share[["hex_id", "population_buffer_m", "buffer_ring_count", "buffer_share_pct"]].copy()
    buffer_geojson = _solar_population_buffer_geojson(float(buffer_m or 0.0))
    if not buffer_geojson:
        return pd.DataFrame(columns=["hex_id", "population_buffer_m", "buffer_ring_count"])
    share = runtime_combined_hex_frame(buffer_geojson, int(target_resolution), [])
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "population_buffer_m", "buffer_ring_count", "buffer_share_pct"])
    share = _filter_frame_to_display_geometries(share, display_geometry_path)
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "population_buffer_m", "buffer_ring_count", "buffer_share_pct"])
    score_col = "wind_score" if "wind_score" in share.columns else "potential_area_share_pct"
    share["buffer_share_pct"] = pd.to_numeric(share.get(score_col), errors="coerce").fillna(0.0)
    share = share[share["buffer_share_pct"].gt(0.0)].copy()
    share["population_buffer_m"] = float(buffer_m or 0.0)
    share["buffer_ring_count"] = 0
    return share[["hex_id", "population_buffer_m", "buffer_ring_count", "buffer_share_pct"]].copy()


def _solar_population_buffer_layer(
    region: dict[str, Any],
    target_resolution: int,
    buffer_m: float,
) -> dict[str, Any] | None:
    if str(region.get("region_id", "")).lower() == "trondelag":
        _ = target_resolution
        return _trondelag_population_buffer_polygon_layer(
            region,
            float(buffer_m or 0.0),
            prefix="Solbuffert",
            context_key="solar",
        )
    buffer_geojson = _solar_population_buffer_geojson(float(buffer_m or 0.0))
    if not buffer_geojson:
        return None
    features = buffer_geojson.get("features") if isinstance(buffer_geojson, dict) else None
    if not isinstance(features, list) or not features:
        return None
    for feature in features:
        props = feature.setdefault("properties", {})
        props["fill"] = "#14b8a6"
        props["popup"] = (
            f"<strong>{SOLAR_POPULATION_BUFFER_LABEL}</strong><br>"
            f"Avstånd: {float(buffer_m or 0.0):.0f} m<br>"
            "Totalt avstånd från befolkningspunkter. Källan har 100 m grundbuffert."
        )
        props["tooltip_title"] = SOLAR_POPULATION_BUFFER_LABEL
        props["tooltip_body"] = f"{float(buffer_m or 0.0):.0f} m total buffert"
    return {
        "name": SOLAR_POPULATION_BUFFER_LABEL,
        "buffer_layer_id": f"{WIND_POPULATION_SOURCE_LAYER_ID}:buffer:{int(round(float(buffer_m or 0.0)))}",
        "feature_collection": buffer_geojson,
        "fill_property": "fill",
        "legend_items": [{"label": "Polygonbuffert runt befolkningspunkter", "color": "#14b8a6"}],
        "legend_id": "solar_population_buffer",
        "legend_title": "",
        "default_visible": False,
        "stroke_color": "#0f766e",
        "fill_color": "#14b8a6",
        "stroke_opacity": 0.48,
        "fill_opacity": 0.20,
        "weight": 0.55,
        "point_radius": 4,
        "use_global_opacity": False,
        "z_index": 455,
        "layer_kind": "vector",
    }


def _solar_filter_source_layers(
    group_id: str,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    spec = _solar_filter_spec(group_id)
    groups, layers, registry_meta = load_acceptance_registry()
    _ = groups
    selected_layer_ids = _solar_available_filter_layer_ids(group_id, layer_ids)
    features: list[dict[str, Any]] = []
    selected_labels: list[str] = []
    source_colors: list[str] = []
    for layer_id in selected_layer_ids:
        layer_spec = layers.get(layer_id)
        if layer_spec is None:
            continue
        geojson = source_geojson_for_layer(registry_meta, layer_id)
        if not geojson:
            continue
        source_color = _rgb_to_hex(layer_spec.source_color)
        label = layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label)
        selected_labels.append(label)
        source_colors.append(source_color)
        for feature in geojson.get("features") or []:
            if not isinstance(feature, dict) or not feature.get("geometry"):
                continue
            copied = json.loads(json.dumps(feature))
            props = copied.setdefault("properties", {})
            props["fill"] = source_color
            props["source_layer_id"] = layer_id
            props["tooltip_title"] = str(spec["source_label"])
            props["tooltip_body"] = label
            props.setdefault("popup", f"<strong>{spec['source_label']}</strong><br>{label}")
            features.append(copied)
    if not features:
        return []
    return [
        {
            "name": str(spec["source_label"]),
            "source_layer_id": f"solar:{group_id}:{'_'.join(selected_layer_ids)}",
            "feature_collection": {"type": "FeatureCollection", "features": features},
            "fill_property": "fill",
            "legend_items": [{"label": str(spec["label"]), "color": source_colors[0] if source_colors else str(spec["source_color"])}],
            "legend_id": f"solar_{group_id}_source",
            "legend_title": "",
            "default_visible": False,
            "stroke_color": source_colors[0] if source_colors else "#15803d",
            "fill_color": source_colors[0] if source_colors else "#15803d",
            "stroke_opacity": 0.82,
            "fill_opacity": 0.22,
            "weight": 1.4,
            "point_radius": 4,
            "use_global_opacity": False,
            "z_index": 456,
            "layer_kind": "vector",
        }
    ]


def _solar_protected_source_layers(layer_ids: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    return _solar_filter_source_layers(SOLAR_PROTECTED_GROUP_ID, layer_ids)


def _solar_available_filter_layer_ids(
    group_id: str,
    layer_ids: list[str] | tuple[str, ...] | set[str] | None = None,
) -> tuple[str, ...]:
    _, layers, registry_meta = load_acceptance_registry()
    requested = list(_solar_filter_layer_ids(group_id)) if layer_ids is None else [str(layer_id) for layer_id in layer_ids]
    allowed = set(_solar_filter_layer_ids(group_id))
    available: list[str] = []
    for layer_id in requested:
        if layer_id not in allowed or layer_id in available:
            continue
        if layer_id not in layers:
            continue
        if source_geojson_for_layer(registry_meta, layer_id):
            available.append(layer_id)
    return tuple(available)


def _solar_available_protected_layer_ids(layer_ids: list[str] | tuple[str, ...] | set[str] | None = None) -> tuple[str, ...]:
    return _solar_available_filter_layer_ids(SOLAR_PROTECTED_GROUP_ID, layer_ids)


def _solar_filter_layer_options(group_id: str) -> list[dict[str, Any]]:
    _, layers, registry_meta = load_acceptance_registry()
    availability = _wind_layer_status_lookup(registry_meta)
    options: list[dict[str, Any]] = []
    for layer_id in _solar_filter_layer_ids(group_id):
        layer_spec = layers.get(layer_id)
        if layer_spec is None:
            continue
        ready = _wind_layer_is_ready(layer_id, availability)
        status = availability.get(layer_id, {})
        message = str(status.get("message", "") or layer_note(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.note) or "")
        options.append(
            {
                "id": layer_id,
                "label": layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label),
                "ready": bool(ready),
                "message": message,
            }
        )
    return options


def _solar_protected_layer_options() -> list[dict[str, Any]]:
    return _solar_filter_layer_options(SOLAR_PROTECTED_GROUP_ID)


def _solar_filter_runtime_result(
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    selected_layer_ids = _solar_available_filter_layer_ids(group_id, layer_ids)
    if not selected_layer_ids:
        return None
    try:
        config = {
            "groups": {
                str(group_id): {
                    "active_layer_ids": list(selected_layer_ids),
                    "analysis_value_m": int(round(max(0.0, float(buffer_m or 0.0)))),
                }
            }
        }
        return run_geometry_runtime(json.dumps(config, sort_keys=True, ensure_ascii=False))
    except Exception:
        return None


def _solar_protected_runtime_result(
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    return _solar_filter_runtime_result(SOLAR_PROTECTED_GROUP_ID, buffer_m, layer_ids)


def _solar_filter_buffer_geojson(
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    runtime_result = _solar_filter_runtime_result(group_id, float(buffer_m or 0.0), layer_ids)
    runtime_group = (runtime_result or {}).get("groups", {}).get(str(group_id)) if isinstance(runtime_result, dict) else None
    if not isinstance(runtime_group, dict):
        return None
    geojson = runtime_group.get("geojson")
    return geojson if isinstance(geojson, dict) else None


def _solar_protected_buffer_geojson(
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    return _solar_filter_buffer_geojson(SOLAR_PROTECTED_GROUP_ID, buffer_m, layer_ids)


def _h3_resolution_from_hex_ids(hex_ids: pd.Series) -> int | None:
    for value in hex_ids.dropna().astype(str).head(250):
        try:
            return int(h3.get_resolution(str(value)))
        except Exception:
            continue
    return None


def _expand_share_frame_to_resolution(frame: pd.DataFrame, target_resolution: int) -> pd.DataFrame:
    if frame.empty or "hex_id" not in frame.columns:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    source_resolution = _h3_resolution_from_hex_ids(frame["hex_id"])
    if source_resolution is None or int(source_resolution) == int(target_resolution):
        out = frame[["hex_id", "filter_buffer_share_pct"]].copy()
        out["hex_id"] = out["hex_id"].astype(str)
        return out
    work = frame[["hex_id", "filter_buffer_share_pct"]].copy()
    work["hex_id"] = work["hex_id"].astype(str)
    if int(source_resolution) > int(target_resolution):
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
        return work.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
    rows: list[dict[str, Any]] = []
    for row in work.itertuples(index=False):
        try:
            children = h3.cell_to_children(str(row.hex_id), int(target_resolution))
        except Exception:
            children = []
        for child in children:
            rows.append({"hex_id": str(child), "filter_buffer_share_pct": float(row.filter_buffer_share_pct or 0.0)})
    if not rows:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    return pd.DataFrame(rows).groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()


def _distance_table_filter_share_frame(
    region: dict[str, Any],
    target_resolution: int,
    filter_configs: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> pd.DataFrame:
    _ = region
    if not filter_configs:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    _, _, registry_meta = load_acceptance_registry()
    status_lookup = _wind_layer_status_lookup(registry_meta)
    frames: list[pd.DataFrame] = []
    for filter_config in filter_configs:
        group_id = str(filter_config.get("group_id", ""))
        if group_id == "population":
            continue
        buffer_m = max(0.0, float(filter_config.get("buffer_m", 0.0) or 0.0))
        layer_ids = _solar_available_filter_layer_ids(group_id, filter_config.get("layer_ids") or [])
        layer_frames: list[pd.DataFrame] = []
        for layer_id in layer_ids:
            distance_df = distance_table_for_layer(registry_meta, layer_id)
            if distance_df.empty or "hex_id" not in distance_df.columns:
                continue
            source_resolution = _h3_resolution_from_hex_ids(distance_df["hex_id"])
            if source_resolution is None:
                continue
            cell_area_m2 = float(h3_hex_area_km2(source_resolution) * 1_000_000.0)
            equivalent_radius_m = math.sqrt(max(cell_area_m2, 1e-9) / math.pi)
            geometry_family = str((status_lookup.get(str(layer_id), {}) or {}).get("geometry_family", "") or "").lower()
            distance = pd.to_numeric(distance_df.get("distance_m"), errors="coerce")
            intersects = distance_df.get("intersects", pd.Series(False, index=distance_df.index)).fillna(False).astype(bool)
            if "line" in geometry_family:
                if buffer_m <= 0:
                    share = pd.Series(0.0, index=distance_df.index, dtype="float64")
                else:
                    line_cap_pct = min(100.0, (4.0 * buffer_m * equivalent_radius_m / max(cell_area_m2, 1e-9)) * 100.0)
                    proximity = ((buffer_m - distance) / max(buffer_m, 1.0)).clip(lower=0.0, upper=1.0).fillna(0.0)
                    share = proximity * line_cap_pct
                    share.loc[intersects] = line_cap_pct
            elif "point" in geometry_family:
                if buffer_m <= 0:
                    share = pd.Series(0.0, index=distance_df.index, dtype="float64")
                else:
                    point_cap_pct = min(100.0, (math.pi * buffer_m * buffer_m / max(cell_area_m2, 1e-9)) * 100.0)
                    proximity = ((buffer_m - distance) / max(buffer_m, 1.0)).clip(lower=0.0, upper=1.0).fillna(0.0)
                    share = proximity * point_cap_pct
                    share.loc[intersects] = max(point_cap_pct, 1.0)
            else:
                if buffer_m <= 0:
                    share = intersects.astype(float) * 100.0
                else:
                    proximity = ((buffer_m - distance) / max(buffer_m, 1.0)).clip(lower=0.0, upper=1.0).fillna(0.0) * 100.0
                    share = proximity
                    share.loc[intersects] = 100.0
            layer_frame = pd.DataFrame(
                {
                    "hex_id": distance_df["hex_id"].astype(str),
                    "filter_buffer_share_pct": pd.to_numeric(share, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0),
                }
            )
            layer_frame = layer_frame[layer_frame["filter_buffer_share_pct"].gt(0.0)].copy()
            if not layer_frame.empty:
                layer_frames.append(layer_frame)
        if not layer_frames:
            continue
        combined = pd.concat(layer_frames, ignore_index=True, sort=False)
        combined = combined.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
        combined = _expand_share_frame_to_resolution(combined, int(target_resolution))
        if not combined.empty:
            frames.append(combined)
    if not frames:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    out = pd.concat(frames, ignore_index=True, sort=False)
    out = out.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
    out["filter_buffer_share_pct"] = pd.to_numeric(out["filter_buffer_share_pct"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
    return out[out["filter_buffer_share_pct"].gt(0.0)][["hex_id", "filter_buffer_share_pct"]].copy()


def _solar_filter_buffer_frame(
    region: dict[str, Any],
    target_resolution: int,
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    buffer_geojson = _solar_filter_buffer_geojson(group_id, float(buffer_m or 0.0), layer_ids)
    if not buffer_geojson:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    share = runtime_combined_hex_frame(buffer_geojson, int(target_resolution), [])
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    share = _filter_frame_to_display_geometries(share, display_geometry_path)
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    score_col = "wind_score" if "wind_score" in share.columns else "potential_area_share_pct"
    share["filter_buffer_share_pct"] = pd.to_numeric(share.get(score_col), errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
    share = share[share["filter_buffer_share_pct"].gt(0.0)].copy()
    share["filter_group_id"] = str(group_id)
    share["filter_buffer_m"] = float(buffer_m or 0.0)
    return share[["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"]].copy()


def _solar_protected_buffer_frame(
    region: dict[str, Any],
    target_resolution: int,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    frame = _solar_filter_buffer_frame(region, target_resolution, SOLAR_PROTECTED_GROUP_ID, buffer_m, layer_ids)
    if frame.empty:
        return pd.DataFrame(columns=["hex_id", "protected_buffer_m", "protected_buffer_share_pct"])
    out = frame.rename(
        columns={
            "filter_buffer_m": "protected_buffer_m",
            "filter_buffer_share_pct": "protected_buffer_share_pct",
        }
    )
    return out[["hex_id", "protected_buffer_m", "protected_buffer_share_pct"]].copy()


def _solar_filter_union_buffer_frame(
    region: dict[str, Any],
    target_resolution: int,
    filter_configs: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    features: list[dict[str, Any]] = []
    fallback_configs: list[dict[str, Any]] = []
    for filter_config in filter_configs or []:
        group_id = str(filter_config.get("group_id", ""))
        layer_ids = filter_config.get("layer_ids") or []
        buffer_m = float(filter_config.get("buffer_m", 0.0) or 0.0)
        if group_id == "population":
            if str(region.get("region_id", "")).lower() == "trondelag":
                pop_share = _population_buffer_share_frame(region, int(target_resolution), buffer_m)
                if not pop_share.empty:
                    features.append({"__population_share_frame__": pop_share})
                continue
            geojson = _solar_population_buffer_geojson(buffer_m)
        else:
            geojson = _solar_filter_buffer_geojson(group_id, buffer_m, layer_ids)
        if not isinstance(geojson, dict):
            fallback_configs.append(dict(filter_config))
            continue
        for feature in geojson.get("features") or []:
            if isinstance(feature, dict) and feature.get("geometry"):
                features.append(feature)
    population_frames = [item["__population_share_frame__"] for item in features if isinstance(item, dict) and "__population_share_frame__" in item]
    features = [
        item
        for item in features
        if not (isinstance(item, dict) and "__population_share_frame__" in item)
    ]
    fallback_share = _distance_table_filter_share_frame(region, int(target_resolution), fallback_configs)
    extra_share_frames = list(population_frames)
    if not fallback_share.empty:
        extra_share_frames.append(fallback_share)
    if extra_share_frames and not features:
        combined = pd.concat(extra_share_frames, ignore_index=True, sort=False)
        combined = (
            combined.groupby("hex_id", as_index=False)["filter_buffer_share_pct"]
            .max()
            .reset_index(drop=True)
        )
        return combined[["hex_id", "filter_buffer_share_pct"]]
    if not features:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    combined_geojson = {"type": "FeatureCollection", "features": features}
    share = runtime_combined_hex_frame(combined_geojson, int(target_resolution), [])
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    share = _filter_frame_to_display_geometries(share, display_geometry_path)
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    score_col = "wind_score" if "wind_score" in share.columns else "potential_area_share_pct"
    share["filter_buffer_share_pct"] = pd.to_numeric(share.get(score_col), errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
    share = share[share["filter_buffer_share_pct"].gt(0.0)].copy()
    if extra_share_frames:
        share = pd.concat([share[["hex_id", "filter_buffer_share_pct"]], *extra_share_frames], ignore_index=True, sort=False)
        share = share.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
    return share[["hex_id", "filter_buffer_share_pct"]].copy()


def _solar_filter_buffer_layer(
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    spec = _solar_filter_spec(group_id)
    selected_layer_ids = _solar_available_filter_layer_ids(group_id, layer_ids)
    buffer_geojson = _solar_filter_buffer_geojson(group_id, float(buffer_m or 0.0), selected_layer_ids)
    if not buffer_geojson:
        return None
    features = buffer_geojson.get("features") if isinstance(buffer_geojson, dict) else None
    if not isinstance(features, list) or not features:
        return None
    buffer_color = str(spec.get("buffer_color", "#16a34a"))
    is_feasibility = str(spec.get("effect", "exclusion")) == "feasibility"
    measure_label = "Max avstånd" if is_feasibility else "Buffert"
    tooltip_body = (
        f"Inom {float(buffer_m or 0.0):.0f} m"
        if is_feasibility
        else f"{float(buffer_m or 0.0):.0f} m buffert"
    )
    legend_label = str(
        spec.get("buffer_legend_label")
        or (
            f"Inom maxavstånd till {str(spec['label']).lower()}"
            if is_feasibility
            else f"Buffert runt {str(spec['label']).lower()}"
        )
    )
    for feature in features:
        props = feature.setdefault("properties", {})
        props["fill"] = buffer_color
        props["popup"] = (
            f"<strong>{spec['buffer_label']}</strong><br>"
            f"{measure_label}: {float(buffer_m or 0.0):.0f} m<br>"
            f"{spec['caption']}"
        )
        props["tooltip_title"] = str(spec["buffer_label"])
        props["tooltip_body"] = tooltip_body
    return {
        "name": str(spec["buffer_label"]),
        "buffer_layer_id": (
            f"solar:{group_id}:buffer:{int(round(float(buffer_m or 0.0)))}:"
            f"{'_'.join(selected_layer_ids) if selected_layer_ids else 'none'}"
        ),
        "feature_collection": buffer_geojson,
        "fill_property": "fill",
        "legend_items": [{"label": legend_label, "color": buffer_color}],
        "legend_id": f"solar_{group_id}_buffer",
        "legend_title": "",
        "default_visible": False,
        "stroke_color": str(spec.get("source_color", buffer_color)),
        "fill_color": buffer_color,
        "stroke_opacity": 0.56,
        "fill_opacity": 0.18,
        "weight": 0.75,
        "point_radius": 4,
        "use_global_opacity": False,
        "z_index": 458,
        "layer_kind": "vector",
    }


def _wind_filter_buffer_layer(
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    if str(group_id) not in SOLAR_FILTER_GROUP_SPECS:
        return None
    spec = _solar_filter_spec(group_id)
    selected_layer_ids = _solar_available_filter_layer_ids(group_id, layer_ids)
    if not selected_layer_ids:
        return None
    buffer_geojson = _solar_filter_buffer_geojson(group_id, float(buffer_m or 0.0), selected_layer_ids)
    if not buffer_geojson:
        return None
    features = buffer_geojson.get("features") if isinstance(buffer_geojson, dict) else None
    if not isinstance(features, list) or not features:
        return None
    groups, _, _ = load_acceptance_registry()
    group_meta = groups.get(group_id)
    label = (
        group_label(group_meta, WIND_CONTROL_LANGUAGE, group_meta.label)
        if group_meta is not None
        else str(spec.get("label") or group_id)
    )
    group_color = _rgb_to_hex(group_meta.group_color) if group_meta is not None else str(spec.get("buffer_color", "#c4322b"))
    buffer_color = group_color
    is_feasibility = str(spec.get("effect", "exclusion")) == "feasibility"
    layer_name = f"Vind nära nät: {label}" if is_feasibility else f"Vindbuffert: {label}"
    measure_label = "Max avstånd" if is_feasibility else "Buffert"
    tooltip_body = (
        f"Inom {float(buffer_m or 0.0):.0f} m"
        if is_feasibility
        else f"{float(buffer_m or 0.0):.0f} m buffert"
    )
    legend_label = (
        f"Inom maxavstånd till {label.lower()}"
        if is_feasibility
        else f"Vindbuffert runt {label.lower()}"
    )
    caption = (
        "Nära nät används som en positiv mask: yta räknas som vindpotential bara inom valt avstånd till elinfrastruktur."
        if is_feasibility
        else str(spec["caption"])
    )
    for feature in features:
        props = feature.setdefault("properties", {})
        props["fill"] = buffer_color
        props["popup"] = (
            f"<strong>{layer_name}</strong><br>"
            f"{measure_label}: {float(buffer_m or 0.0):.0f} m<br>"
            f"{caption}"
        )
        props["tooltip_title"] = layer_name
        props["tooltip_body"] = tooltip_body
    return {
        "name": layer_name,
        "buffer_layer_id": (
            f"wind:{group_id}:buffer:{int(round(float(buffer_m or 0.0)))}:"
            f"{'_'.join(selected_layer_ids) if selected_layer_ids else 'none'}"
        ),
        "feature_collection": buffer_geojson,
        "fill_property": "fill",
        "legend_items": [{"label": legend_label, "color": buffer_color}],
        "legend_id": f"wind_{group_id}_buffer",
        "legend_title": "",
        "default_visible": False,
        "stroke_color": group_color,
        "fill_color": buffer_color,
        "stroke_opacity": 0.56,
        "fill_opacity": 0.18,
        "weight": 0.75,
        "point_radius": 4,
        "use_global_opacity": False,
        "z_index": 459,
        "layer_kind": "vector",
    }


def _solar_protected_buffer_layer(
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    return _solar_filter_buffer_layer(SOLAR_PROTECTED_GROUP_ID, buffer_m, layer_ids)


def _solar_large_scale_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
    population_buffer_m: float,
    protected_buffer_m: float | None = None,
    protected_layer_ids: list[str] | tuple[str, ...] | None = None,
    unfiltered_land_active: bool = False,
    filter_configs: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> pd.DataFrame:
    target_resolution = int(resolution)
    landscape = _landscape_frame(region, landscape_manifest, target_resolution)
    columns = [
        "hex_id",
        "class_km",
        "landscape_type",
        "potential_area_m2",
        "potential_area_km2",
        "potential_area_share_pct",
        "protected_buffer_share_pct",
        "solar_score",
        "solar_class",
        "solar_class_label",
        "solar_color",
    ]
    if landscape.empty:
        return pd.DataFrame(columns=columns)

    active_filter_configs: list[dict[str, Any]] = []
    if float(population_buffer_m or 0.0) > 0:
        active_filter_configs.append(
            {
                "group_id": "population",
                "layer_ids": [WIND_POPULATION_SOURCE_LAYER_ID],
                "buffer_m": float(population_buffer_m or 0.0),
                "label": "Befolkning",
                "effect": "exclusion",
            }
        )
    if filter_configs:
        active_filter_configs.extend(dict(item) for item in filter_configs if isinstance(item, dict))
    elif protected_buffer_m is not None:
        active_filter_configs.append(
            {
                "group_id": SOLAR_PROTECTED_GROUP_ID,
                "layer_ids": list(protected_layer_ids or []),
                "buffer_m": float(protected_buffer_m or 0.0),
                "label": PROTECTED_NATURE_LABEL,
                "effect": "exclusion",
            }
        )

    if unfiltered_land_active and not active_filter_configs:
        target_hex_area_m2 = float(h3_hex_area_km2(target_resolution) * 1_000_000.0)
        work = landscape[["hex_id", "class_km", "landscape_type"]].copy()
        work["potential_area_m2"] = target_hex_area_m2
        work["potential_area_km2"] = target_hex_area_m2 / 1_000_000.0
        work["potential_area_share_pct"] = 100.0
        work["protected_buffer_share_pct"] = 0.0
        work["solar_score"] = 100.0
        classes = [_solar_score_class(float(value)) for value in work["solar_score"]]
        work["solar_class"] = [item["id"] for item in classes]
        work["solar_class_label"] = [item["label"] for item in classes]
        work["solar_color"] = [item["color"] for item in classes]
        return work.reindex(columns=columns)

    source_resolution = target_resolution if str(region.get("region_id", "")).lower() == "trondelag" else max(target_resolution, WIND_RUNTIME_BASE_RESOLUTION)
    if source_resolution != target_resolution and not _h3_display_geometry_path(region, source_resolution):
        source_resolution = target_resolution
    source_landscape = _landscape_frame(region, landscape_manifest, source_resolution)
    if source_landscape.empty and source_resolution != target_resolution:
        source_resolution = target_resolution
        source_landscape = landscape

    source = source_landscape[["hex_id"]].copy()
    work = source.copy()
    work["potential_area_share_pct"] = 100.0
    if work.empty:
        return pd.DataFrame(columns=columns)

    work["protected_buffer_share_pct"] = 0.0
    exclusion_filter_configs = [
        dict(config)
        for config in active_filter_configs
        if str(config.get("effect", "exclusion")) != "feasibility"
    ]
    feasibility_filter_configs = [
        dict(config)
        for config in active_filter_configs
        if str(config.get("effect", "exclusion")) == "feasibility"
    ]
    if exclusion_filter_configs:
        filters = _solar_filter_union_buffer_frame(region, source_resolution, exclusion_filter_configs)
        if not filters.empty:
            filters = filters[["hex_id", "filter_buffer_share_pct"]].copy()
            work = work.merge(filters, on="hex_id", how="left")
            work["protected_buffer_share_pct"] = pd.to_numeric(
                work.get("filter_buffer_share_pct"),
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0, upper=100.0)
            if "filter_buffer_share_pct" in work.columns:
                work = work.drop(columns=["filter_buffer_share_pct"])
        work["potential_area_share_pct"] = (
            work["potential_area_share_pct"] - work["protected_buffer_share_pct"]
        ).clip(lower=0.0, upper=100.0)
    if feasibility_filter_configs:
        work["feasibility_share_pct"] = 0.0
        feasible = _solar_filter_union_buffer_frame(region, source_resolution, feasibility_filter_configs)
        if not feasible.empty:
            feasible = feasible[["hex_id", "filter_buffer_share_pct"]].rename(
                columns={"filter_buffer_share_pct": "feasibility_share_pct"}
            )
            work = work.merge(feasible, on="hex_id", how="left", suffixes=("", "_from_filter"))
            work["feasibility_share_pct"] = pd.to_numeric(
                work.get("feasibility_share_pct_from_filter", work.get("feasibility_share_pct")),
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0, upper=100.0)
            for extra_col in ["feasibility_share_pct_from_filter"]:
                if extra_col in work.columns:
                    work = work.drop(columns=[extra_col])
        work["potential_area_share_pct"] = (
            work["potential_area_share_pct"] * work["feasibility_share_pct"] / 100.0
        ).clip(lower=0.0, upper=100.0)

    source_hex_area_m2 = float(h3_hex_area_km2(source_resolution) * 1_000_000.0)
    work["potential_area_m2"] = (work["potential_area_share_pct"] / 100.0 * source_hex_area_m2).clip(lower=0.0, upper=source_hex_area_m2)
    work["protected_buffer_area_m2"] = (work["protected_buffer_share_pct"] / 100.0 * source_hex_area_m2).clip(lower=0.0, upper=source_hex_area_m2)

    if target_resolution < source_resolution:
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), target_resolution)))
        work = (
            work.groupby("hex_id", as_index=False)
            .agg(
                potential_area_m2=("potential_area_m2", "sum"),
                protected_buffer_area_m2=("protected_buffer_area_m2", "sum"),
            )
            .sort_values("hex_id")
            .reset_index(drop=True)
        )

    source = landscape[["hex_id", "class_km", "landscape_type"]].copy()
    work = source.merge(work[["hex_id", "potential_area_m2", "protected_buffer_area_m2"]], on="hex_id", how="left")
    work["potential_area_m2"] = pd.to_numeric(work["potential_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    work["protected_buffer_area_m2"] = pd.to_numeric(work["protected_buffer_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0)

    target_hex_area_m2 = float(h3_hex_area_km2(target_resolution) * 1_000_000.0)
    work["potential_area_m2"] = work["potential_area_m2"].clip(lower=0.0, upper=target_hex_area_m2)
    work["potential_area_km2"] = work["potential_area_m2"] / 1_000_000.0
    work["potential_area_share_pct"] = (work["potential_area_m2"] / max(target_hex_area_m2, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    work["protected_buffer_share_pct"] = (work["protected_buffer_area_m2"] / max(target_hex_area_m2, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    work["solar_score"] = work["potential_area_share_pct"].round(1)
    classes = [_solar_score_class(float(value)) for value in work["solar_score"]]
    work["solar_class"] = [item["id"] for item in classes]
    work["solar_class_label"] = [item["label"] for item in classes]
    work["solar_color"] = [item["color"] for item in classes]
    return _filter_frame_to_display_geometries(work.reindex(columns=columns), _h3_display_geometry_path(region, target_resolution))


def _combined_solar_hex_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
    small_frame: pd.DataFrame,
    large_frame: pd.DataFrame,
) -> pd.DataFrame:
    base = _landscape_frame(region, landscape_manifest, int(resolution))[["hex_id", "class_km", "landscape_type"]].copy()
    if base.empty:
        return pd.DataFrame()
    hex_area_m2 = float(h3_hex_area_km2(int(resolution)) * 1_000_000.0)
    base["small_score"] = 0.0
    base["large_score"] = 0.0
    base["small_area_m2"] = 0.0
    base["large_area_m2"] = 0.0
    base["large_filter_buffer_share_pct"] = 0.0
    base["large_filter_buffer_area_m2"] = 0.0
    if not small_frame.empty:
        small = small_frame[["hex_id", "solar_v1_score", "solar_v1_area_m2"]].rename(
            columns={"solar_v1_score": "small_score", "solar_v1_area_m2": "small_area_m2"}
        ).copy()
        base = base.drop(columns=["small_score", "small_area_m2"]).merge(small, on="hex_id", how="left")
        base["small_score"] = pd.to_numeric(base["small_score"], errors="coerce").fillna(0.0)
        base["small_area_m2"] = pd.to_numeric(base["small_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    if not large_frame.empty:
        large = large_frame[["hex_id", "solar_score", "potential_area_m2"]].rename(
            columns={"solar_score": "large_score", "potential_area_m2": "large_area_m2"}
        ).copy()
        if "protected_buffer_share_pct" in large_frame.columns:
            large["large_filter_buffer_share_pct"] = pd.to_numeric(
                large_frame["protected_buffer_share_pct"],
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0, upper=100.0)
        else:
            large["large_filter_buffer_share_pct"] = 0.0
        if "protected_buffer_area_m2" in large_frame.columns:
            large["large_filter_buffer_area_m2"] = pd.to_numeric(
                large_frame["protected_buffer_area_m2"],
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0)
        else:
            large["large_filter_buffer_area_m2"] = large["large_filter_buffer_share_pct"] / 100.0 * hex_area_m2
        base = base.drop(
            columns=[
                "large_score",
                "large_area_m2",
                "large_filter_buffer_share_pct",
                "large_filter_buffer_area_m2",
            ]
        ).merge(large, on="hex_id", how="left")
        base["large_score"] = pd.to_numeric(base["large_score"], errors="coerce").fillna(0.0)
        base["large_area_m2"] = pd.to_numeric(base["large_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0)
        base["large_filter_buffer_share_pct"] = pd.to_numeric(
            base["large_filter_buffer_share_pct"],
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0, upper=100.0)
        base["large_filter_buffer_area_m2"] = pd.to_numeric(
            base["large_filter_buffer_area_m2"],
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0, upper=hex_area_m2)
    base["potential_area_m2"] = (base["small_area_m2"] + base["large_area_m2"]).clip(lower=0.0, upper=hex_area_m2)
    base["potential_area_km2"] = base["potential_area_m2"] / 1_000_000.0
    base["potential_area_share_pct"] = (base["potential_area_m2"] / max(hex_area_m2, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    base["solar_score"] = base["potential_area_share_pct"].round(1)
    base["solar_group"] = "Ingen aktiv solpotential"
    base.loc[base["large_area_m2"].gt(base["small_area_m2"]) & base["large_area_m2"].gt(0), "solar_group"] = SOLAR_LARGE_SCALE_LABEL
    base.loc[base["small_area_m2"].ge(base["large_area_m2"]) & base["small_area_m2"].gt(0), "solar_group"] = SOLAR_SMALL_SCALE_LABEL
    classes = [_solar_score_class(float(value)) for value in base["solar_score"]]
    base["solar_class"] = [item["id"] for item in classes]
    base["solar_class_label"] = [item["label"] for item in classes]
    base["solar_color"] = [item["color"] for item in classes]
    return _filter_frame_to_display_geometries(base, _h3_display_geometry_path(region, int(resolution)))


def _solar_establishment_potential_source_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
    large_frame: pd.DataFrame,
) -> pd.DataFrame:
    # Small-scale rooftop solar is a schematic demand/pedagogy layer, not a
    # contiguous land-establishment surface.
    return _combined_solar_hex_frame(region, landscape_manifest, int(resolution), pd.DataFrame(), large_frame)


def _combined_solar_hex_layer(
    name: str,
    frame: pd.DataFrame,
    display_geometry_path: str | None,
) -> dict[str, Any] | None:
    if frame.empty or not display_geometry_path:
        return None
    display_geometries = load_h3_display_geometries(display_geometry_path)
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        geometry = display_geometries.get(str(row.hex_id))
        if geometry is None:
            continue
        score = float(getattr(row, "solar_score", 0.0) or 0.0)
        area_m2 = float(getattr(row, "potential_area_m2", 0.0) or 0.0)
        area_share_pct = float(getattr(row, "potential_area_share_pct", score) or 0.0)
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": str(row.hex_id),
                    "fill": str(getattr(row, "solar_color", "#991b1b")),
                    "popup": (
                        (
                            f"<strong>{name}</strong><br>"
                            f"Area share: {area_share_pct:.1f}%<br>"
                            f"Potentiell solyta: {area_m2:,.0f} m2<br>"
                            f"Dominerande grupp: {getattr(row, 'solar_group', '-') }<br>"
                            f"Landskapstyp: {getattr(row, 'landscape_type', '-') }<br>"
                            f"H3: {row.hex_id}"
                        ).replace(",", " ")
                    ),
                    "tooltip_title": f"{name}: {area_share_pct:.1f}%",
                    "tooltip_body": f"{area_m2:,.0f} m2 - {getattr(row, 'solar_group', '')}".replace(",", " "),
                },
            }
        )
    if not features:
        return None
    return {
        "name": name,
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "fill_property": "fill",
        "legend_items": _solar_score_legend_items(),
        "legend_id": "solar_combined_hex",
        "legend_title": SOLAR_POTENTIAL_HEX_LABEL,
        "default_visible": False,
        "stroke": False,
        "weight": 0.0,
        "layer_kind": "hex",
        "opacity_family": name,
        "opacity_label": name,
    }


def _solar_potential_polygon_layer(
    small_buffer_geojson: dict[str, Any] | None,
    large_frame: pd.DataFrame,
    large_polygon_geojson: dict[str, Any] | None,
) -> dict[str, Any] | None:
    features: list[dict[str, Any]] = []
    if isinstance(small_buffer_geojson, dict):
        for feature in small_buffer_geojson.get("features") or []:
            if not isinstance(feature, dict) or not feature.get("geometry"):
                continue
            copied = json.loads(json.dumps(feature))
            props = copied.setdefault("properties", {})
            props["fill"] = "#facc15"
            props["popup"] = (
                f"<strong>{SOLAR_POTENTIAL_POLYGON_LABEL}</strong><br>"
                f"Grupp: {SOLAR_SMALL_SCALE_LABEL}<br>"
                "Faktisk polygonbuffert runt befolkningspunkter."
            )
            props["tooltip_title"] = SOLAR_POTENTIAL_POLYGON_LABEL
            props["tooltip_body"] = SOLAR_SMALL_SCALE_LABEL
            features.append(copied)

    if not large_frame.empty and isinstance(large_polygon_geojson, dict):
        has_large_score = pd.to_numeric(large_frame.get("solar_score"), errors="coerce").fillna(0.0).gt(0.0).any()
        if has_large_score:
            for feature in large_polygon_geojson.get("features") or []:
                if not isinstance(feature, dict) or not feature.get("geometry"):
                    continue
                copied = json.loads(json.dumps(feature))
                props = copied.setdefault("properties", {})
                props.setdefault("fill", "#ca8a04")
                props.setdefault(
                    "popup",
                    (
                        f"<strong>{SOLAR_POTENTIAL_POLYGON_LABEL}</strong><br>"
                        f"Grupp: {SOLAR_LARGE_SCALE_LABEL}<br>"
                        "Polygonkälla: kandidatmark v0"
                    ),
                )
                props["tooltip_title"] = SOLAR_POTENTIAL_POLYGON_LABEL
                props["tooltip_body"] = SOLAR_LARGE_SCALE_LABEL
                features.append(copied)

    if not features:
        return None
    legend_items = []
    if isinstance(small_buffer_geojson, dict) and small_buffer_geojson.get("features"):
        legend_items.append({"label": SOLAR_SMALL_SCALE_LABEL, "color": "#facc15"})
    if isinstance(large_polygon_geojson, dict) and large_polygon_geojson.get("features"):
        legend_items.append({"label": SOLAR_LARGE_SCALE_LABEL, "color": "#ca8a04"})
    if not legend_items:
        legend_items = [
            {"label": SOLAR_SMALL_SCALE_LABEL, "color": "#facc15"},
            {"label": SOLAR_LARGE_SCALE_LABEL, "color": "#ca8a04"},
        ]
    return {
        "name": SOLAR_POTENTIAL_POLYGON_LABEL,
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "fill_property": "fill",
        "legend_items": legend_items,
        "legend_id": "solar_potential_polygon",
        "legend_title": SOLAR_POTENTIAL_POLYGON_LABEL,
        "default_visible": False,
        "stroke_color": "#854d0e",
        "fill_color": "#facc15",
        "stroke_opacity": 0.72,
        "fill_opacity": 0.18,
        "weight": 1.3,
        "point_radius": 6,
        "dash_array": "6 4",
        "use_global_opacity": False,
        "z_index": 442,
        "layer_kind": "vector",
    }


def _solar_establishment_frame(
    region: dict[str, Any] | pd.DataFrame,
    small_frame: pd.DataFrame,
    large_frame: pd.DataFrame | float,
    solar_area_need_km2: float,
    solar_twh_need: float,
    solar_km2_per_twh: float,
    hex_area_km2: float | int | dict[str, Any] | None,
    h3_resolution: int | dict[str, Any] | None = None,
    social_acceptance_manifest: dict[str, Any] | str | None = None,
    social_acceptance_scenario: str | float = SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID,
    social_acceptance_allocation_priority_pct: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(region, dict):
        legacy_small_frame = region if isinstance(region, pd.DataFrame) else pd.DataFrame()
        legacy_large_frame = small_frame if isinstance(small_frame, pd.DataFrame) else pd.DataFrame()
        legacy_area_need_km2 = large_frame
        legacy_twh_need = solar_area_need_km2
        legacy_km2_per_twh = solar_twh_need
        legacy_hex_area_km2 = solar_km2_per_twh
        legacy_h3_resolution = hex_area_km2
        legacy_manifest = h3_resolution
        legacy_scenario = social_acceptance_manifest
        legacy_priority_pct = social_acceptance_scenario
        region = {}
        small_frame = legacy_small_frame
        large_frame = legacy_large_frame
        solar_area_need_km2 = float(legacy_area_need_km2 or 0.0)
        solar_twh_need = float(legacy_twh_need or 0.0)
        solar_km2_per_twh = float(legacy_km2_per_twh or math.nan)
        hex_area_km2 = float(legacy_hex_area_km2 or 0.0)
        h3_resolution = int(legacy_h3_resolution) if legacy_h3_resolution is not None else None
        social_acceptance_manifest = legacy_manifest if isinstance(legacy_manifest, dict) else None
        social_acceptance_scenario = str(legacy_scenario or SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID)
        social_acceptance_allocation_priority_pct = float(legacy_priority_pct or 0.0)

    rows: list[dict[str, Any]] = []

    def _numeric_frame_column(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(default)
        return pd.Series(default, index=frame.index, dtype="float64")

    if not small_frame.empty:
        small = small_frame[_numeric_frame_column(small_frame, "solar_v1_area_km2").gt(0.0)].copy()
        for row in small.itertuples(index=False):
            rows.append(
                {
                    "hex_id": str(row.hex_id),
                    "source_group": SOLAR_SMALL_SCALE_LABEL,
                    "potential_score": float(getattr(row, "solar_v1_score", 0.0) or 0.0),
                    "potential_area_km2": float(getattr(row, "solar_v1_area_km2", 0.0) or 0.0),
                    "outside_et": False,
                    "expansion_ring": 0,
                    "sort_group": 0,
                }
            )
    if not large_frame.empty:
        large = large_frame[_numeric_frame_column(large_frame, "solar_score").gt(0.0)].copy()
        for row in large.itertuples(index=False):
            potential_area_km2 = float(getattr(row, "potential_area_km2", 0.0) or 0.0)
            if potential_area_km2 <= 0:
                potential_area_km2 = float(getattr(row, "potential_area_m2", 0.0) or 0.0) / 1_000_000.0
            if potential_area_km2 <= 0:
                continue
            rows.append(
                {
                    "hex_id": str(row.hex_id),
                    "source_group": SOLAR_LARGE_SCALE_LABEL,
                    "potential_score": float(getattr(row, "solar_score", 0.0) or 0.0),
                    "potential_area_km2": min(float(hex_area_km2), potential_area_km2),
                    "outside_et": False,
                    "expansion_ring": 0,
                    "sort_group": 1,
                }
            )
    if not rows or float(solar_area_need_km2 or 0.0) <= 0:
        return pd.DataFrame(), {
            "selected_area_km2": 0.0,
            "unmet_area_km2": max(0.0, float(solar_area_need_km2 or 0.0)),
            "selected_hex_count": 0,
        }
    candidates = pd.DataFrame(rows)
    if h3_resolution is not None:
        candidates = _apply_landscape_priority_to_allocation_frame(
            candidates,
            region,
            "solar",
            int(h3_resolution),
        )
        candidates = _apply_social_acceptance_priority_to_solar_candidates(
            candidates,
            social_acceptance_manifest,
            social_acceptance_scenario,
            int(h3_resolution),
            float(social_acceptance_allocation_priority_pct or 0.0),
        )
    if "allocation_priority_score" not in candidates.columns:
        candidates["allocation_priority_score"] = (
            pd.to_numeric(candidates.get("potential_score", pd.Series(0.0, index=candidates.index)), errors="coerce")
            .fillna(0.0)
            .clip(lower=0.0, upper=100.0)
            .div(100.0)
        )
        candidates["landscape_priority_score"] = 0.0
        candidates["technical_priority_score"] = candidates["allocation_priority_score"]
        candidates["allocation_priority_reason"] = "Prioriteras efter solpotential."
    if "allocation_priority_score" in candidates.columns:
        candidates = candidates.sort_values(
            ["allocation_priority_score", "potential_score", "potential_area_km2", "sort_group", "hex_id"],
            ascending=[False, False, False, True, True],
        )
    else:
        candidates = candidates.sort_values(["sort_group", "potential_score", "potential_area_km2", "hex_id"], ascending=[True, False, False, True])
    remaining = float(solar_area_need_km2 or 0.0)
    selected_rows: list[dict[str, Any]] = []
    for rank, row in enumerate(candidates.itertuples(index=False), start=1):
        available_area = max(0.0, float(row.potential_area_km2 or 0.0))
        allocated_area = min(available_area, remaining)
        if allocated_area <= 0:
            continue
        if solar_km2_per_twh > 0 and math.isfinite(float(solar_km2_per_twh)):
            allocated_twh = allocated_area / float(solar_km2_per_twh)
        elif solar_area_need_km2 > 0:
            allocated_twh = float(solar_twh_need or 0.0) * allocated_area / float(solar_area_need_km2)
        else:
            allocated_twh = 0.0
        remaining = max(0.0, remaining - allocated_area)
        selected_rows.append(
            {
                "hex_id": str(row.hex_id),
                "selected_rank": int(rank),
                "source_group": str(row.source_group),
                "potential_score": float(row.potential_score or 0.0),
                "potential_area_km2": available_area,
                "allocated_area_km2": allocated_area,
                "allocated_twh": allocated_twh,
                "allocated_gwh": allocated_twh * 1000.0,
                "allocated_hex_share_pct": (allocated_area / max(float(hex_area_km2), 1e-9)) * 100.0,
                "remaining_area_after_km2": remaining,
                "outside_et": bool(getattr(row, "outside_et", False)),
                "expansion_ring": int(getattr(row, "expansion_ring", 0) or 0),
                "allocation_phase": "Inom LP",
                "landscape_priority_score": float(getattr(row, "landscape_priority_score", 0.0) or 0.0),
                "allocation_priority_score": float(getattr(row, "allocation_priority_score", 0.0) or 0.0),
                "allocation_priority_reason": str(getattr(row, "allocation_priority_reason", "") or ""),
                "social_acceptance_value": float(getattr(row, "social_acceptance_value", 1.0) or 1.0),
                "social_acceptance_allocation_priority_pct": float(
                    getattr(row, "social_acceptance_allocation_priority_pct", 0.0) or 0.0
                ),
                "social_acceptance_priority_score": float(getattr(row, "social_acceptance_priority_score", 0.0) or 0.0),
            }
        )
        if remaining <= 1e-9:
            break
    selected = pd.DataFrame(selected_rows)
    stats = {
        "selected_area_km2": float(selected["allocated_area_km2"].sum()) if not selected.empty else 0.0,
        "unmet_area_km2": remaining,
        "selected_hex_count": int(len(selected)),
        "selected_twh": float(selected["allocated_twh"].sum()) if not selected.empty else 0.0,
        "available_candidate_hex": int(len(candidates)),
        "available_candidate_area_km2": float(candidates["potential_area_km2"].sum()),
    }
    return selected, stats


def _rollup_solar_establishment_frame(
    selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
) -> pd.DataFrame:
    if selected.empty or int(target_resolution) >= int(source_resolution):
        return selected.copy()

    work = selected.copy()

    def _numeric_column(column: str, default: float = 0.0) -> pd.Series:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce").fillna(default)
        return pd.Series(default, index=work.index, dtype="float64")

    work["hex_id"] = work["hex_id"].astype(str).map(lambda value: h3.cell_to_parent(value, int(target_resolution)))
    work["allocated_area_km2"] = _numeric_column("allocated_area_km2", 0.0)
    work["potential_area_km2"] = _numeric_column("potential_area_km2", 0.0)
    work["allocated_twh"] = _numeric_column("allocated_twh", 0.0)
    work["selected_rank"] = _numeric_column("selected_rank", 0.0).astype(int)
    work["potential_score"] = _numeric_column("potential_score", 0.0)
    work["landscape_priority_score"] = _numeric_column("landscape_priority_score", 0.0)
    work["allocation_priority_score"] = _numeric_column("allocation_priority_score", 0.0)
    work["social_acceptance_priority_score"] = _numeric_column("social_acceptance_priority_score", 0.0)
    work["social_acceptance_value"] = _numeric_column("social_acceptance_value", 1.0)
    work["social_acceptance_allocation_priority_pct"] = _numeric_column("social_acceptance_allocation_priority_pct", 0.0)
    work["expansion_ring"] = _numeric_column("expansion_ring", 0.0).astype(int)
    if "outside_et" not in work.columns:
        work["outside_et"] = False
    if "source_group" not in work.columns:
        work["source_group"] = ""
    if "allocation_priority_reason" not in work.columns:
        work["allocation_priority_reason"] = ""
    work["outside_et"] = work["outside_et"].fillna(False).astype(bool)
    work["outside_area_km2"] = work["allocated_area_km2"].where(work["outside_et"], 0.0)
    work["inside_area_km2"] = work["allocated_area_km2"].where(~work["outside_et"], 0.0)

    def _source_group_label(values: pd.Series) -> str:
        labels = [str(value) for value in values.dropna().tolist() if str(value)]
        unique = list(dict.fromkeys(labels))
        return ", ".join(unique[:3])

    rolled = (
        work.groupby("hex_id", as_index=False)
        .agg(
            selected_rank=("selected_rank", "min"),
            source_group=("source_group", _source_group_label),
            potential_score=("potential_score", "max"),
            landscape_priority_score=("landscape_priority_score", "max"),
            allocation_priority_score=("allocation_priority_score", "max"),
            allocation_priority_reason=("allocation_priority_reason", _source_group_label),
            social_acceptance_priority_score=("social_acceptance_priority_score", "max"),
            social_acceptance_value=("social_acceptance_value", "mean"),
            social_acceptance_allocation_priority_pct=("social_acceptance_allocation_priority_pct", "max"),
            potential_area_km2=("potential_area_km2", "sum"),
            allocated_area_km2=("allocated_area_km2", "sum"),
            allocated_twh=("allocated_twh", "sum"),
            outside_area_km2=("outside_area_km2", "sum"),
            inside_area_km2=("inside_area_km2", "sum"),
            expansion_ring=("expansion_ring", "max"),
        )
        .sort_values(["selected_rank", "hex_id"])
        .reset_index(drop=True)
    )
    hex_area = h3_hex_area_km2(int(target_resolution))
    rolled["outside_et"] = rolled["outside_area_km2"].gt(rolled["inside_area_km2"])
    rolled["allocation_phase"] = rolled["outside_et"].map(lambda value: "Utanför LP" if value else "Inom LP")
    rolled["allocated_hex_share_pct"] = (rolled["allocated_area_km2"] / max(hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    rolled["remaining_area_after_km2"] = 0.0
    rolled["allocated_gwh"] = rolled["allocated_twh"] * 1000.0
    return rolled


def _expand_solar_area_outside_lp(
    source_frame: pd.DataFrame,
    selected_frame: pd.DataFrame,
    proposal_stats: dict[str, Any],
    display_geometry_path: str | None,
    hex_area_km2: float,
    solar_twh_need: float,
    solar_area_need_km2: float,
    solar_km2_per_twh: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if source_frame.empty or not display_geometry_path or hex_area_km2 <= 0:
        return selected_frame, proposal_stats

    shortage = float(proposal_stats.get("unmet_area_km2", 0.0) or 0.0)
    proposal_stats["lp_selected_area_km2"] = float(proposal_stats.get("selected_area_km2", 0.0) or 0.0)
    proposal_stats["lp_unmet_area_km2"] = max(0.0, shortage)
    if shortage <= 1e-9:
        proposal_stats.setdefault("outside_selected_area_km2", 0.0)
        proposal_stats.setdefault("outside_hex_count", 0)
        proposal_stats.setdefault("max_expansion_ring", 0)
        return selected_frame, proposal_stats

    display_hexes = set(load_h3_display_geometries(display_geometry_path))
    if not display_hexes:
        return selected_frame, proposal_stats

    work = source_frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    work["solar_score"] = pd.to_numeric(work.get("solar_score"), errors="coerce").fillna(0.0)
    lp_hexes = set(work.loc[work["solar_score"].gt(0.0), "hex_id"].astype(str)) & display_hexes
    selected_hexes = set(selected_frame.get("hex_id", pd.Series(dtype=str)).astype(str)) if not selected_frame.empty else set()
    anchor_hexes = (selected_hexes or lp_hexes) & display_hexes

    neighbor_map = _wind_runtime_hex_neighbor_map(display_geometry_path)
    distance_lookup: dict[str, int] = {}
    if anchor_hexes:
        visited = set(anchor_hexes)
        frontier: deque[tuple[str, int]] = deque((hex_id, 0) for hex_id in anchor_hexes)
        while frontier:
            current, distance = frontier.popleft()
            for neighbor in neighbor_map.get(current, []):
                neighbor = str(neighbor)
                if neighbor not in display_hexes or neighbor in visited:
                    continue
                visited.add(neighbor)
                distance_lookup[neighbor] = distance + 1
                frontier.append((neighbor, distance + 1))

    outside_hexes = sorted(display_hexes - lp_hexes)
    outside = pd.DataFrame({"hex_id": outside_hexes})
    if outside.empty:
        return selected_frame, proposal_stats
    priority_cols = [
        column
        for column in [
            "hex_id",
            "landscape_priority_score",
            "allocation_priority_score",
            "allocation_priority_reason",
            "social_acceptance_priority_score",
            "social_acceptance_value",
            "social_acceptance_allocation_priority_pct",
        ]
        if column in work.columns
    ]
    if len(priority_cols) > 1:
        outside = outside.merge(work[priority_cols].drop_duplicates(subset=["hex_id"]), on="hex_id", how="left")
    outside["expansion_ring"] = outside["hex_id"].map(distance_lookup).fillna(999999).astype(int)
    outside = outside[outside["expansion_ring"].lt(999999)].copy()
    if outside.empty:
        return selected_frame, proposal_stats
    outside["allocation_priority_score"] = pd.to_numeric(
        outside.get("allocation_priority_score", pd.Series(0.0, index=outside.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    outside = outside.sort_values(
        ["expansion_ring", "allocation_priority_score", "hex_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    remaining = shortage
    start_rank = int(len(selected_frame)) + 1
    rows: list[dict[str, Any]] = []
    for offset, row in enumerate(outside.itertuples(index=False), start=0):
        allocated_area = min(float(hex_area_km2), max(0.0, remaining))
        if allocated_area <= 0:
            break
        if solar_km2_per_twh > 0 and math.isfinite(float(solar_km2_per_twh)):
            allocated_twh = allocated_area / float(solar_km2_per_twh)
        elif solar_area_need_km2 > 0:
            allocated_twh = float(solar_twh_need or 0.0) * allocated_area / float(solar_area_need_km2)
        else:
            allocated_twh = 0.0
        remaining = max(0.0, remaining - allocated_area)
        rows.append(
            {
                "hex_id": str(row.hex_id),
                "selected_rank": start_rank + offset,
                "source_group": "Utanför LP",
                "potential_score": 0.0,
                "potential_area_km2": 0.0,
                "allocated_area_km2": allocated_area,
                "allocated_twh": allocated_twh,
                "allocated_gwh": allocated_twh * 1000.0,
                "allocated_hex_share_pct": (allocated_area / max(float(hex_area_km2), 1e-9)) * 100.0,
                "remaining_area_after_km2": remaining,
                "outside_et": True,
                "expansion_ring": int(row.expansion_ring),
                "allocation_phase": "Utanför LP",
                "landscape_priority_score": float(getattr(row, "landscape_priority_score", 0.0) or 0.0),
                "allocation_priority_score": float(getattr(row, "allocation_priority_score", 0.0) or 0.0),
                "allocation_priority_reason": str(getattr(row, "allocation_priority_reason", "") or ""),
                "social_acceptance_priority_score": float(getattr(row, "social_acceptance_priority_score", 0.0) or 0.0),
                "social_acceptance_value": float(getattr(row, "social_acceptance_value", 1.0) or 1.0),
                "social_acceptance_allocation_priority_pct": float(
                    getattr(row, "social_acceptance_allocation_priority_pct", 0.0) or 0.0
                ),
            }
        )
        if remaining <= 1e-9:
            break

    if not rows:
        return selected_frame, proposal_stats

    outside_frame = pd.DataFrame(rows)
    if "outside_et" not in selected_frame.columns and not selected_frame.empty:
        selected_frame = selected_frame.copy()
        selected_frame["outside_et"] = False
    combined = pd.concat([selected_frame, outside_frame], ignore_index=True, sort=False)
    outside_area = float(outside_frame["allocated_area_km2"].sum())
    proposal_stats.update(
        {
            "selected_area_km2": float(proposal_stats.get("lp_selected_area_km2", 0.0) or 0.0) + outside_area,
            "unmet_area_km2": max(0.0, remaining),
            "selected_hex_count": int(len(combined)),
            "outside_selected_area_km2": outside_area,
            "outside_hex_count": int(len(outside_frame)),
            "outside_candidate_hex": int(len(outside)),
            "outside_candidate_area_km2": float(len(outside) * float(hex_area_km2)),
            "max_expansion_ring": int(outside_frame["expansion_ring"].max()),
            "selected_twh": float(combined.get("allocated_twh", pd.Series(dtype=float)).sum()),
        }
    )
    return combined, proposal_stats


def _solar_v1_stats(frame: pd.DataFrame, energy_model_state: dict[str, Any]) -> dict[str, float]:
    total_area_km2 = float(pd.to_numeric(frame.get("solar_v1_area_km2", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not frame.empty else 0.0
    solar_area_need = float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0) if energy_model_state.get("available") else 0.0
    solar_twh_need = float(energy_model_state.get("solar_twh", 0.0) or 0.0) if energy_model_state.get("available") else 0.0
    solar_km2_per_twh = float(energy_model_state.get("solar_km2_per_twh", math.nan) or math.nan) if energy_model_state.get("available") else math.nan
    covered_area_km2 = min(total_area_km2, solar_area_need) if solar_area_need > 0 else 0.0
    remaining_area_km2 = max(0.0, solar_area_need - total_area_km2) if solar_area_need > 0 else 0.0
    covered_share_pct = (covered_area_km2 / solar_area_need * 100.0) if solar_area_need > 0 else 0.0
    if solar_km2_per_twh > 0 and math.isfinite(solar_km2_per_twh):
        covered_twh = covered_area_km2 / solar_km2_per_twh
    elif solar_area_need > 0:
        covered_twh = solar_twh_need * covered_area_km2 / solar_area_need
    else:
        covered_twh = 0.0
    return {
        "total_area_km2": total_area_km2,
        "solar_area_need_km2": solar_area_need,
        "covered_area_km2": covered_area_km2,
        "covered_share_pct": covered_share_pct,
        "remaining_area_km2": remaining_area_km2,
        "covered_twh": min(covered_twh, solar_twh_need) if solar_twh_need > 0 else covered_twh,
        "remaining_twh": max(0.0, solar_twh_need - covered_twh) if solar_twh_need > 0 else 0.0,
        "population": float(pd.to_numeric(frame.get("population", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not frame.empty else 0.0,
    }


def _combined_establishment_stats(energy_model_state: dict[str, Any]) -> dict[str, float]:
    proposal_stats = energy_model_state.get("proposal_stats") if isinstance(energy_model_state, dict) else None
    solar_v1_stats = energy_model_state.get("solar_v1_stats") if isinstance(energy_model_state, dict) else None
    solar_proposal_stats = energy_model_state.get("solar_proposal_stats") if isinstance(energy_model_state, dict) else None
    wind_area_need = float(energy_model_state.get("wind_area_need_km2", 0.0) or 0.0)
    solar_area_need = float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0)
    wind_selected_area = float((proposal_stats or {}).get("selected_area_km2", 0.0) or 0.0) if isinstance(proposal_stats, dict) else 0.0
    wind_unmet_area = float((proposal_stats or {}).get("unmet_area_km2", wind_area_need) or 0.0) if isinstance(proposal_stats, dict) else wind_area_need
    if isinstance(solar_proposal_stats, dict):
        solar_v1_area = float(solar_proposal_stats.get("selected_area_km2", 0.0) or 0.0)
        solar_unmet_area = float(solar_proposal_stats.get("unmet_area_km2", max(0.0, solar_area_need - solar_v1_area)) or 0.0)
    else:
        solar_v1_area = float((solar_v1_stats or {}).get("covered_area_km2", 0.0) or 0.0) if isinstance(solar_v1_stats, dict) else 0.0
        solar_unmet_area = max(0.0, solar_area_need - solar_v1_area)
    total_need = wind_area_need + solar_area_need
    total_covered = min(wind_selected_area, wind_area_need) + min(solar_v1_area, solar_area_need)
    return {
        "wind_selected_area_km2": wind_selected_area,
        "wind_unmet_area_km2": wind_unmet_area,
        "solar_v1_covered_area_km2": solar_v1_area,
        "solar_unmet_area_km2": solar_unmet_area,
        "total_need_area_km2": total_need,
        "total_covered_area_km2": total_covered,
        "total_covered_share_pct": (total_covered / total_need * 100.0) if total_need > 0 else 0.0,
    }


def _count_text(value: int | float) -> str:
    return f"{int(value):,}".replace(",", " ")


AREA_DISPLAY_UNITS = ["km²", "ha", "m²", "hex"]


def _format_measure_number(value: float, decimals: int = 0) -> str:
    return f"{float(value):,.{int(decimals)}f}".replace(",", " ")


def _format_area_primary(area_km2: float, unit: str, hex_area_km2: float = 0.0) -> str:
    area = max(0.0, float(area_km2 or 0.0))
    selected_unit = str(unit or "km²")
    hex_area = max(0.0, float(hex_area_km2 or 0.0))
    if selected_unit == "hex":
        if hex_area <= 0:
            return "0 hex"
        return f"{_format_measure_number(area / hex_area, 0)} hex"
    if selected_unit == "ha":
        return f"{_format_measure_number(area * 100.0, 0)} ha"
    if selected_unit == "m²":
        return f"{_format_measure_number(area * 1_000_000.0, 0)} m²"
    return f"{area:.2f} km²"


def _format_area_context(area_km2: float, unit: str, hex_area_km2: float = 0.0) -> str:
    area = max(0.0, float(area_km2 or 0.0))
    selected_unit = str(unit or "km²")
    hex_area = max(0.0, float(hex_area_km2 or 0.0))
    if selected_unit == "km²":
        return f"{_format_measure_number(area * 100.0, 0)} ha"
    if selected_unit == "ha":
        return f"{area:.2f} km²"
    if selected_unit == "m²":
        return f"{area:.2f} km²"
    if selected_unit == "hex" and hex_area > 0:
        return f"{area:.2f} km²"
    return ""


def _format_area_with_context(area_km2: float, unit: str, hex_area_km2: float = 0.0) -> str:
    primary = _format_area_primary(area_km2, unit, hex_area_km2)
    context = _format_area_context(area_km2, unit, hex_area_km2)
    return f"{primary} ({context})" if context else primary


def _percent_change(current: float, previous: float | None) -> float | None:
    if previous is None:
        return 0.0
    current_value = float(current or 0.0)
    previous_value = float(previous or 0.0)
    if abs(previous_value) < 1e-9:
        return 0.0 if abs(current_value) < 1e-9 else None
    return (current_value - previous_value) / abs(previous_value) * 100.0


def _change_delta_text(current: float, previous: float | None) -> str | None:
    if previous is not None and abs(float(previous or 0.0)) < 1e-9 and abs(float(current or 0.0)) >= 1e-9:
        return "+nytt"
    change = _percent_change(current, previous)
    if change is None:
        return None
    if abs(change) < 0.05:
        return "0.0%"
    return f"{change:+.1f}%"


def _change_delta_color(current: float, previous: float | None) -> str:
    if previous is not None and abs(float(previous or 0.0)) < 1e-9 and abs(float(current or 0.0)) >= 1e-9:
        return "normal"
    change = _percent_change(current, previous)
    if change is None or abs(change) < 0.05:
        return "off"
    return "normal"


def _change_badge_html(current: float, previous: float | None) -> str:
    if previous is not None and abs(float(previous or 0.0)) < 1e-9 and abs(float(current or 0.0)) >= 1e-9:
        return (
            "<span style='display:inline-block;margin-top:0.12rem;padding:0.08rem 0.32rem;"
            "border-radius:999px;background:#dcfce7;color:#15803d;font-size:0.72rem;font-weight:650;"
            "white-space:nowrap;'>↑ nytt</span>"
        )
    change = _percent_change(current, previous)
    if change is None:
        return ""
    if abs(change) < 0.05:
        arrow = "→"
        text = "0.0%"
        color = "#92400e"
        background = "#fef3c7"
    elif change > 0:
        arrow = "↑"
        text = f"{change:.1f}%"
        color = "#15803d"
        background = "#dcfce7"
    else:
        arrow = "↓"
        text = f"{abs(change):.1f}%"
        color = "#b91c1c"
        background = "#fee2e2"
    return (
        f"<span style='display:inline-block;margin-top:0.12rem;padding:0.08rem 0.32rem;"
        f"border-radius:999px;background:{background};color:{color};font-size:0.72rem;font-weight:650;"
        f"white-space:nowrap;'>{arrow} {text}</span>"
    )


def _value_with_change_html(value: str, current: float, previous: float | None) -> str:
    return (
        "<div style='display:flex;flex-direction:column;align-items:flex-start;gap:0.04rem;'>"
        f"<span>{html.escape(str(value))}</span>"
        f"{_change_badge_html(current, previous)}"
        "</div>"
    )


def _establishment_change_snapshot_key(energy_model_state: dict[str, Any]) -> str:
    region_id = str(energy_model_state.get("region_id", "region") or "region")
    return f"establishment_change_snapshot_{region_id}"


def _snapshot_fingerprint(snapshot: dict[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple((str(key), round(float(value or 0.0), 9)) for key, value in sorted(snapshot.items()))


def _previous_snapshot_value(snapshot: dict[str, Any], key: str) -> float | None:
    if key not in snapshot:
        return None
    try:
        return float(snapshot.get(key))
    except Exception:
        return None


def _render_impact_change_table(rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    headers = [
        "teknik",
        "energi",
        "ytbehov",
        "potential efter filter",
        "potential efter acceptanspåverkan",
        "inom potential",
        "outnyttjad potential",
        "ytbehov utanför potential",
        "andel inom potential",
    ]

    def _header_html(header: str) -> str:
        wrapped_headers = {
            "potential efter filter": "potential<br>efter filter",
            "potential efter acceptanspåverkan": "potential<br>efter acceptans-<br>påverkan",
            "inom potential": "inom<br>potential",
            "outnyttjad potential": "outnyttjad<br>potential",
            "ytbehov utanför potential": "ytbehov utanför<br>potential",
            "andel inom potential": "andel inom<br>potential",
        }
        if header not in wrapped_headers:
            return html.escape(header)
        return wrapped_headers[header]

    header_classes = {
        "teknik": "change-col-tech",
        "energi": "change-col-energy",
        "ytbehov": "change-col-area",
        "potential efter filter": "change-col-filter",
        "potential efter acceptanspåverkan": "change-col-acceptance",
        "inom potential": "change-col-area",
        "outnyttjad potential": "change-col-unused",
        "ytbehov utanför potential": "change-col-outside",
        "andel inom potential": "change-col-share",
    }
    colgroup_html = (
        "<colgroup>"
        + "".join(f"<col class='{header_classes.get(header, 'change-col-value')}'>" for header in headers)
        + "</colgroup>"
    )
    header_html = "".join(
        f"<th class='{header_classes.get(header, 'change-col-value')}'>{_header_html(header)}</th>"
        for header in headers
    )
    row_html = ""
    for row in rows:
        row_html += (
            "<tr>"
            + "".join(
                f"<td class='{header_classes.get(header, 'change-col-value')}'>{row.get(header, '')}</td>"
                for header in headers
            )
            + "</tr>"
        )
    st.markdown(
        "<div class='change-table-wrap' data-potential-tutorial-anchor='results-table'>"
        "<table class='change-table'>"
        f"{colgroup_html}"
        "<thead><tr>"
        f"{header_html}"
        "</tr></thead><tbody>"
        f"{row_html}"
        "</tbody></table></div>"
        "<style>"
        ".change-table-wrap{display:block;width:100%;max-width:100%;overflow-x:auto;border:1px solid rgba(49,51,63,0.14);border-radius:6px;margin-top:0.35rem;}"
        ".change-table{width:100%;min-width:645px;border-collapse:collapse;font-size:0.68rem;line-height:1.12;table-layout:fixed;}"
        ".change-table .change-col-tech{width:6%;}"
        ".change-table .change-col-energy{width:10%;}"
        ".change-table .change-col-area{width:10%;}"
        ".change-table .change-col-filter{width:13%;}"
        ".change-table .change-col-acceptance{width:15%;}"
        ".change-table .change-col-unused{width:13%;}"
        ".change-table .change-col-outside{width:13%;}"
        ".change-table .change-col-share{width:10%;}"
        ".change-table th{background:#f8fafc;color:#475569;text-align:left;font-weight:600;padding:0.22rem 0.3rem;border-bottom:1px solid rgba(49,51,63,0.12);white-space:normal;overflow-wrap:anywhere;line-height:1.12;}"
        ".change-table td{padding:0.22rem 0.3rem;border-top:1px solid rgba(49,51,63,0.08);vertical-align:top;white-space:normal;overflow-wrap:anywhere;}"
        ".change-table td div{gap:0!important;min-width:0;}"
        ".change-table td span:first-child{white-space:nowrap;}"
        "@media (max-width:900px){.change-table{font-size:0.66rem;}.change-table-wrap{width:100%;}}"
        "</style>",
        unsafe_allow_html=True,
    )


def _format_hex_size_caption(h3_resolution: int | None, hex_area_km2: float) -> str:
    area = max(0.0, float(hex_area_km2 or 0.0))
    resolution_label = f"R{int(h3_resolution)}" if h3_resolution is not None else "vald H3"
    return (
        f"1 {resolution_label}-hex ≈ {area:.4f} km² = "
        f"{area * 100.0:.2f} ha = {_format_measure_number(area * 1_000_000.0, 0)} m²."
    )


def _lp_selected_area_from_stats(
    stats: dict[str, Any] | None,
    selected_area_fallback: float = 0.0,
    outside_area_fallback: float = 0.0,
) -> float:
    if not isinstance(stats, dict):
        return max(0.0, float(selected_area_fallback or 0.0) - float(outside_area_fallback or 0.0))
    raw_lp = stats.get("lp_selected_area_km2")
    if raw_lp is not None:
        try:
            return max(0.0, float(raw_lp or 0.0))
        except Exception:
            return 0.0
    selected_area = float(stats.get("selected_area_km2", selected_area_fallback) or 0.0)
    outside_area = float(stats.get("outside_selected_area_km2", outside_area_fallback) or 0.0)
    return max(0.0, selected_area - outside_area)


def _acceptance_adjusted_technology_metrics(
    technology: str,
    need_area_km2: float,
    filtered_potential_area_km2: float,
    social_effect: dict[str, Any] | None,
) -> dict[str, float]:
    need_area = max(0.0, float(need_area_km2 or 0.0))
    filtered_potential = max(0.0, float(filtered_potential_area_km2 or 0.0))
    ratio = 1.0
    if isinstance(social_effect, dict):
        try:
            ratio = float(social_effect.get(f"{technology}_potential_acceptance_ratio", 1.0) or 1.0)
        except Exception:
            ratio = 1.0
    ratio = max(0.0, min(1.0, ratio))
    potential_after_acceptance = filtered_potential * ratio
    inside_potential = min(need_area, potential_after_acceptance)
    outside_need = max(0.0, need_area - inside_potential)
    unused_potential = max(0.0, potential_after_acceptance - inside_potential)
    return {
        "need_area_km2": need_area,
        "filtered_potential_area_km2": filtered_potential,
        "potential_acceptance_ratio": ratio,
        "potential_after_acceptance_km2": potential_after_acceptance,
        "inside_potential_km2": inside_potential,
        "outside_need_km2": outside_need,
        "unused_potential_km2": unused_potential,
        "coverage_pct": (inside_potential / need_area * 100.0) if need_area > 0 else 0.0,
    }


def _acceptance_adjusted_capacity_metrics(
    wind_need_area_km2: float,
    wind_filtered_potential_area_km2: float,
    solar_need_area_km2: float,
    solar_filtered_potential_area_km2: float,
    social_effect: dict[str, Any] | None,
) -> dict[str, Any]:
    wind = _acceptance_adjusted_technology_metrics(
        "wind",
        wind_need_area_km2,
        wind_filtered_potential_area_km2,
        social_effect,
    )
    solar = _acceptance_adjusted_technology_metrics(
        "solar",
        solar_need_area_km2,
        solar_filtered_potential_area_km2,
        social_effect,
    )
    total_need = wind["need_area_km2"] + solar["need_area_km2"]
    total_inside = wind["inside_potential_km2"] + solar["inside_potential_km2"]
    total = {
        "need_area_km2": total_need,
        "filtered_potential_area_km2": wind["filtered_potential_area_km2"] + solar["filtered_potential_area_km2"],
        "potential_after_acceptance_km2": wind["potential_after_acceptance_km2"] + solar["potential_after_acceptance_km2"],
        "inside_potential_km2": total_inside,
        "outside_need_km2": wind["outside_need_km2"] + solar["outside_need_km2"],
        "unused_potential_km2": wind["unused_potential_km2"] + solar["unused_potential_km2"],
        "coverage_pct": (total_inside / total_need * 100.0) if total_need > 0 else 0.0,
    }
    return {"wind": wind, "solar": solar, "total": total}


def _combined_outside_lp_shortage_stats(frame: pd.DataFrame, hex_area_km2: float) -> dict[str, float]:
    def _stats_from_area(wind_area_value: float, solar_area_value: float) -> dict[str, float]:
        hex_area = max(float(hex_area_km2 or 0.0), 1e-9)
        wind_count = int(math.ceil(max(0.0, float(wind_area_value or 0.0)) / hex_area))
        solar_count = int(math.ceil(max(0.0, float(solar_area_value or 0.0)) / hex_area))
        return {
            "wind_hex_count": wind_count,
            "solar_hex_count": solar_count,
            "both_hex_count": 0,
            "total_shortage_hex_count": wind_count + solar_count,
            "wind_area_km2": max(0.0, float(wind_area_value or 0.0)),
            "solar_area_km2": max(0.0, float(solar_area_value or 0.0)),
            "hex_area_km2": float(hex_area_km2 or 0.0),
        }

    if frame.empty:
        return _stats_from_area(0.0, 0.0)
    wind_area = pd.to_numeric(frame.get("wind_outside_lp_area_km2", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0).clip(lower=0.0)
    solar_area = pd.to_numeric(frame.get("solar_outside_lp_area_km2", pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0).clip(lower=0.0)
    wind_mask = wind_area.gt(0.0)
    solar_mask = solar_area.gt(0.0)
    total_mask = wind_mask | solar_mask
    return {
        "wind_hex_count": int(wind_mask.sum()),
        "solar_hex_count": int(solar_mask.sum()),
        "both_hex_count": int((wind_mask & solar_mask).sum()),
        "total_shortage_hex_count": int(total_mask.sum()),
        "wind_area_km2": float(wind_area.sum()),
        "solar_area_km2": float(solar_area.sum()),
        "hex_area_km2": float(hex_area_km2 or 0.0),
    }


def _outside_need_stats_from_areas(wind_area_km2: float, solar_area_km2: float, hex_area_km2: float) -> dict[str, float]:
    hex_area = max(float(hex_area_km2 or 0.0), 1e-9)
    wind_area = max(0.0, float(wind_area_km2 or 0.0))
    solar_area = max(0.0, float(solar_area_km2 or 0.0))
    if wind_area < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2:
        wind_area = 0.0
    if solar_area < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2:
        solar_area = 0.0
    wind_count = int(math.ceil(wind_area / hex_area)) if wind_area > 0 else 0
    solar_count = int(math.ceil(solar_area / hex_area)) if solar_area > 0 else 0
    return {
        "wind_hex_count": wind_count,
        "solar_hex_count": solar_count,
        "both_hex_count": 0,
        "total_shortage_hex_count": wind_count + solar_count,
        "wind_area_km2": wind_area,
        "solar_area_km2": solar_area,
        "hex_area_km2": float(hex_area_km2 or 0.0),
    }


def _render_shortage_hex_stack_card(stats: dict[str, Any], unit: str = "km²") -> None:
    total_count = int(stats.get("total_shortage_hex_count", 0) or 0)
    wind_count = int(stats.get("wind_hex_count", 0) or 0)
    solar_count = int(stats.get("solar_hex_count", 0) or 0)
    both_count = int(stats.get("both_hex_count", 0) or 0)
    wind_area = float(stats.get("wind_area_km2", 0.0) or 0.0)
    solar_area = float(stats.get("solar_area_km2", 0.0) or 0.0)
    hex_area = float(stats.get("hex_area_km2", 0.0) or 0.0)
    max_count = max(total_count, wind_count, solar_count, 1)
    symbol_scale = max(1, int(math.ceil(max_count / 64)))

    def _hex_symbols(count: int, fill: str) -> str:
        symbol_count = int(math.ceil(max(0, count) / symbol_scale)) if count > 0 else 0
        hexes = "".join(
            f"<span style='display:inline-block;width:0.46rem;height:0.40rem;margin:0.035rem;background:{fill};"
            "border:1px solid #111111;clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);'></span>"
            for _ in range(min(symbol_count, 64))
        )
        if symbol_count > 64:
            hexes += "<span style='font-size:0.72rem;color:#6b7280;margin-left:0.2rem;'>+</span>"
        return hexes or "<span style='font-size:0.74rem;color:#6b7280;'>Inga bristhex</span>"

    def _row(label: str, count: int, area: float, accent: str) -> str:
        area_text = _format_area_with_context(area, unit, hex_area)
        return (
            "<div style='border-left:4px solid "
            f"{accent};padding:0.42rem 0.5rem;margin:0.35rem 0;border-radius:6px;"
            "background:rgba(255,255,255,0.68);border-top:1px solid rgba(49,51,63,0.12);"
            "border-right:1px solid rgba(49,51,63,0.12);border-bottom:1px solid rgba(49,51,63,0.12);'>"
            "<div style='display:flex;justify-content:space-between;gap:0.5rem;font-size:0.82rem;font-weight:700;'>"
            f"<span>{label}</span><span>{_count_text(count)} hex</span></div>"
            f"<div style='font-size:0.74rem;color:#6b7280;margin:0.08rem 0 0.25rem;'>{area_text} utanför landskapets potential</div>"
            f"<div style='line-height:0.5rem;'>{_hex_symbols(count, accent)}</div>"
            "</div>"
        )

    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:0.86rem;font-weight:750;margin-bottom:0.2rem;'>{OUTSIDE_LP_NEED_LAYER_LABEL}</div>"
            "<div style='font-size:0.75rem;color:#6b7280;margin-bottom:0.35rem;'>"
            "Samma ytbudget visas schematiskt i separata fält utanför ön, inte som faktisk placering.</div>"
            + _row("Vind behöver yta", wind_count, wind_area, ESTABLISHMENT_CLASS_SPECS["wind_only"]["color"])
            + _row("Sol behöver yta", solar_count, solar_area, ESTABLISHMENT_CLASS_SPECS["solar_only"]["color"])
            + (
                f"<div style='font-size:0.74rem;color:#6b7280;margin-top:0.2rem;'>"
                f"Unika ytbehovshex: {_count_text(total_count)}. "
                f"Både vind och sol i samma hex: {_count_text(both_count)}. "
                f"1 symbol ≈ {_count_text(symbol_scale)} hex.</div>"
            ),
            unsafe_allow_html=True,
        )


def _wind_source_frame(
    landscape_manifest: dict[str, Any],
    solar_rules: dict[str, Any],
    ui_params: dict[str, float],
    group_layer_selection: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    return wind_acceptance_potential_frame(
        landscape_manifest,
        _class_breaks(solar_rules),
        _wind_score_params_from_ui(ui_params),
        ui_params,
        group_layer_map=group_layer_selection,
    )


def _wind_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    solar_rules: dict[str, Any],
    resolution: int,
    ui_params: dict[str, float],
    group_layer_selection: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    base = _wind_source_frame(landscape_manifest, solar_rules, ui_params, group_layer_selection=group_layer_selection)
    frame = wind_acceptance_rollup_frame(base, resolution, _class_breaks(solar_rules))
    return _filter_frame_to_display_geometries(frame, _h3_display_geometry_path(region, resolution))


@st.cache_data(show_spinner=False)
def _landscape_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
) -> pd.DataFrame:
    frame = landscape_frame_for_resolution(landscape_manifest, resolution)
    return _filter_frame_to_display_geometries(frame, _h3_display_geometry_path(region, resolution))


def _pdf_landscape_manifest(landscape_manifest: dict[str, Any]) -> dict[str, Any] | None:
    pdf_path = landscape_manifest.get("pdf_landscape_geojson")
    if not pdf_path:
        if not bool(landscape_manifest.get("is_lablab_landscape")):
            return None
        manifest = landscape_manifest.copy()
        manifest["use_region_display_geometries"] = bool(
            landscape_manifest.get("use_region_display_geometries", True)
        )
        return manifest
    manifest = landscape_manifest.copy()
    manifest["landscape_geojson"] = pdf_path
    manifest["factor_scores"] = pdf_path
    manifest["analysis_id"] = f"{landscape_manifest.get('analysis_id', 'landscape')}_pdf"
    if landscape_manifest.get("pdf_landscape_source_h3_resolution") is not None:
        manifest["source_h3_resolution"] = int(landscape_manifest["pdf_landscape_source_h3_resolution"])
        manifest["default_h3_resolution"] = int(landscape_manifest["pdf_landscape_source_h3_resolution"])
    if landscape_manifest.get("pdf_landscape_available_h3_resolutions"):
        manifest["available_h3_resolutions"] = list(landscape_manifest["pdf_landscape_available_h3_resolutions"])
    if landscape_manifest.get("pdf_landscape_type_labels"):
        manifest["landscape_type_labels"] = dict(landscape_manifest["pdf_landscape_type_labels"])
    if landscape_manifest.get("pdf_landscape_type_colors"):
        manifest["landscape_type_colors"] = dict(landscape_manifest["pdf_landscape_type_colors"])
    manifest["use_region_display_geometries"] = bool(
        landscape_manifest.get("pdf_landscape_use_region_display_geometries", True)
    )
    return manifest


@st.cache_data(show_spinner=False)
def _unclipped_landscape_frame(
    landscape_manifest: dict[str, Any],
    resolution: int,
) -> pd.DataFrame:
    return landscape_frame_for_resolution(landscape_manifest, resolution)


def _landscape_display_geometry_path_for_manifest(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
) -> str | None:
    if not bool(landscape_manifest.get("use_region_display_geometries", True)):
        return None
    return _h3_display_geometry_path(region, int(resolution))


def _solar_legend_items(solar_rules: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": str(item.get("label", item.get("id", "Okänd"))), "color": str(item.get("color", "#999999"))}
        for item in _solar_class_breaks_for_display(solar_rules)
    ]


def _cluster_legend_items(landscape_manifest: dict[str, Any]) -> list[dict[str, str]]:
    labels = landscape_manifest.get("cluster_labels") or {}

    def sort_key(value: str) -> int:
        return int(value) if str(value).isdigit() else 999

    return [
        {"label": f"{key} - {labels[key]}", "color": CLUSTER_COLORS.get(str(key), "#999999")}
        for key in sorted(labels, key=sort_key)
    ]


def _landscape_type_legend_items(landscape_manifest: dict[str, Any]) -> list[dict[str, str]]:
    labels = landscape_manifest.get("landscape_type_labels") or {}
    colors = landscape_type_display_colors(landscape_manifest)
    return [{"label": str(labels.get(key, key)), "color": colors.get(key, "#999999")} for key in sorted(colors)]


def _factor_legend_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for idx, (_, color) in enumerate(FACTOR_STOPS):
        if idx == 0:
            label = "Blå = låg laddning"
        elif idx == len(FACTOR_STOPS) - 1:
            label = "Röd = hög laddning"
        else:
            label = " "
        items.append({"label": label, "color": color})
    return items


def _default_solar_params(solar_rules: dict[str, Any]) -> dict[str, float]:
    score_model = solar_rules.get("score_model") or {}
    cluster_terms = {term.get("cluster_ref"): float(term.get("weight", 0)) for term in score_model.get("cluster_terms") or []}
    role_terms = {term.get("role"): float(term.get("weight", 0)) for term in score_model.get("role_terms") or []}
    return {
        "base_score": float(score_model.get("base_score", 55)),
        "grid_access_bonus": 0.0,
        "everyday_matrix_bonus": max(cluster_terms.get("class_km:3", 0.0), cluster_terms.get("class_km:6", 0.0), cluster_terms.get("class_km:2", 15.0)),
        "coastal_penalty": abs(role_terms.get("coastal_lowland", -12.0)),
        "terrain_penalty": abs(role_terms.get("steep_valley_relief", -12.0)),
        "protected_penalty": abs(role_terms.get("protected_forest_habitat", -18.0)),
        "settlement_penalty": abs(role_terms.get("settlement_built_structure", -10.0)),
        "population_buffer_m": 250.0,
    }


def _solar_class_breaks_for_display(solar_rules: dict[str, Any]) -> list[dict[str, Any]]:
    breaks = [dict(item) for item in _class_breaks(solar_rules)]
    palette = {
        "very_low": "#991b1b",
        "low": "#f87171",
        "medium": "#fef08a",
        "high": "#facc15",
        "very_high": "#ca8a04",
    }
    for item in breaks:
        class_id = str(item.get("id", ""))
        if class_id in palette:
            item["color"] = palette[class_id]
    return breaks


def _solar_rules_with_display_palette(solar_rules: dict[str, Any]) -> dict[str, Any]:
    rules = read_manifest(str(resolve_repo_path(solar_rules.get("_manifest_path")))) if solar_rules.get("_manifest_path") else solar_rules.copy()
    rules = {
        **rules,
        "score_model": {
            **(rules.get("score_model") or {}),
            "cluster_terms": [dict(item) for item in (rules.get("score_model") or {}).get("cluster_terms") or []],
            "role_terms": [dict(item) for item in (rules.get("score_model") or {}).get("role_terms") or []],
        },
    }
    rules["score_model"]["class_breaks"] = _solar_class_breaks_for_display(rules)
    return rules


def _solar_rules_from_params(solar_rules: dict[str, Any], params: dict[str, float]) -> dict[str, Any]:
    rules = _solar_rules_with_display_palette(solar_rules)
    score_model = rules["score_model"]
    score_model["base_score"] = float(params.get("base_score", 55.0)) + float(params.get("grid_access_bonus", 0.0))
    for term in score_model.get("cluster_terms") or []:
        if term.get("cluster_ref") in {"class_km:2", "class_km:3", "class_km:6"}:
            term["weight"] = float(params.get("everyday_matrix_bonus", term.get("weight", 15.0)))
    role_weight_map = {
        "coastal_lowland": -float(params.get("coastal_penalty", 12.0)),
        "steep_valley_relief": -float(params.get("terrain_penalty", 12.0)),
        "protected_forest_habitat": -float(params.get("protected_penalty", 18.0)),
        "settlement_built_structure": -float(params.get("settlement_penalty", 10.0)),
    }
    for term in score_model.get("role_terms") or []:
        role = term.get("role")
        if role in role_weight_map:
            term["weight"] = role_weight_map[role]
    score_model["class_breaks"] = _solar_class_breaks_for_display(rules)
    return rules


def _default_wind_params() -> dict[str, float]:
    return {
        "settlement_distance_m": 100.0,
        "road_distance_m": 100.0,
        "grid_max_distance_m": 2000.0,
        "protected_buffer_m": 0.0,
        "coastal_buffer_m": 0.0,
        "culture_buffer_m": 0.0,
        "reindeer_buffer_m": 0.0,
        "aviation_approach_buffer_m": 0.0,
        "aviation_bird_distance_m": 0.0,
        "military_buffer_m": 0.0,
        "landscape_sensitivity_percent": 60.0,
    }


def _reference_default_wind_params() -> dict[str, float]:
    params = _default_wind_params()
    params.update(
        {
            "settlement_distance_m": 500.0,
            "road_distance_m": 300.0,
            "grid_max_distance_m": 1000.0,
            "protected_buffer_m": 250.0,
            "culture_buffer_m": 100.0,
            "reindeer_buffer_m": 100.0,
        }
    )
    return params


def _reference_default_wind_layer_selection() -> dict[str, list[str]]:
    return normalize_group_layer_map(
        {
            "settlement": [WIND_POPULATION_SOURCE_LAYER_ID],
            "transport": list(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_ROAD_GROUP_ID, [])),
            "electrical": [],
            "protected": ["protected_areas"],
            "coastal": [],
            "culture": [
                layer_id
                for layer_id in ("cultural_preservation", "valuable_cultural_environment")
                if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(WIND_CULTURE_GROUP_ID, [])
            ],
            "reindeer": [
                layer_id
                for layer_id in ("reindeer_grazing_merged",)
                if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(WIND_REINDEER_GROUP_ID, [])
            ],
            "aviation_approach": [],
            "aviation_bird": [],
            "military": [],
        }
    )


def _apply_reference_default_wind_to_controls() -> None:
    params = _reference_default_wind_params()
    selected = _reference_default_wind_layer_selection()
    st.session_state[WIND_LAYER_SELECTION_KEY] = selected
    for group_id, layer_ids in WIND_GROUP_LAYER_DEFAULTS.items():
        param_key = GROUP_PARAM_MAP.get(group_id)
        group_param_value = params.get(param_key) if param_key else None
        if group_param_value is not None:
            st.session_state[_wind_control_key("analysis", group_id)] = int(round(float(group_param_value)))
        selected_ids = set(selected.get(group_id, []))
        for layer_id in layer_ids:
            st.session_state[_wind_control_key("layer", layer_id)] = layer_id in selected_ids
    for group_id in (
        WIND_SETTLEMENT_GROUP_ID,
        WIND_CULTURE_GROUP_ID,
        WIND_REINDEER_GROUP_ID,
        SOLAR_PROTECTED_GROUP_ID,
    ):
        st.session_state[_wind_control_key("group", group_id)] = bool(selected.get(group_id))


def _wind_score_params_from_ui(ui_params: dict[str, float]) -> dict[str, float]:
    return {
        "base_score": 55.0,
        "everyday_matrix_bonus": 12.0,
        "infrastructure_bonus": min(float(ui_params["grid_max_distance_m"]) / 15000.0, 1.0) * 18.0,
        "settlement_penalty": min(float(ui_params["settlement_distance_m"]) / 3000.0, 1.0) * 35.0,
        "road_penalty": min(float(ui_params["road_distance_m"]) / 2000.0, 1.0) * 12.0,
        "protected_penalty": 10.0 + min(float(ui_params["protected_buffer_m"]) / 2000.0, 1.0) * 25.0,
        "coastal_penalty": 8.0 + min(float(ui_params["coastal_buffer_m"]) / 1000.0, 1.0) * 18.0,
        "terrain_penalty": 10.0,
        "landscape_sensitivity": max(0.0, min(2.0, float(ui_params["landscape_sensitivity_percent"]) / 60.0)),
        "factor_positive_cap": 2.0,
    }


def _state_params(prefix: str, defaults: dict[str, float]) -> dict[str, float]:
    params: dict[str, float] = {}
    for key, value in defaults.items():
        params[key] = float(st.session_state.get(f"{prefix}_{key}", value))
    return params


def _prime_solar_builder_state(defaults: dict[str, float], saved_params: dict[str, float] | None = None) -> None:
    source = saved_params or {}
    for key, value in defaults.items():
        seeded = float(source.get(key, value)) if isinstance(source, dict) else float(value)
        st.session_state.setdefault(f"solar_builder_{key}", seeded)
    for group in SOLAR_CONTROL_GROUPS:
        st.session_state.setdefault(_solar_control_key("active", str(group["id"])), False)


def _solar_control_key(kind: str, item_id: str) -> str:
    return f"solar_control__{kind}__{item_id}"


def _solar_params_from_control_state(defaults: dict[str, float]) -> dict[str, float]:
    params = _state_params("solar_builder", defaults)
    for group in SOLAR_CONTROL_GROUPS:
        active = bool(st.session_state.get(_solar_control_key("active", str(group["id"])), True))
        if active:
            continue
        for param_key in group.get("params") or []:
            params[str(param_key)] = 0.0
    return params


def _solar_group_controls(defaults: dict[str, float]) -> tuple[dict[str, float], bool]:
    st.caption(
        f"Bygg {SOLAR_LANDSCAPE_POTENTIAL_LABEL} med kriteriegrupper från Sol over land-underlaget. "
        "Grupper som stängs av får ingen positiv eller negativ effekt i scoremodellen."
    )
    with st.form("solar_landscape_potential_controls", clear_on_submit=False):
        with st.expander("Bas och metod", expanded=False):
            control = SOLAR_PARAM_CONTROLS["base_score"]
            st.slider(
                str(control["label"]),
                min_value=float(control["min"]),
                max_value=float(control["max"]),
                step=float(control["step"]),
                value=float(st.session_state.get("solar_builder_base_score", defaults["base_score"])),
                key="solar_builder_base_score",
                help=str(control["help"]),
            )
            st.caption("Hög LP Sol betyder robust landskap med låg konflikt och god teknisk logik, inte bara hög solinstrålning.")
        for group in SOLAR_CONTROL_GROUPS:
            group_id = str(group["id"])
            with st.expander(str(group["label"]), expanded=False):
                st.caption(str(group.get("caption", "")))
                st.checkbox("Aktiv", key=_solar_control_key("active", group_id))
                active = bool(st.session_state.get(_solar_control_key("active", group_id), True))
                for param_key in group.get("params") or []:
                    param_key = str(param_key)
                    control = SOLAR_PARAM_CONTROLS[param_key]
                    st.slider(
                        str(control["label"]),
                        min_value=float(control["min"]),
                        max_value=float(control["max"]),
                        step=float(control["step"]),
                        value=float(st.session_state.get(f"solar_builder_{param_key}", defaults[param_key])),
                        key=f"solar_builder_{param_key}",
                        disabled=not active,
                        help=str(control["help"]),
                    )
        applied = st.form_submit_button("Använd ändringar", type="primary", width="stretch")
    return _solar_params_from_control_state(defaults), bool(applied)


def _builder_slider(prefix: str, key: str, label: str, min_value: float, max_value: float, step: float, defaults: dict[str, float], help_text: str) -> None:
    st.slider(
        label,
        min_value=min_value,
        max_value=max_value,
        step=step,
        value=float(st.session_state.get(f"{prefix}_{key}", defaults[key])),
        key=f"{prefix}_{key}",
        help=help_text,
    )


def _reset_builder(prefix: str, defaults: dict[str, float]) -> None:
    for key, value in defaults.items():
        st.session_state[f"{prefix}_{key}"] = value
    st.rerun()


def _wind_builder_controls(defaults: dict[str, float]) -> None:
    _builder_slider("wind_builder", "settlement_distance_m", "Minsta avstånd till boende", 100.0, 3000.0, 50.0, defaults, "Större avstånd begränsar etablering närmare bebyggelse.")
    _builder_slider("wind_builder", "road_distance_m", "Minsta avstånd till vägar", 50.0, 2000.0, 25.0, defaults, "Större avstånd begränsar etablering närmare vägar och bebyggelse.")
    _builder_slider("wind_builder", "grid_max_distance_m", "Max avstånd till elinfrastruktur", 500.0, 15000.0, 250.0, defaults, "Större tillåtet avstånd gör fler lägen tekniskt möjliga.")
    _builder_slider("wind_builder", "protected_buffer_m", "Buffert skyddade områden", 0.0, 2000.0, 50.0, defaults, "0 stänger av gruppen. Högre värden hard-excludar skyddade natur- och habitatlager.")
    _builder_slider("wind_builder", "coastal_buffer_m", "Buffert kust/strand", 0.0, 1000.0, 50.0, defaults, "0 stänger av gruppen. Högre värden hard-excludar kustzon och strandskydd.")
    _builder_slider("wind_builder", "landscape_sensitivity_percent", "Landskapskänslighet", 0.0, 120.0, 5.0, defaults, f"Viktar hur starkt landskapsrollerna ska bromsa {WIND_LANDSCAPE_POTENTIAL_LABEL}.")
    with st.expander("Avancerade restriktioner"):
        _builder_slider("wind_builder", "culture_buffer_m", "Buffert kulturmiljöer", 0.0, 1500.0, 50.0, defaults, "0 stänger av gruppen. Högre värden hard-excludar värdefulla kulturmiljöer.")
        _builder_slider("wind_builder", "aviation_approach_buffer_m", "Buffert inflygningszoner", 0.0, 3000.0, 100.0, defaults, "0 stänger av gruppen. Högre värden hard-excludar flygplatsens inflygningszoner.")
        _builder_slider("wind_builder", "aviation_bird_distance_m", "Minsta avstånd fågelkollision", 0.0, 4000.0, 100.0, defaults, "0 stänger av gruppen. Högre värden ger distance-conflict mot fågelkollisionszoner.")
        _builder_slider("wind_builder", "military_buffer_m", "Buffert militära områden", 0.0, 2000.0, 50.0, defaults, "0 stänger av gruppen. Högre värden hard-excludar militära områden.")
        st.dataframe(wind_acceptance_group_summary(), width="stretch", hide_index=True, height=220)


def _save_solar_potential(params: dict[str, float], resolution: int) -> None:
    st.session_state["saved_solar_potential"] = {
        "params": dict(params),
        "preview_resolution": int(resolution),
    }


def _saved_solar_params() -> dict[str, float] | None:
    saved = st.session_state.get("saved_solar_potential")
    if not isinstance(saved, dict):
        return None
    params = saved.get("params")
    return dict(params) if isinstance(params, dict) else None


def _render_html_map(map_html: str, height: int = 820) -> None:
    iframe = getattr(st, "iframe", None)
    if callable(iframe):
        iframe(map_html, width="stretch", height=height)
        return
    if components is None:
        st.error(
            "Kartan kan inte renderas med den installerade Streamlit-versionen. "
            "Uppgradera Streamlit eller använd en version med st.iframe."
        )
        return
    components.html(map_html, height=height)


def _render_layers(
    region: dict[str, Any],
    layers: list[dict[str, Any]],
    opacity: float,
    map_state_key: str | None = None,
    map_reset_token: int = 0,
    opacity_key_prefix: str | None = None,
    note_title: str = "Samlad potential",
    note_body: str = "Aktiva lager styrs i appen och kan även slås av/på i kartkontrollen.",
    after_map_renderer: Any | None = None,
) -> None:
    if not layers:
        st.info("Välj minst ett kartlager.")
        return
    adjusted_layers = _apply_layer_opacity_state(layers, opacity_key_prefix or "combined")
    map_html = build_layered_hex_map_html(
        adjusted_layers,
        center=list(region.get("default_map_center", [55.14, 14.92])),
        zoom=int(region.get("default_zoom", 9)),
        bounds=region.get("default_map_bounds"),
        fill_opacity=opacity,
        map_state_key=map_state_key,
        map_reset_token=map_reset_token,
        note_title=note_title,
        note_body=note_body,
    )
    map_left, map_center, map_right = st.columns([0.02, 0.96, 0.02], gap="small")
    with map_center:
        st.markdown('<span data-potential-tutorial-anchor="map"></span>', unsafe_allow_html=True)
        _render_html_map(map_html, height=820)
        if callable(after_map_renderer):
            after_map_renderer()
        if opacity_key_prefix:
            with st.expander(_t("Avancerade kartinställningar"), expanded=False):
                st.caption("Justera kartopacitet när lager behöver jämföras mer tekniskt.")
                _hex_opacity_controls(adjusted_layers, opacity_key_prefix)
                _render_opacity_control(opacity_key_prefix)


def _potential_layer(
    name: str,
    frame: pd.DataFrame,
    technology: str,
    display_geometry_path: str | None,
    legend_items: list[dict[str, str]],
) -> dict[str, Any]:
    land_frame = _filter_frame_to_display_geometries(frame, display_geometry_path)
    return {
        "name": name,
        "feature_collection": potential_feature_collection(land_frame, technology, None),
        "fill_property": "fill",
        "legend_items": legend_items,
        "legend_id": "potential_classes",
        "legend_title": "Potentialklasser",
        "default_visible": False,
        "stroke": False,
        "weight": 0.0,
        "layer_kind": "hex",
        "opacity_family": name,
        "opacity_label": name,
    }


def _solar_polygon_feature_collection(
    frame: pd.DataFrame,
    display_geometry_path: str | None,
    label: str,
) -> dict[str, Any] | None:
    if frame.empty:
        return None
    selected = frame[frame["solar_class"].astype(str).isin(["high", "very_high"])].copy()
    if selected.empty:
        return None
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else {}
    multipolygon_parts: list[Any] = []
    for row in selected.itertuples(index=False):
        geometry = geometry_for_hex(str(row.hex_id), display_geometries)
        if geometry is None:
            continue
        geometry_type = str(geometry.get("type", ""))
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon" and coordinates:
            multipolygon_parts.append(coordinates)
        elif geometry_type == "MultiPolygon" and coordinates:
            multipolygon_parts.extend(coordinates)
    if not multipolygon_parts:
        return None

    selected_share = (len(selected) / len(frame)) * 100.0
    popup = (
        f"<strong>{label}</strong><br>"
        f"Hex med hög/mycket hög LP Sol: {len(selected)}<br>"
        f"Andel av visad yta: {selected_share:.1f}%<br>"
        f"Medelpoäng i polygonlagret: {float(selected['solar_score'].mean()):.1f}"
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "MultiPolygon", "coordinates": multipolygon_parts},
                "properties": {"fill": "#d97706", "popup": popup},
            }
        ],
    }


def _solar_polygon_layer(
    name: str,
    frame: pd.DataFrame,
    display_geometry_path: str | None,
    stroke_color: str = "#d97706",
    fill_color: str = "#d97706",
) -> dict[str, Any] | None:
    feature_collection = _solar_polygon_feature_collection(frame, display_geometry_path, name)
    if feature_collection is None:
        return None
    return {
        "name": name,
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "legend_items": [],
        "legend_id": f"solar_polygon_{name.lower().replace(' ', '_')}",
        "legend_title": "",
        "default_visible": False,
        "stroke_color": stroke_color,
        "fill_color": fill_color,
        "stroke_opacity": 0.74,
        "fill_opacity": 0.08,
        "weight": 1.6,
        "point_radius": 6,
        "dash_array": "6 4",
        "use_global_opacity": False,
        "z_index": 430,
        "layer_kind": "vector",
    }


def _wind_vector_layer(
    name: str,
    source_frame: pd.DataFrame,
    display_geometry_path: str | None,
    legend_items: list[dict[str, str]],
) -> dict[str, Any]:
    land_frame = _filter_frame_to_display_geometries(source_frame, display_geometry_path)
    return {
        "name": name,
        "feature_collection": wind_vector_feature_collection(land_frame, None, only_potential_area=True),
        "fill_property": "fill",
        "legend_items": legend_items,
        "legend_id": "potential_classes",
        "legend_title": "Potentialklasser",
        "default_visible": True,
        "layer_kind": "vector",
    }


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(int(value) for value in rgb)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    color = str(value).strip().lstrip("#")
    if len(color) != 6:
        return (153, 153, 153)
    return tuple(int(color[idx : idx + 2], 16) for idx in (0, 2, 4))


def _mix_hex_colors(left: str, right: str, amount: float) -> str:
    amount = max(0.0, min(1.0, float(amount)))
    left_rgb = _hex_to_rgb(left)
    right_rgb = _hex_to_rgb(right)
    mixed = tuple(int(round(left_rgb[idx] + ((right_rgb[idx] - left_rgb[idx]) * amount))) for idx in range(3))
    return _rgb_to_hex(mixed)


def _social_acceptance_values_frame(
    manifest: dict[str, Any] | None,
    scenario_id: str,
    target_resolution: int,
) -> pd.DataFrame:
    if not isinstance(manifest, dict):
        return pd.DataFrame(columns=["hex_id", "acceptance_value", "source_hex_count"])
    frame = load_social_acceptance_frame(manifest)
    value_column = social_acceptance_value_column(manifest, scenario_id)
    if frame.empty or value_column not in frame.columns or "hex_id" not in frame.columns:
        return pd.DataFrame(columns=["hex_id", "acceptance_value", "source_hex_count"])
    try:
        source_resolution = int(manifest.get("hex_resolution") or target_resolution)
    except Exception:
        source_resolution = int(target_resolution)

    work = frame[["hex_id", value_column]].copy()
    work["hex_id"] = work["hex_id"].astype(str)
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce").clip(lower=0.0, upper=1.0)
    if int(target_resolution) < int(source_resolution):
        work["hex_id"] = work["hex_id"].map(lambda cell: h3.cell_to_parent(str(cell), int(target_resolution)))
    rolled = (
        work.groupby("hex_id", as_index=False)
        .agg(acceptance_value=(value_column, "mean"), source_hex_count=(value_column, "count"))
        .sort_values("hex_id")
        .reset_index(drop=True)
    )
    rolled["acceptance_value"] = pd.to_numeric(rolled["acceptance_value"], errors="coerce").clip(lower=0.0, upper=1.0).round(3)
    rolled["source_hex_count"] = pd.to_numeric(rolled["source_hex_count"], errors="coerce").fillna(0).astype(int)
    return rolled


def _apply_social_acceptance_impact_to_establishment_frame(
    frame: pd.DataFrame,
    manifest: dict[str, Any] | None,
    scenario_id: str,
    target_resolution: int,
    impact_pct: float,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    impact_fraction = max(0.0, min(1.0, float(impact_pct or 0.0) / 100.0))
    if impact_fraction <= 0.0 or not isinstance(manifest, dict):
        return frame

    acceptance_frame = _social_acceptance_values_frame(manifest, scenario_id, int(target_resolution))
    if acceptance_frame.empty:
        return frame

    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    work = work.merge(acceptance_frame, on="hex_id", how="left")
    work["acceptance_value"] = pd.to_numeric(work["acceptance_value"], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    work["source_hex_count"] = pd.to_numeric(work["source_hex_count"], errors="coerce").fillna(0).astype(int)
    work["social_acceptance_value"] = work["acceptance_value"].round(3)
    work["social_acceptance_source_hex_count"] = work["source_hex_count"]
    work["social_acceptance_impact_pct"] = float(impact_fraction * 100.0)
    work["social_acceptance_tint_amount"] = (impact_fraction * (1.0 - work["social_acceptance_value"])).clip(lower=0.0, upper=1.0)
    work["social_acceptance_weight"] = ((1.0 - impact_fraction) + (impact_fraction * work["social_acceptance_value"])).clip(
        lower=0.0,
        upper=1.0,
    )
    fill_values = work["fill"] if "fill" in work.columns else pd.Series("#999999", index=work.index)
    stroke_values = work["stroke"] if "stroke" in work.columns else pd.Series("#999999", index=work.index)
    work["fill"] = [
        _mix_hex_colors(str(color), SOCIAL_ACCEPTANCE_IMPACT_TINT_COLOR, float(tint_amount))
        for color, tint_amount in zip(fill_values, work["social_acceptance_tint_amount"])
    ]
    work["stroke"] = [
        _mix_hex_colors(str(color), SOCIAL_ACCEPTANCE_IMPACT_TINT_COLOR, float(tint_amount))
        for color, tint_amount in zip(stroke_values, work["social_acceptance_tint_amount"])
    ]
    return work.drop(columns=["acceptance_value", "source_hex_count"], errors="ignore")


def _merge_social_acceptance_for_priority(
    frame: pd.DataFrame,
    manifest: dict[str, Any] | None,
    scenario_id: str,
    target_resolution: int,
    priority_pct: float,
) -> tuple[pd.DataFrame, float]:
    priority_fraction = max(0.0, min(1.0, float(priority_pct or 0.0) / 100.0))
    if frame.empty or priority_fraction <= 0.0 or not isinstance(manifest, dict):
        return frame, 0.0
    acceptance_frame = _social_acceptance_values_frame(manifest, scenario_id, int(target_resolution))
    if acceptance_frame.empty:
        return frame, 0.0
    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    work = work.merge(acceptance_frame[["hex_id", "acceptance_value"]], on="hex_id", how="left")
    work["social_acceptance_value"] = pd.to_numeric(work["acceptance_value"], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    work["social_acceptance_allocation_priority_pct"] = float(priority_fraction * 100.0)
    return work.drop(columns=["acceptance_value"], errors="ignore"), priority_fraction


def _apply_social_acceptance_priority_to_wind_allocation_frame(
    frame: pd.DataFrame,
    manifest: dict[str, Any] | None,
    scenario_id: str,
    target_resolution: int,
    priority_pct: float,
) -> pd.DataFrame:
    work, priority_fraction = _merge_social_acceptance_for_priority(frame, manifest, scenario_id, target_resolution, priority_pct)
    if priority_fraction <= 0.0 or work.empty:
        return work
    if "allocation_priority_score" in work.columns:
        technical_score = pd.to_numeric(work["allocation_priority_score"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    else:
        core_source = work["core_score"] if "core_score" in work.columns else pd.Series(0.0, index=work.index)
        share_source = work["potential_area_share_pct"] if "potential_area_share_pct" in work.columns else pd.Series(0.0, index=work.index)
        core_score = pd.to_numeric(core_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
        potential_share = pd.to_numeric(share_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
        technical_score = ((0.7 * core_score) + (0.3 * potential_share)).clip(lower=0.0, upper=1.0)
    acceptance = pd.to_numeric(work["social_acceptance_value"], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    work["technical_priority_score"] = technical_score
    core_before_source = work["core_score"] if "core_score" in work.columns else pd.Series(0.0, index=work.index)
    work["core_score_before_acceptance"] = pd.to_numeric(core_before_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    work["social_acceptance_priority_score"] = ((1.0 - priority_fraction) * technical_score + priority_fraction * acceptance).clip(
        lower=0.0,
        upper=1.0,
    )
    work["allocation_priority_score"] = work["social_acceptance_priority_score"]
    work["core_score"] = work["allocation_priority_score"]
    return work


def _apply_social_acceptance_priority_to_solar_candidates(
    frame: pd.DataFrame,
    manifest: dict[str, Any] | None,
    scenario_id: str,
    target_resolution: int,
    priority_pct: float,
) -> pd.DataFrame:
    work, priority_fraction = _merge_social_acceptance_for_priority(frame, manifest, scenario_id, target_resolution, priority_pct)
    if priority_fraction <= 0.0 or work.empty:
        return work
    if "allocation_priority_score" in work.columns:
        technical_score = pd.to_numeric(work["allocation_priority_score"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    else:
        score_source = work["potential_score"] if "potential_score" in work.columns else pd.Series(0.0, index=work.index)
        technical_score = pd.to_numeric(score_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
    acceptance = pd.to_numeric(work["social_acceptance_value"], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    work["technical_priority_score"] = technical_score
    work["social_acceptance_priority_score"] = ((1.0 - priority_fraction) * technical_score + priority_fraction * acceptance).clip(
        lower=0.0,
        upper=1.0,
    )
    work["allocation_priority_score"] = work["social_acceptance_priority_score"]
    return work


def _social_acceptance_establishment_summary(
    establishment_frame: pd.DataFrame,
    manifest: dict[str, Any] | None,
    scenario_id: str,
    target_resolution: int,
    hex_area_km2: float,
    impact_pct: float,
) -> dict[str, Any]:
    if establishment_frame.empty or not isinstance(manifest, dict):
        return {}
    acceptance_frame = _social_acceptance_values_frame(manifest, scenario_id, int(target_resolution))
    if acceptance_frame.empty:
        return {}

    work = establishment_frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    if "establishment_class" in work.columns:
        potential_mask = work["establishment_class"].astype(str).ne("not_suitable")
    else:
        wind_suitable = work["wind_suitable"].astype(bool) if "wind_suitable" in work.columns else pd.Series(False, index=work.index)
        solar_suitable = work["solar_suitable"].astype(bool) if "solar_suitable" in work.columns else pd.Series(False, index=work.index)
        potential_mask = wind_suitable | solar_suitable
    potential_hexes = work.loc[potential_mask, ["hex_id"]].drop_duplicates().copy()
    if potential_hexes.empty:
        return {}

    joined = potential_hexes.merge(acceptance_frame, on="hex_id", how="left")
    joined["acceptance_value"] = pd.to_numeric(joined.get("acceptance_value"), errors="coerce")
    measured = joined.dropna(subset=["acceptance_value"]).copy()
    if measured.empty:
        return {}
    measured["acceptance_value"] = measured["acceptance_value"].clip(lower=0.0, upper=1.0)
    low_mask = measured["acceptance_value"].lt(SOCIAL_ACCEPTANCE_LOW_THRESHOLD)
    high_mask = measured["acceptance_value"].ge(SOCIAL_ACCEPTANCE_HIGH_THRESHOLD)
    potential_hex_count = int(len(potential_hexes))
    measured_hex_count = int(len(measured))
    low_hex_count = int(low_mask.sum())
    high_hex_count = int(high_mask.sum())
    hex_area = max(0.0, float(hex_area_km2 or 0.0))
    impact_fraction = max(0.0, min(1.0, float(impact_pct or 0.0) / 100.0))

    def _technology_potential_area(column_prefix: str) -> pd.Series:
        area_col = f"{column_prefix}_potential_area_km2"
        if area_col in work.columns:
            return pd.to_numeric(work[area_col], errors="coerce").fillna(0.0).clip(lower=0.0)
        suitable_col = f"{column_prefix}_suitable"
        if suitable_col in work.columns and hex_area > 0:
            return work[suitable_col].map(lambda value: False if pd.isna(value) else bool(value)).astype(float) * hex_area
        return pd.Series(0.0, index=work.index, dtype="float64")

    tech_area = work[["hex_id"]].copy()
    tech_area["wind_potential_area_km2"] = _technology_potential_area("wind")
    tech_area["solar_potential_area_km2"] = _technology_potential_area("solar")
    tech_area = (
        tech_area.groupby("hex_id", as_index=False)
        .agg(
            wind_potential_area_km2=("wind_potential_area_km2", "sum"),
            solar_potential_area_km2=("solar_potential_area_km2", "sum"),
        )
        .merge(acceptance_frame, on="hex_id", how="left")
    )
    tech_area["acceptance_value"] = pd.to_numeric(tech_area.get("acceptance_value"), errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    tech_area["acceptance_weight"] = ((1.0 - impact_fraction) + (impact_fraction * tech_area["acceptance_value"])).clip(lower=0.0, upper=1.0)

    def _weighted_potential_stats(column_prefix: str) -> dict[str, float]:
        area_col = f"{column_prefix}_potential_area_km2"
        raw_area = float(pd.to_numeric(tech_area.get(area_col), errors="coerce").fillna(0.0).clip(lower=0.0).sum())
        weighted_area = float((pd.to_numeric(tech_area.get(area_col), errors="coerce").fillna(0.0).clip(lower=0.0) * tech_area["acceptance_weight"]).sum())
        return {
            f"{column_prefix}_potential_after_acceptance_km2": max(0.0, weighted_area),
            f"{column_prefix}_potential_acceptance_reduction_km2": max(0.0, raw_area - weighted_area),
            f"{column_prefix}_potential_acceptance_ratio": (weighted_area / raw_area) if raw_area > 1e-9 else 1.0,
        }

    wind_acceptance_stats = _weighted_potential_stats("wind")
    solar_acceptance_stats = _weighted_potential_stats("solar")
    total_potential_after_acceptance = (
        wind_acceptance_stats["wind_potential_after_acceptance_km2"]
        + solar_acceptance_stats["solar_potential_after_acceptance_km2"]
    )
    total_raw_potential = float(tech_area["wind_potential_area_km2"].sum() + tech_area["solar_potential_area_km2"].sum())
    return {
        "scenario_id": str(scenario_id),
        "scenario_label": social_acceptance_scenario_label(manifest, str(scenario_id)),
        "impact_pct": float(impact_fraction * 100.0),
        "h3_resolution": int(target_resolution),
        "hex_area_km2": hex_area,
        "potential_hex_count": potential_hex_count,
        "measured_hex_count": measured_hex_count,
        "missing_hex_count": max(0, potential_hex_count - measured_hex_count),
        "mean_acceptance": float(measured["acceptance_value"].mean()),
        "median_acceptance": float(measured["acceptance_value"].median()),
        "low_threshold": float(SOCIAL_ACCEPTANCE_LOW_THRESHOLD),
        "high_threshold": float(SOCIAL_ACCEPTANCE_HIGH_THRESHOLD),
        "low_acceptance_hex_count": low_hex_count,
        "low_acceptance_area_km2": float(low_hex_count * hex_area),
        "low_acceptance_share_pct": (low_hex_count / measured_hex_count * 100.0) if measured_hex_count > 0 else 0.0,
        "high_acceptance_hex_count": high_hex_count,
        "high_acceptance_area_km2": float(high_hex_count * hex_area),
        "high_acceptance_share_pct": (high_hex_count / measured_hex_count * 100.0) if measured_hex_count > 0 else 0.0,
        **wind_acceptance_stats,
        **solar_acceptance_stats,
        "total_potential_after_acceptance_km2": max(0.0, total_potential_after_acceptance),
        "total_potential_acceptance_reduction_km2": max(0.0, total_raw_potential - total_potential_after_acceptance),
        "total_potential_acceptance_ratio": (total_potential_after_acceptance / total_raw_potential) if total_raw_potential > 1e-9 else 1.0,
    }


def _default_wind_layer_selection() -> dict[str, list[str]]:
    return {
        group_id: list(DEFAULT_WIND_ESTABLISHMENT_LAYER_SELECTION.get(group_id, []))
        for group_id in WIND_GROUP_LAYER_DEFAULTS
    }


def _selected_wind_layers() -> dict[str, list[str]]:
    raw = st.session_state.get(WIND_LAYER_SELECTION_KEY)
    if not isinstance(raw, dict):
        selected = normalize_group_layer_map(_default_wind_layer_selection())
        st.session_state[WIND_LAYER_SELECTION_KEY] = selected
        return selected
    selected = normalize_group_layer_map(raw)
    st.session_state[WIND_LAYER_SELECTION_KEY] = selected
    return selected


def _wind_runtime_overlays_enabled() -> bool:
    st.session_state[WIND_RUNTIME_OVERLAY_KEY] = True
    return True


def _wind_control_key(prefix: str, item_id: str) -> str:
    return f"wind_control__{prefix}__{item_id}"


def _wind_visual_options_from_state(layer_selection: dict[str, list[str]] | None = None) -> dict[str, Any]:
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    active_group_ids = [group_id for group_id, layer_ids in selected.items() if layer_ids]
    return {
        "source_group_ids": [
            group_id
            for group_id in active_group_ids
            if bool(st.session_state.get(_wind_control_key("visual_source", group_id), False))
        ],
        "buffer_group_ids": [
            group_id
            for group_id in active_group_ids
            if bool(st.session_state.get(_wind_control_key("visual_buffer", group_id), False))
        ],
    }


def _normalize_wind_visual_options(visual_options: dict[str, Any] | None) -> dict[str, Any]:
    source_raw = (visual_options or {}).get("source_group_ids", [])
    buffer_raw = (visual_options or {}).get("buffer_group_ids", [])
    source_group_ids = {str(group_id) for group_id in source_raw} if isinstance(source_raw, (list, tuple, set)) else set()
    buffer_group_ids = {str(group_id) for group_id in buffer_raw} if isinstance(buffer_raw, (list, tuple, set)) else set()
    return {
        "source_group_ids": source_group_ids,
        "buffer_group_ids": buffer_group_ids,
    }


def _init_wind_control_state() -> None:
    groups, layers, _ = load_acceptance_registry()
    st.session_state[WIND_RUNTIME_OVERLAY_KEY] = True
    for group in groups.values():
        st.session_state.setdefault(_wind_control_key("analysis", group.id), int(group.analysis_default_m))
        st.session_state.setdefault(_wind_control_key("blend", group.id), int(group.blend_default))
        st.session_state.setdefault(_wind_control_key("visual_source", group.id), False)
        st.session_state.setdefault(_wind_control_key("visual_buffer", group.id), False)
    for layer in layers.values():
        st.session_state.setdefault(_wind_control_key("layer", layer.id), False)


def _prime_wind_builder_state(
    saved_ui_params: dict[str, float] | None = None,
    saved_layer_selection: dict[str, list[str]] | None = None,
) -> None:
    _init_wind_control_state()
    selected = normalize_group_layer_map(saved_layer_selection or {})
    for group in ordered_groups():
        param_key = GROUP_PARAM_MAP.get(group.id)
        if param_key and isinstance(saved_ui_params, dict) and param_key in saved_ui_params:
            st.session_state.setdefault(
                _wind_control_key("analysis", group.id),
                int(round(float(saved_ui_params[param_key]))),
            )
    for layer in ordered_layers():
        st.session_state.setdefault(
            _wind_control_key("layer", layer.id),
            bool(layer.id in selected.get(layer.group_id, [])),
        )


def _wind_layer_status_lookup(registry_meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    status_df = acceptance_layer_status_table(registry_meta)
    if status_df.empty:
        return {}
    return {str(row["layer_id"]): row.to_dict() for _, row in status_df.iterrows()}


def _wind_layer_is_ready(layer_id: str, availability: dict[str, dict[str, Any]]) -> bool:
    status = availability.get(str(layer_id), {})
    return (
        bool(status.get("geojson_ready"))
        and bool(status.get("source_exists"))
        and int(status.get("feature_count", 0) or 0) > 0
        and str(status.get("status", "")) == "ok"
    )


def _wind_group_has_ready_layers(group_id: str, group_layers: list[Any], availability: dict[str, dict[str, Any]]) -> bool:
    return any(_wind_layer_is_ready(str(layer.id), availability) for layer in group_layers)


def _default_wind_advanced_layer_ids(
    group_id: str,
    group_layers: list[Any],
    availability: dict[str, dict[str, Any]],
) -> list[str]:
    layer_ids = [str(layer.id) for layer in group_layers]
    preferred_ids = [layer_id for layer_id in DEFAULT_WIND_ADVANCED_LAYER_SELECTION.get(str(group_id), []) if layer_id in layer_ids]
    ready_preferred = [layer_id for layer_id in preferred_ids if _wind_layer_is_ready(layer_id, availability)]
    if ready_preferred:
        return ready_preferred
    return [layer_id for layer_id in layer_ids if _wind_layer_is_ready(layer_id, availability)][:1]


def _seed_wind_advanced_layer_defaults(
    group_id: str,
    group_layers: list[Any],
    availability: dict[str, dict[str, Any]],
) -> None:
    existing_keys = [_wind_control_key("layer", layer.id) for layer in group_layers]
    if any(bool(st.session_state.get(key, False)) for key in existing_keys):
        return
    for layer_id in _default_wind_advanced_layer_ids(group_id, group_layers, availability):
        st.session_state[_wind_control_key("layer", layer_id)] = True


def _wind_blend_value(group_id: str) -> int:
    try:
        value = int(st.session_state.get(_wind_control_key("blend", group_id), 50))
    except Exception:
        value = 50
    return max(0, min(100, value))


def _wind_source_opacity(group_id: str) -> float:
    return max(0.0, 1.0 - (_wind_blend_value(group_id) / 100.0))


def _wind_group_opacity(group_id: str) -> float:
    return max(0.0, min(1.0, _wind_blend_value(group_id) / 100.0))


def _wind_group_controls(
    widget_prefix: str,
    language: str = WIND_CONTROL_LANGUAGE,
) -> tuple[dict[str, list[str]], dict[str, float], bool]:
    _init_wind_control_state()
    groups, layers, registry_meta = load_acceptance_registry()
    availability = _wind_layer_status_lookup(registry_meta)
    selected: dict[str, list[str]] = {group.id: [] for group in ordered_groups()}

    st.header(ui_text("groups_header", language))
    with st.form(f"{widget_prefix}_group_controls", clear_on_submit=False):
        for group in ordered_groups():
            is_protected_group = group.id == SOLAR_PROTECTED_GROUP_ID
            is_settlement_group = group.id == WIND_SETTLEMENT_GROUP_ID
            is_culture_group = group.id == WIND_CULTURE_GROUP_ID
            is_reindeer_group = group.id == WIND_REINDEER_GROUP_ID
            group_layers = [item for item in ordered_layers() if item.group_id == group.id]
            group_available = _wind_group_has_ready_layers(group.id, group_layers, availability)
            if is_protected_group:
                display_group_label = _protected_group_label()
            elif is_settlement_group:
                display_group_label = _settlement_group_label()
            else:
                display_group_label = group_label(group, language, group.label)
            expander_label = display_group_label if group_available else f"{display_group_label} - ej tillgänglig"
            with st.expander(expander_label, expanded=group.id in {"settlement", "transport", "electrical"}):
                st.caption(group_interpretation(group, language, group.interpretation))
                if not group_available:
                    st.caption("Ej tillgängligt för vald region ännu. Källager/assets behöver kopplas innan gruppen kan användas.")
                st.slider(
                    group_analysis_label(group, language, group.analysis_label),
                    min_value=int(group.analysis_min_m),
                    max_value=int(group.analysis_max_m),
                    step=int(group.analysis_step_m),
                    key=_wind_control_key("analysis", group.id),
                    help=ui_text("analysis_slider_help", language),
                    disabled=not group_available,
                )
                group_enabled = True
                if is_protected_group or is_settlement_group or is_culture_group or is_reindeer_group:
                    if group_available:
                        _seed_wind_advanced_layer_defaults(group.id, group_layers, availability)
                    group_layer_keys = [
                        _wind_control_key("layer", layer.id)
                        for layer in group_layers
                    ]
                    st.session_state.setdefault(
                        _wind_control_key("group", group.id),
                        any(bool(st.session_state.get(key, False)) for key in group_layer_keys),
                    )
                    if not group_available:
                        st.session_state[_wind_control_key("group", group.id)] = False
                    group_help = (
                        "Befolkningspunkter används som standard. Övriga bebyggelselager kan slås på under avancerade inställningar."
                        if is_settlement_group
                        else "Samlar valda kulturmiljölager till en gemensam restriktion i vindpotentialen."
                        if is_culture_group
                        else "Samlar valda reindriftslager till en gemensam restriktion i vindpotentialen."
                        if is_reindeer_group
                        else "Samlar valda naturskyddslager till en gemensam restriktion i vindpotentialen."
                    )
                    group_checkbox_label = (
                        f"Använd {WIND_CULTURE_GROUP_LABEL}"
                        if is_culture_group
                        else f"Använd {WIND_REINDEER_GROUP_LABEL}"
                        if is_reindeer_group
                        else f"Använd {display_group_label}"
                    )
                    group_enabled = st.checkbox(
                        group_checkbox_label,
                        key=_wind_control_key("group", group.id),
                        help=group_help,
                        disabled=not group_available,
                    )
                main_layers = group_layers
                advanced_layers: list[Any] = []
                if is_protected_group or is_settlement_group or is_culture_group or is_reindeer_group:
                    main_layers = []
                    advanced_layers = group_layers

                def render_layer_checkbox(layer: Any) -> None:
                    status = availability.get(layer.id, {})
                    ready = _wind_layer_is_ready(layer.id, availability)
                    message = str(status.get("message", "") or layer_note(layer, language, layer.note) or "")
                    checked = st.checkbox(
                        layer_label(layer, language, layer.label),
                        key=_wind_control_key("layer", layer.id),
                        disabled=(not group_available) or (not ready),
                        help=message,
                    )
                    if checked and ready and group_enabled:
                        selected[group.id].append(layer.id)

                for layer in main_layers:
                    render_layer_checkbox(layer)

                with st.expander("Avancerade inställningar", expanded=False):
                    if is_settlement_group:
                        st.caption("Befolkningspunkter är standard. Välj fler bebyggelseproxyer om de behövs för analysen.")
                    elif is_culture_group:
                        st.caption("Välj vilka kulturmiljölager som ska ingå i gruppen.")
                    elif is_reindeer_group:
                        st.caption("Välj vilka reindriftslager som ska ingå i gruppen.")
                    elif is_protected_group:
                        st.caption(f"Välj vilka del-lager som ingår i {PROTECTED_NATURE_LABEL}.")
                    for layer in advanced_layers:
                        render_layer_checkbox(layer)
                    if not advanced_layers and main_layers:
                        st.caption("Del-lagren väljs ovanför. Avancerade inställningar styr bara kartvisningen.")
                    elif not advanced_layers:
                        st.caption("Inga del-lager är kopplade ännu.")
                    st.caption("Kartvisning: valda lager används i analysen även när källa och buffert är dolda på kartan.")
                    st.checkbox(
                        "Visa källa i kartan",
                        key=_wind_control_key("visual_source", group.id),
                        disabled=not group_available,
                    )
                    st.checkbox(
                        "Visa buffert i kartan",
                        key=_wind_control_key("visual_buffer", group.id),
                        disabled=not group_available,
                    )

                if not selected[group.id]:
                    if not group_available:
                        st.caption("Gruppen är gråmarkerad och ej valbar tills data finns.")
                    elif (is_protected_group or is_settlement_group or is_culture_group or is_reindeer_group) and not group_enabled:
                        st.caption("Gruppen är avstängd. Del-lager kan väljas, men används först när gruppen är aktiv.")
                    else:
                        st.caption(ui_text("group_inactive", language))
        applied = st.form_submit_button(ui_text("apply_changes", language), type="primary", width="stretch")

    normalized = normalize_group_layer_map(selected)
    st.session_state[WIND_LAYER_SELECTION_KEY] = normalized
    if applied:
        _invalidate_workspace_cache("wind controls applied")
        st.session_state[WIND_EMPTY_SELECTION_ACTIVE_KEY] = not _has_selected_wind_layers(normalized)

    ui_params = _default_wind_params()
    for group in ordered_groups():
        param_key = GROUP_PARAM_MAP.get(group.id)
        if not param_key:
            continue
        ui_params[param_key] = float(st.session_state.get(_wind_control_key("analysis", group.id), group.analysis_default_m))
    return normalized, ui_params, bool(applied)


def _wind_runtime_overlay_control() -> bool:
    st.session_state.setdefault(WIND_RUNTIME_OVERLAY_KEY, True)
    st.checkbox(
        "Visa potentiell etableringsyta (geometri)",
        key=WIND_RUNTIME_OVERLAY_KEY,
        help="Kör geometri-runtime och lägg till grupplager plus kombinerad acceptansyta i vektorvyn.",
    )
    return _wind_runtime_overlays_enabled()


def _wind_layer_selector_controls(widget_prefix: str) -> None:
    groups, layers, _ = load_acceptance_registry()
    selected_layers = _selected_wind_layers()
    with st.expander("Kallager per regelgrupp", expanded=False):
        st.caption("Valj vilka vindlager som ska anvandas och klicka Anvand andringar.")
        with st.form(f"{widget_prefix}_wind_layer_selector", clear_on_submit=False):
            draft_layers: dict[str, list[str]] = {}
            for group_id, default_layer_ids in WIND_GROUP_LAYER_DEFAULTS.items():
                label = GROUP_LABELS.get(group_id, groups[group_id].label if group_id in groups else group_id)
                st.markdown(f"**{label}**")
                options = [layer_id for layer_id in default_layer_ids if layer_id in layers]
                selected_default = [layer_id for layer_id in selected_layers.get(group_id, []) if layer_id in options]
                draft_layers[group_id] = st.multiselect(
                    f"Lager ({len(selected_default)} valda)",
                    options=options,
                    default=selected_default,
                    format_func=lambda layer_id: layers[layer_id].label,
                    key=f"{widget_prefix}_wind_layers_{group_id}",
                )
            applied = st.form_submit_button("Anvand andringar", type="primary", width="stretch")
        if applied:
            _invalidate_workspace_cache("wind layer selector applied")
            st.session_state[WIND_LAYER_SELECTION_KEY] = normalize_group_layer_map(draft_layers)
            st.success("Vindlager uppdaterade.")


def _wind_active_group_ids(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]] | None = None,
) -> list[str]:
    _ = ui_params
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    active: list[str] = []
    for group_id, layer_ids in selected.items():
        if not layer_ids:
            continue
        active.append(group_id)
    return active


def _wind_source_vector_layers(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    _ = ui_params
    groups, layers, registry_meta = load_acceptance_registry()
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    map_layers: list[dict[str, Any]] = []
    for group_id in _wind_active_group_ids(ui_params, layer_selection=selected):
        group_label = GROUP_LABELS.get(group_id, groups[group_id].label if group_id in groups else group_id)
        for layer_id in selected.get(group_id, []):
            layer_spec = layers.get(layer_id)
            if layer_spec is None:
                continue
            geojson = source_geojson_for_layer(registry_meta, layer_id)
            if not geojson:
                continue
            source_color = _rgb_to_hex(layer_spec.source_color)
            source_opacity = _wind_source_opacity(group_id)
            map_layers.append(
                {
                    "name": f"Källa: {layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label)} ({group_label})",
                    "feature_collection": geojson,
                    "fill_property": "fill",
                    "legend_items": [],
                    "legend_id": f"wind_source_{layer_id}",
                    "legend_title": "",
                    "default_visible": False,
                    "stroke_color": source_color,
                    "fill_color": source_color,
                    "stroke_opacity": max(min(source_opacity, 1.0), 0.0),
                    "fill_opacity": max(min(source_opacity * 0.28, 1.0), 0.0),
                    "weight": 2.0,
                    "point_radius": int(layer_spec.point_radius),
                    "use_global_opacity": False,
                    "source_layer_id": layer_id,
                    "layer_kind": "vector",
                }
            )
    return map_layers


def _wind_share_class_spec(area_share_pct: float) -> dict[str, Any]:
    share_value = max(0.0, min(100.0, float(area_share_pct)))
    for spec in WIND_SHARE_CLASS_SPECS:
        if share_value <= float(spec["max_pct"]):
            return spec
    return WIND_SHARE_CLASS_SPECS[-1]


def _wind_share_legend_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for spec in WIND_SHARE_CLASS_SPECS:
        if not spec.get("legend_label"):
            continue
        if str(spec.get("id")) == "share_0":
            items.append({"label": "Mörkare röd = djupare kärnområde", "color": "#7f0000"})
        items.append({"label": str(spec["legend_label"]), "color": str(spec["base_color"])})
        if str(spec.get("id")) == "share_9":
            items.append({"label": "Mörkare blå = djupare kärnområde", "color": "#1e3a8a"})
    return items


def _wind_core_label(core_score: float, zone_size: int) -> str:
    core_value = max(0.0, min(1.0, float(core_score)))
    zone_size_value = max(0, int(zone_size))
    if zone_size_value <= 1:
        return "Enskild hex"
    if core_value >= 0.72:
        return "Djup kärna"
    if core_value >= 0.36:
        return "Mellanläge"
    return "Kantzon"


def _wind_polygon_source_layers(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]] | None = None,
    include_group_ids: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    groups, layers, registry_meta = load_acceptance_registry()
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    included_groups = None if include_group_ids is None else {str(group_id) for group_id in include_group_ids}
    map_layers: list[dict[str, Any]] = []
    for group_id in _wind_active_group_ids(ui_params, layer_selection=selected):
        if included_groups is not None and group_id not in included_groups:
            continue
        opacity = _wind_source_opacity(group_id)
        group_meta = groups.get(group_id)
        translated_group_label = GROUP_LABELS.get(group_id, group_meta.label if group_meta is not None else group_id)
        if group_meta is not None:
            translated_group_label = group_label(group_meta, WIND_CONTROL_LANGUAGE, group_meta.label)
        if group_id == WIND_SETTLEMENT_GROUP_ID:
            translated_group_label = WIND_SETTLEMENT_GROUP_LABEL
        if group_id == SOLAR_PROTECTED_GROUP_ID:
            translated_group_label = PROTECTED_NATURE_LABEL
            protected_features: list[dict[str, Any]] = []
            protected_colors: list[str] = []
            for layer_id in selected.get(group_id, []):
                layer_spec = layers.get(layer_id)
                if layer_spec is None:
                    continue
                geojson = source_geojson_for_layer(registry_meta, layer_id)
                if geojson is None:
                    continue
                source_color = _rgb_to_hex(layer_spec.source_color)
                protected_colors.append(source_color)
                label = layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label)
                for feature in geojson.get("features") or []:
                    if not isinstance(feature, dict) or not feature.get("geometry"):
                        continue
                    copied = json.loads(json.dumps(feature))
                    props = copied.setdefault("properties", {})
                    props["fill"] = source_color
                    props["tooltip_title"] = f"Vind källa: {PROTECTED_NATURE_LABEL}"
                    props["tooltip_body"] = label
                    props.setdefault("popup", f"<strong>Vind källa: {PROTECTED_NATURE_LABEL}</strong><br>{label}")
                    protected_features.append(copied)
            if protected_features:
                color = protected_colors[0] if protected_colors else "#15803d"
                map_layers.append(
                    {
                        "name": f"Vind källa: {PROTECTED_NATURE_LABEL}",
                        "feature_collection": {"type": "FeatureCollection", "features": protected_features},
                        "fill_property": "fill",
                        "legend_items": [],
                        "legend_id": "wind_polygon_source_protected_nature",
                        "legend_title": "",
                        "default_visible": False,
                        "stroke_color": color,
                        "fill_color": color,
                        "stroke_opacity": max(min(opacity, 1.0), 0.0),
                        "fill_opacity": max(min(opacity * 0.28, 1.0), 0.0),
                        "weight": 2.0,
                        "point_radius": 4,
                        "use_global_opacity": False,
                        "source_layer_id": f"wind:{SOLAR_PROTECTED_GROUP_ID}",
                        "layer_kind": "vector",
                    }
                )
            continue
        for layer_id in selected.get(group_id, []):
            layer_spec = layers.get(layer_id)
            if layer_spec is None:
                continue
            geojson = source_geojson_for_layer(registry_meta, layer_id)
            if geojson is None:
                continue
            is_trondelag_population = group_id == WIND_SETTLEMENT_GROUP_ID and layer_id == WIND_POPULATION_SOURCE_LAYER_ID
            map_layers.append(
                {
                    "name": f"Vind källa: {layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label)} ({translated_group_label})",
                    "feature_collection": geojson,
                    "fill_property": "fill",
                    "legend_items": [],
                    "legend_id": f"wind_polygon_source_{layer_id}",
                    "legend_title": "",
                    "default_visible": bool(is_trondelag_population),
                    "stroke_color": _rgb_to_hex(layer_spec.source_color),
                    "fill_color": _rgb_to_hex(layer_spec.source_color),
                    "stroke_opacity": max(min(opacity, 1.0), 0.0),
                    "fill_opacity": max(min(opacity * 0.28, 1.0), 0.0),
                    "weight": 2.0,
                    "point_radius": int(layer_spec.point_radius),
                    "use_global_opacity": False,
                    "source_layer_id": f"wind:{layer_id}",
                    "layer_kind": "vector",
                }
            )
    return map_layers


def _wind_polygon_group_layers(
    runtime_result: dict[str, Any],
    include_group_ids: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    groups, _, _ = load_acceptance_registry()
    included_groups = None if include_group_ids is None else {str(group_id) for group_id in include_group_ids}
    map_layers: list[dict[str, Any]] = []
    for group in ordered_groups():
        if included_groups is not None and group.id not in included_groups:
            continue
        runtime_group = (runtime_result.get("groups") or {}).get(group.id)
        if runtime_group is None or runtime_group.get("geojson") is None:
            continue
        opacity = _wind_group_opacity(group.id)
        selected_sources = str(runtime_group.get("selected_sources", "") or "")
        analysis_value = int(round(float(runtime_group.get("analysis_value_m", 0.0) or 0.0)))
        buffer_layer_id = (
            f"wind:{WIND_SETTLEMENT_GROUP_ID}:buffer:{analysis_value}:{WIND_POPULATION_SOURCE_LAYER_ID}"
            if group.id == WIND_SETTLEMENT_GROUP_ID and selected_sources.strip().lower() == "population points"
            else f"wind:{group.id}:buffer:{analysis_value}"
        )
        map_layers.append(
            {
                "name": (
                    f"Vindbuffert: {_protected_group_label()}"
                    if group.id == SOLAR_PROTECTED_GROUP_ID
                    else f"Vindbuffert: {_settlement_group_label()}"
                    if group.id == WIND_SETTLEMENT_GROUP_ID
                    else f"Vindbuffert: {group_label(groups[group.id], WIND_CONTROL_LANGUAGE, groups[group.id].label)}"
                ),
                "buffer_layer_id": buffer_layer_id,
                "feature_collection": runtime_group["geojson"],
                "fill_property": "fill",
                "legend_items": [],
                "legend_id": f"wind_polygon_buffer_{group.id}",
                "legend_title": "",
                "default_visible": False,
                "stroke_color": _rgb_to_hex(groups[group.id].group_color),
                "fill_color": _rgb_to_hex(groups[group.id].group_color),
                "stroke_opacity": max(min(opacity * 0.95, 1.0), 0.0),
                "fill_opacity": max(min(opacity * 0.32, 1.0), 0.0),
                "weight": 2.2,
                "point_radius": 6,
                "use_global_opacity": False,
                "layer_kind": "vector",
            }
        )
    return map_layers

def _wind_polygon_group_summary_frame(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]],
    runtime_result: dict[str, Any],
) -> pd.DataFrame:
    groups, layers, _ = load_acceptance_registry()
    selected = normalize_group_layer_map(layer_selection)
    rows: list[dict[str, Any]] = []
    for group in ordered_groups():
        selected_layer_ids = selected.get(group.id, [])
        selected_labels = [
            layer_label(layers[layer_id], WIND_CONTROL_LANGUAGE, layers[layer_id].label)
            for layer_id in selected_layer_ids
            if layer_id in layers
        ]
        runtime_group = (runtime_result.get("groups") or {}).get(group.id)
        threshold_key = GROUP_PARAM_MAP.get(group.id)
        threshold_value = float(ui_params.get(threshold_key, group.analysis_default_m)) if threshold_key else 0.0
        land_share = runtime_group.get("land_share_pct") if isinstance(runtime_group, dict) else None
        rows.append(
            {
                "Regelgrupp": group_label(groups[group.id], WIND_CONTROL_LANGUAGE, groups[group.id].label),
                "Källager": ", ".join(selected_labels) if selected_labels else "-",
                "Avstånd m": int(round(threshold_value)),
                "Buffert synlig": bool(runtime_group and runtime_group.get("geojson")),
                "Landandel": "-" if land_share is None else f"{float(land_share):.1f}%",
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _wind_runtime_hex_neighbor_map(display_geometry_path: str) -> dict[str, list[str]]:
    land_hexes = set(load_h3_display_geometries(display_geometry_path))
    neighbor_map: dict[str, list[str]] = {}
    for hex_id in land_hexes:
        neighbor_map[str(hex_id)] = [str(neighbor) for neighbor in h3.grid_disk(str(hex_id), 1) if str(neighbor) != str(hex_id)]
    return neighbor_map


def _wind_runtime_hex_core_scores(frame: pd.DataFrame, neighbor_map: dict[str, list[str]]) -> pd.DataFrame:
    if frame.empty:
        return frame

    work = frame.copy()
    class_lookup = {str(row.hex_id): int(row.share_class_index) for row in work[["hex_id", "share_class_index"]].itertuples(index=False)}
    zone_id_lookup: dict[str, str] = {}
    zone_size_lookup: dict[str, int] = {}
    core_distance_lookup: dict[str, int] = {}
    core_score_lookup: dict[str, float] = {}
    rank_lookup_global: dict[str, int] = {}

    visited: set[str] = set()
    zone_counter = 0

    for hex_id in work["hex_id"].astype(str):
        if hex_id in visited:
            continue
        class_index = class_lookup.get(hex_id)
        if class_index is None:
            continue

        queue: deque[str] = deque([hex_id])
        component: list[str] = []
        visited.add(hex_id)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in neighbor_map.get(current, []):
                if neighbor in visited:
                    continue
                if class_lookup.get(neighbor) != class_index:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)

        component_set = set(component)
        boundary = [cell for cell in component if any(neighbor not in component_set for neighbor in neighbor_map.get(cell, []))]
        if not boundary:
            boundary = list(component)

        distance_lookup = {cell: None for cell in component}
        frontier: deque[str] = deque()
        for cell in boundary:
            distance_lookup[cell] = 0
            frontier.append(cell)

        while frontier:
            current = frontier.popleft()
            current_distance = int(distance_lookup[current] or 0)
            for neighbor in neighbor_map.get(current, []):
                if neighbor not in component_set:
                    continue
                if distance_lookup[neighbor] is not None:
                    continue
                distance_lookup[neighbor] = current_distance + 1
                frontier.append(neighbor)

        max_distance = max(int(distance_lookup[cell] or 0) for cell in component) if component else 0
        ranked_cells = sorted(component, key=lambda cell: (-int(distance_lookup[cell] or 0), cell))
        rank_lookup = {cell: idx + 1 for idx, cell in enumerate(ranked_cells)}
        zone_id = f"class_{class_index}_{zone_counter}"
        zone_counter += 1

        for cell in component:
            distance_value = int(distance_lookup[cell] or 0)
            core_value = 0.0 if max_distance <= 0 else float(distance_value) / float(max_distance)
            zone_id_lookup[cell] = zone_id
            zone_size_lookup[cell] = int(len(component))
            core_distance_lookup[cell] = distance_value
            core_score_lookup[cell] = round(core_value, 3)
            rank_lookup_global[cell] = int(rank_lookup[cell])

    work["zone_id"] = work["hex_id"].astype(str).map(zone_id_lookup).fillna("")
    work["zone_size"] = work["hex_id"].astype(str).map(zone_size_lookup).fillna(0).astype(int)
    work["core_distance"] = work["hex_id"].astype(str).map(core_distance_lookup).fillna(0).astype(int)
    work["core_score"] = work["hex_id"].astype(str).map(core_score_lookup).fillna(0.0).astype(float)
    work["center_mass_rank"] = work["hex_id"].astype(str).map(rank_lookup_global).fillna(1).astype(int)

    return work


def _wind_runtime_hex_color(area_share_pct: float, core_score: float, zone_size: int) -> str:
    class_spec = _wind_share_class_spec(area_share_pct)
    share_value = float(area_share_pct)
    core_value = max(0.0, min(1.0, float(core_score)))
    zone_size_value = max(0, int(zone_size))
    if zone_size_value <= 1:
        return str(class_spec["base_color"])

    if share_value <= 0.0:
        core_target = _mix_hex_colors(str(class_spec["core_color"]), "#180000", min(1.0, float(zone_size_value) / 150.0))
        intensity = (core_value ** 0.82) * min(1.0, 0.48 + (float(zone_size_value) / 120.0))
        return _mix_hex_colors(str(class_spec["base_color"]), core_target, intensity)

    if share_value >= 80.0:
        core_target = _mix_hex_colors(str(class_spec["core_color"]), "#082f6f", min(1.0, max(0.0, float(zone_size_value - 4)) / 40.0))
        intensity = (core_value ** 0.86) * min(0.82, 0.36 + (float(zone_size_value) / 70.0))
        return _mix_hex_colors(str(class_spec["base_color"]), core_target, intensity)

    intensity = (core_value ** 0.9) * min(0.56, 0.16 + (float(zone_size_value) / 52.0))
    return _mix_hex_colors(str(class_spec["base_color"]), str(class_spec["core_color"]), intensity)


@st.cache_data(show_spinner=False)
def _build_wind_runtime_hex_layer_data(
    combined_geojson_json: str,
    display_geometry_path: str,
    target_resolution: int,
) -> pd.DataFrame:
    combined_geojson = json.loads(combined_geojson_json)
    base_share = runtime_combined_hex_frame(combined_geojson, WIND_RUNTIME_BASE_RESOLUTION, [])
    raw_share = pd.DataFrame(columns=["hex_id", "potential_area_share_pct", "potential_area_km2"])
    if not base_share.empty and "hex_id" in base_share.columns:
        raw_share = base_share[["hex_id", "wind_score"]].rename(columns={"wind_score": "potential_area_share_pct"}).copy()
        raw_share["hex_id"] = raw_share["hex_id"].astype(str)
        raw_share["potential_area_share_pct"] = raw_share["potential_area_share_pct"].fillna(0.0).astype(float).clip(lower=0.0, upper=100.0)
        base_hex_area = float(h3_hex_area_km2(WIND_RUNTIME_BASE_RESOLUTION))
        raw_share["potential_area_km2"] = raw_share["potential_area_share_pct"].div(100.0) * base_hex_area
        if int(target_resolution) < WIND_RUNTIME_BASE_RESOLUTION:
            raw_share["hex_id"] = raw_share["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
            raw_share = (
                raw_share.groupby("hex_id", as_index=False)
                .agg(potential_area_km2=("potential_area_km2", "sum"))
            )
            target_hex_area = float(h3_hex_area_km2(int(target_resolution)))
            raw_share["potential_area_share_pct"] = (
                raw_share["potential_area_km2"] / max(target_hex_area, 1e-9) * 100.0
            ).clip(lower=0.0, upper=100.0)
    display_geometries = load_h3_display_geometries(display_geometry_path)
    frame = pd.DataFrame({"hex_id": list(display_geometries.keys())})
    if not raw_share.empty and "hex_id" in raw_share.columns:
        frame = frame.merge(
            raw_share[["hex_id", "potential_area_share_pct", "potential_area_km2"]],
            on="hex_id",
            how="left",
        )
    frame["potential_area_share_pct"] = frame["potential_area_share_pct"].fillna(0.0).astype(float).clip(lower=0.0, upper=100.0)
    if "potential_area_km2" not in frame.columns:
        frame["potential_area_km2"] = 0.0
    frame["potential_area_km2"] = pd.to_numeric(frame["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    frame["potential_area_share"] = frame["potential_area_share_pct"].div(100.0).round(4)

    class_specs = []
    for share_value in frame["potential_area_share_pct"]:
        class_spec = _wind_share_class_spec(float(share_value))
        class_specs.append((class_spec["id"], class_spec["label"], WIND_SHARE_CLASS_SPECS.index(class_spec)))
    frame["share_class_id"] = [item[0] for item in class_specs]
    frame["share_class_label"] = [item[1] for item in class_specs]
    frame["share_class_index"] = [item[2] for item in class_specs]

    frame = _wind_runtime_hex_core_scores(frame, _wind_runtime_hex_neighbor_map(display_geometry_path))
    frame["fill"] = [
        _wind_runtime_hex_color(share_value, core_value, zone_size)
        for share_value, core_value, zone_size in zip(
            frame["potential_area_share_pct"],
            frame["core_score"],
            frame["zone_size"],
        )
    ]
    frame["core_label"] = [
        _wind_core_label(core_value, zone_size)
        for core_value, zone_size in zip(frame["core_score"], frame["zone_size"])
    ]
    frame["stroke"] = frame["fill"].map(lambda value: _mix_hex_colors(str(value), "#3a3a3a", 0.28))
    return frame.sort_values("hex_id").reset_index(drop=True)


def _target_resolution_distance_frame(
    distance_frame: pd.DataFrame,
    target_resolution: int,
    display_geometry_path: str,
) -> pd.DataFrame:
    if distance_frame.empty or "hex_id" not in distance_frame.columns:
        return pd.DataFrame(columns=["hex_id", "distance_m", "intersects"])
    work = distance_frame[["hex_id", "distance_m", "intersects"]].copy()
    work["hex_id"] = work["hex_id"].astype(str)
    try:
        source_resolution = int(h3.get_resolution(str(work["hex_id"].iloc[0])))
    except Exception:
        source_resolution = int(target_resolution)
    if source_resolution > int(target_resolution):
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
        work = (
            work.groupby("hex_id", as_index=False)
            .agg(distance_m=("distance_m", "min"), intersects=("intersects", "max"))
        )
    elif source_resolution < int(target_resolution):
        work["source_hex_id"] = work["hex_id"].astype(str)
        display_geometries = load_h3_display_geometries(display_geometry_path)
        target = pd.DataFrame({"hex_id": list(display_geometries.keys())})
        if not target.empty:
            target["source_hex_id"] = target["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), source_resolution)))
            source_work = work[["source_hex_id", "distance_m", "intersects"]].copy()
            work = target.merge(source_work, on="source_hex_id", how="left")[["hex_id", "distance_m", "intersects"]]
    work["distance_m"] = pd.to_numeric(work["distance_m"], errors="coerce")
    work["intersects"] = work["intersects"].fillna(False).astype(bool)
    return work[["hex_id", "distance_m", "intersects"]].copy()


def _wind_establishment_intersection_block_frame(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "wind_hard_exclusion_intersects"])
    groups_meta = runtime_result.get("groups") if isinstance(runtime_result, dict) else None
    if not isinstance(groups_meta, dict):
        return pd.DataFrame(columns=["hex_id", "wind_hard_exclusion_intersects"])
    _, _, registry_meta = load_acceptance_registry()
    frames: list[pd.DataFrame] = []
    for group_id in WIND_ESTABLISHMENT_INTERSECTION_BLOCK_GROUP_IDS:
        group_meta = groups_meta.get(group_id)
        if not isinstance(group_meta, dict):
            continue
        layer_ids = [str(layer_id) for layer_id in (group_meta.get("active_layer_ids") or [])]
        for layer_id in _solar_available_filter_layer_ids(group_id, layer_ids):
            distance_frame = _target_resolution_distance_frame(
                distance_table_for_layer(registry_meta, layer_id),
                int(target_resolution),
                display_geometry_path,
            )
            if distance_frame.empty:
                continue
            blocked = distance_frame.loc[distance_frame["intersects"].astype(bool), ["hex_id"]].copy()
            if not blocked.empty:
                frames.append(blocked)
    if not frames:
        return pd.DataFrame(columns=["hex_id", "wind_hard_exclusion_intersects"])
    combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["hex_id"])
    combined["wind_hard_exclusion_intersects"] = True
    return combined[["hex_id", "wind_hard_exclusion_intersects"]]


def _allocation_priority_distance_cap_m(group: Any) -> float:
    candidates = [
        float(getattr(group, "analysis_max_m", 0.0) or 0.0),
        float(getattr(group, "analysis_default_m", 0.0) or 0.0) * 2.0,
        float(getattr(group, "analysis_step_m", 0.0) or 0.0) * 20.0,
    ]
    cap = max([value for value in candidates if math.isfinite(value) and value > 0.0] or [1000.0])
    return max(cap, 1.0)


def _allocation_priority_layer_groups(technology: str) -> list[dict[str, Any]]:
    groups, layers, registry_meta = load_acceptance_registry()
    availability = _wind_layer_status_lookup(registry_meta)
    raw_groups: list[tuple[str, list[str]]] = []
    if str(technology) == "solar":
        raw_groups.append((WIND_SETTLEMENT_GROUP_ID, [WIND_POPULATION_SOURCE_LAYER_ID]))
        for group_id in SOLAR_FILTER_GROUP_IDS:
            raw_groups.append((group_id, list(_solar_filter_layer_ids(group_id))))
    else:
        for group_id, layer_ids in WIND_GROUP_LAYER_DEFAULTS.items():
            raw_groups.append((group_id, list(layer_ids)))

    specs: list[dict[str, Any]] = []
    seen_group_ids: set[str] = set()
    for group_id, layer_ids in raw_groups:
        if group_id in seen_group_ids:
            continue
        seen_group_ids.add(group_id)
        group = groups.get(group_id)
        if group is None:
            continue
        ready_layer_ids = [
            str(layer_id)
            for layer_id in layer_ids
            if str(layer_id) in layers and _wind_layer_is_ready(str(layer_id), availability)
        ]
        if not ready_layer_ids:
            continue
        specs.append(
            {
                "group_id": str(group_id),
                "group": group,
                "layer_ids": ready_layer_ids,
                "label": group_label(group, WIND_CONTROL_LANGUAGE, group.label),
                "analysis_kind": str(group.analysis_kind),
            }
        )
    return specs


def _allocation_priority_group_score(
    analysis_kind: str,
    min_distance_m: pd.Series,
    any_intersection: pd.Series,
    cap_m: float,
) -> tuple[pd.Series, str]:
    distance = pd.to_numeric(min_distance_m, errors="coerce")
    intersects = any_intersection.fillna(False).astype(bool)
    cap = max(float(cap_m or 0.0), 1.0)
    if str(analysis_kind) == "proximity_feasibility":
        score = (1.0 - (distance / cap)).clip(lower=0.0, upper=1.0).fillna(0.0)
        score.loc[intersects] = 1.0
        return score, "proximity"
    score = (distance / cap).clip(lower=0.0, upper=1.0).fillna(0.0)
    score.loc[intersects] = 0.0
    return score, "clearance"


def _allocation_priority_reason(row: Any, components: list[dict[str, str]]) -> str:
    strengths: list[str] = []
    compromises: list[str] = []
    for component in components:
        try:
            value = float(getattr(row, component["column"], 0.0) or 0.0)
        except Exception:
            value = 0.0
        label = str(component["label"]).lower()
        if component["role"] == "proximity":
            if value >= 0.67:
                strengths.append(f"nära {label}")
            elif value <= 0.33:
                compromises.append(f"långt från {label}")
        else:
            if value >= 0.67:
                strengths.append(f"långt från {label}")
            elif value <= 0.33:
                compromises.append(f"nära {label}")
    parts: list[str] = []
    if strengths:
        parts.append("Styrkor: " + ", ".join(strengths[:3]))
    if compromises:
        parts.append("Kompromiss: " + ", ".join(compromises[:2]))
    return ". ".join(parts) if parts else "Balanserad placering enligt landskaps- och teknikranking."


def _apply_landscape_priority_to_allocation_frame(
    frame: pd.DataFrame,
    region: dict[str, Any],
    technology: str,
    target_resolution: int,
) -> pd.DataFrame:
    if frame.empty or "hex_id" not in frame.columns:
        return frame
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return frame

    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    groups, _, registry_meta = load_acceptance_registry()
    component_cols: list[str] = []
    component_meta: list[dict[str, str]] = []
    for spec in _allocation_priority_layer_groups(str(technology)):
        group_id = str(spec["group_id"])
        group = groups.get(group_id)
        if group is None:
            continue
        parts: list[pd.DataFrame] = []
        for layer_id in spec["layer_ids"]:
            layer_frame = _target_resolution_distance_frame(
                distance_table_for_layer(registry_meta, str(layer_id)),
                int(target_resolution),
                display_geometry_path,
            )
            if not layer_frame.empty:
                parts.append(layer_frame)
        if not parts:
            continue
        merged = work[["hex_id"]].copy()
        distance_cols: list[str] = []
        intersect_cols: list[str] = []
        for idx, part in enumerate(parts):
            distance_col = f"distance_{idx}"
            intersect_col = f"intersects_{idx}"
            merged = merged.merge(
                part.rename(columns={"distance_m": distance_col, "intersects": intersect_col}),
                on="hex_id",
                how="left",
            )
            distance_cols.append(distance_col)
            intersect_cols.append(intersect_col)
        if not distance_cols:
            continue
        intersection_frame = pd.DataFrame(
            {
                column: merged[column].where(merged[column].notna(), False).astype(bool)
                for column in intersect_cols
            }
        )
        score, role = _allocation_priority_group_score(
            str(spec["analysis_kind"]),
            merged[distance_cols].min(axis=1, skipna=True),
            intersection_frame.any(axis=1),
            _allocation_priority_distance_cap_m(group),
        )
        column = f"allocation_priority_component_{group_id}"
        work[column] = score.astype(float).clip(lower=0.0, upper=1.0)
        component_cols.append(column)
        component_meta.append({"column": column, "label": str(spec["label"]), "role": role})

    if component_cols:
        work["landscape_priority_score"] = work[component_cols].mean(axis=1, skipna=True).fillna(0.0).clip(lower=0.0, upper=1.0)
        reason_frame = work[component_cols].copy()
        work["allocation_priority_reason"] = [
            _allocation_priority_reason(row, component_meta)
            for row in reason_frame.itertuples(index=False)
        ]
    else:
        work["landscape_priority_score"] = 0.0
        work["allocation_priority_reason"] = "Prioriteras efter befintlig potential; inga distanskomponenter hittades."

    if str(technology) == "wind":
        share_source = work["potential_area_share_pct"] if "potential_area_share_pct" in work.columns else pd.Series(0.0, index=work.index)
        core_source = work["core_score"] if "core_score" in work.columns else pd.Series(0.0, index=work.index)
        share = pd.to_numeric(share_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
        core = pd.to_numeric(core_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
        work["allocation_priority_score"] = (
            (0.65 * work["landscape_priority_score"]) + (0.20 * share) + (0.15 * core)
        ).clip(lower=0.0, upper=1.0)
        work["core_score_before_allocation_priority"] = core
        work["core_score"] = work["allocation_priority_score"]
    else:
        if "potential_score" in work.columns:
            potential_source = work["potential_score"]
        elif "solar_score" in work.columns:
            potential_source = work["solar_score"]
        else:
            potential_source = work.get("potential_area_share_pct", pd.Series(0.0, index=work.index))
        potential = pd.to_numeric(potential_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
        work["allocation_priority_score"] = (
            (0.75 * work["landscape_priority_score"]) + (0.25 * potential)
        ).clip(lower=0.0, upper=1.0)
    work["technical_priority_score"] = work["allocation_priority_score"]
    return work.drop(columns=component_cols, errors="ignore")


def _population_buffer_share_frame(
    region: dict[str, Any],
    target_resolution: int,
    buffer_m: float,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    _, layers, registry_meta = load_acceptance_registry()
    if WIND_POPULATION_SOURCE_LAYER_ID not in layers:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    distance_frame = _target_resolution_distance_frame(
        distance_table_for_layer(registry_meta, WIND_POPULATION_SOURCE_LAYER_ID),
        int(target_resolution),
        display_geometry_path,
    )
    if distance_frame.empty:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    distance = pd.to_numeric(distance_frame["distance_m"], errors="coerce")
    in_buffer = distance.le(float(buffer_m or 0.0)).fillna(False) | distance_frame["intersects"].fillna(False).astype(bool)
    out = distance_frame.loc[in_buffer, ["hex_id"]].copy()
    out["filter_buffer_share_pct"] = 100.0
    return out[["hex_id", "filter_buffer_share_pct"]]


def _acceptance_series_for_group(
    analysis_kind: str,
    min_distance_m: pd.Series,
    any_intersection: pd.Series,
    threshold_m: float,
) -> pd.Series:
    distance = pd.to_numeric(min_distance_m, errors="coerce")
    intersects = any_intersection.fillna(False).astype(bool)
    threshold = float(threshold_m or 0.0)
    if str(analysis_kind) == "proximity_feasibility":
        capped = max(threshold, 1.0)
        acceptance = (1.0 - (distance / capped)).clip(lower=0.0, upper=1.0).fillna(0.0)
        acceptance.loc[intersects] = 1.0
        return acceptance
    if str(analysis_kind) == "hard_exclusion":
        blocked = intersects if threshold <= 0 else (intersects | distance.le(threshold).fillna(False))
        return (~blocked).astype(float)
    if threshold <= 0:
        return (~intersects).astype(float)
    ramp_end = max(float(threshold * 2.0), float(threshold + 1.0))
    acceptance = ((distance - threshold) / (ramp_end - threshold)).clip(lower=0.0, upper=1.0).fillna(0.0)
    acceptance.loc[intersects] = 0.0
    return acceptance


def _finalize_fast_wind_share_frame(
    frame: pd.DataFrame,
    display_geometry_path: str,
    compute_core: bool = True,
) -> pd.DataFrame:
    work = frame.copy()
    work["potential_area_share_pct"] = pd.to_numeric(work["potential_area_share_pct"], errors="coerce").fillna(0.0).clip(
        lower=0.0,
        upper=100.0,
    )
    if "potential_area_km2" not in work.columns:
        work["potential_area_km2"] = work["potential_area_share_pct"].div(100.0) * float(h3_hex_area_km2(WIND_RUNTIME_BASE_RESOLUTION))
    work["potential_area_km2"] = pd.to_numeric(work["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    work["potential_area_share"] = work["potential_area_share_pct"].div(100.0).round(4)
    class_specs = [_wind_share_class_spec(float(value)) for value in work["potential_area_share_pct"]]
    work["share_class_id"] = [str(item["id"]) for item in class_specs]
    work["share_class_label"] = [str(item["label"]) for item in class_specs]
    work["share_class_index"] = [WIND_SHARE_CLASS_SPECS.index(item) for item in class_specs]
    if compute_core:
        work = _wind_runtime_hex_core_scores(work, _wind_runtime_hex_neighbor_map(display_geometry_path))
    else:
        work["core_score"] = 0.0
        work["zone_size"] = 1
        work["center_mass_rank"] = 1
    work["fill"] = [
        _wind_runtime_hex_color(share_value, core_value, zone_size)
        for share_value, core_value, zone_size in zip(work["potential_area_share_pct"], work["core_score"], work["zone_size"])
    ]
    work["core_label"] = [_wind_core_label(core_value, zone_size) for core_value, zone_size in zip(work["core_score"], work["zone_size"])]
    work["stroke"] = work["fill"].map(lambda value: _mix_hex_colors(str(value), "#3a3a3a", 0.28))
    return work.sort_values("hex_id").reset_index(drop=True)


def _wind_fast_distance_runtime_result(
    region: dict[str, Any],
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]],
    target_resolution: int,
) -> dict[str, Any] | None:
    if str(region.get("region_id", "")).lower() != "trondelag":
        return None
    selected = normalize_group_layer_map(layer_selection)
    if not any(selected.values()):
        return None
    groups, layers, registry_meta = load_acceptance_registry()
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return None
    display_geometries = load_h3_display_geometries(display_geometry_path)
    frame = pd.DataFrame({"hex_id": list(display_geometries.keys())})
    if frame.empty:
        return None
    frame["potential_area_share_pct"] = 100.0
    active_groups: list[str] = []
    group_meta: dict[str, dict[str, Any]] = {}
    for group_id, layer_ids in selected.items():
        group = groups.get(group_id)
        if group is None or not layer_ids:
            continue
        distance_parts: list[pd.DataFrame] = []
        for layer_id in layer_ids:
            layer_df = _target_resolution_distance_frame(
                distance_table_for_layer(registry_meta, layer_id),
                int(target_resolution),
                display_geometry_path,
            )
            if not layer_df.empty:
                distance_parts.append(layer_df)
        if not distance_parts:
            continue
        merged = frame[["hex_id"]].copy()
        distance_cols: list[str] = []
        intersect_cols: list[str] = []
        for idx, part in enumerate(distance_parts):
            distance_col = f"distance_{idx}"
            intersect_col = f"intersects_{idx}"
            renamed = part.rename(columns={"distance_m": distance_col, "intersects": intersect_col})
            merged = merged.merge(renamed, on="hex_id", how="left")
            distance_cols.append(distance_col)
            intersect_cols.append(intersect_col)
        min_distance = merged[distance_cols].min(axis=1, skipna=True)
        any_intersection = merged[intersect_cols].fillna(False).astype(bool).any(axis=1)
        threshold_key = GROUP_PARAM_MAP.get(group_id)
        threshold_m = float(ui_params.get(threshold_key, group.analysis_default_m)) if threshold_key else float(group.analysis_default_m)
        group_acceptance = _acceptance_series_for_group(group.analysis_kind, min_distance, any_intersection, threshold_m)
        frame["potential_area_share_pct"] = frame["potential_area_share_pct"].combine(
            group_acceptance.mul(100.0),
            min,
        )
        active_groups.append(group_id)
        role = "feasible" if group.analysis_kind == "proximity_feasibility" else "conflict"
        share_series = group_acceptance.mul(100.0) if role == "feasible" else (1.0 - group_acceptance).mul(100.0)
        selected_labels = [
            layer_label(layers[layer_id], WIND_CONTROL_LANGUAGE, layers[layer_id].label)
            for layer_id in layer_ids
            if layer_id in layers
        ]
        group_meta[group_id] = {
            "label": group.label,
            "analysis_kind": group.analysis_kind,
            "role": role,
            "active_layer_ids": list(layer_ids),
            "selected_sources": selected_labels,
            "analysis_value_m": float(threshold_m),
            "land_share_pct": float(share_series.fillna(0.0).mean()),
        }
    if not active_groups:
        return None
    hex_area = float(h3_hex_area_km2(int(target_resolution)))
    frame["potential_area_km2"] = frame["potential_area_share_pct"].div(100.0) * hex_area
    frame = _finalize_fast_wind_share_frame(frame, display_geometry_path, compute_core=False)
    return {
        "cache_key": f"trondelag_fast_distance_r{int(target_resolution)}",
        "groups": group_meta,
        "combined": {"land_share_pct": float(frame["potential_area_share_pct"].mean())},
        "fast_distance_frame": frame,
        "fast_distance": True,
    }


def _wind_runtime_hex_layer_frame(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    fast_frame = runtime_result.get("fast_distance_frame")
    if isinstance(fast_frame, pd.DataFrame):
        return fast_frame.copy()
    combined = runtime_result.get("combined")
    if not isinstance(combined, dict) or combined.get("geojson") is None:
        return pd.DataFrame()
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    return _build_wind_runtime_hex_layer_data(
        json.dumps(combined["geojson"], sort_keys=True, ensure_ascii=False),
        display_geometry_path,
        int(target_resolution),
    )


def _wind_runtime_hex_feature_collection(
    frame: pd.DataFrame,
    display_geometry_path: str,
    target_resolution: int,
) -> dict[str, Any]:
    display_geometries = load_h3_display_geometries(display_geometry_path)
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        geometry = display_geometries.get(str(row.hex_id))
        if geometry is None:
            continue
        popup = (
            f"<strong>{WIND_LANDSCAPE_POTENTIAL_LABEL}</strong><br>"
            f"Hex: {row.hex_id}<br>"
            f"LP-andel: {float(row.potential_area_share_pct):.1f}%<br>"
            f"Klass: {row.share_class_label}<br>"
            f"Kärnläge: {row.core_label}<br>"
            f"Kärnscore: {float(row.core_score):.2f}<br>"
            f"Sammanhängande zon: {int(row.zone_size)} hex<br>"
            f"Kärnrank i zon: {int(row.center_mass_rank)} av {int(row.zone_size)}<br>"
            f"<em>Mörkare nyans betyder längre in i en sammanhängande zon av samma potentialklass.</em>"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": str(row.hex_id),
                    "fill": str(row.fill),
                    "stroke": str(row.stroke),
                    "core_score": float(row.core_score),
                    "core_label": str(row.core_label),
                    "zone_size": int(row.zone_size),
                    "tooltip_title": f"{WIND_LANDSCAPE_POTENTIAL_LABEL} {float(row.potential_area_share_pct):.1f}%",
                    "tooltip_body": f"{row.share_class_label} · {row.core_label}",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _wind_runtime_hex_layer(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
    control_name: str | None = None,
) -> dict[str, Any] | None:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return None
    frame = _wind_runtime_hex_layer_frame(region, runtime_result, int(target_resolution))
    if frame.empty:
        return None
    return {
        "name": str(control_name or WIND_LANDSCAPE_POTENTIAL_LABEL),
        "feature_collection": _wind_runtime_hex_feature_collection(frame, display_geometry_path, int(target_resolution)),
        "fill_property": "fill",
        "stroke_property": "stroke",
        "legend_items": _wind_share_legend_items(),
        "legend_id": "wind_polygon_hex_share",
        "legend_title": WIND_POTENTIAL_HEX_LABEL,
        "default_visible": True,
        "stroke": False,
        "weight": 0.0,
        "point_radius": 4,
        "z_index": 410,
        "layer_kind": "hex",
        "opacity_family": str(control_name or WIND_LANDSCAPE_POTENTIAL_LABEL),
        "opacity_label": str(control_name or WIND_LANDSCAPE_POTENTIAL_LABEL),
    }


def _rollup_energy_area_proposal_frame(
    selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
) -> pd.DataFrame:
    if selected.empty or int(target_resolution) >= int(source_resolution):
        return selected.copy()

    work = selected.copy()

    def _numeric_column(column: str, default: float = 0.0) -> pd.Series:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce").fillna(default)
        return pd.Series(default, index=work.index, dtype="float64")

    work["hex_id"] = work["hex_id"].astype(str).map(lambda value: h3.cell_to_parent(value, int(target_resolution)))
    work["allocated_area_km2"] = _numeric_column("allocated_area_km2", 0.0)
    work["potential_area_km2"] = _numeric_column("potential_area_km2", 0.0)
    work["allocated_twh"] = _numeric_column("allocated_twh", 0.0)
    work["selected_rank"] = _numeric_column("selected_rank", 0.0).astype(int)
    work["core_score"] = _numeric_column("core_score", 0.0)
    work["landscape_priority_score"] = _numeric_column("landscape_priority_score", 0.0)
    work["allocation_priority_score"] = _numeric_column("allocation_priority_score", 0.0)
    work["social_acceptance_priority_score"] = _numeric_column("social_acceptance_priority_score", 0.0)
    work["social_acceptance_value"] = _numeric_column("social_acceptance_value", 1.0)
    work["social_acceptance_allocation_priority_pct"] = _numeric_column("social_acceptance_allocation_priority_pct", 0.0)
    work["zone_size"] = _numeric_column("zone_size", 0.0).astype(int)
    work["expansion_ring"] = _numeric_column("expansion_ring", 0.0).astype(int)
    if "allocation_priority_reason" not in work.columns:
        work["allocation_priority_reason"] = ""
    if "outside_et" not in work.columns:
        work["outside_et"] = False
    if "reserved_by_other_technology" not in work.columns:
        work["reserved_by_other_technology"] = False
    work["outside_et"] = work["outside_et"].fillna(False).astype(bool)
    work["reserved_by_other_technology"] = work["reserved_by_other_technology"].fillna(False).astype(bool)
    work["outside_area_km2"] = work["allocated_area_km2"].where(work["outside_et"], 0.0)
    work["inside_area_km2"] = work["allocated_area_km2"].where(~work["outside_et"], 0.0)

    def _first_text(values: pd.Series) -> str:
        labels = [str(value) for value in values.dropna().tolist() if str(value)]
        unique = list(dict.fromkeys(labels))
        return ", ".join(unique[:3])

    rolled = (
        work.groupby("hex_id", as_index=False)
        .agg(
            selected_rank=("selected_rank", "min"),
            potential_area_km2=("potential_area_km2", "sum"),
            allocated_area_km2=("allocated_area_km2", "sum"),
            allocated_twh=("allocated_twh", "sum"),
            outside_area_km2=("outside_area_km2", "sum"),
            inside_area_km2=("inside_area_km2", "sum"),
            core_score=("core_score", "max"),
            landscape_priority_score=("landscape_priority_score", "max"),
            allocation_priority_score=("allocation_priority_score", "max"),
            allocation_priority_reason=("allocation_priority_reason", _first_text),
            social_acceptance_priority_score=("social_acceptance_priority_score", "max"),
            social_acceptance_value=("social_acceptance_value", "mean"),
            social_acceptance_allocation_priority_pct=("social_acceptance_allocation_priority_pct", "max"),
            zone_size=("zone_size", "sum"),
            expansion_ring=("expansion_ring", "max"),
            reserved_by_other_technology=("reserved_by_other_technology", "max"),
        )
        .sort_values(["selected_rank", "hex_id"])
        .reset_index(drop=True)
    )
    hex_area = h3_hex_area_km2(int(target_resolution))
    rolled["outside_et"] = rolled["outside_area_km2"].gt(rolled["inside_area_km2"])
    rolled["allocation_phase"] = rolled["outside_et"].map(lambda value: "Utanför LP" if value else "Inom LP")
    rolled["potential_area_share_pct"] = (rolled["potential_area_km2"] / max(hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    rolled["allocated_hex_share_pct"] = (rolled["allocated_area_km2"] / max(hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    rolled["remaining_area_after_km2"] = 0.0
    rolled["allocated_gwh"] = rolled["allocated_twh"] * 1000.0
    return rolled


def _combined_establishment_legend_items() -> list[dict[str, str]]:
    order = ["wind_and_solar", "wind_only", "solar_only", "not_suitable"]
    return [
        {"label": ESTABLISHMENT_CLASS_SPECS[class_id]["label"], "color": ESTABLISHMENT_CLASS_SPECS[class_id]["color"]}
        for class_id in order
    ]


def _establishment_source_frame(
    selected: pd.DataFrame,
    technology: str,
    target_resolution: int,
    source_resolution: int,
) -> pd.DataFrame:
    columns = [
        "hex_id",
        f"{technology}_suitable",
        f"{technology}_rank",
        f"{technology}_potential_score",
        f"{technology}_potential_area_km2",
        f"{technology}_allocated_area_km2",
        f"{technology}_allocated_gwh",
        f"{technology}_allocated_hex_share_pct",
        f"{technology}_landscape_priority_score",
        f"{technology}_allocation_priority_score",
        f"{technology}_allocation_priority_reason",
        f"{technology}_social_acceptance_priority_score",
        f"{technology}_social_acceptance_value",
        f"{technology}_social_acceptance_allocation_priority_pct",
        f"{technology}_last_resort_overlap",
        f"{technology}_outside_lp",
        f"{technology}_conflict_area_km2",
        f"{technology}_conflict",
        f"{technology}_expansion_ring",
        f"{technology}_phase",
    ]
    if selected.empty:
        return pd.DataFrame(columns=columns)

    if technology == "wind":
        rolled = _rollup_energy_area_proposal_frame(selected, int(target_resolution), int(source_resolution))
        score_column = "potential_area_share_pct"
    else:
        rolled = _rollup_solar_establishment_frame(selected, int(target_resolution), int(source_resolution))
        score_column = "potential_score"
    if rolled.empty or "hex_id" not in rolled.columns:
        return pd.DataFrame(columns=columns)

    work = rolled.copy()
    work["hex_id"] = work["hex_id"].astype(str)

    def _numeric_source(column: str, default: float = 0.0) -> pd.Series:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce").fillna(default)
        return pd.Series(default, index=work.index, dtype="float64")

    work[f"{technology}_rank"] = _numeric_source("selected_rank", 0.0).astype(int)
    work[f"{technology}_potential_score"] = _numeric_source(score_column, 0.0).clip(lower=0.0, upper=100.0)
    work[f"{technology}_potential_area_km2"] = _numeric_source("potential_area_km2", 0.0).clip(lower=0.0)
    work[f"{technology}_allocated_area_km2"] = _numeric_source("allocated_area_km2", 0.0).clip(lower=0.0)
    if "allocated_gwh" in work.columns:
        allocated_gwh = _numeric_source("allocated_gwh", 0.0)
    else:
        allocated_gwh = _numeric_source("allocated_twh", 0.0) * 1000.0
    work[f"{technology}_allocated_gwh"] = allocated_gwh.clip(lower=0.0)
    work[f"{technology}_allocated_hex_share_pct"] = _numeric_source("allocated_hex_share_pct", 0.0).clip(lower=0.0, upper=100.0)
    work[f"{technology}_landscape_priority_score"] = _numeric_source("landscape_priority_score", 0.0).clip(lower=0.0, upper=1.0)
    work[f"{technology}_allocation_priority_score"] = _numeric_source("allocation_priority_score", 0.0).clip(lower=0.0, upper=1.0)
    work[f"{technology}_social_acceptance_priority_score"] = _numeric_source("social_acceptance_priority_score", 0.0).clip(
        lower=0.0,
        upper=1.0,
    )
    work[f"{technology}_social_acceptance_value"] = _numeric_source("social_acceptance_value", 1.0).clip(lower=0.0, upper=1.0)
    work[f"{technology}_social_acceptance_allocation_priority_pct"] = _numeric_source(
        "social_acceptance_allocation_priority_pct",
        0.0,
    ).clip(lower=0.0, upper=100.0)
    if "reserved_by_other_technology" in work.columns:
        work[f"{technology}_last_resort_overlap"] = work["reserved_by_other_technology"].fillna(False).astype(bool)
    else:
        work[f"{technology}_last_resort_overlap"] = False
    if "allocation_priority_reason" in work.columns:
        work[f"{technology}_allocation_priority_reason"] = work["allocation_priority_reason"].fillna("").astype(str)
    else:
        work[f"{technology}_allocation_priority_reason"] = ""
    if "outside_et" in work.columns:
        work[f"{technology}_outside_lp"] = work["outside_et"].fillna(False).astype(bool)
    else:
        work[f"{technology}_outside_lp"] = False
    work[f"{technology}_suitable"] = work[f"{technology}_allocated_area_km2"].gt(0.0) & ~work[f"{technology}_outside_lp"]
    work[f"{technology}_conflict_area_km2"] = work[f"{technology}_allocated_area_km2"].where(work[f"{technology}_outside_lp"], 0.0)
    work[f"{technology}_conflict"] = work[f"{technology}_conflict_area_km2"].gt(0.0)
    work[f"{technology}_expansion_ring"] = _numeric_source("expansion_ring", 0.0).astype(int)
    if "allocation_phase" in work.columns:
        work[f"{technology}_phase"] = work["allocation_phase"].fillna("").astype(str)
    else:
        work[f"{technology}_phase"] = work[f"{technology}_outside_lp"].map(lambda value: "Utanför LP" if value else "Inom LP")
    return work.reindex(columns=columns)


def _potential_establishment_source_frame(
    source: pd.DataFrame,
    technology: str,
    target_resolution: int,
    source_resolution: int,
    coarse_filter_intersection_blocks: bool = False,
) -> pd.DataFrame:
    columns = [
        "hex_id",
        f"{technology}_suitable",
        f"{technology}_potential_score",
        f"{technology}_potential_area_km2",
    ]
    if source.empty or "hex_id" not in source.columns:
        return pd.DataFrame(columns=columns)

    work = source.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    source_hex_area = float(h3_hex_area_km2(int(source_resolution)))
    target_hex_area = float(h3_hex_area_km2(int(target_resolution)))

    if technology == "wind":
        score_col = "potential_area_share_pct" if "potential_area_share_pct" in work.columns else "wind_score"
        if "potential_area_km2" in work.columns:
            work["potential_area_km2"] = pd.to_numeric(work["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
            if score_col in work.columns:
                work["potential_score"] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
            else:
                work["potential_score"] = (work["potential_area_km2"] / max(source_hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
        else:
            work["potential_score"] = pd.to_numeric(work.get(score_col), errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
            work["potential_area_km2"] = work["potential_score"] / 100.0 * source_hex_area
        if "wind_hard_exclusion_intersects" not in work.columns:
            work["wind_hard_exclusion_intersects"] = False
        work["wind_hard_exclusion_intersects"] = work["wind_hard_exclusion_intersects"].fillna(False).astype(bool)
    else:
        if "potential_area_km2" in work.columns:
            area = pd.to_numeric(work["potential_area_km2"], errors="coerce").fillna(0.0)
        elif "potential_area_m2" in work.columns:
            area = pd.to_numeric(work["potential_area_m2"], errors="coerce").fillna(0.0) / 1_000_000.0
        else:
            area = pd.Series(0.0, index=work.index, dtype="float64")
        work["potential_area_km2"] = area.clip(lower=0.0, upper=source_hex_area)
        score_col = "potential_area_share_pct" if "potential_area_share_pct" in work.columns else "solar_score"
        if score_col in work.columns:
            work["potential_score"] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
        else:
            work["potential_score"] = (work["potential_area_km2"] / max(source_hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
        filter_share_sources = [
            pd.to_numeric(work[column], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
            for column in [
                "large_filter_buffer_share_pct",
                "filter_buffer_share_pct",
                "protected_buffer_share_pct",
            ]
            if column in work.columns
        ]
        if filter_share_sources:
            work["_solar_filter_intersection_share_pct"] = pd.concat(filter_share_sources, axis=1).max(axis=1)
        else:
            work["_solar_filter_intersection_share_pct"] = 0.0
        if "small_area_m2" in work.columns:
            work["_solar_small_area_km2"] = pd.to_numeric(work["small_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0) / 1_000_000.0
        else:
            work["_solar_small_area_km2"] = 0.0

    if int(target_resolution) < int(source_resolution):
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
        agg_spec: dict[str, Any] = {"potential_area_km2": ("potential_area_km2", "sum")}
        if technology == "wind":
            agg_spec["wind_hard_exclusion_intersects"] = ("wind_hard_exclusion_intersects", "max")
        if technology == "solar":
            agg_spec["_solar_filter_intersection_share_pct"] = ("_solar_filter_intersection_share_pct", "max")
            agg_spec["_solar_small_area_km2"] = ("_solar_small_area_km2", "sum")
        work = (
            work.groupby("hex_id", as_index=False)
            .agg(**agg_spec)
            .sort_values("hex_id")
            .reset_index(drop=True)
        )
        work["potential_area_km2"] = work["potential_area_km2"].clip(lower=0.0, upper=target_hex_area)
        work["potential_score"] = (work["potential_area_km2"] / max(target_hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    else:
        work["potential_area_km2"] = work["potential_area_km2"].clip(lower=0.0, upper=target_hex_area)
        work["potential_score"] = (work["potential_area_km2"] / max(target_hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)

    out = work[["hex_id", "potential_score", "potential_area_km2"]].copy()
    suitable = out["potential_area_km2"].gt(1e-9)
    if technology == "wind":
        wind_hard_blocked = pd.Series(False, index=work.index)
        if "wind_hard_exclusion_intersects" in work.columns:
            wind_hard_blocked = work["wind_hard_exclusion_intersects"].fillna(False).astype(bool)
        suitable = suitable & ~wind_hard_blocked
    if technology == "solar" and bool(coarse_filter_intersection_blocks):
        filter_share = pd.to_numeric(work.get("_solar_filter_intersection_share_pct"), errors="coerce").fillna(0.0)
        small_area = pd.to_numeric(work.get("_solar_small_area_km2"), errors="coerce").fillna(0.0)
        # Trondelag uses R7 as app level. Any selected land-exclusion overlap must be visible at
        # cell level so the coarse map mirrors Bornholm's finer-grid establishment behavior.
        suitable = suitable & ~(filter_share.gt(0.0) & small_area.le(1e-9))
    out[f"{technology}_suitable"] = suitable
    out[f"{technology}_potential_score"] = out["potential_score"].round(1)
    out[f"{technology}_potential_area_km2"] = out["potential_area_km2"].clip(lower=0.0)
    return out.reindex(columns=columns)


def _combined_establishment_class(wind_suitable: bool, solar_suitable: bool) -> str:
    if wind_suitable and solar_suitable:
        return "wind_and_solar"
    if wind_suitable:
        return "wind_only"
    if solar_suitable:
        return "solar_only"
    return "not_suitable"


def _dominant_establishment_class_from_areas(row: Any) -> str:
    class_order = ["wind_and_solar", "wind_only", "solar_only", "not_suitable"]
    best_class = "not_suitable"
    best_area = -1.0
    for class_id in class_order:
        area = float(getattr(row, f"rollup_area_{class_id}", 0.0) or 0.0)
        if area > best_area:
            best_class = class_id
            best_area = area
    return best_class if best_area > 0.0 else "not_suitable"


def _apply_establishment_style_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame["establishment_label"] = frame["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["label"]
    )
    frame["fill"] = frame["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["color"]
    )
    frame["stroke"] = frame["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["stroke"]
    )
    frame["stroke_weight"] = 0.12
    frame["fill_opacity"] = 0.58
    return frame


def _combined_establishment_frame(
    region: dict[str, Any],
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    display_geometries = load_h3_display_geometries(display_geometry_path)
    base = pd.DataFrame({"hex_id": sorted(str(hex_id) for hex_id in display_geometries)})
    if base.empty:
        return base

    wind = _establishment_source_frame(wind_selected, "wind", int(target_resolution), int(source_resolution))
    solar = _establishment_source_frame(solar_selected, "solar", int(target_resolution), int(source_resolution))
    if not wind.empty:
        base = base.merge(wind, on="hex_id", how="left")
    if not solar.empty:
        base = base.merge(solar, on="hex_id", how="left")

    for technology in ["wind", "solar"]:
        bool_col = f"{technology}_suitable"
        if bool_col not in base.columns:
            base[bool_col] = False
        base[bool_col] = base[bool_col].map(lambda value: False if pd.isna(value) else bool(value))
        for column in [
            f"{technology}_rank",
            f"{technology}_potential_score",
            f"{technology}_potential_area_km2",
            f"{technology}_allocated_area_km2",
            f"{technology}_allocated_gwh",
            f"{technology}_allocated_hex_share_pct",
            f"{technology}_conflict_area_km2",
            f"{technology}_expansion_ring",
        ]:
            if column not in base.columns:
                base[column] = 0.0
            base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)
        outside_col = f"{technology}_outside_lp"
        if outside_col not in base.columns:
            base[outside_col] = False
        base[outside_col] = base[outside_col].map(lambda value: False if pd.isna(value) else bool(value))
        overlap_col = f"{technology}_last_resort_overlap"
        if overlap_col not in base.columns:
            base[overlap_col] = False
        base[overlap_col] = base[overlap_col].map(lambda value: False if pd.isna(value) else bool(value))
        conflict_col = f"{technology}_conflict"
        if conflict_col not in base.columns:
            base[conflict_col] = False
        base[conflict_col] = base[conflict_col].map(lambda value: False if pd.isna(value) else bool(value))
        phase_col = f"{technology}_phase"
        if phase_col not in base.columns:
            base[phase_col] = ""
        base[phase_col] = base[phase_col].fillna("").astype(str)

    base["establishment_class"] = [
        _combined_establishment_class(bool(wind), bool(solar))
        for wind, solar in zip(base["wind_suitable"], base["solar_suitable"])
    ]
    base["wind_outside_lp_area_km2"] = pd.to_numeric(base.get("wind_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    base["solar_outside_lp_area_km2"] = pd.to_numeric(base.get("solar_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    base["outside_lp_shortage"] = base["wind_outside_lp_area_km2"].gt(0.0) | base["solar_outside_lp_area_km2"].gt(0.0)
    base["outside_lp_reason"] = [
        "vind + sol" if wind_area > 0 and solar_area > 0 else "vind" if wind_area > 0 else "sol" if solar_area > 0 else ""
        for wind_area, solar_area in zip(base["wind_outside_lp_area_km2"], base["solar_outside_lp_area_km2"])
    ]
    base["establishment_label"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["label"]
    )
    base["fill"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["color"]
    )
    base["stroke"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["stroke"]
    )
    base["stroke_weight"] = 0.12
    base["fill_opacity"] = 0.58
    return base


def _trondelag_rollup_potential_establishment_frame(
    region: dict[str, Any],
    source_frame: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    display_geometries = load_h3_display_geometries(display_geometry_path)
    base = pd.DataFrame({"hex_id": sorted(str(hex_id) for hex_id in display_geometries)})
    if base.empty:
        return base
    if source_frame.empty or "hex_id" not in source_frame.columns:
        base["establishment_class"] = "not_suitable"
        for technology in ["wind", "solar"]:
            base[f"{technology}_suitable"] = False
            base[f"{technology}_potential_score"] = 0.0
            base[f"{technology}_potential_area_km2"] = 0.0
        base["wind_outside_lp_area_km2"] = 0.0
        base["solar_outside_lp_area_km2"] = 0.0
        base["outside_lp_shortage"] = False
        base["outside_lp_reason"] = ""
        return _apply_establishment_style_columns(base)

    work = source_frame.copy()
    work["hex_id"] = work["hex_id"].astype(str).map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
    child_hex_area_km2 = float(h3_hex_area_km2(int(source_resolution)))
    target_hex_area_km2 = float(h3_hex_area_km2(int(target_resolution)))
    for class_id in ["wind_and_solar", "wind_only", "solar_only", "not_suitable"]:
        work[f"rollup_area_{class_id}"] = work.get("establishment_class", "").astype(str).eq(class_id).astype(float) * child_hex_area_km2

    agg_spec: dict[str, Any] = {
        "rollup_area_wind_and_solar": ("rollup_area_wind_and_solar", "sum"),
        "rollup_area_wind_only": ("rollup_area_wind_only", "sum"),
        "rollup_area_solar_only": ("rollup_area_solar_only", "sum"),
        "rollup_area_not_suitable": ("rollup_area_not_suitable", "sum"),
    }
    for technology in ["wind", "solar"]:
        for column, method in [
            (f"{technology}_potential_area_km2", "sum"),
            (f"{technology}_allocated_area_km2", "sum"),
            (f"{technology}_allocated_gwh", "sum"),
            (f"{technology}_allocated_hex_share_pct", "sum"),
            (f"{technology}_conflict_area_km2", "sum"),
            (f"{technology}_rank", "max"),
            (f"{technology}_expansion_ring", "max"),
        ]:
            if column in work.columns:
                work[column] = pd.to_numeric(work[column], errors="coerce").fillna(0.0)
                agg_spec[column] = (column, method)
        for column in [f"{technology}_outside_lp", f"{technology}_conflict"]:
            if column in work.columns:
                work[column] = work[column].map(lambda value: False if pd.isna(value) else bool(value)).astype(int)
                agg_spec[column] = (column, "max")
        overlap_col = f"{technology}_last_resort_overlap"
        if overlap_col in work.columns:
            work[overlap_col] = work[overlap_col].map(lambda value: False if pd.isna(value) else bool(value)).astype(int)
            agg_spec[overlap_col] = (overlap_col, "max")

    rolled = (
        work.groupby("hex_id", as_index=False)
        .agg(**agg_spec)
        .sort_values("hex_id")
        .reset_index(drop=True)
    )
    base = base.merge(rolled, on="hex_id", how="left")
    for column in base.columns:
        if column.startswith("rollup_area_"):
            base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)
    base["establishment_class"] = [
        _dominant_establishment_class_from_areas(row)
        for row in base.itertuples(index=False)
    ]
    base["wind_suitable"] = base["establishment_class"].isin(["wind_and_solar", "wind_only"])
    base["solar_suitable"] = base["establishment_class"].isin(["wind_and_solar", "solar_only"])

    for technology in ["wind", "solar"]:
        area_col = f"{technology}_potential_area_km2"
        if area_col not in base.columns:
            base[area_col] = 0.0
        base[area_col] = pd.to_numeric(base[area_col], errors="coerce").fillna(0.0).clip(lower=0.0, upper=target_hex_area_km2)
        base[f"{technology}_potential_score"] = (base[area_col] / max(target_hex_area_km2, 1e-9) * 100.0).clip(lower=0.0, upper=100.0).round(1)
        for column in [
            f"{technology}_rank",
            f"{technology}_allocated_area_km2",
            f"{technology}_allocated_gwh",
            f"{technology}_allocated_hex_share_pct",
            f"{technology}_conflict_area_km2",
            f"{technology}_expansion_ring",
        ]:
            if column not in base.columns:
                base[column] = 0.0
            base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)
        for column in [f"{technology}_outside_lp", f"{technology}_conflict"]:
            if column not in base.columns:
                base[column] = False
            base[column] = base[column].map(lambda value: False if pd.isna(value) else bool(value))
        overlap_col = f"{technology}_last_resort_overlap"
        if overlap_col not in base.columns:
            base[overlap_col] = False
        base[overlap_col] = base[overlap_col].map(lambda value: False if pd.isna(value) else bool(value))
        phase_col = f"{technology}_phase"
        if phase_col not in base.columns:
            base[phase_col] = ""

    base["wind_outside_lp_area_km2"] = pd.to_numeric(base.get("wind_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    base["solar_outside_lp_area_km2"] = pd.to_numeric(base.get("solar_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    base["outside_lp_shortage"] = base["wind_outside_lp_area_km2"].gt(0.0) | base["solar_outside_lp_area_km2"].gt(0.0)
    base["outside_lp_reason"] = [
        "vind + sol" if wind_area > 0 and solar_area > 0 else "vind" if wind_area > 0 else "sol" if solar_area > 0 else ""
        for wind_area, solar_area in zip(base["wind_outside_lp_area_km2"], base["solar_outside_lp_area_km2"])
    ]
    return _apply_establishment_style_columns(base)


def _combined_potential_establishment_frame(
    region: dict[str, Any],
    wind_potential: pd.DataFrame,
    solar_potential: pd.DataFrame,
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    display_geometries = load_h3_display_geometries(display_geometry_path)
    base = pd.DataFrame({"hex_id": sorted(str(hex_id) for hex_id in display_geometries)})
    if base.empty:
        return base
    if (
        str(region.get("region_id", "") or "").lower() == "trondelag"
        and int(target_resolution) < int(source_resolution)
    ):
        source_frame = _combined_potential_establishment_frame(
            region,
            wind_potential,
            solar_potential,
            wind_selected,
            solar_selected,
            int(source_resolution),
            int(source_resolution),
        )
        return _trondelag_rollup_potential_establishment_frame(
            region,
            source_frame,
            int(target_resolution),
            int(source_resolution),
        )

    wind = _potential_establishment_source_frame(wind_potential, "wind", int(target_resolution), int(source_resolution))
    solar_filter_intersection_blocks = (
        str(region.get("region_id", "") or "").lower() == "trondelag"
        and int(target_resolution) <= 7
    )
    solar = _potential_establishment_source_frame(
        solar_potential,
        "solar",
        int(target_resolution),
        int(source_resolution),
        coarse_filter_intersection_blocks=solar_filter_intersection_blocks,
    )
    if not wind.empty:
        base = base.merge(wind, on="hex_id", how="left")
    if not solar.empty:
        base = base.merge(solar, on="hex_id", how="left")

    allocation = _combined_establishment_frame(region, wind_selected, solar_selected, int(target_resolution), int(source_resolution))
    allocation_columns: list[str] = []
    for technology in ["wind", "solar"]:
        allocation_columns.extend(
            [
                f"{technology}_rank",
                f"{technology}_allocated_area_km2",
                f"{technology}_allocated_gwh",
                f"{technology}_allocated_hex_share_pct",
                f"{technology}_outside_lp",
                f"{technology}_conflict_area_km2",
                f"{technology}_conflict",
                f"{technology}_expansion_ring",
                f"{technology}_phase",
                f"{technology}_last_resort_overlap",
            ]
        )
    allocation_columns.extend(["outside_lp_shortage", "outside_lp_reason"])
    if not allocation.empty:
        available_columns = ["hex_id"] + [column for column in allocation_columns if column in allocation.columns]
        base = base.merge(
            allocation[available_columns].rename(columns={column: f"{column}__allocation" for column in available_columns if column != "hex_id"}),
            on="hex_id",
            how="left",
        )

    for technology in ["wind", "solar"]:
        bool_col = f"{technology}_suitable"
        if bool_col not in base.columns:
            base[bool_col] = False
        base[bool_col] = base[bool_col].map(lambda value: False if pd.isna(value) else bool(value))
        for column in [f"{technology}_potential_score", f"{technology}_potential_area_km2"]:
            if column not in base.columns:
                base[column] = 0.0
            base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0).clip(lower=0.0)
        for column in [
            f"{technology}_rank",
            f"{technology}_allocated_area_km2",
            f"{technology}_allocated_gwh",
            f"{technology}_allocated_hex_share_pct",
            f"{technology}_conflict_area_km2",
            f"{technology}_expansion_ring",
        ]:
            allocation_col = f"{column}__allocation"
            if allocation_col in base.columns:
                base[column] = pd.to_numeric(base[allocation_col], errors="coerce").fillna(0.0)
            elif column not in base.columns:
                base[column] = 0.0
            base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)
        for column in [f"{technology}_outside_lp", f"{technology}_conflict"]:
            allocation_col = f"{column}__allocation"
            if allocation_col in base.columns:
                base[column] = base[allocation_col].map(lambda value: False if pd.isna(value) else bool(value))
            elif column not in base.columns:
                base[column] = False
            base[column] = base[column].map(lambda value: False if pd.isna(value) else bool(value))
        overlap_col = f"{technology}_last_resort_overlap"
        allocation_overlap_col = f"{overlap_col}__allocation"
        if allocation_overlap_col in base.columns:
            base[overlap_col] = base[allocation_overlap_col].map(lambda value: False if pd.isna(value) else bool(value))
        elif overlap_col not in base.columns:
            base[overlap_col] = False
        base[overlap_col] = base[overlap_col].map(lambda value: False if pd.isna(value) else bool(value))
        phase_col = f"{technology}_phase"
        allocation_phase_col = f"{phase_col}__allocation"
        if allocation_phase_col in base.columns:
            base[phase_col] = base[allocation_phase_col].fillna("").astype(str)
        elif phase_col not in base.columns:
            base[phase_col] = ""
        else:
            base[phase_col] = base[phase_col].fillna("").astype(str)

    base["establishment_class"] = [
        _combined_establishment_class(bool(wind), bool(solar))
        for wind, solar in zip(base["wind_suitable"], base["solar_suitable"])
    ]
    base["wind_outside_lp_area_km2"] = pd.to_numeric(base.get("wind_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    base["solar_outside_lp_area_km2"] = pd.to_numeric(base.get("solar_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    shortage_col = "outside_lp_shortage__allocation"
    if shortage_col in base.columns:
        base["outside_lp_shortage"] = base[shortage_col].map(lambda value: False if pd.isna(value) else bool(value))
    else:
        base["outside_lp_shortage"] = base["wind_outside_lp_area_km2"].gt(0.0) | base["solar_outside_lp_area_km2"].gt(0.0)
    reason_col = "outside_lp_reason__allocation"
    if reason_col in base.columns:
        base["outside_lp_reason"] = base[reason_col].fillna("").astype(str)
    else:
        base["outside_lp_reason"] = [
            "vind + sol" if wind_area > 0 and solar_area > 0 else "vind" if wind_area > 0 else "sol" if solar_area > 0 else ""
            for wind_area, solar_area in zip(base["wind_outside_lp_area_km2"], base["solar_outside_lp_area_km2"])
        ]
    base["establishment_label"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["label"]
    )
    base["fill"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["color"]
    )
    base["stroke"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["stroke"]
    )
    base["stroke_weight"] = 0.12
    base["fill_opacity"] = 0.58
    return base


def _h3_polygon_geometry(hex_id: str) -> dict[str, Any] | None:
    try:
        boundary = h3.cell_to_boundary(str(hex_id))
    except Exception:
        return None
    ring = [[float(lng), float(lat)] for lat, lng in boundary]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    if not ring:
        return None
    return {"type": "Polygon", "coordinates": [ring]}


def _geometry_bbox_from_geometries(geometries: dict[str, Any]) -> tuple[float, float, float, float] | None:
    coords: list[tuple[float, float]] = []

    def _collect(value: Any) -> None:
        if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            coords.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                _collect(item)

    for geometry in geometries.values():
        if isinstance(geometry, dict):
            _collect(geometry.get("coordinates"))
    if not coords:
        return None
    lngs = [lng for lng, _ in coords]
    lats = [lat for _, lat in coords]
    return min(lngs), min(lats), max(lngs), max(lats)


def _region_bounds_tuple(region: dict[str, Any], fallback_bbox: tuple[float, float, float, float] | None) -> tuple[float, float, float, float] | None:
    raw = region.get("default_map_bounds")
    if isinstance(raw, list) and len(raw) == 2:
        try:
            south = float(raw[0][0])
            west = float(raw[0][1])
            north = float(raw[1][0])
            east = float(raw[1][1])
            if south < north and west < east:
                return west, south, east, north
        except Exception:
            pass
    if fallback_bbox is None:
        return None
    west, south, east, north = fallback_bbox
    lon_pad = max(0.05, (east - west) * 0.45)
    lat_pad = max(0.04, (north - south) * 0.25)
    return west - lon_pad, south - lat_pad, east + lon_pad, north + lat_pad


def _h3_cells_in_bounds(bounds: tuple[float, float, float, float], resolution: int) -> set[str]:
    west, south, east, north = bounds
    if west >= east or south >= north:
        return set()
    try:
        polygon = h3.LatLngPoly([(south, west), (south, east), (north, east), (north, west)])
        return {str(cell) for cell in h3.polygon_to_cells(polygon, int(resolution))}
    except Exception:
        return set()


def _cell_sort_key(cell: str, anchor: str, fallback_lat: float, fallback_lng: float) -> tuple[float, str]:
    try:
        return float(h3.grid_distance(anchor, str(cell))), str(cell)
    except Exception:
        try:
            lat, lng = h3.cell_to_latlng(str(cell))
            distance = (float(lat) - fallback_lat) ** 2 + (float(lng) - fallback_lng) ** 2
            return distance, str(cell)
        except Exception:
            return 999999.0, str(cell)


def _nearest_candidate_cell(candidates: set[str], anchor_lat: float, anchor_lng: float) -> str | None:
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda cell: _cell_sort_key(cell, "", float(anchor_lat), float(anchor_lng)))
    return ordered[0] if ordered else None


def _radial_schematic_zone_cells(
    candidates: set[str],
    anchor_lat: float,
    anchor_lng: float,
    count: int,
) -> list[str]:
    if count <= 0 or not candidates:
        return []
    resolution = int(h3.get_resolution(next(iter(candidates))))
    try:
        anchor = str(h3.latlng_to_cell(float(anchor_lat), float(anchor_lng), resolution))
    except Exception:
        anchor = ""
    if anchor not in candidates:
        anchor = _nearest_candidate_cell(candidates, float(anchor_lat), float(anchor_lng)) or anchor
    if not anchor:
        ordered = sorted(candidates, key=lambda cell: _cell_sort_key(cell, "", float(anchor_lat), float(anchor_lng)))
        return ordered[: int(count)]

    selected: list[str] = []
    seen: set[str] = set()
    max_ring = max(8, int(math.ceil(math.sqrt(max(1, int(count))) * 2.6)))
    ring = 0
    while len(selected) < int(count) and ring <= max_ring:
        try:
            disk = {str(cell) for cell in h3.grid_disk(anchor, ring)}
        except Exception:
            break
        ring_cells = sorted(
            (disk - seen) & candidates,
            key=lambda cell: _cell_sort_key(cell, anchor, float(anchor_lat), float(anchor_lng)),
        )
        selected.extend(ring_cells)
        seen = disk
        ring += 1

    if len(selected) < int(count):
        remaining = sorted(
            candidates - set(selected),
            key=lambda cell: _cell_sort_key(cell, anchor, float(anchor_lat), float(anchor_lng)),
        )
        selected.extend(remaining)
    return selected[: int(count)]


def _radial_schematic_disk_cells(
    anchor_lat: float,
    anchor_lng: float,
    count: int,
    target_resolution: int,
    excluded_cells: set[str] | None = None,
) -> list[str]:
    if count <= 0:
        return []
    excluded = set(str(cell) for cell in (excluded_cells or set()))
    try:
        anchor = str(h3.latlng_to_cell(float(anchor_lat), float(anchor_lng), int(target_resolution)))
    except Exception:
        return []

    selected: list[str] = []
    seen: set[str] = set()
    max_ring = max(10, int(math.ceil(math.sqrt(max(1, int(count)) / 3.0))) + 18)
    ring = 0
    while len(selected) < int(count) and ring <= max_ring:
        try:
            disk = {str(cell) for cell in h3.grid_disk(anchor, ring)}
        except Exception:
            break
        ring_cells = sorted(
            (disk - seen) - excluded,
            key=lambda cell: _cell_sort_key(cell, anchor, float(anchor_lat), float(anchor_lng)),
        )
        selected.extend(ring_cells)
        seen = disk
        ring += 1
    return selected[: int(count)]


def _compacted_schematic_features(
    cells: list[str],
    technology: str,
    target_resolution: int,
    base_hex_area_km2: float,
    total_area_km2: float,
    anchor_lat: float | None = None,
    anchor_lng: float | None = None,
) -> list[dict[str, Any]]:
    if not cells:
        return []
    display_cells = [str(cell) for cell in cells]
    if anchor_lat is not None and anchor_lng is not None:
        display_cells = sorted(
            display_cells,
            key=lambda cell: _cell_sort_key(cell, "", float(anchor_lat), float(anchor_lng)),
        )
    else:
        display_cells = sorted(display_cells)
    label = "Vind" if technology == "wind" else "Sol"
    fill = "#2563eb" if technology == "wind" else "#facc15"
    stroke = "#dbeafe"
    stroke_weight = 0.26 if technology == "wind" else 0.18
    fill_opacity = 0.76 if technology == "wind" else 0.82
    remaining_area = max(0.0, float(total_area_km2 or 0.0))
    features: list[dict[str, Any]] = []
    for cell in display_cells:
        try:
            cell_resolution = int(h3.get_resolution(cell))
        except Exception:
            cell_resolution = int(target_resolution)
        try:
            base_cell_count = int(h3.cell_to_children_size(cell, int(target_resolution))) if cell_resolution < int(target_resolution) else 1
        except Exception:
            base_cell_count = 1
        represented_area = min(remaining_area, max(0.0, float(base_cell_count) * float(base_hex_area_km2 or 0.0)))
        remaining_area = max(0.0, remaining_area - represented_area)
        geometry = _h3_polygon_geometry(cell)
        if geometry is None:
            continue
        popup = (
            f"<strong>{OUTSIDE_LP_NEED_LAYER_LABEL}</strong><br>"
            f"Teknik: {label}<br>"
            f"Schematisk yta: {represented_area:.3f} km²<br>"
            f"Bas: R{int(target_resolution)} ≈ {base_cell_count} hex<br>"
            f"Visningshex: R{cell_resolution} {cell}<br>"
            "Ej verklig placering - visar mängd utanför landskapets potential."
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": cell,
                    "schematic_technology": technology,
                    "schematic_label": label,
                    "represented_area_km2": represented_area,
                    "represented_base_hex_count": base_cell_count,
                    "display_resolution": cell_resolution,
                    "fill": fill,
                    "stroke": stroke,
                    "stroke_weight": stroke_weight,
                    "fill_opacity": fill_opacity,
                    "tooltip_title": f"Schematisk yta utanför potential: {label}",
                    "tooltip_body": f"{represented_area:.2f} km² · ej verklig placering",
                    "popup": popup,
                },
            }
        )
    return features


def _outside_lp_need_feature_collection(
    region: dict[str, Any],
    frame: pd.DataFrame,
    target_resolution: int,
    wind_area_override_km2: float | None = None,
    solar_area_override_km2: float | None = None,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    if frame.empty or "outside_lp_shortage" not in frame.columns:
        if wind_area_override_km2 is None and solar_area_override_km2 is None:
            return {"type": "FeatureCollection", "features": features}
        selected = pd.DataFrame()
    else:
        selected = frame[frame["outside_lp_shortage"].fillna(False).astype(bool)].copy()
    if wind_area_override_km2 is None:
        wind_area = float(pd.to_numeric(selected.get("wind_outside_lp_area_km2", pd.Series(dtype=float)), errors="coerce").fillna(0.0).clip(lower=0.0).sum())
    else:
        wind_area = max(0.0, float(wind_area_override_km2 or 0.0))
    if solar_area_override_km2 is None:
        solar_area = float(pd.to_numeric(selected.get("solar_outside_lp_area_km2", pd.Series(dtype=float)), errors="coerce").fillna(0.0).clip(lower=0.0).sum())
    else:
        solar_area = max(0.0, float(solar_area_override_km2 or 0.0))
    if wind_area < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2:
        wind_area = 0.0
    if solar_area < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2:
        solar_area = 0.0
    if wind_area <= 0 and solar_area <= 0:
        return {"type": "FeatureCollection", "features": features}

    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else {}
    land_cells = set(str(cell) for cell in display_geometries)
    land_bbox = _geometry_bbox_from_geometries(display_geometries)
    map_bounds = _region_bounds_tuple(region, land_bbox)
    if map_bounds is None or land_bbox is None:
        return {"type": "FeatureCollection", "features": features}

    land_west, land_south, land_east, land_north = land_bbox
    map_west, map_south, map_east, map_north = map_bounds
    gap_lon = max(0.012, (land_east - land_west) * 0.035)
    center_lat = (land_south + land_north) / 2.0
    land_width = max(0.001, land_east - land_west)
    west_space = max(0.001, land_west - map_west)
    east_space = max(0.001, map_east - land_east)
    desired_offset = max(gap_lon * 6.0, land_width * 0.42)
    wind_anchor_lng = land_west - min(desired_offset, max(west_space * 0.86, desired_offset))
    solar_anchor_lng = land_east + min(desired_offset, max(east_space * 0.86, desired_offset))
    wind_count = int(math.ceil(wind_area / max(float(h3_hex_area_km2(int(target_resolution))), 1e-9))) if wind_area > 0 else 0
    solar_count = int(math.ceil(solar_area / max(float(h3_hex_area_km2(int(target_resolution))), 1e-9))) if solar_area > 0 else 0
    base_hex_area = float(h3_hex_area_km2(int(target_resolution)))

    wind_cells = _radial_schematic_disk_cells(
        center_lat,
        wind_anchor_lng,
        wind_count,
        int(target_resolution),
        land_cells,
    )
    solar_cells = _radial_schematic_disk_cells(
        center_lat,
        solar_anchor_lng,
        solar_count,
        int(target_resolution),
        land_cells | set(wind_cells),
    )
    if not wind_cells and wind_count > 0:
        all_map_cells = _h3_cells_in_bounds(map_bounds, int(target_resolution))
        water_cells = all_map_cells - land_cells
        west_candidates = {
            cell
            for cell in water_cells
            if h3.cell_to_latlng(cell)[1] <= land_west - gap_lon
        }
        wind_cells = _radial_schematic_zone_cells(
            west_candidates or water_cells,
            center_lat,
            wind_anchor_lng,
            wind_count,
        )
    if not solar_cells and solar_count > 0:
        all_map_cells = _h3_cells_in_bounds(map_bounds, int(target_resolution))
        water_cells = all_map_cells - land_cells - set(wind_cells)
        east_candidates = {
            cell
            for cell in water_cells
            if h3.cell_to_latlng(cell)[1] >= land_east + gap_lon
        }
        solar_cells = _radial_schematic_zone_cells(
            east_candidates or water_cells,
            center_lat,
            solar_anchor_lng,
            solar_count,
        )

    features.extend(
        _compacted_schematic_features(
            wind_cells,
            "wind",
            int(target_resolution),
            base_hex_area,
            wind_area,
            center_lat,
            wind_anchor_lng,
        )
    )
    features.extend(
        _compacted_schematic_features(
            solar_cells,
            "solar",
            int(target_resolution),
            base_hex_area,
            solar_area,
            center_lat,
            solar_anchor_lng,
        )
    )
    return {"type": "FeatureCollection", "features": features}


def _outside_lp_need_layer(
    region: dict[str, Any],
    frame: pd.DataFrame,
    target_resolution: int,
    wind_area_km2: float | None = None,
    solar_area_km2: float | None = None,
) -> dict[str, Any] | None:
    if frame.empty and wind_area_km2 is None and solar_area_km2 is None:
        return None
    feature_collection = _outside_lp_need_feature_collection(region, frame, int(target_resolution), wind_area_km2, solar_area_km2)
    if not feature_collection.get("features"):
        return None
    return {
        "name": OUTSIDE_LP_NEED_LAYER_LABEL,
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "stroke_weight_property": "stroke_weight",
        "legend_items": [
            {"label": "Schematisk vindyta utanför potential", "color": "#2563eb"},
            {"label": "Schematisk solyta utanför potential", "color": "#facc15"},
        ],
        "legend_id": "outside_lp_need",
        "legend_title": OUTSIDE_LP_NEED_LAYER_LABEL,
        "default_visible": True,
        "stroke": True,
        "stroke_opacity": 0.55,
        "fill_opacity": 0.76,
        "weight": 0.28,
        "z_index": 486,
        "layer_kind": "hex",
        "opacity_family": OUTSIDE_LP_NEED_LAYER_LABEL,
        "opacity_label": OUTSIDE_LP_NEED_LAYER_LABEL,
    }


def _outside_lp_need_family_layers(
    region: dict[str, Any],
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    source_resolution: int | None = None,
    wind_area_km2: float | None = None,
    solar_area_km2: float | None = None,
) -> list[dict[str, Any]]:
    if (
        (wind_area_km2 is None or max(0.0, float(wind_area_km2 or 0.0)) < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2)
        and (solar_area_km2 is None or max(0.0, float(solar_area_km2 or 0.0)) < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2)
    ):
        wind_area_km2 = 0.0 if wind_area_km2 is not None else None
        solar_area_km2 = 0.0 if solar_area_km2 is not None else None
    if wind_selected.empty and solar_selected.empty and wind_area_km2 is None and solar_area_km2 is None:
        return []
    source_resolution = int(source_resolution or selected_resolution)
    source_frame = _combined_establishment_frame(
        region,
        wind_selected,
        solar_selected,
        int(source_resolution),
        int(source_resolution),
    )
    if source_frame.empty and wind_area_km2 is None and solar_area_km2 is None:
        return []
    return _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "outside_lp_need",
        OUTSIDE_LP_NEED_LAYER_LABEL,
        lambda resolution: _outside_lp_need_layer(
            region,
            source_frame,
            int(resolution),
            wind_area_km2,
            solar_area_km2,
        ),
    )


SCENARIO_ALLOCATION_SPECS: dict[str, dict[str, str]] = {
    "wind": {
        "label": "Scenarioyta: vind",
        "fill": "#1d4ed8",
        "stroke": "#0f172a",
        "legend_color": "#1d4ed8",
    },
    "solar": {
        "label": "Scenarioyta: sol",
        "fill": "#f59e0b",
        "stroke": "#92400e",
        "legend_color": "#f59e0b",
    },
    "both": {
        "label": "Scenarioyta: vind och sol",
        "fill": "#166534",
        "stroke": "#052e16",
        "legend_color": "#166534",
    },
}


def _scenario_allocation_class(
    wind_suitable: bool,
    solar_suitable: bool,
    wind_area_km2: float = 0.0,
    solar_area_km2: float = 0.0,
    both_required: bool = False,
) -> str:
    if wind_suitable and solar_suitable:
        if both_required:
            return "both"
        return "wind" if float(wind_area_km2 or 0.0) >= float(solar_area_km2 or 0.0) else "solar"
    if wind_suitable:
        return "wind"
    if solar_suitable:
        return "solar"
    return ""


def _scenario_allocation_child_cell(hex_id: str, target_resolution: int) -> str:
    child_resolution = min(15, int(target_resolution) + 1)
    if child_resolution <= int(target_resolution):
        return str(hex_id)
    try:
        return str(h3.cell_to_center_child(str(hex_id), child_resolution))
    except Exception:
        try:
            children = sorted(str(cell) for cell in h3.cell_to_children(str(hex_id), child_resolution))
            if children:
                return children[len(children) // 2]
        except Exception:
            pass
    return str(hex_id)


def _scenario_allocation_marker_feature_collection(
    frame: pd.DataFrame,
    target_resolution: int,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    if frame.empty:
        return {"type": "FeatureCollection", "features": features}

    def _priority_html(row: Any, technology: str, label: str) -> str:
        allocated_area = float(getattr(row, f"{technology}_allocated_area_km2", 0.0) or 0.0)
        if allocated_area <= 0.0:
            return ""
        landscape_score = float(getattr(row, f"{technology}_landscape_priority_score", 0.0) or 0.0)
        allocation_score = float(getattr(row, f"{technology}_allocation_priority_score", 0.0) or 0.0)
        social_pct = float(getattr(row, f"{technology}_social_acceptance_allocation_priority_pct", 0.0) or 0.0)
        social_score = float(getattr(row, f"{technology}_social_acceptance_priority_score", 0.0) or 0.0)
        reason = html.escape(str(getattr(row, f"{technology}_allocation_priority_reason", "") or ""))
        lines = [
            f"<strong>{label}: varför här?</strong>",
            f"Landskaps-/teknikranking: {landscape_score * 100.0:.0f}%",
        ]
        if social_pct > 0.0:
            lines.append(f"Slutlig ranking efter social acceptans ({social_pct:.0f}%): {social_score * 100.0:.0f}%")
        else:
            lines.append(f"Slutlig ranking: {allocation_score * 100.0:.0f}%")
        if reason:
            lines.append(f"Förklaring: {reason}")
        return "<br>".join(lines) + "<br>"

    for row in frame.itertuples(index=False):
        wind_area = float(getattr(row, "wind_allocated_area_km2", 0.0) or 0.0)
        solar_area = float(getattr(row, "solar_allocated_area_km2", 0.0) or 0.0)
        wind_suitable = bool(getattr(row, "wind_suitable", False)) and wind_area > 0.0
        solar_suitable = bool(getattr(row, "solar_suitable", False)) and solar_area > 0.0
        both_required = bool(getattr(row, "wind_last_resort_overlap", False)) or bool(
            getattr(row, "solar_last_resort_overlap", False)
        )
        class_id = _scenario_allocation_class(wind_suitable, solar_suitable, wind_area, solar_area, both_required)
        if not class_id:
            continue
        spec = SCENARIO_ALLOCATION_SPECS[class_id]
        parent_hex = str(getattr(row, "hex_id", "") or "")
        child_hex = _scenario_allocation_child_cell(parent_hex, int(target_resolution))
        geometry = _h3_polygon_geometry(child_hex)
        if geometry is None:
            continue
        if class_id == "both":
            note = (
                "Markören visar scenarioyta i en större hex där båda teknikerna används. "
                "Grön används när både vind och sol faktiskt hamnar i samma scenariohex."
            )
        elif wind_suitable and solar_suitable:
            note = (
                "Parent-hexen innehåller båda teknikerna i underliggande celler. Färgen visar den dominerande tekniken, "
                "eftersom kombination inte behövs som sista utväg här."
            )
        else:
            note = "Markören visar scenariots placering från den mest lämpade ytan först enligt aktiva filter och prioriteringar."
        popup = (
            f"<strong>{SCENARIO_ALLOCATION_LAYER_LABEL}</strong><br>"
            f"{spec['label']}<br>"
            f"Parent-hex: R{int(target_resolution)} {parent_hex}<br>"
            f"Child-hex: {child_hex}<br>"
            f"Vind fördelad yta: {wind_area:.3f} km²<br>"
            f"Sol fördelad yta: {solar_area:.3f} km²<br>"
            f"{_priority_html(row, 'wind', 'Vind')}"
            f"{_priority_html(row, 'solar', 'Sol')}"
            f"{note}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": child_hex,
                    "parent_hex_id": parent_hex,
                    "allocation_class": class_id,
                    "allocation_label": spec["label"],
                    "wind_allocated_area_km2": wind_area,
                    "solar_allocated_area_km2": solar_area,
                    "fill": spec["fill"],
                    "stroke": spec["stroke"],
                    "stroke_weight": 0.0,
                    "fill_opacity": 0.88,
                    "tooltip_title": spec["label"],
                    "tooltip_body": f"Vind {wind_area:.2f} km² · sol {solar_area:.2f} km²",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _scenario_allocation_marker_layer(
    frame: pd.DataFrame,
    target_resolution: int,
    default_visible: bool | None = None,
) -> dict[str, Any] | None:
    if frame.empty:
        return None
    feature_collection = _scenario_allocation_marker_feature_collection(frame, int(target_resolution))
    feature_count = len(feature_collection.get("features", []))
    if feature_count <= 0:
        return None
    return {
        "name": SCENARIO_ALLOCATION_LAYER_LABEL,
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "stroke_weight_property": "stroke_weight",
        "legend_items": [
            {"label": str(spec["label"]), "color": str(spec["legend_color"])}
            for spec in SCENARIO_ALLOCATION_SPECS.values()
        ],
        "legend_id": "scenario_allocation",
        "legend_title": SCENARIO_ALLOCATION_LAYER_LABEL,
        "default_visible": bool(default_visible) if default_visible is not None else int(target_resolution) <= 9 and feature_count <= 12000,
        "stroke": False,
        "stroke_opacity": 0.0,
        "fill_opacity": 0.88,
        "weight": 0.0,
        "z_index": 540,
        "layer_kind": "hex",
        "opacity_family": SCENARIO_ALLOCATION_LAYER_LABEL,
        "opacity_label": SCENARIO_ALLOCATION_LAYER_LABEL,
    }


def _scenario_allocation_marker_family_layers(
    region: dict[str, Any],
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    source_resolution: int | None = None,
) -> list[dict[str, Any]]:
    if wind_selected.empty and solar_selected.empty:
        return []
    source_resolution = int(source_resolution or selected_resolution)
    default_visible = False if str(region.get("region_id", "")).lower() == "trondelag" else None
    return _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "scenario_allocation",
        SCENARIO_ALLOCATION_LAYER_LABEL,
        lambda resolution: _scenario_allocation_marker_layer(
            _combined_establishment_frame(
                region,
                wind_selected,
                solar_selected,
                int(resolution),
                int(source_resolution),
            ),
            int(resolution),
            default_visible=default_visible,
        ),
    )


def _combined_establishment_feature_collection(
    frame: pd.DataFrame,
    display_geometry_path: str,
    target_resolution: int,
) -> dict[str, Any]:
    display_geometries = load_h3_display_geometries(display_geometry_path)
    features: list[dict[str, Any]] = []

    def _tech_html(row: Any, technology: str, label: str, score_label: str) -> str:
        suitable = bool(getattr(row, f"{technology}_suitable", False))
        potential_score = float(getattr(row, f"{technology}_potential_score", 0.0) or 0.0)
        potential_area = float(getattr(row, f"{technology}_potential_area_km2", 0.0) or 0.0)
        allocated_area = float(getattr(row, f"{technology}_allocated_area_km2", 0.0) or 0.0)
        allocated_share = float(getattr(row, f"{technology}_allocated_hex_share_pct", 0.0) or 0.0)
        allocated_gwh = float(getattr(row, f"{technology}_allocated_gwh", 0.0) or 0.0)
        conflict_area = float(getattr(row, f"{technology}_conflict_area_km2", 0.0) or 0.0)
        rank = int(float(getattr(row, f"{technology}_rank", 0.0) or 0.0))
        lines = [
            f"<strong>{label}</strong>",
            f"Potential efter filter: {'ja' if suitable else 'nej'}",
            f"{score_label}: {potential_score:.1f}%",
            f"Potentiell yta: {potential_area:.3f} km²",
        ]
        if allocated_area > 0:
            rank_label = f" · prioritet {rank}" if rank > 0 else ""
            lines.append(f"Scenarioyta i hex: {allocated_area:.3f} km² ({allocated_share:.1f}% av hex){rank_label}")
            lines.append(f"Scenarioenergi: {allocated_gwh:.2f} GWh")
        if conflict_area > 0:
            lines.append(f"Scenarioyta utanför potential: {conflict_area:.3f} km²")
        return "<br>".join(lines) + "<br>"

    for row in frame.itertuples(index=False):
        geometry = display_geometries.get(str(row.hex_id))
        if geometry is None:
            continue
        class_id = str(getattr(row, "establishment_class", "not_suitable") or "not_suitable")
        label = str(getattr(row, "establishment_label", ESTABLISHMENT_CLASS_SPECS["not_suitable"]["label"]))
        outside_lp_shortage = bool(getattr(row, "outside_lp_shortage", False))
        outside_lp_reason = str(getattr(row, "outside_lp_reason", "") or "")
        social_acceptance_impact = float(getattr(row, "social_acceptance_impact_pct", 0.0) or 0.0)
        social_acceptance_value = float(getattr(row, "social_acceptance_value", 1.0) or 1.0)
        social_acceptance_weight = float(getattr(row, "social_acceptance_weight", 1.0) or 1.0)
        social_acceptance_source_hex_count = int(float(getattr(row, "social_acceptance_source_hex_count", 0.0) or 0.0))
        social_acceptance_popup = ""
        social_acceptance_tooltip = ""
        if social_acceptance_impact > 0.0:
            social_acceptance_popup = (
                "<br><strong>Social acceptans</strong><br>"
                f"Acceptansvärde: {social_acceptance_value:.3f}<br>"
                f"Acceptanspåverkan: {social_acceptance_impact:.0f}%<br>"
                f"Färgvikt: {social_acceptance_weight:.3f}<br>"
                f"Källhex: {social_acceptance_source_hex_count}"
            )
            social_acceptance_tooltip = f" · acceptans {social_acceptance_value:.2f}"
        popup = (
            f"<strong>{COMBINED_ESTABLISHMENT_LAYER_LABEL}</strong><br>"
            "Klassning: potential efter aktiva filter<br>"
            f"Klass: {label}<br>"
            f"Hex: {row.hex_id}<br>"
            f"{_tech_html(row, 'wind', 'Vind', 'Vindpotential')}"
            f"{_tech_html(row, 'solar', 'Sol', 'Solpotential')}"
            f"H3: R{int(target_resolution)}"
            f"{social_acceptance_popup}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": str(row.hex_id),
                    "establishment_class": class_id,
                    "establishment_label": label,
                    "outside_lp_shortage": outside_lp_shortage,
                    "outside_lp_reason": outside_lp_reason,
                    "wind_outside_lp_area_km2": float(getattr(row, "wind_outside_lp_area_km2", 0.0) or 0.0),
                    "solar_outside_lp_area_km2": float(getattr(row, "solar_outside_lp_area_km2", 0.0) or 0.0),
                    "wind_suitable": bool(getattr(row, "wind_suitable", False)),
                    "solar_suitable": bool(getattr(row, "solar_suitable", False)),
                    "fill": str(getattr(row, "fill", ESTABLISHMENT_CLASS_SPECS["not_suitable"]["color"])),
                    "stroke": str(getattr(row, "stroke", ESTABLISHMENT_CLASS_SPECS["not_suitable"]["stroke"])),
                    "stroke_weight": float(getattr(row, "stroke_weight", 0.38) or 0.38),
                    "fill_opacity": float(getattr(row, "fill_opacity", 0.58) or 0.58),
                    "social_acceptance_value": social_acceptance_value,
                    "social_acceptance_impact_pct": social_acceptance_impact,
                    "social_acceptance_weight": social_acceptance_weight,
                    "social_acceptance_source_hex_count": social_acceptance_source_hex_count,
                    "tooltip_title": label,
                    "tooltip_body": (
                        f"Vindpotential: {'ja' if bool(getattr(row, 'wind_suitable', False)) else 'nej'} · Solpotential: {'ja' if bool(getattr(row, 'solar_suitable', False)) else 'nej'}{social_acceptance_tooltip}"
                    ),
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _combined_establishment_layer(
    frame: pd.DataFrame,
    display_geometry_path: str | None,
    target_resolution: int,
) -> dict[str, Any] | None:
    if frame.empty or not display_geometry_path:
        return None
    return {
        "name": COMBINED_ESTABLISHMENT_LAYER_LABEL,
        "feature_collection": _combined_establishment_feature_collection(frame, display_geometry_path, int(target_resolution)),
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "stroke_weight_property": "stroke_weight",
        "legend_items": _combined_establishment_legend_items(),
        "legend_id": "combined_establishment",
        "legend_title": COMBINED_ESTABLISHMENT_LAYER_LABEL,
        "default_visible": True,
        "stroke": True,
        "stroke_opacity": 0.72,
        "fill_opacity": 0.58,
        "weight": 0.12,
        "z_index": 476,
        "layer_kind": "hex",
        "opacity_family": COMBINED_ESTABLISHMENT_LAYER_LABEL,
        "opacity_label": COMBINED_ESTABLISHMENT_LAYER_LABEL,
    }


def _combined_establishment_family_layers(
    region: dict[str, Any],
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    social_acceptance_manifest: dict[str, Any] | None = None,
    social_acceptance_scenario: str = SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID,
    social_acceptance_impact_pct: float = 0.0,
) -> list[dict[str, Any]]:
    if wind_selected.empty and solar_selected.empty:
        return []

    def build_layer(resolution: int) -> dict[str, Any] | None:
        frame = _combined_establishment_frame(
            region,
            wind_selected,
            solar_selected,
            int(resolution),
            int(selected_resolution),
        )
        frame = _apply_social_acceptance_impact_to_establishment_frame(
            frame,
            social_acceptance_manifest,
            social_acceptance_scenario,
            int(resolution),
            float(social_acceptance_impact_pct),
        )
        return _combined_establishment_layer(frame, _h3_display_geometry_path(region, int(resolution)), int(resolution))

    return _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "combined_establishment",
        COMBINED_ESTABLISHMENT_LAYER_LABEL,
        build_layer,
    )


def _combined_potential_establishment_family_layers(
    region: dict[str, Any],
    wind_potential: pd.DataFrame,
    solar_potential: pd.DataFrame,
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    source_resolution: int | None = None,
    social_acceptance_manifest: dict[str, Any] | None = None,
    social_acceptance_scenario: str = SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID,
    social_acceptance_impact_pct: float = 0.0,
) -> list[dict[str, Any]]:
    if wind_potential.empty and solar_potential.empty:
        return []
    source_resolution = int(source_resolution or selected_resolution)

    def build_layer(resolution: int) -> dict[str, Any] | None:
        frame = _combined_potential_establishment_frame(
            region,
            wind_potential,
            solar_potential,
            wind_selected,
            solar_selected,
            int(resolution),
            int(source_resolution),
        )
        frame = _apply_social_acceptance_impact_to_establishment_frame(
            frame,
            social_acceptance_manifest,
            social_acceptance_scenario,
            int(resolution),
            float(social_acceptance_impact_pct),
        )
        return _combined_establishment_layer(frame, _h3_display_geometry_path(region, int(resolution)), int(resolution))

    return _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "combined_establishment",
        COMBINED_ESTABLISHMENT_LAYER_LABEL,
        build_layer,
    )


def _expand_wind_area_outside_et(
    source_frame: pd.DataFrame,
    selected_frame: pd.DataFrame,
    proposal_stats: dict[str, Any],
    display_geometry_path: str | None,
    hex_area_km2: float,
    avoid_hex_ids: set[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if source_frame.empty or not display_geometry_path or hex_area_km2 <= 0:
        return selected_frame, proposal_stats

    et_shortage = float(proposal_stats.get("unmet_area_km2", 0.0) or 0.0)
    proposal_stats["et_selected_area_km2"] = float(proposal_stats.get("selected_area_km2", 0.0) or 0.0)
    proposal_stats["et_unmet_area_km2"] = max(0.0, et_shortage)
    if et_shortage <= 1e-9:
        proposal_stats.setdefault("outside_selected_area_km2", 0.0)
        proposal_stats.setdefault("outside_hex_count", 0)
        proposal_stats.setdefault("max_expansion_ring", 0)
        return selected_frame, proposal_stats

    display_hexes = set(load_h3_display_geometries(display_geometry_path))
    if not display_hexes:
        return selected_frame, proposal_stats

    work = source_frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    work["potential_area_share_pct"] = pd.to_numeric(work.get("potential_area_share_pct"), errors="coerce").fillna(0.0)
    work["core_score"] = pd.to_numeric(work.get("core_score"), errors="coerce").fillna(0.0)
    work["zone_size"] = pd.to_numeric(work.get("zone_size"), errors="coerce").fillna(0).astype(int)
    et_hexes = set(work.loc[work["potential_area_share_pct"].gt(0.0), "hex_id"].astype(str)) & display_hexes
    selected_hexes = set(selected_frame.get("hex_id", pd.Series(dtype=str)).astype(str)) if not selected_frame.empty else set()
    anchor_hexes = (selected_hexes or et_hexes) & display_hexes

    neighbor_map = _wind_runtime_hex_neighbor_map(display_geometry_path)
    distance_lookup: dict[str, int] = {}
    if anchor_hexes:
        visited = set(anchor_hexes)
        frontier: deque[tuple[str, int]] = deque((hex_id, 0) for hex_id in anchor_hexes)
        while frontier:
            current, distance = frontier.popleft()
            for neighbor in neighbor_map.get(current, []):
                neighbor = str(neighbor)
                if neighbor not in display_hexes or neighbor in visited:
                    continue
                visited.add(neighbor)
                distance_lookup[neighbor] = distance + 1
                frontier.append((neighbor, distance + 1))

    outside = work[work["hex_id"].isin(display_hexes - et_hexes)].copy()
    if outside.empty:
        return selected_frame, proposal_stats
    outside["expansion_ring"] = outside["hex_id"].map(distance_lookup).fillna(999999).astype(int)
    outside = outside[outside["expansion_ring"].lt(999999)].copy()
    if outside.empty:
        return selected_frame, proposal_stats

    outside["allocation_priority_score"] = pd.to_numeric(
        outside.get("allocation_priority_score", outside.get("core_score", pd.Series(0.0, index=outside.index))),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    reserved_hexes = {str(hex_id) for hex_id in (avoid_hex_ids or set())}
    outside["reserved_by_other_technology"] = outside["hex_id"].astype(str).isin(reserved_hexes)
    outside = outside.sort_values(
        ["reserved_by_other_technology", "expansion_ring", "allocation_priority_score", "zone_size", "hex_id"],
        ascending=[True, True, False, False, True],
    ).reset_index(drop=True)

    remaining_area = et_shortage
    start_rank = int(len(selected_frame)) + 1
    outside_rows: list[dict[str, Any]] = []
    for offset, row in enumerate(outside.itertuples(index=False), start=0):
        allocated_area = min(float(hex_area_km2), max(0.0, remaining_area))
        if allocated_area <= 0:
            break
        record = row._asdict()
        record["selected_rank"] = start_rank + offset
        record["outside_et"] = True
        record["reserved_by_other_technology"] = bool(getattr(row, "reserved_by_other_technology", False))
        record["allocation_phase"] = "Utanför LP"
        record["potential_area_km2"] = 0.0
        record["allocated_area_km2"] = allocated_area
        record["allocated_hex_share_pct"] = (allocated_area / max(float(hex_area_km2), 1e-9)) * 100.0
        remaining_area = max(0.0, remaining_area - allocated_area)
        record["remaining_area_after_km2"] = remaining_area
        outside_rows.append(record)
        if remaining_area <= 1e-9:
            break

    if not outside_rows:
        return selected_frame, proposal_stats

    outside_frame = pd.DataFrame(outside_rows)
    if "outside_et" not in selected_frame.columns and not selected_frame.empty:
        selected_frame = selected_frame.copy()
        selected_frame["outside_et"] = False
    combined = pd.concat([selected_frame, outside_frame], ignore_index=True, sort=False)
    outside_area = float(outside_frame["allocated_area_km2"].sum())
    proposal_stats.update(
        {
            "selected_area_km2": float(proposal_stats.get("et_selected_area_km2", 0.0) or 0.0) + outside_area,
            "unmet_area_km2": max(0.0, remaining_area),
            "selected_hex_count": int(len(combined)),
            "outside_selected_area_km2": outside_area,
            "outside_hex_count": int(len(outside_frame)),
            "outside_candidate_hex": int(len(outside)),
            "outside_candidate_area_km2": float(len(outside) * float(hex_area_km2)),
            "max_expansion_ring": int(outside_frame["expansion_ring"].max()),
            "outside_reserved_candidate_hex": int(outside["reserved_by_other_technology"].sum()),
            "outside_selected_reserved_hex": int(outside_frame["reserved_by_other_technology"].sum()),
        }
    )
    return combined, proposal_stats


def _wind_runtime_hex_layers(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    preferred_resolution: int,
    zoom_family_enabled: bool,
    family_key: str = "wind_runtime_share",
    control_name: str = WIND_POTENTIAL_HEX_LABEL,
) -> list[dict[str, Any]]:
    preferred = min(int(preferred_resolution), WIND_RUNTIME_BASE_RESOLUTION)
    return _hex_family_layers(
        region,
        preferred,
        bool(zoom_family_enabled),
        family_key,
        control_name,
        lambda resolution: _wind_runtime_hex_layer(region, runtime_result, int(resolution), control_name),
    )


def _wind_polygon_preview_state(
    region: dict[str, Any],
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]],
    target_resolution: int,
    zoom_family_enabled: bool,
    family_key: str = "wind_runtime_share",
    control_name: str = WIND_POTENTIAL_HEX_LABEL,
    visual_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_error: str | None = None
    selected = normalize_group_layer_map(layer_selection)
    normalized_visual_options = _normalize_wind_visual_options(visual_options)
    source_group_ids = normalized_visual_options["source_group_ids"]
    buffer_group_ids = normalized_visual_options["buffer_group_ids"]
    if _wind_empty_selection_is_active(selected):
        runtime_result: dict[str, Any] = {
            "groups": {},
            "combined": {"land_share_pct": 100.0},
            "cache_key": "unfiltered_land",
            "unfiltered_land": True,
        }
    else:
        runtime_result = {"groups": {}, "combined": None, "cache_key": None}
        try:
            runtime_result = _wind_fast_distance_runtime_result(region, ui_params, selected, int(target_resolution))
            if runtime_result is None:
                runtime_result = _wind_runtime_result(ui_params, layer_selection=selected)
        except Exception as exc:
            runtime_error = str(exc)

    layers: list[dict[str, Any]] = []
    hex_layers: list[dict[str, Any]] = []
    if not runtime_error and bool(runtime_result.get("fast_distance")):
        def build_fast_distance_layer(resolution: int) -> dict[str, Any] | None:
            layer_result = runtime_result
            if int(resolution) != int(target_resolution):
                layer_result = _wind_fast_distance_runtime_result(region, ui_params, selected, int(resolution))
            if layer_result is None:
                return None
            return _wind_runtime_hex_layer(region, layer_result, int(resolution), control_name)

        hex_layers = _hex_family_layers(
            region,
            int(target_resolution),
            bool(zoom_family_enabled),
            family_key,
            control_name,
            build_fast_distance_layer,
        )
        layers.extend(hex_layers)
    if source_group_ids:
        for source_layer in _wind_polygon_source_layers(
            ui_params,
            layer_selection=selected,
            include_group_ids=source_group_ids,
        ):
            _append_unique_layer(layers, _layer_visible_by_default(source_layer))
    if str(region.get("region_id", "")).lower() == "trondelag" and bool(runtime_result.get("fast_distance")):
        groups, _, _ = load_acceptance_registry()
        for group_id in _wind_active_group_ids(ui_params, layer_selection=selected):
            if group_id not in buffer_group_ids:
                continue
            if group_id == WIND_SETTLEMENT_GROUP_ID:
                continue
            group = groups.get(group_id)
            if group is None:
                continue
            threshold_key = GROUP_PARAM_MAP.get(group_id)
            threshold_m = float(ui_params.get(threshold_key, group.analysis_default_m)) if threshold_key else float(group.analysis_default_m)
            _append_unique_layer(
                layers,
                _layer_visible_by_default(
                    _wind_filter_buffer_layer(
                        group_id,
                        threshold_m,
                        selected.get(group_id, []),
                    )
                ),
            )
    if (
        str(region.get("region_id", "")).lower() == "trondelag"
        and WIND_POPULATION_SOURCE_LAYER_ID in selected.get(WIND_SETTLEMENT_GROUP_ID, [])
        and WIND_SETTLEMENT_GROUP_ID in buffer_group_ids
    ):
        settlement_group = load_acceptance_registry()[0].get(WIND_SETTLEMENT_GROUP_ID)
        threshold_key = GROUP_PARAM_MAP.get(WIND_SETTLEMENT_GROUP_ID)
        threshold_m = float(
            ui_params.get(
                threshold_key,
                settlement_group.analysis_default_m if settlement_group is not None else 0.0,
            )
            if threshold_key
            else 0.0
        )
        population_buffer_layer = _trondelag_population_buffer_polygon_layer(
            region,
            threshold_m,
            prefix="Vindbuffert",
            context_key="wind",
        )
        if population_buffer_layer is not None:
            _append_unique_layer(layers, _layer_visible_by_default(population_buffer_layer))
    if not runtime_error and buffer_group_ids:
        for buffer_layer in _wind_polygon_group_layers(runtime_result, include_group_ids=buffer_group_ids):
            _append_unique_layer(layers, _layer_visible_by_default(buffer_layer))

    return {
        "layers": layers,
        "runtime_error": runtime_error,
        "runtime_result": runtime_result,
        "active_source_count": sum(len(layer_ids) for layer_ids in selected.values()),
        "active_group_count": len(runtime_result.get("groups") or {}) or sum(1 for layer_ids in selected.values() if layer_ids),
        "combined_land_share_pct": (runtime_result.get("combined") or {}).get("land_share_pct"),
        "hex_layer_available": bool(hex_layers),
        "unfiltered_land": bool(runtime_result.get("unfiltered_land")),
    }


def _wind_preview_layers_for_map(
    region: dict[str, Any],
    energy_model_state: dict[str, Any] | None,
    preview_layers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if str(region.get("region_id", "")).lower() != "trondelag" or not (energy_model_state or {}).get("available"):
        return list(preview_layers)
    return [
        layer
        for layer in preview_layers
        if str(layer.get("source_layer_id", "") or "").startswith("wind:")
        or str(layer.get("buffer_layer_id", "") or "").startswith("wind:")
    ]


def _unfiltered_wind_summary_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    frame = _landscape_frame(region, landscape_manifest, int(target_resolution)).copy()
    if frame.empty:
        return pd.DataFrame()

    hex_area = float(h3_hex_area_km2(int(target_resolution)))
    frame["potential_area_share_pct"] = 100.0
    frame["potential_area_share"] = 1.0
    frame["potential_area_km2"] = hex_area
    class_spec = _wind_share_class_spec(100.0)
    frame["share_class_id"] = str(class_spec["id"])
    frame["share_class_label"] = str(class_spec["label"])
    frame["share_class_index"] = WIND_SHARE_CLASS_SPECS.index(class_spec)
    frame = _wind_runtime_hex_core_scores(frame, _wind_runtime_hex_neighbor_map(display_geometry_path))
    frame["fill"] = [
        _wind_runtime_hex_color(100.0, core_value, zone_size)
        for core_value, zone_size in zip(frame["core_score"], frame["zone_size"])
    ]
    frame["core_label"] = [
        _wind_core_label(core_value, zone_size)
        for core_value, zone_size in zip(frame["core_score"], frame["zone_size"])
    ]
    frame["stroke"] = frame["fill"].map(lambda value: _mix_hex_colors(str(value), "#3a3a3a", 0.28))
    frame["wind_score"] = 100.0
    frame["wind_class"] = frame["share_class_id"].astype(str)
    frame["wind_class_label"] = frame["share_class_label"].astype(str)
    frame["wind_color"] = frame["fill"].astype(str)
    if "class_km" not in frame.columns:
        frame["class_km"] = ""
    else:
        frame["class_km"] = frame["class_km"].fillna("").astype(str)
    if "landscape_type" not in frame.columns:
        frame["landscape_type"] = ""
    else:
        frame["landscape_type"] = frame["landscape_type"].fillna("").astype(str)
    return frame.sort_values("hex_id").reset_index(drop=True)


def _wind_polygon_summary_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    if bool(runtime_result.get("unfiltered_land")):
        return _unfiltered_wind_summary_frame(region, landscape_manifest, int(target_resolution))

    frame = _wind_runtime_hex_layer_frame(region, runtime_result, int(target_resolution)).copy()
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "hex_id",
                "potential_area_share_pct",
                "share_class_id",
                "share_class_label",
                "fill",
                "potential_area_km2",
                "wind_score",
                "wind_class",
                "wind_class_label",
                "wind_color",
                "core_score",
                "core_label",
                "zone_size",
                "center_mass_rank",
                "class_km",
                "landscape_type",
                "wind_hard_exclusion_intersects",
            ]
        )

    if "potential_area_km2" not in frame.columns:
        hex_area = float(h3_hex_area_km2(int(target_resolution)))
        frame["potential_area_km2"] = pd.to_numeric(frame["potential_area_share_pct"], errors="coerce").fillna(0.0).clip(
            lower=0.0,
            upper=100.0,
        ).div(100.0) * hex_area
    else:
        frame["potential_area_km2"] = pd.to_numeric(frame["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    frame["wind_score"] = frame["potential_area_share_pct"].astype(float)
    frame["wind_class"] = frame["share_class_id"].astype(str)
    frame["wind_class_label"] = frame["share_class_label"].astype(str)
    frame["wind_color"] = frame["fill"].astype(str)
    frame["core_score"] = pd.to_numeric(frame.get("core_score"), errors="coerce").fillna(0.0)
    frame["core_label"] = frame.get("core_label", "").fillna("").astype(str)
    frame["zone_size"] = pd.to_numeric(frame.get("zone_size"), errors="coerce").fillna(0).astype(int)
    frame["center_mass_rank"] = pd.to_numeric(frame.get("center_mass_rank"), errors="coerce").fillna(1).astype(int)

    landscape = _landscape_frame(region, landscape_manifest, int(target_resolution))
    context_cols = [column for column in ["hex_id", "class_km", "landscape_type"] if column in landscape.columns]
    if context_cols:
        context = landscape[context_cols].drop_duplicates(subset=["hex_id"])
        frame = frame.merge(context, on="hex_id", how="left")

    if "class_km" not in frame.columns:
        frame["class_km"] = ""
    else:
        frame["class_km"] = frame["class_km"].fillna("").astype(str)
    if "landscape_type" not in frame.columns:
        frame["landscape_type"] = ""
    else:
        frame["landscape_type"] = frame["landscape_type"].fillna("").astype(str)
    block_frame = _wind_establishment_intersection_block_frame(region, runtime_result, int(target_resolution))
    if not block_frame.empty:
        frame = frame.merge(block_frame, on="hex_id", how="left")
    if "wind_hard_exclusion_intersects" not in frame.columns:
        frame["wind_hard_exclusion_intersects"] = False
    frame["wind_hard_exclusion_intersects"] = frame["wind_hard_exclusion_intersects"].fillna(False).astype(bool)

    return frame.sort_values("hex_id").reset_index(drop=True)


def _wind_group_summary_frame(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    groups, _, _ = load_acceptance_registry()
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    rows: list[dict[str, Any]] = []
    for group_id, layer_ids in WIND_GROUP_LAYER_DEFAULTS.items():
        threshold_key = GROUP_PARAM_MAP.get(group_id)
        threshold_value = float(ui_params.get(threshold_key, 0.0)) if threshold_key else 0.0
        selected_layer_count = len(selected.get(group_id, []))
        active = selected_layer_count > 0
        rows.append(
            {
                "regelgrupp": GROUP_LABELS.get(group_id, groups[group_id].label if group_id in groups else group_id),
                "analystyp": str(groups[group_id].analysis_kind) if group_id in groups else "-",
                "aktiv": bool(active),
                "troskel_m": "-" if threshold_key is None else int(round(threshold_value)),
                "valda_kallager": int(selected_layer_count),
                "kallager_total": int(len(layer_ids)),
            }
        )
    return pd.DataFrame(rows)


def _wind_source_status_frame() -> pd.DataFrame:
    groups, _, registry_meta = load_acceptance_registry()
    status_df = acceptance_layer_status_table(registry_meta).copy()
    if status_df.empty:
        return status_df

    status_df["group_id"] = status_df["group"].map(
        lambda label: next((group_id for group_id, spec in groups.items() if spec.label == label), label)
    )
    status_df["regelgrupp"] = status_df["group_id"].map(lambda value: GROUP_LABELS.get(str(value), str(value)))
    status_df["klar"] = (
        status_df["geojson_ready"].astype(bool)
        & status_df["source_exists"].astype(bool)
        & status_df["status"].astype(str).eq("ok")
    )
    output = status_df[
        ["regelgrupp", "label", "geometry_family", "feature_count", "status", "klar", "message"]
    ].rename(
        columns={
            "label": "källager",
            "geometry_family": "geometri",
            "feature_count": "objekt",
            "status": "status",
            "message": "notering",
        }
    )
    return output.sort_values(["regelgrupp", "källager"], ascending=[True, True]).reset_index(drop=True)


def _wind_runtime_config_json(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]] | None = None,
) -> str:
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    groups_payload: dict[str, dict[str, Any]] = {}
    for group_id, layer_ids in selected.items():
        if not layer_ids:
            continue
        threshold_key = GROUP_PARAM_MAP.get(group_id)
        threshold_value = float(ui_params.get(threshold_key, 0.0)) if threshold_key else 0.0
        groups_payload[group_id] = {
            "active_layer_ids": list(layer_ids),
            "analysis_value_m": int(round(threshold_value)),
        }
    return json.dumps({"groups": groups_payload}, sort_keys=True, ensure_ascii=False)


def _wind_runtime_result(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    runtime_cfg = _wind_runtime_config_json(ui_params, layer_selection=layer_selection)
    result = run_geometry_runtime(runtime_cfg)
    groups = result.get("groups") if isinstance(result, dict) else None
    if isinstance(groups, dict):
        for group_id, group_meta in groups.items():
            if isinstance(group_meta, dict):
                group_meta.setdefault("active_layer_ids", list(selected.get(str(group_id), [])))
    return result


def _landscape_layer(
    name: str,
    frame: pd.DataFrame,
    manifest: dict[str, Any],
    factor: str,
    display_geometry_path: str | None,
    mode: str,
) -> dict[str, Any]:
    land_frame = _filter_frame_to_display_geometries(frame, display_geometry_path)
    return {
        "name": name,
        "feature_collection": feature_collection_for_frame(manifest, land_frame, factor, None),
        "fill_property": "factor_fill" if mode == "factor" else "cluster_fill",
        "legend_items": _factor_legend_items() if mode == "factor" else _cluster_legend_items(manifest),
        "legend_id": f"landscape_{mode}_{factor}",
        "legend_title": name,
        "default_visible": True,
        "stroke": False,
        "weight": 0.0,
        "layer_kind": "hex",
        "opacity_family": name,
        "opacity_label": name,
    }


def _landscape_type_layer(
    name: str,
    frame: pd.DataFrame,
    manifest: dict[str, Any],
    display_geometry_path: str | None,
) -> dict[str, Any]:
    land_frame = _filter_frame_to_display_geometries(frame, display_geometry_path)
    return {
        "name": name,
        "feature_collection": landscape_type_feature_collection_for_frame(manifest, land_frame, None),
        "fill_property": "landscape_type_fill",
        "legend_items": _landscape_type_legend_items(manifest),
        "legend_id": "landscape_v10_types",
        "legend_title": name,
        "default_visible": True,
        "stroke": False,
        "weight": 0.0,
        "layer_kind": "hex",
        "opacity_family": name,
        "opacity_label": name,
    }


def _render_establishment_focus(energy_model_state: dict[str, Any], geography_renderer: Any | None = None) -> None:
    def _render_establishment_heading() -> None:
        st.subheader(_t("Vind/sol och landskapspåverkan"))

    if not energy_model_state.get("available"):
        _render_establishment_heading()
        st.caption("Etableringsytan visas när energimodelleringen är aktiv.")
        return
    if not bool(energy_model_state.get("show_proposal", False)):
        _render_establishment_heading()
        st.info("Föreslagen etableringsyta är avstängd i energimodelleringen. Kartan visar därför inget etableringslager.")
        return
    if str(energy_model_state.get("placement_mode", "auto")) != "auto":
        _render_establishment_heading()
        st.info("Självplacering är valt. Etableringsytan summeras när automatisk placering är aktiv eller när ett manuellt urval finns.")
        return
    if not bool(energy_model_state.get("establishment_layer_visible", False)):
        _render_establishment_heading()
        st.caption("Etableringsytan visas när vind- och/eller solpotential finns aktiv i kartan.")
        return

    combined = energy_model_state.get("combined_establishment_stats")
    if not isinstance(combined, dict):
        _render_establishment_heading()
        st.caption("Etableringsytan beräknas när vind- och/eller solpotential finns aktiv i kartan.")
        return

    proposal_stats = energy_model_state.get("proposal_stats") if isinstance(energy_model_state, dict) else None
    solar_stats = energy_model_state.get("solar_proposal_stats") if isinstance(energy_model_state, dict) else None
    solar_v1_stats = energy_model_state.get("solar_v1_stats") if isinstance(energy_model_state, dict) else None
    proposal_stats = proposal_stats if isinstance(proposal_stats, dict) else {}
    solar_stats = solar_stats if isinstance(solar_stats, dict) else {}
    social_summary = energy_model_state.get("social_acceptance_summary")
    social_effect = social_summary if isinstance(social_summary, dict) else {}

    wind_need = float(energy_model_state.get("wind_area_need_km2", 0.0) or 0.0)
    solar_need = float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0)
    wind_selected = float(proposal_stats.get("selected_area_km2", 0.0) or 0.0)
    solar_selected = float(solar_stats.get("selected_area_km2", combined.get("solar_v1_covered_area_km2", 0.0)) or 0.0)
    wind_outside = float(proposal_stats.get("outside_selected_area_km2", 0.0) or 0.0)
    solar_outside = float(solar_stats.get("outside_selected_area_km2", 0.0) or 0.0)
    wind_inside = _lp_selected_area_from_stats(proposal_stats, wind_selected, wind_outside)
    solar_inside = _lp_selected_area_from_stats(solar_stats, solar_selected, solar_outside)
    wind_outside_need = max(0.0, wind_need - wind_inside)
    solar_outside_need = max(0.0, solar_need - solar_inside)

    total_need = float(combined.get("total_need_area_km2", wind_need + solar_need) or 0.0)
    inside_total = wind_inside + solar_inside
    outside_total = wind_outside_need + solar_outside_need
    total_covered = inside_total
    covered_share = (inside_total / total_need * 100.0) if total_need > 0 else 0.0
    hex_area = float(energy_model_state.get("hex_area_km2", 0.0) or 0.0)
    h3_resolution = energy_model_state.get("h3_resolution")
    try:
        h3_resolution = int(h3_resolution)
    except Exception:
        h3_resolution = None
    display_h3_resolution = energy_model_state.get("display_h3_resolution")
    try:
        display_h3_resolution = int(display_h3_resolution)
    except Exception:
        display_h3_resolution = h3_resolution

    wind_twh = float(energy_model_state.get("wind_twh", 0.0) or 0.0)
    solar_twh = float(energy_model_state.get("solar_twh", 0.0) or 0.0)
    total_twh = wind_twh + solar_twh
    wind_share_pct = float(energy_model_state.get("wind_share_pct", 0.0) or 0.0)
    solar_share_pct = float(energy_model_state.get("solar_share_pct", 0.0) or 0.0)
    wind_available_area = float(proposal_stats.get("available_candidate_area_km2", 0.0) or 0.0)
    wind_available_hex = int(proposal_stats.get("available_candidate_hex", 0) or 0)
    solar_available_area = float(solar_stats.get("available_candidate_area_km2", 0.0) or 0.0)
    solar_available_hex = int(solar_stats.get("available_candidate_hex", 0) or 0)
    total_available_area = wind_available_area + solar_available_area
    capacity_metrics = energy_model_state.get("acceptance_adjusted_capacity")
    if not isinstance(capacity_metrics, dict):
        capacity_metrics = _acceptance_adjusted_capacity_metrics(
            wind_need,
            wind_available_area,
            solar_need,
            solar_available_area,
            social_effect,
        )
    wind_capacity = capacity_metrics.get("wind", {}) if isinstance(capacity_metrics.get("wind"), dict) else {}
    solar_capacity = capacity_metrics.get("solar", {}) if isinstance(capacity_metrics.get("solar"), dict) else {}
    total_capacity = capacity_metrics.get("total", {}) if isinstance(capacity_metrics.get("total"), dict) else {}
    wind_after_acceptance_area = float(wind_capacity.get("potential_after_acceptance_km2", wind_available_area) or 0.0)
    solar_after_acceptance_area = float(solar_capacity.get("potential_after_acceptance_km2", solar_available_area) or 0.0)
    total_after_acceptance_area = float(total_capacity.get("potential_after_acceptance_km2", wind_after_acceptance_area + solar_after_acceptance_area) or 0.0)
    wind_inside = float(wind_capacity.get("inside_potential_km2", min(wind_need, wind_after_acceptance_area)) or 0.0)
    solar_inside = float(solar_capacity.get("inside_potential_km2", min(solar_need, solar_after_acceptance_area)) or 0.0)
    inside_total = float(total_capacity.get("inside_potential_km2", wind_inside + solar_inside) or 0.0)
    wind_outside_need = float(wind_capacity.get("outside_need_km2", max(0.0, wind_need - wind_inside)) or 0.0)
    solar_outside_need = float(solar_capacity.get("outside_need_km2", max(0.0, solar_need - solar_inside)) or 0.0)
    outside_total = float(total_capacity.get("outside_need_km2", wind_outside_need + solar_outside_need) or 0.0)
    wind_unused_potential = float(wind_capacity.get("unused_potential_km2", max(0.0, wind_after_acceptance_area - wind_inside)) or 0.0)
    solar_unused_potential = float(solar_capacity.get("unused_potential_km2", max(0.0, solar_after_acceptance_area - solar_inside)) or 0.0)
    total_unused_potential = float(total_capacity.get("unused_potential_km2", wind_unused_potential + solar_unused_potential) or 0.0)
    total_covered = inside_total
    covered_share = float(total_capacity.get("coverage_pct", (inside_total / total_need * 100.0) if total_need > 0 else 0.0) or 0.0)
    wind_coverage_pct = float(wind_capacity.get("coverage_pct", (wind_inside / wind_need * 100.0) if wind_need > 0 else 0.0) or 0.0)
    solar_coverage_pct = float(solar_capacity.get("coverage_pct", (solar_inside / solar_need * 100.0) if solar_need > 0 else 0.0) or 0.0)
    snapshot_key = _establishment_change_snapshot_key(energy_model_state)
    current_snapshot = {
        "total_covered_area_km2": total_covered,
        "total_need_area_km2": total_need,
        "inside_total_km2": inside_total,
        "outside_total_km2": outside_total,
        "wind_twh": wind_twh,
        "solar_twh": solar_twh,
        "total_twh": total_twh,
        "wind_need_km2": wind_need,
        "solar_need_km2": solar_need,
        "wind_available_km2": wind_available_area,
        "solar_available_km2": solar_available_area,
        "total_available_km2": total_available_area,
        "wind_inside_km2": wind_inside,
        "solar_inside_km2": solar_inside,
        "wind_unused_potential_km2": wind_unused_potential,
        "solar_unused_potential_km2": solar_unused_potential,
        "total_unused_potential_km2": total_unused_potential,
        "wind_outside_km2": wind_outside_need,
        "solar_outside_km2": solar_outside_need,
        "wind_coverage_pct": wind_coverage_pct,
        "solar_coverage_pct": solar_coverage_pct,
        "total_coverage_pct": covered_share,
    }
    current_fingerprint = _snapshot_fingerprint(current_snapshot)
    snapshot_state_raw = st.session_state.get(snapshot_key)
    snapshot_state = snapshot_state_raw if isinstance(snapshot_state_raw, dict) else {}
    stored_current = snapshot_state.get("current") if isinstance(snapshot_state.get("current"), dict) else {}
    stored_previous = snapshot_state.get("previous") if isinstance(snapshot_state.get("previous"), dict) else {}
    if stored_current and snapshot_state.get("fingerprint") != current_fingerprint:
        previous_snapshot = stored_current
    else:
        previous_snapshot = stored_previous
    scenario_label = str(energy_model_state.get("scenario_label", energy_model_state.get("scenario", "-")) or "-")
    source_label = str(energy_model_state.get("source_scenario_label", "-") or "-")
    source_year = str(energy_model_state.get("source_year", "-") or "-")
    energy_scale = float(energy_model_state.get("energy_scale", 1.0) or 1.0)
    st.session_state.setdefault("establishment_area_display_unit", "km²")
    unit = str(st.session_state.get("establishment_area_display_unit", "km²") or "km²")
    if unit not in AREA_DISPLAY_UNITS:
        unit = "km²"
        st.session_state["establishment_area_display_unit"] = unit
    outside_summary_sentence = (
        f"{_format_area_primary(outside_total, unit, hex_area)} behöver hanteras utanför potentialområdet."
        if outside_total > 1e-6
        else "Ingen yta behöver lösas utanför potentialområdet."
    )
    energy_total_summary_text = (
        f"Scenariot motsvarar {total_twh:.2f} TWh och ger ett teknikspecifikt ytanspråk på "
        f"{_format_area_primary(total_need, unit, hex_area)}. Efter geografiska filter finns "
        f"{_format_area_primary(total_available_area, unit, hex_area)} möjlig etableringsyta som tekniksumma "
        "(vindpotential + solpotential). Det är alltså inte unik fysisk markyta: samma hex kan räknas en gång för "
        "vind och en gång för sol när teknikerna kan samnyttja ytan. Efter eventuell social acceptanspåverkan är "
        f"motsvarande tekniksumma {_format_area_primary(total_after_acceptance_area, unit, hex_area)}. "
        f"Av ytanspråket placeras {_format_area_primary(inside_total, unit, hex_area)} inom potentialområdet, "
        f"vilket motsvarar {covered_share:.1f}% av behovet. {outside_summary_sentence} "
        f"När scenariot är placerat återstår {_format_area_primary(total_unused_potential, unit, hex_area)} "
        "outnyttjad teknikpotential."
    )

    impact_rows = [
        {
            "teknik": "Vind",
            "energi": _value_with_change_html(f"{wind_twh:.2f} TWh", wind_twh, _previous_snapshot_value(previous_snapshot, "wind_twh")),
            "ytbehov": _value_with_change_html(_format_area_primary(wind_need, unit, hex_area), wind_need, _previous_snapshot_value(previous_snapshot, "wind_need_km2")),
            "potential efter filter": _value_with_change_html(
                _format_area_primary(wind_available_area, unit, hex_area),
                wind_available_area,
                _previous_snapshot_value(previous_snapshot, "wind_available_km2"),
            ),
            "potential efter acceptanspåverkan": _value_with_change_html(
                _format_area_primary(wind_after_acceptance_area, unit, hex_area),
                wind_after_acceptance_area,
                wind_available_area,
            ),
            "inom potential": _value_with_change_html(_format_area_primary(wind_inside, unit, hex_area), wind_inside, _previous_snapshot_value(previous_snapshot, "wind_inside_km2")),
            "outnyttjad potential": _value_with_change_html(
                _format_area_primary(wind_unused_potential, unit, hex_area),
                wind_unused_potential,
                _previous_snapshot_value(previous_snapshot, "wind_unused_potential_km2"),
            ),
            "ytbehov utanför potential": _value_with_change_html(
                _format_area_primary(wind_outside_need, unit, hex_area),
                wind_outside_need,
                _previous_snapshot_value(previous_snapshot, "wind_outside_km2"),
            ),
            "andel inom potential": _value_with_change_html(f"{wind_coverage_pct:.1f}%", wind_coverage_pct, _previous_snapshot_value(previous_snapshot, "wind_coverage_pct")),
        },
        {
            "teknik": "Sol",
            "energi": _value_with_change_html(f"{solar_twh:.2f} TWh", solar_twh, _previous_snapshot_value(previous_snapshot, "solar_twh")),
            "ytbehov": _value_with_change_html(_format_area_primary(solar_need, unit, hex_area), solar_need, _previous_snapshot_value(previous_snapshot, "solar_need_km2")),
            "potential efter filter": _value_with_change_html(
                _format_area_primary(solar_available_area, unit, hex_area),
                solar_available_area,
                _previous_snapshot_value(previous_snapshot, "solar_available_km2"),
            ),
            "potential efter acceptanspåverkan": _value_with_change_html(
                _format_area_primary(solar_after_acceptance_area, unit, hex_area),
                solar_after_acceptance_area,
                solar_available_area,
            ),
            "inom potential": _value_with_change_html(_format_area_primary(solar_inside, unit, hex_area), solar_inside, _previous_snapshot_value(previous_snapshot, "solar_inside_km2")),
            "outnyttjad potential": _value_with_change_html(
                _format_area_primary(solar_unused_potential, unit, hex_area),
                solar_unused_potential,
                _previous_snapshot_value(previous_snapshot, "solar_unused_potential_km2"),
            ),
            "ytbehov utanför potential": _value_with_change_html(
                _format_area_primary(solar_outside_need, unit, hex_area),
                solar_outside_need,
                _previous_snapshot_value(previous_snapshot, "solar_outside_km2"),
            ),
            "andel inom potential": _value_with_change_html(f"{solar_coverage_pct:.1f}%", solar_coverage_pct, _previous_snapshot_value(previous_snapshot, "solar_coverage_pct")),
        },
        {
            "teknik": "Totalt",
            "energi": _value_with_change_html(f"{total_twh:.2f} TWh", total_twh, _previous_snapshot_value(previous_snapshot, "total_twh")),
            "ytbehov": _value_with_change_html(_format_area_primary(total_need, unit, hex_area), total_need, _previous_snapshot_value(previous_snapshot, "total_need_area_km2")),
            "potential efter filter": _value_with_change_html(
                _format_area_primary(total_available_area, unit, hex_area),
                total_available_area,
                _previous_snapshot_value(previous_snapshot, "total_available_km2"),
            ),
            "potential efter acceptanspåverkan": _value_with_change_html(
                _format_area_primary(total_after_acceptance_area, unit, hex_area),
                total_after_acceptance_area,
                total_available_area,
            ),
            "inom potential": _value_with_change_html(_format_area_primary(inside_total, unit, hex_area), inside_total, _previous_snapshot_value(previous_snapshot, "inside_total_km2")),
            "outnyttjad potential": _value_with_change_html(
                _format_area_primary(total_unused_potential, unit, hex_area),
                total_unused_potential,
                _previous_snapshot_value(previous_snapshot, "total_unused_potential_km2"),
            ),
            "ytbehov utanför potential": _value_with_change_html(
                _format_area_primary(outside_total, unit, hex_area),
                outside_total,
                _previous_snapshot_value(previous_snapshot, "outside_total_km2"),
            ),
            "andel inom potential": _value_with_change_html(f"{covered_share:.1f}%", covered_share, _previous_snapshot_value(previous_snapshot, "total_coverage_pct")),
        },
    ]
    _render_establishment_heading()
    st.caption(
        "Tabellen visar hur mycket teknikspecifik yta scenariot kräver, hur mycket möjlig teknikpotential som finns efter filter, och om något behöver lösas utanför potentialen."
    )
    _render_impact_change_table(impact_rows)

    if outside_total > 1e-6:
        st.warning(
            "Vald energimix ryms inte helt inom landskapets potential. "
            f"{_format_area_with_context(outside_total, unit, hex_area)} behöver lösas utanför landskapets potential."
        )
    elif total_need > 0:
        st.success("Vald energimix ryms inom landskapets potential med nuvarande urval.")

    st.caption(
        " · ".join(
            [
                f"Ryms: {covered_share:.1f}%",
                f"Inom potential: {_format_area_with_context(inside_total, unit, hex_area)}",
                f"Utanför potential: {_format_area_with_context(outside_total, unit, hex_area)}",
            ]
        )
    )
    with st.expander(_t("Så läses tabellen"), expanded=False):
        st.caption(
            "Tabellen jämför scenariots teknikspecifika ytbehov med möjlig yta efter aktiva filter. Totalraden summerar vind och sol och kan därför vara större än den unika fysiska markytan."
        )
        st.caption(
            "En grön etableringshex med mörk scenariohex kan bära både vind- och solscenarioyta. Det betyder samnyttjande i modellen."
        )
        st.caption("Pilarna visar förändring sedan föregående beräknade läge.")

    if callable(geography_renderer):
        geography_renderer()

    st.subheader(_t("Energimodellering"))
    st.markdown(f"**{_t('Sammanfattning')}**")
    st.markdown(energy_total_summary_text)

    if isinstance(social_summary, dict) and social_summary:
        st.subheader(_t("Social acceptans"))
        scenario_label = str(social_summary.get("scenario_label", social_summary.get("scenario_id", "-")) or "-")
        impact_pct = float(social_summary.get("impact_pct", 0.0) or 0.0)
        measured_hex_count = int(social_summary.get("measured_hex_count", 0) or 0)
        potential_hex_count = int(social_summary.get("potential_hex_count", 0) or 0)
        st.caption(
            f"Scenario: {scenario_label}. Beräknas på {measured_hex_count:,} av {potential_hex_count:,} potentiella etableringshex."
            .replace(",", " ")
        )
        metric_cols = st.columns(3)
        metric_cols[0].metric("Medelacceptans", f"{float(social_summary.get('mean_acceptance', 0.0) or 0.0):.2f}")
        metric_cols[1].metric("Medianacceptans", f"{float(social_summary.get('median_acceptance', 0.0) or 0.0):.2f}")
        metric_cols[2].metric("Acceptanspåverkan", f"{impact_pct:.0f}%")
        allocation_priority_pct = float(energy_model_state.get("social_acceptance_allocation_priority_pct", 0.0) or 0.0)
        if allocation_priority_pct > 0.0:
            st.caption(f"Scenariohexar prioriteras med {allocation_priority_pct:.0f}% social acceptansstyrning.")
        low_threshold = float(social_summary.get("low_threshold", SOCIAL_ACCEPTANCE_LOW_THRESHOLD) or SOCIAL_ACCEPTANCE_LOW_THRESHOLD)
        high_threshold = float(social_summary.get("high_threshold", SOCIAL_ACCEPTANCE_HIGH_THRESHOLD) or SOCIAL_ACCEPTANCE_HIGH_THRESHOLD)
        acceptance_rows = [
            {
                "klass": f"Låg < {low_threshold:.1f}",
                "yta": _format_area_primary(float(social_summary.get("low_acceptance_area_km2", 0.0) or 0.0), unit, hex_area),
                "andel": f"{float(social_summary.get('low_acceptance_share_pct', 0.0) or 0.0):.1f}%",
                "hex": _count_text(int(social_summary.get("low_acceptance_hex_count", 0) or 0)),
            },
            {
                "klass": f"Hög ≥ {high_threshold:.1f}",
                "yta": _format_area_primary(float(social_summary.get("high_acceptance_area_km2", 0.0) or 0.0), unit, hex_area),
                "andel": f"{float(social_summary.get('high_acceptance_share_pct', 0.0) or 0.0):.1f}%",
                "hex": _count_text(int(social_summary.get("high_acceptance_hex_count", 0) or 0)),
            },
        ]
        st.dataframe(pd.DataFrame(acceptance_rows), width="stretch", hide_index=True, height=124)
        missing_hex_count = int(social_summary.get("missing_hex_count", 0) or 0)
        if missing_hex_count > 0:
            st.caption(f"Acceptansdata saknas för {missing_hex_count:,} potentiella hex och räknas inte i statistiken.".replace(",", " "))

    with st.expander(_t("Avancerade inställningar"), expanded=False):
        _render_right_panel_width_control(st)
        st.radio(
            "Enhet",
            options=AREA_DISPLAY_UNITS,
            index=AREA_DISPLAY_UNITS.index(unit),
            horizontal=True,
            key="establishment_area_display_unit",
        )
        st.caption("Byte av enhet ändrar bara hur ytor visas i panelen, inte modellresultatet.")
        st.caption(
            "Panelen visar om vald mix av vind och sol ryms i de landskap som modellen bedömer som möjliga efter aktiva filter. "
            "Kartan färgsätter platser som möjliga för vind, sol, båda teknikerna eller ingen av dem."
        )
        st.caption(
            f"Dummy/prototypdata · {scenario_label}: {energy_scale:g}x energi · "
            f"markintensitet {energy_model_state.get('area_scenario_label', '-')} · "
            f"mix {wind_share_pct:.0f}% vind / {solar_share_pct:.0f}% sol · källa {source_label} {source_year}"
        )
        st.caption(_format_hex_size_caption(h3_resolution, hex_area))
        st.caption(
            "Ytorna summeras som hela H3-celler. Vid kusten kan därför redovisad yta vara större än faktisk landyta, "
            "eftersom kustceller räknas med även när delar av cellen ligger i havet."
        )
        if display_h3_resolution is not None and h3_resolution is not None and display_h3_resolution != h3_resolution:
            st.caption(
                f"Kartan visas som R{display_h3_resolution}. Ytbalans, täckning och scenarioallokering beräknas i R{h3_resolution}."
            )
        with st.expander(_t("Hexdetaljer och kartmarkörer"), expanded=False):
            st.caption("Tekniska kartmått för granskning av hexmarkörer och färgklasser.")
            hex_stats = energy_model_state.get("establishment_hex_stats")
            if isinstance(hex_stats, dict):
                total_hex = int(hex_stats.get("total_hex_count", 0) or 0)
                black_hex = int(hex_stats.get("black_hex_count", 0) or 0)
                red_hex = int(hex_stats.get("red_hex_count", 0) or 0)
                wind_only_hex = int(hex_stats.get("wind_only_hex_count", 0) or 0)
                solar_only_hex = int(hex_stats.get("solar_only_hex_count", 0) or 0)
                wind_and_solar_hex = int(hex_stats.get("wind_and_solar_hex_count", 0) or 0)
                hex_rows = [
                    {
                        "kategori": f"Totalt antal R{h3_resolution}-hex" if h3_resolution is not None else "Totalt antal H3-hex",
                        "antal hex": _count_text(total_hex),
                        "motsvarar": _format_area_with_context(total_hex * hex_area, unit, hex_area),
                    },
                    {
                        "kategori": "Schematiska ytbudgethex",
                        "antal hex": _count_text(black_hex),
                        "motsvarar": f"{_format_area_with_context(outside_total, unit, hex_area)} ytbehov",
                    },
                    {
                        "kategori": "Röda hex i etableringslagret",
                        "antal hex": _count_text(red_hex),
                        "motsvarar": _format_area_with_context(red_hex * hex_area, unit, hex_area),
                    },
                    {
                        "kategori": "Child-hex scenario: vind",
                        "antal hex": _count_text(wind_only_hex),
                        "motsvarar": "scenarioplacering",
                    },
                    {
                        "kategori": "Child-hex scenario: sol",
                        "antal hex": _count_text(solar_only_hex),
                        "motsvarar": "scenarioplacering",
                    },
                    {
                        "kategori": "Child-hex scenario: båda",
                        "antal hex": _count_text(wind_and_solar_hex),
                        "motsvarar": "samma större hex",
                    },
                ]
                st.dataframe(pd.DataFrame(hex_rows), width="stretch", hide_index=True, height=246)
                st.caption(
                    "Ytbudgethex visar extra ytbehov i separata schematiska fält ute till havs. Child-hex visar scenarioyta inom lämpliga etableringshex med teknikfärg: blå för vind, gul för sol och grön när båda samnyttjar samma större hex."
                )
            else:
                st.caption("Hexstatistik saknas för denna vy.")

            shortage_stats = energy_model_state.get("outside_lp_shortage_stats")
            if isinstance(shortage_stats, dict) and outside_total > 1e-6:
                _render_shortage_hex_stack_card(shortage_stats, unit)

        with st.expander(_t("Urval och ytdetaljer"), expanded=False):
            if isinstance(solar_v1_stats, dict):
                small_cols = st.columns(3)
                small_cols[0].metric(f"{SOLAR_SMALL_SCALE_LABEL}: yta", f"{float(solar_v1_stats.get('total_area_km2', 0.0) or 0.0):.2f} km²")
                small_cols[1].metric("Täcker solbehov", f"{float(solar_v1_stats.get('covered_share_pct', 0.0) or 0.0):.1f}%")
                small_cols[2].metric("Solbehov efter tak", f"{float(solar_v1_stats.get('remaining_area_km2', 0.0) or 0.0):.2f} km²")
            if proposal_stats:
                selected_twh = float(proposal_stats.get("selected_twh", 0.0) or 0.0)
                if selected_twh > 0:
                    st.metric("Fördelad vindproduktion", f"{selected_twh:.2f} TWh")
                needed_hex = int(proposal_stats.get("needed_hex", 0) or 0)
                selected_count = int(proposal_stats.get("selected_hex_count", 0) or 0)
                if selected_count <= 0:
                    selected_count = len(energy_model_state.get("proposal_frame", pd.DataFrame()))
                detail_cols = st.columns(3)
                detail_cols[0].metric("Area per hex", f"{hex_area:.4f} km²")
                detail_cols[1].metric("Hela hex behövs", f"{needed_hex:,}".replace(",", " "))
                detail_cols[2].metric("Valda vindhex", f"{selected_count:,}".replace(",", " "))
                available_hex = int(proposal_stats.get("available_candidate_hex", 0) or 0)
                available_area = float(proposal_stats.get("available_candidate_area_km2", 0.0) or 0.0)
                primary_candidates = int(proposal_stats.get("primary_candidate_hex", 0) or 0)
                extension_candidates = int(proposal_stats.get("extension_candidate_hex", 0) or 0)
                selected_primary = int(proposal_stats.get("selected_primary_hex", 0) or 0)
                selected_extension = int(proposal_stats.get("selected_extension_hex", 0) or 0)
                min_share = float(proposal_stats.get("min_share_pct", energy_model_state.get("auto_min_potential_share_pct", 65.0)) or 65.0)
                mean_share = float(proposal_stats.get("mean_selected_share_pct", 0.0) or 0.0)
                selected_potential_area = float(proposal_stats.get("selected_potential_area_km2", 0.0) or 0.0)
                selected_hex_footprint = float(proposal_stats.get("selected_hex_footprint_km2", 0.0) or 0.0)
                st.caption(
                    f"Vindurvalet innehåller {selected_potential_area:.2f} km² potentiell yta inom "
                    f"{selected_hex_footprint:.2f} km² hexavtryck. Valbara LP-hex: "
                    f"{available_hex:,} med {available_area:.2f} km² potentiell yta; medelandel i urvalet {mean_share:.1f}%.".replace(",", " ")
                )
                st.caption(
                    f"Urvalsordning: först kärn-LP med LP ≥ {min_share:.0f}% "
                    f"({selected_primary:,}/{primary_candidates:,} valda), sedan kompletterande LP "
                    f"({selected_extension:,}/{extension_candidates:,} valda).".replace(",", " ")
                )
                if selected_count > needed_hex:
                    st.caption("Area-share gör att fler hex behövs än den teoretiska jämförelsen med helt fyllda hex.")
                if wind_outside_need > 1e-6:
                    st.warning(
                        "Vindbehovet ryms inte helt inom landskapets potential. Planeringsval behövs: sänk potentialkrav, "
                        "släpp in kantzoner, ändra restriktioner, välj ett lägre framtidsscenario eller minska ytbehovet."
                    )
            warning_table = energy_model_state.get("area_warnings")
            if isinstance(warning_table, pd.DataFrame) and not warning_table.empty:
                st.caption("AreaDemand har datakvalitetsvarningar. Se Energimodellering-panelen för detaljer.")
            st.caption(
                f"{COMBINED_ESTABLISHMENT_LAYER_LABEL} visar vind och sol tillsammans. "
                f"{OUTSIDE_LP_NEED_LAYER_LABEL} visar den extra etableringsyta som krävs när scenariot inte ryms."
            )
    if stored_current and snapshot_state.get("fingerprint") != current_fingerprint:
        snapshot_previous = stored_current
    else:
        snapshot_previous = previous_snapshot
    st.session_state[snapshot_key] = {
        "previous": snapshot_previous,
        "current": current_snapshot,
        "fingerprint": current_fingerprint,
    }


def _render_performance_log(performance_log: list[dict[str, Any]]) -> None:
    if not performance_log:
        return
    with st.expander(_t("Prestanda"), expanded=False):
        total_seconds = sum(float(row.get("tid_s", 0.0) or 0.0) for row in performance_log)
        slowest = max(performance_log, key=lambda row: float(row.get("tid_s", 0.0) or 0.0))
        st.caption(
            "Tidslogg för den senaste körningen. Den mäter Python- och HTML-byggsteg; webbläsarens egen ritning kan tillkomma."
        )
        frame = pd.DataFrame(performance_log)
        frame["tid"] = frame["tid_s"].map(lambda value: f"{float(value):.2f} s")
        st.dataframe(frame[["steg", "tid", "detalj"]], width="stretch", hide_index=True, height=min(360, 72 + 34 * len(frame)))
        st.caption(f"Summa mätta steg: {total_seconds:.2f} s. Långsammast: {slowest.get('steg', '-')} ({float(slowest.get('tid_s', 0.0) or 0.0):.2f} s).")


def _render_reused_workspace_outputs(
    cache: dict[str, Any],
    region: dict[str, Any],
    scenario_state: dict[str, Any],
    opacity: float,
    preserve_map_view: bool,
    map_reset_token: int,
    right_panel: Any | None,
) -> None:
    layers = cache.get("layers") if isinstance(cache.get("layers"), list) else []
    map_state = cache.get("map_state") if isinstance(cache.get("map_state"), dict) else {}
    energy_model_state = cache.get("energy_model_state") if isinstance(cache.get("energy_model_state"), dict) else {"available": False}
    if isinstance(map_state, dict):
        map_state = dict(map_state)
        map_state.setdefault("establishment_hex_stats", energy_model_state.get("establishment_hex_stats"))
        map_state.setdefault("geography_effect_notes", _geography_effect_notes(energy_model_state))
    performance_log = cache.get("performance_log") if isinstance(cache.get("performance_log"), list) else []
    note_body = str(cache.get("note_body", ""))

    reason = _ui_only_rerun_reason() or "visning"
    st.caption(f"Visningsändring ({reason}): återanvänder senaste beräknade karta och potential. Ingen ny potentialberäkning körs.")
    _render_layers(
        region,
        layers,
        opacity,
        map_state_key=f"{region.get('region_id', 'region')}:workspace:{MAP_STATE_VERSION}" if preserve_map_view else None,
        map_reset_token=map_reset_token,
        opacity_key_prefix="combined",
        note_title="Gemensam potentialvy",
        note_body=note_body,
        after_map_renderer=lambda: _render_energy_mix_card(st, region, energy_model_state),
    )

    summary_target = right_panel or st.container()
    with summary_target:
        _render_establishment_focus(energy_model_state, lambda: _combined_summary(map_state, scenario_state))
        _data_method(region)
        with st.expander(_t("Debug och prestanda"), expanded=False):
            _render_performance_log(performance_log)
            st.markdown(f"**{_t('Aktiva beräkningar')}**")
            st.caption(
                "Den senaste visningsändringen återanvände redan beräknade resultat. "
                "Samma princip används nu för språk, paneler, kartvy och opacitet."
            )
            performance_diagnostics = energy_model_state.get("performance_diagnostics") if isinstance(energy_model_state, dict) else None
            if isinstance(performance_diagnostics, list) and performance_diagnostics:
                st.dataframe(
                    pd.DataFrame(performance_diagnostics).head(8),
                    width="stretch",
                    hide_index=True,
                    height=min(344, 72 + 32 * min(8, len(performance_diagnostics))),
                )


def _combined_summary(map_state: dict[str, Any], scenario_state: dict[str, Any]) -> None:
    landscape_manifest = map_state.get("landscape_manifest") if isinstance(map_state.get("landscape_manifest"), dict) else {}
    landscape_factors = [str(value) for value in (map_state.get("landscape_factors") or [])]
    lablab_landscape_manifest = _pdf_landscape_manifest(landscape_manifest)

    def _lablab_landscape_label(row: pd.Series, labels: dict[str, Any]) -> str:
        for column in [
            "landscape_type",
            "landscape_type_id",
            "landscape_type_code",
            "type_id",
            "class_id",
            "class_km",
        ]:
            if column not in row.index:
                continue
            raw = row.get(column)
            if pd.isna(raw):
                continue
            text = str(raw).strip()
            if not text:
                continue
            if text in labels:
                return str(labels[text])
            try:
                number = float(text)
                if math.isfinite(number):
                    key = f"LT{int(number):02d}"
                    if key in labels:
                        return str(labels[key])
            except Exception:
                pass
            return text
        return "Okänd"

    def _lablab_landscape_context(resolution: int | None) -> pd.DataFrame:
        if lablab_landscape_manifest is None or resolution is None:
            return pd.DataFrame(columns=["hex_id", "lablab_landskapstyp"])
        try:
            context = _unclipped_landscape_frame(lablab_landscape_manifest, int(resolution)).copy()
        except Exception:
            return pd.DataFrame(columns=["hex_id", "lablab_landskapstyp"])
        if context.empty or "hex_id" not in context.columns:
            return pd.DataFrame(columns=["hex_id", "lablab_landskapstyp"])
        labels = {str(key): value for key, value in (lablab_landscape_manifest.get("landscape_type_labels") or {}).items()}
        context["lablab_landskapstyp"] = context.apply(lambda row: _lablab_landscape_label(row, labels), axis=1)
        return context[["hex_id", "lablab_landskapstyp"]].drop_duplicates(subset=["hex_id"])

    def _wind_share_summary(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["klass", "klass_label", "hexagoner", "medelandel", "djupa_karnor"])
        work = frame.copy()
        work["potential_area_share_pct"] = pd.to_numeric(work["potential_area_share_pct"], errors="coerce").fillna(0.0)
        work["share_class_index"] = pd.to_numeric(work.get("share_class_index"), errors="coerce").fillna(999).astype(int)
        work["core_score"] = pd.to_numeric(work.get("core_score"), errors="coerce").fillna(0.0)
        work["share_class_id"] = work["share_class_id"].astype(str)
        work["share_class_label"] = work["share_class_label"].astype(str)
        work["deep_core"] = work["core_score"].ge(0.72)
        return (
            work.groupby(["share_class_index", "share_class_id", "share_class_label"], as_index=False)
            .agg(
                hexagoner=("hex_id", "count"),
                medelandel=("potential_area_share_pct", "mean"),
                djupa_karnor=("deep_core", "sum"),
            )
            .sort_values(["share_class_index", "medelandel"])
            .assign(medelandel=lambda data: data["medelandel"].round(1))
            .rename(columns={"share_class_id": "klass", "share_class_label": "klass_label"})
            [["klass", "klass_label", "hexagoner", "medelandel", "djupa_karnor"]]
        )

    def _solar_area_share_summary(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["klass", "klass_label", "hexagoner", "medel_areaandel", "yta_m2"])
        work = frame.copy()
        work["potential_area_share_pct"] = pd.to_numeric(work.get("potential_area_share_pct"), errors="coerce").fillna(0.0)
        work["potential_area_m2"] = pd.to_numeric(work.get("potential_area_m2"), errors="coerce").fillna(0.0)
        work["solar_class"] = work["solar_class"].astype(str)
        work["solar_class_label"] = work["solar_class_label"].astype(str)
        return (
            work.groupby(["solar_class", "solar_class_label"], as_index=False)
            .agg(
                hexagoner=("hex_id", "count"),
                medel_areaandel=("potential_area_share_pct", "mean"),
                yta_m2=("potential_area_m2", "sum"),
            )
            .sort_values("medel_areaandel")
            .assign(
                medel_areaandel=lambda data: data["medel_areaandel"].round(1),
                yta_m2=lambda data: data["yta_m2"].round(0).astype(int),
            )
            .rename(columns={"solar_class": "klass", "solar_class_label": "klass_label"})
            [["klass", "klass_label", "hexagoner", "medel_areaandel", "yta_m2"]]
        )

    def _wind_core_summary(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or "core_label" not in frame.columns:
            return pd.DataFrame(columns=["kärnläge", "hexagoner", "medelandel"])
        work = frame.copy()
        work["potential_area_share_pct"] = pd.to_numeric(work["potential_area_share_pct"], errors="coerce").fillna(0.0)
        work["core_score"] = pd.to_numeric(work.get("core_score"), errors="coerce").fillna(0.0)
        work["core_label"] = work["core_label"].fillna("").astype(str).replace("", "Okänt")
        order = {"Kantzon": 1, "Mellanläge": 2, "Djup kärna": 3, "Enskild hex": 4, "Okänt": 5}
        return (
            work.groupby("core_label", as_index=False)
            .agg(hexagoner=("hex_id", "count"), medelandel=("potential_area_share_pct", "mean"), kärnscore=("core_score", "mean"))
            .assign(sort=lambda data: data["core_label"].map(order).fillna(99))
            .sort_values("sort")
            .assign(medelandel=lambda data: data["medelandel"].round(1), kärnscore=lambda data: data["kärnscore"].round(2))
            .rename(columns={"core_label": "kärnläge"})
            [["kärnläge", "hexagoner", "medelandel", "kärnscore"]]
        )

    def _potential_area_series(frame: pd.DataFrame, technology: str) -> pd.Series:
        if frame.empty:
            return pd.Series(dtype="float64")
        if "potential_area_km2" in frame.columns:
            return pd.to_numeric(frame["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
        if "solar_v1_area_km2" in frame.columns:
            return pd.to_numeric(frame["solar_v1_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
        if "potential_area_m2" in frame.columns:
            return pd.to_numeric(frame["potential_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0) / 1_000_000.0
        score_col = f"{technology}_score"
        if score_col in frame.columns:
            return pd.to_numeric(frame[score_col], errors="coerce").fillna(0.0).clip(lower=0.0) / 100.0
        return pd.Series(1.0, index=frame.index, dtype="float64")

    def _landscape_derivation_summary(frame: pd.DataFrame, technology: str, resolution: int | None, unit: str, hex_area_km2: float) -> tuple[pd.DataFrame, str]:
        columns = ["Landskapstyp", "Andel av potentialen", "Potentialyta", "Antal hexagoner"]
        if frame.empty:
            return pd.DataFrame(columns=columns), "Ingen potential finns att fördela på LABLAB:s landskapstyper."
        context = _lablab_landscape_context(resolution)
        if context.empty:
            return pd.DataFrame(columns=columns), "LABLAB:s landskapsanalys saknas för vald H3-upplösning."
        work = frame.copy()
        work["potential_area_km2__derived"] = _potential_area_series(work, technology)
        work = work[work["potential_area_km2__derived"].gt(0.0)].copy()
        if work.empty:
            return pd.DataFrame(columns=columns), "Ingen positiv potential finns att fördela på LABLAB:s landskapstyper."
        work = work.merge(context, on="hex_id", how="left")
        work["Landskapstyp"] = work["lablab_landskapstyp"].fillna("Okänd").astype(str).replace("", "Okänd")
        work = work[work["Landskapstyp"].ne("Okänd")].copy()
        if work.empty:
            return pd.DataFrame(columns=columns), "Potentialen matchar inga LABLAB-landskapstyper i vald upplösning."
        total_area = float(work["potential_area_km2__derived"].sum())
        grouped = (
            work.groupby("Landskapstyp", as_index=False)
            .agg(
                _hexagoner=("hex_id", "count"),
                _potential_km2=("potential_area_km2__derived", "sum"),
            )
        )
        labels = (lablab_landscape_manifest or {}).get("landscape_type_labels") or {}
        if isinstance(labels, dict) and labels:
            ordered_types = pd.DataFrame(
                [
                    {"Landskapstyp": str(label), "_type_order": order}
                    for order, (_, label) in enumerate(
                        sorted(
                            labels.items(),
                            key=lambda item: int(str(item[0]).replace("LT", "")) if str(item[0]).replace("LT", "").isdigit() else 999,
                        )
                    )
                ]
            )
            grouped = ordered_types.merge(grouped, on="Landskapstyp", how="left")
        else:
            grouped["_type_order"] = range(len(grouped))
        grouped["_hexagoner"] = pd.to_numeric(grouped["_hexagoner"], errors="coerce").fillna(0).astype(int)
        grouped["_potential_km2"] = pd.to_numeric(grouped["_potential_km2"], errors="coerce").fillna(0.0)
        grouped["_andel_potential_pct"] = grouped["_potential_km2"] / max(total_area, 1e-9) * 100.0
        grouped["_has_potential"] = grouped["_potential_km2"].gt(0.0)
        grouped = grouped.sort_values(
            ["_has_potential", "_potential_km2", "_type_order"],
            ascending=[False, False, True],
        )
        top = grouped.iloc[0]
        zero_count = int((~grouped["_has_potential"]).sum())
        text = (
            f"Störst del av potentialen ligger i {top['Landskapstyp']} "
            f"({float(top['_andel_potential_pct']):.1f}% av potentialytan)."
        )
        if zero_count > 0:
            text += f" {zero_count} landskapstyp(er) saknar positiv potential i aktuellt urval och visas som 0."
        display = pd.DataFrame(
            {
                "Landskapstyp": grouped["Landskapstyp"],
                "Andel av potentialen": grouped["_andel_potential_pct"].map(lambda value: f"{float(value):.1f}%"),
                "Potentialyta": grouped["_potential_km2"].map(lambda value: _format_area_primary(float(value), unit, hex_area_km2)),
                "Antal hexagoner": grouped["_hexagoner"].map(lambda value: _count_text(int(value))),
            }
        )
        return display[columns], text

    def _structure_id_text(value: Any) -> str:
        if pd.isna(value):
            return "Okänd"
        try:
            number = float(str(value).strip())
            if math.isfinite(number):
                return str(int(number)) if number.is_integer() else f"{number:g}"
        except Exception:
            pass
        text = str(value).strip()
        return text or "Okänd"

    def _structure_label(value: Any) -> str:
        if pd.isna(value):
            return "Okänd"
        try:
            return cluster_label(landscape_manifest, float(str(value).strip()))
        except Exception:
            structure_id = _structure_id_text(value)
            labels = (landscape_manifest or {}).get("cluster_labels") or {}
            return str(labels.get(structure_id, f"Cluster {structure_id}"))

    def _landscape_structure_summary(frame: pd.DataFrame, technology: str) -> tuple[pd.DataFrame, str]:
        columns = ["struktur", "struktur_label", "hexagoner", "potential_km2", "andel_potential_pct", "medelpoäng"]
        if frame.empty or "class_km" not in frame.columns:
            return pd.DataFrame(columns=columns), "Strukturhärledning saknas för detta lager."
        work = frame.copy()
        work["struktur"] = work["class_km"].map(_structure_id_text)
        work["struktur_label"] = work["class_km"].map(_structure_label)
        work["potential_area_km2__derived"] = _potential_area_series(work, technology)
        score_col = f"{technology}_score"
        if score_col not in work.columns and technology == "solar_v1" and "solar_v1_score" in work.columns:
            score_col = "solar_v1_score"
        work["score__derived"] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0) if score_col in work.columns else 0.0
        work = work[work["potential_area_km2__derived"].gt(0.0)].copy()
        if work.empty:
            return pd.DataFrame(columns=columns), "Ingen positiv potential finns att härleda till landskapsstrukturer."
        total_area = float(work["potential_area_km2__derived"].sum())
        grouped = (
            work.groupby(["struktur", "struktur_label"], as_index=False)
            .agg(
                hexagoner=("hex_id", "count"),
                potential_km2=("potential_area_km2__derived", "sum"),
                medelpoäng=("score__derived", "mean"),
            )
            .sort_values("potential_km2", ascending=False)
        )
        grouped["andel_potential_pct"] = (grouped["potential_km2"] / max(total_area, 1e-9) * 100.0).round(1)
        grouped["potential_km2"] = grouped["potential_km2"].round(2)
        grouped["medelpoäng"] = grouped["medelpoäng"].round(1)
        top = grouped.iloc[0]
        text = (
            f"Störst del av potentialen ligger i struktur {top['struktur']}: {top['struktur_label']} "
            f"({float(top['andel_potential_pct']):.1f}% av potentialytan)."
        )
        return grouped[columns], text

    def _landscape_factor_summary(frame: pd.DataFrame, technology: str) -> tuple[pd.DataFrame, str]:
        columns = ["faktor", "faktor_label", "viktat_medel", "oviktat_medel", "potential_km2", "täckning_pct"]
        factor_cols = [factor for factor in landscape_factors if factor in frame.columns]
        if frame.empty or not factor_cols:
            return pd.DataFrame(columns=columns), "Faktorhärledning saknas för detta lager."
        work = frame.copy()
        work["potential_area_km2__derived"] = _potential_area_series(work, technology)
        work = work[work["potential_area_km2__derived"].gt(0.0)].copy()
        if work.empty:
            return pd.DataFrame(columns=columns), "Ingen positiv potential finns att väga mot landskapsfaktorer."
        weights = pd.to_numeric(work["potential_area_km2__derived"], errors="coerce").fillna(0.0).clip(lower=0.0)
        total_weight = float(weights.sum())
        rows: list[dict[str, Any]] = []
        for factor in factor_cols:
            values = pd.to_numeric(work[factor], errors="coerce")
            valid = values.notna()
            if not bool(valid.any()):
                continue
            valid_weights = weights.where(valid, 0.0)
            weight_sum = float(valid_weights.sum())
            weighted_mean = float((values.fillna(0.0) * valid_weights).sum() / max(weight_sum, 1e-9))
            rows.append(
                {
                    "faktor": factor,
                    "faktor_label": factor_label(landscape_manifest, factor),
                    "viktat_medel": round(weighted_mean, 3),
                    "oviktat_medel": round(float(values[valid].mean()), 3),
                    "potential_km2": round(weight_sum, 2),
                    "täckning_pct": round(weight_sum / max(total_weight, 1e-9) * 100.0, 1),
                    "_sort_abs": abs(weighted_mean),
                }
            )
        if not rows:
            return pd.DataFrame(columns=columns), "Faktorhärledning saknar numeriska faktorvärden."
        grouped = pd.DataFrame(rows).sort_values(["_sort_abs", "potential_km2"], ascending=[False, False])
        top = grouped.iloc[0]
        direction = "positivt" if float(top["viktat_medel"]) >= 0 else "negativt"
        text = (
            f"Starkast viktad faktor i potentialytan är {top['faktor']} - {top['faktor_label']} "
            f"({direction} medel {float(top['viktat_medel']):.3f})."
        )
        return grouped[columns], text

    def _metric_value_text(frame: pd.DataFrame, score_col: str, template: str) -> str:
        if frame.empty:
            return "-"
        value = float(frame[score_col].mean())
        try:
            return template.format(value=value)
        except Exception:
            return f"{value:.1f}"

    def _high_share_pct(frame: pd.DataFrame, class_col: str, high_classes: list[str] | tuple[str, ...] | None) -> float:
        if frame.empty:
            return 0.0
        target_classes = [str(value) for value in (high_classes or ["high", "very_high"])]
        return float(frame[class_col].astype(str).isin(target_classes).mean() * 100.0)

    st.markdown(
        f"<h3 data-potential-tutorial-anchor='right-geographies'>{html.escape(_t('Geografier'))}</h3>",
        unsafe_allow_html=True,
    )
    _render_geography_user_summary(map_state)

    unit = str(st.session_state.get("establishment_area_display_unit", "km²") or "km²")
    if unit not in AREA_DISPLAY_UNITS:
        unit = "km²"
    visible_potential_labels = {SOLAR_LANDSCAPE_POTENTIAL_LABEL, WIND_LANDSCAPE_POTENTIAL_LABEL}
    potential_items = [
        item
        for item in (map_state.get("potential_frames") or [])
        if str(item.get("label", "")) in visible_potential_labels
    ]
    if potential_items:
        st.markdown(
            "<div data-potential-tutorial-anchor='landscape-distribution' "
            "style='margin-top:0.65rem;margin-bottom:0.25rem;font-weight:650;color:#374151;'>"
            f"{html.escape(_t('Potentialfördelning per landskapstyp'))}"
            "</div>",
            unsafe_allow_html=True,
        )
    for item in potential_items:
        frame = item["frame"]
        technology = item["technology"]
        item_resolution = item.get("resolution")
        try:
            item_resolution_int = int(item_resolution) if item_resolution is not None else None
        except Exception:
            item_resolution_int = None
        item_hex_area = float(h3_hex_area_km2(item_resolution_int)) if item_resolution_int is not None else 0.0
        with st.expander(item["label"], expanded=False):
            derivation_frame, derivation_text = _landscape_derivation_summary(
                frame,
                technology,
                item_resolution_int,
                unit,
                item_hex_area,
            )
            st.caption(derivation_text)
            if not derivation_frame.empty:
                st.dataframe(derivation_frame.head(10), width="stretch", hide_index=True)


def _data_method(region: dict[str, Any]) -> None:
    with st.expander(_t("Data och metod"), expanded=False):
        rows = []
        for key, label in [
            ("scenario_manifest", "Scenarier"),
            ("landscape_manifest", "Landskapsanalys"),
            ("potential_manifest", "Potential"),
        ]:
            path = resolve_repo_path(region.get(key))
            rows.append(
                {
                    "manifest": label,
                    "path": str(path) if path is not None else "",
                    "exists": bool(path and path.exists()),
                }
            )
        status_frame = pd.DataFrame(rows)
        st.caption("Datakällor och modellmanifest som används i denna region.")
        st.dataframe(status_frame[["manifest", "exists"]], width="stretch", hide_index=True)
        with st.expander(_t("Manifest och tekniska sökvägar"), expanded=False):
            st.dataframe(status_frame, width="stretch", hide_index=True)
            st.json(region)


def _status_for_part(status_rows: list[dict[str, Any]], label: str) -> str:
    for row in status_rows:
        if str(row.get("del")) == str(label):
            return str(row.get("status", "saknas"))
    return "saknas"


def _disabled_note(label: str, status_rows: list[dict[str, Any]]) -> str:
    status = _status_for_part(status_rows, label)
    return "Data kopplad." if status == "klar" else f"Data saknas: {label}."


def _missing_wind_controls(status_rows: list[dict[str, Any]]) -> None:
    language = _wind_control_language()
    st.caption(_disabled_note("Vindregler", status_rows))
    st.caption("Samma vindkontroller visas för alla regioner. De aktiveras när regionens vindregler och H3-/landskapsunderlag finns.")
    for group in ordered_groups():
        label = group_label(group, language, group.label)
        if group.id == WIND_SETTLEMENT_GROUP_ID:
            label = _t(WIND_SETTLEMENT_GROUP_LABEL)
        elif group.id == SOLAR_PROTECTED_GROUP_ID:
            label = _t(PROTECTED_NATURE_LABEL)
        with st.expander(label, expanded=group.id in {"settlement", "transport", "electrical"}):
            st.caption(group_interpretation(group, language, group.interpretation))
            st.slider(
                group_analysis_label(group, language, group.analysis_label),
                min_value=int(group.analysis_min_m),
                max_value=int(group.analysis_max_m),
                value=int(group.analysis_default_m),
                step=int(group.analysis_step_m),
                key=f"missing_wind_analysis_{group.id}",
                disabled=True,
            )
            group_layers = [item for item in ordered_layers() if item.group_id == group.id]
            if not group_layers:
                st.caption("Inga källager är registrerade för denna grupp ännu.")
            for layer in group_layers[:6]:
                st.checkbox(
                    layer_label(layer, language, layer.label),
                    value=False,
                    key=f"missing_wind_layer_{layer.id}",
                    disabled=True,
                    help="Aktiveras när regionens källager finns.",
                )
            if len(group_layers) > 6:
                st.caption(f"{len(group_layers) - 6} ytterligare del-lager visas när data kopplas in.")


def _missing_solar_controls(status_rows: list[dict[str, Any]]) -> None:
    st.caption(_disabled_note("Solregler", status_rows))
    st.caption("Samma solkontroller visas för alla regioner. De aktiveras när solregler, H3-/landskapsunderlag och relevanta källager finns.")
    with st.form("missing_solar_landscape_potential_controls", clear_on_submit=False):
        with st.expander(_t(SOLAR_SMALL_SCALE_LABEL), expanded=True):
            st.checkbox(
                _t("Befolkningspunkter"),
                value=False,
                key="missing_solar_small_population_active",
                disabled=True,
                help="Aktiveras när befolkningsunderlag finns för regionen.",
            )
            st.slider(
                _t("Panelyta per person"),
                min_value=0.0,
                max_value=25.0,
                value=10.0,
                step=1.0,
                key="missing_solar_area_m2_per_person",
                disabled=True,
            )
            st.caption("Småskalig sol kan fyllas på senare med befolkningsunderlag.")
        with st.expander(_t(SOLAR_LARGE_SCALE_LABEL), expanded=True):
            with st.expander(_t("Befolkning"), expanded=False):
                st.checkbox(_t("Befolkningspunkter"), value=False, key="missing_solar_large_population", disabled=True)
                st.slider(
                    _t("Avstånd till befolkning"),
                    min_value=100.0,
                    max_value=500.0,
                    value=250.0,
                    step=25.0,
                    key="missing_solar_population_buffer_m",
                    disabled=True,
                )
            for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
                label = str(spec["label"])
                with st.expander(label, expanded=False):
                    st.checkbox(f"Använd {label}", value=False, key=f"missing_solar_filter_{group_id}", disabled=True)
                    st.slider(
                        str(spec.get("slider_label") or f"Buffert {label.lower()}"),
                        min_value=float(spec.get("buffer_min_m", 0.0)),
                        max_value=float(spec.get("buffer_max_m", 1000.0)),
                        value=float(spec.get("buffer_default_m", 0.0)),
                        step=float(spec.get("buffer_step_m", 50.0)),
                        key=f"missing_solar_filter_buffer_{group_id}",
                        disabled=True,
                    )
                    st.caption(str(spec.get("caption", "Kopplas in när regiondata finns.")))
        st.form_submit_button(_t("Använd ändringar"), disabled=True, width="stretch")


def _missing_energy_controls(status_rows: list[dict[str, Any]]) -> None:
    st.caption(_disabled_note("Scenarier/energimodell", status_rows))
    st.selectbox(
        {"en": "Energy scenario", "da_no": "Energiscenario"}.get(_language(), "Energiscenario"),
        options=["Låg", "Mellan", "Hög"],
        index=1,
        key="missing_energy_scenario",
        disabled=True,
    )
    st.selectbox(
        {"en": "Land intensity", "da_no": "Arealintensitet"}.get(_language(), "Markintensitet"),
        options=["Låg", "Mellan", "Hög"],
        index=1,
        key="missing_area_intensity",
        disabled=True,
    )
    st.slider(_t("Energimix"), min_value=0, max_value=100, value=50, step=5, format="%d%% sol", key="missing_energy_mix", disabled=True)
    st.checkbox(_t("Visa föreslagen etableringsyta"), value=True, key="missing_energy_show_proposal", disabled=True)
    st.info("Energimodellering aktiveras när scenariomanifest, DuckDB och AreaDemand är kopplade.")


def _missing_potential_summary(label: str, missing_text: str) -> None:
    with st.expander(_t(label), expanded=False):
        left, right = st.columns(2)
        left.metric("Medelpoäng", "-")
        right.metric("Hög potential", "-")
        st.info(missing_text)
        with st.expander(_t("Landskapstyper"), expanded=False):
            st.caption("Härledning visas när landskapsanalys finns för regionen.")
        with st.expander(_t("Landskapstrukturer"), expanded=False):
            st.caption("Strukturhärledning visas när kluster/strukturdata finns.")
        with st.expander(_t("Landskapsfaktorer"), expanded=False):
            st.caption("Faktorhärledning visas när faktoranalysen finns.")


def _render_missing_data_workspace(
    region: dict[str, Any],
    scenario_state: dict[str, Any],
    context: dict[str, Any],
    left_panel: Any | None,
    right_panel: Any | None,
) -> None:
    status_rows = region_data_status_rows(region, context)
    missing_rows = [row for row in status_rows if str(row.get("status")) != "klar"]
    region_label = str(region.get("display_name", region.get("region_id", "region")))

    if left_panel is not None:
        with left_panel.expander(_t("Geografier"), expanded=True):
            st.caption(f"{region_label}: fast Trøndelag-version.")
            with st.expander(_t("Landskap"), expanded=True):
                st.caption("Landskapsdata saknas ännu för denna region." if context.get("landscape_manifest") is None else "Landskapsmanifest finns.")
                st.checkbox(_t("Landskapstyper"), value=False, disabled=True, key="missing_show_landscape_v10")
                st.checkbox(_t("Landskapstrukturer"), value=False, disabled=True, key="missing_show_landscape_cluster")
                st.checkbox(_t("Landskapsfaktorer"), value=False, disabled=True, key="missing_show_landscape_factor")
                st.selectbox(
                    _t("Faktor"),
                    options=["F1 - faktoranalys saknas"],
                    index=0,
                    key="missing_landscape_factor",
                    disabled=True,
                )
            with st.expander("Avancerade inställningar", expanded=False):
                st.markdown(f"**{_t('H3-upplösning')}**")
                resolutions = _available_h3_resolutions(region)
                st.selectbox(
                    _t("H3-upplösning"),
                    options=resolutions,
                    index=0,
                    key="missing_combined_h3_resolution",
                    format_func=lambda value: f"R{value}",
                    disabled=True,
                )
                display_modes = ["selected", "zoom_family"] if len({int(value) for value in resolutions}) > 1 else ["selected"]
                st.radio(
                    _t("Hexvisning"),
                    options=display_modes,
                    index=display_modes.index("zoom_family") if "zoom_family" in display_modes else 0,
                    format_func=lambda value: {
                        "selected": _t("Vald upplösning"),
                        "zoom_family": _t("Zoomanpassad upplösning"),
                    }.get(str(value), str(value)),
                    key="missing_combined_h3_display_mode",
                    disabled=True,
                )
                st.caption("Hexgeometrier kopplas in via regionmanifestet.")
                st.dataframe(
                    pd.DataFrame([row for row in status_rows if str(row.get("del", "")).startswith("H3")]),
                    width="stretch",
                    hide_index=True,
                    height=180,
                )
            with st.expander(_t(WIND_LANDSCAPE_POTENTIAL_LABEL), expanded=False):
                _missing_wind_controls(status_rows)
            with st.expander(_t(SOLAR_LANDSCAPE_POTENTIAL_LABEL), expanded=False):
                _missing_solar_controls(status_rows)
        with left_panel.expander(_t("Energimodellering"), expanded=False):
            _missing_energy_controls(status_rows)
        with left_panel.expander(_t("Social acceptans"), expanded=False):
            st.checkbox(_t("Visa social acceptans"), value=False, key="missing_social_acceptance", disabled=True)
            st.caption("Social acceptans kan kopplas in som regiondata senare.")

    st.info(
        f"{region_label} är öppnad i data-tolerant läge. Appens UI kan byggas vidare, men vissa beräkningar väntar på regiondata."
    )
    if missing_rows:
        st.warning("Data saknas för vissa lager/funktioner. Det är okej i detta läge.")
        st.dataframe(pd.DataFrame(status_rows), width="stretch", hide_index=True, height=min(420, 72 + 32 * len(status_rows)))
    else:
        st.success("Alla grundmanifest och H3-geometrier finns.")

    st.caption(
        "Kartan visar inte potentiallager förrän minst H3-geometrier och relevant sol-/vindunderlag finns. "
        "Regionens default center/zoom används när kartlager saknas."
    )
    st.code(
        json.dumps(
            {
                "region_id": region.get("region_id"),
                "default_map_center": region.get("default_map_center"),
                "default_zoom": region.get("default_zoom"),
                "available_h3_resolutions": _available_h3_resolutions(region),
            },
            ensure_ascii=False,
            indent=2,
        ),
        language="json",
    )

    summary_target = right_panel or st.container()
    with summary_target:
        st.markdown('<span data-potential-tutorial-anchor="right-panel"></span>', unsafe_allow_html=True)
        st.subheader(_t("Karta"))
        st.caption("Karta och lagerkontroll visas när H3-geometrier och minst ett lager finns.")
        with st.expander(f"{_t('Lager som visas')} (0)", expanded=False):
            st.caption("Inga lager är tända eftersom regiondata saknas.")
        st.subheader(_t("Etableringsyta"))
        st.caption("Etableringsytan visas när sol- eller vindpotential och energimodellering är kopplade.")
        _missing_potential_summary(WIND_LANDSCAPE_POTENTIAL_LABEL, "Vindpotential väntar på H3-/landskapsunderlag och vindregler.")
        _missing_potential_summary(SOLAR_LANDSCAPE_POTENTIAL_LABEL, "Solpotential väntar på H3-/landskapsunderlag och solregler.")
        st.subheader(_t("Regionstatus"))
        st.caption("Samma appstruktur används för alla regioner. Saknade delar visas som status, inte som krasch.")
        st.dataframe(pd.DataFrame(status_rows), width="stretch", hide_index=True, height=min(420, 72 + 32 * len(status_rows)))
        with st.expander(_t("Nästa datapaket"), expanded=True):
            st.caption("Minsta praktiska paket för att börja visa potential är H3-geometrier, potentialmanifest och teknikregler.")
            st.markdown(
                "- `h3_display_geometries` i regionmanifestet\n"
                "- `landscape_manifest` om härledning/faktorer ska fungera\n"
                "- `potential_manifest` med sol- och vindregler\n"
                "- `scenario_manifest` om energimodellering ska fungera"
            )
        _data_method(region)


def _unified_workspace_tab(
    region: dict[str, Any],
    scenario_state: dict[str, Any],
    context: dict[str, Any],
    left_panel: Any | None = None,
    right_panel: Any | None = None,
) -> None:
    landscape_manifest = context["landscape_manifest"]
    potential_manifest = context["potential_manifest"]
    solar_rules = context["solar_rules"]
    if not bool(context.get("runtime_ready")):
        _render_missing_data_workspace(region, scenario_state, context, left_panel, right_panel)
        return

    factors = factor_columns(landscape_manifest)
    _ensure_default_start_state(region)

    saved_solar_params = _saved_solar_params()
    solar_defaults = _default_solar_params(solar_rules)
    _prime_solar_builder_state(solar_defaults, saved_solar_params)
    _prime_wind_builder_state(_default_wind_params(), _selected_wind_layers())
    h3_resolution, zoom_family_enabled, opacity, preserve_map_view, map_reset_token = _map_panel_controls(region, "combined")

    st.session_state["show_default_solar"] = False
    st.session_state.setdefault("show_user_solar", False)
    st.session_state.setdefault("show_solar_v1", False)
    st.session_state.setdefault("solar_small_population_active", True)
    st.session_state.setdefault("solar_large_scale_active", False)
    st.session_state.setdefault("solar_large_population_active", False)
    st.session_state.setdefault("solar_v1_area_m2_per_person", 10.0)
    st.session_state.setdefault("solar_protected_buffer_m", 0.0)
    st.session_state["show_default_wind"] = False
    st.session_state["show_user_wind"] = False
    st.session_state["show_landscape_v10"] = False
    st.session_state.setdefault("show_landscape_pdf_types", True)
    st.session_state["show_landscape_cluster"] = False
    st.session_state["show_landscape_factor"] = False

    applied_solar_config = _solar_config_from_session()
    _prime_solar_draft_state(applied_solar_config)
    show_solar_v1 = bool(applied_solar_config.get("small_population_active", False))
    show_user_solar = bool(applied_solar_config.get("large_scale_active", False))
    solar_small_population_active = bool(applied_solar_config.get("small_population_active", False))
    solar_large_population_active = bool(applied_solar_config.get("large_population_active", False))
    solar_large_protected_layer_ids = list(applied_solar_config.get("large_protected_layer_ids", []))
    solar_large_protected_active = bool(solar_large_protected_layer_ids)
    solar_large_filter_configs = _solar_active_filter_configs(applied_solar_config)
    show_user_wind = _wind_potential_is_active(_selected_wind_layers())
    lablab_landscape_manifest = _pdf_landscape_manifest(landscape_manifest)
    pdf_landscape_available = lablab_landscape_manifest is not None
    show_v10 = False
    show_pdf_types = bool(st.session_state.get("show_landscape_pdf_types", True)) and pdf_landscape_available
    pdf_landscape_label = str(
        (lablab_landscape_manifest or {}).get("display_name")
        or (landscape_manifest or {}).get("pdf_landscape_display_name")
        or "LABLAB:s landskapstyper"
    )
    show_cluster = False
    show_factor = False
    selected_factor = str(st.session_state.get("combined_landscape_factor", factors[0] if factors else ""))
    if selected_factor not in factors and factors:
        selected_factor = factors[0]
    social_manifest = _social_acceptance_manifest(region)
    show_social_acceptance = bool(st.session_state.get("show_social_acceptance", False)) and social_manifest is not None
    social_acceptance_scenario = (
        _social_acceptance_scenario(region, social_manifest)
        if social_manifest is not None
        else SOCIAL_ACCEPTANCE_DEFAULT_SCENARIO_ID
    )
    social_acceptance_impact_pct = _social_acceptance_impact_pct(region) if social_manifest is not None else 0.0
    social_acceptance_allocation_priority_pct = (
        _social_acceptance_allocation_priority_pct(region)
        if social_manifest is not None
        else 0.0
    )
    active_landscape_count = _count_enabled(show_pdf_types)
    active_solar_count = _count_enabled(show_user_solar, show_solar_v1)
    _, acceptance_layers_for_labels, _ = load_acceptance_registry()
    population_layer_label = layer_label(
        acceptance_layers_for_labels[WIND_POPULATION_SOURCE_LAYER_ID],
        WIND_CONTROL_LANGUAGE,
        acceptance_layers_for_labels[WIND_POPULATION_SOURCE_LAYER_ID].label,
    ) if WIND_POPULATION_SOURCE_LAYER_ID in acceptance_layers_for_labels else _t("Befolkningspunkter")
    if str(region.get("region_id", "")).lower() == "trondelag":
        population_layer_label = "Befolkningsrutor 250 m (proxy)"

    wind_selected_layers = _selected_wind_layers()
    wind_ui_params = _default_wind_params()
    wind_controls_applied = False
    solar_params = _solar_params_from_control_state(solar_defaults)
    solar_params["population_buffer_m"] = float(applied_solar_config.get("population_buffer_m", 250.0) or 250.0)
    for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
        solar_params[str(spec["buffer_key"])] = float(
            applied_solar_config.get(str(spec["buffer_key"]), spec.get("buffer_default_m", 0.0)) or 0.0
        )
    solar_v1_area_m2_per_person = float(applied_solar_config.get("panel_area_m2_per_person", 10.0) or 0.0)
    solar_controls_applied = False
    energy_model_state: dict[str, Any] = {"available": False}
    performance_log: list[dict[str, Any]] = []
    if left_panel is not None:
        with left_panel.expander(_t("Geografier"), expanded=False):
            with st.expander(_t("Landskap"), expanded=True):
                show_pdf_types = st.checkbox(
                    _t("Landskapstyper"),
                    value=show_pdf_types,
                    disabled=not pdf_landscape_available,
                    key="show_landscape_pdf_types",
                )
                active_landscape_count = _count_enabled(show_pdf_types)
                st.caption(f"Aktiva kartlager: {active_landscape_count}")
                st.caption(f"Datakälla: {pdf_landscape_label}.")

            with st.expander("Avancerade inställningar", expanded=False):
                h3_resolution, zoom_family_enabled, opacity, preserve_map_view, map_reset_token = _map_panel_controls(region, "combined", st)
            analysis_h3_resolution = _analysis_h3_resolution(region)
            analysis_hex_area_km2 = float(h3_hex_area_km2(analysis_h3_resolution))

            with st.expander(_t(WIND_LANDSCAPE_POTENTIAL_LABEL), expanded=False):
                wind_selected_layers, wind_ui_params, wind_controls_applied = _wind_group_controls("wind_unified", language=_wind_control_language())
                show_user_wind = _wind_potential_is_active(wind_selected_layers)
                if _wind_empty_selection_is_active(wind_selected_layers):
                    st.caption("Inga vindfilter är valda: ofiltrerad vindpotential används som startläge.")

            with st.expander(_t(SOLAR_LANDSCAPE_POTENTIAL_LABEL), expanded=active_solar_count > 0):
                st.caption(f"Aktiva solgrupper: {active_solar_count}")
                with st.form("solar_landscape_potential_controls_unified", clear_on_submit=False):
                    st.caption(
                        f"{SOLAR_LANDSCAPE_POTENTIAL_LABEL} är en samlad solmodell med grupper. "
                        f"Ändringar i lager och sliders appliceras först när du trycker på Använd ändringar."
                    )
                    st.markdown(
                        "[Vill du veta mer om att anlägga sol över land? Läs guiden från Byplanlab.]"
                        "(https://byplanlab.dk/sites/default/files/2025-06/Sol%20over%20land%20-%20Guide%20til%20planl%C3%A6gning%20af%20solenergi.pdf)"
                    )
                    with st.expander(_t(SOLAR_SMALL_SCALE_LABEL), expanded=False):
                        draft_small_population_active = st.checkbox(
                            population_layer_label,
                            key="solar_draft_small_population_active",
                            help="Trøndelag-källan visas som 250 m befolkningsrutor från centroider, inte som individpunkter.",
                        )
                        if draft_small_population_active and not _solar_v1_population_source_available(region):
                            st.warning(_solar_v1_population_source_status(region))
                        if draft_small_population_active:
                            if str(region.get("region_id", "")).lower() == "trondelag":
                                st.info(
                                    "Småskalig sol är en schablon från befolkning i Trondelags 250 m-rutor per hex. "
                                    "Den visas som små gula schablonhexar, inte som faktisk takpotential eller sammanhängande markyta."
                                )
                            else:
                                st.info(
                                    "Småskalig sol är en schablon från befolkning per hex. "
                                    "Den visas som små gula schablonhexar, inte som faktiska takpolygoner eller sammanhängande markyta."
                                )
                        st.slider(
                            _solar_v1_panel_area_label(region),
                            min_value=0.0,
                            max_value=25.0,
                            step=1.0,
                            key="solar_draft_area_m2_per_person",
                            help=_solar_v1_formula_text(region, float(st.session_state.get("solar_draft_area_m2_per_person", 10.0) or 10.0)),
                        )
                        with st.expander("Avancerade inställningar", expanded=False):
                            st.caption("Kartvisning: befolkningsunderlaget används i analysen även när källa och buffert är dolda på kartan.")
                            st.checkbox(
                                "Visa källa i kartan",
                                key=_solar_visual_control_key("source", SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID),
                            )
                            st.checkbox(
                                "Visa buffert i kartan",
                                key=_solar_visual_control_key("buffer", SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID),
                            )
                        st.caption("Kartlager: schablonhexar och gemensam potentiell etableringsyta. Källa och buffert kan visas via avancerade inställningar.")
                    with st.expander(_t(SOLAR_LARGE_SCALE_LABEL), expanded=False):
                        with st.expander(_t("Befolkning"), expanded=False):
                            draft_large_population_active = st.checkbox(
                                population_layer_label,
                                key="solar_draft_large_population_active",
                            )
                            st.slider(
                                _t("Avstånd till befolkning"),
                                min_value=100.0,
                                max_value=500.0,
                                step=25.0,
                                key="solar_draft_population_buffer_m",
                                help="Totalt avstånd från valt befolkningsunderlag. För Trøndelag är källan 250 m befolkningsrutor från centroider.",
                            )
                            st.caption("Avståndet är totalt från befolkningsunderlaget. Trøndelag använder 250 m befolkningsrutor från centroider som proxy.")
                            with st.expander("Avancerade inställningar", expanded=False):
                                st.caption("Kartvisning: befolkningsunderlaget används i analysen även när källa och buffert är dolda på kartan.")
                                st.checkbox(
                                    "Visa källa i kartan",
                                    key=_solar_visual_control_key("source", SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID),
                                )
                                st.checkbox(
                                    "Visa buffert i kartan",
                                    key=_solar_visual_control_key("buffer", SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID),
                                )
                        for solar_filter_group_id in (
                            SOLAR_PROTECTED_GROUP_ID,
                            SOLAR_LAND_USE_GROUP_ID,
                            SOLAR_ROAD_GROUP_ID,
                            SOLAR_ELECTRICAL_GROUP_ID,
                            SOLAR_CULTURE_GROUP_ID,
                            SOLAR_REINDEER_GROUP_ID,
                            SOLAR_COASTAL_GROUP_ID,
                        ):
                            if (
                                solar_filter_group_id != SOLAR_REINDEER_GROUP_ID
                                or _solar_filter_layer_options(solar_filter_group_id)
                            ):
                                _render_solar_filter_control(solar_filter_group_id)
                        st.caption("Storskalig sol använder hela landskapsunderlaget som kandidatbas. Valda skydds-/avståndsfilter drar bort yta, medan nära nät begränsar ytan till platser inom valt maxavstånd.")
                        st.caption("Ingen bonitets- eller jordklassvariabel finns i nuvarande solunderlag; jordart/prekvartär beskriver geologi, inte jordbruksmarkens kvalitet.")
                    apply_solar = st.form_submit_button(_t("Använd ändringar"), type="primary", width="stretch")
                if apply_solar:
                    region_id = str(region.get("region_id", "region"))
                    scenario_manifest = scenario_state.get("manifest") or {}
                    scenario_levels = scenario_manifest.get("scenario_levels") or []
                    potential_scenario_key = f"potential_scenario_{region_id}"
                    energy_scenario_key = f"energy_model_planning_scenario_{region_id}"
                    current_scenario = str(
                        st.session_state.get(energy_scenario_key)
                        or st.session_state.get(potential_scenario_key)
                        or scenario_state.get("scenario")
                        or ""
                    )
                    if current_scenario in scenario_levels:
                        st.session_state[potential_scenario_key] = current_scenario
                        st.session_state[energy_scenario_key] = current_scenario
                    _invalidate_workspace_cache("solar controls applied")
                    st.session_state[SOLAR_APPLIED_CONFIG_KEY] = _solar_draft_config_from_session()
                    solar_controls_applied = True
                    st.rerun()

        with left_panel.expander(_t("Energimodellering"), expanded=False):
            st.caption(_t("Levereras av EML"))
            st.markdown(f"[Energy Modelling Lab]({EML_PROVIDER_URL})")
            perf_started = _perf_start()
            energy_model_state = _render_energy_modeling_panel(
                region,
                scenario_state,
                analysis_h3_resolution,
                st,
            )
            _add_perf_timing(performance_log, "Energimodellering", perf_started, f"analys R{analysis_h3_resolution}")
            if energy_model_state.get("available"):
                scenario_state = {
                    "scenario": energy_model_state.get("scenario_label") or energy_model_state.get("scenario"),
                    "manifest": scenario_state.get("manifest"),
                    "year": energy_model_state.get("source_year"),
                    "energy_model": energy_model_state,
                }

        with left_panel.expander(_t("Social acceptans"), expanded=False):
            st.caption(_t("Levereras av IVL"))
            st.caption("Syntetiskt testlager tills IVL-data finns.")
            if social_manifest is None:
                st.checkbox(_t("Visa social acceptans"), value=False, key="show_social_acceptance", disabled=True)
                st.caption(_t("Kommer i augusti"))
            else:
                show_social_acceptance = st.checkbox(
                    _t("Visa social acceptanslager"),
                    value=show_social_acceptance,
                    key="show_social_acceptance",
                )
                social_acceptance_impact_pct = float(
                    st.slider(
                        _t("Acceptanspåverkan"),
                        min_value=0,
                        max_value=100,
                        value=int(round(social_acceptance_impact_pct)),
                        step=5,
                        format="%d%%",
                        key=_social_acceptance_impact_state_key(region),
                        help=(
                            "0% lämnar potentiell etableringsyta oförändrad. "
                            "100% tonar färgen fullt efter social acceptans: hög acceptans behåller färgen, låg acceptans tonar mot rött."
                        ),
                    )
                )
                social_acceptance_allocation_priority_pct = float(
                    st.slider(
                        "Acceptansstyrning av scenariohexar",
                        min_value=0,
                        max_value=100,
                        value=int(round(social_acceptance_allocation_priority_pct)),
                        step=5,
                        format="%d%%",
                        key=_social_acceptance_allocation_priority_state_key(region),
                        help=(
                            "0% använder lagrets interna landskaps-/teknikranking. "
                            "100% låter hög social acceptans väga tungt när scenariohexar väljs först."
                        ),
                    )
                )
                scenario_options = [scenario["id"] for scenario in social_acceptance_scenarios(social_manifest)]
                social_acceptance_scenario = st.radio(
                    "Acceptansscenario",
                    options=scenario_options,
                    key=_social_acceptance_state_key(region),
                    format_func=lambda scenario_id: social_acceptance_scenario_label(social_manifest, str(scenario_id)),
                    horizontal=True,
                    disabled=not (
                        show_social_acceptance
                        or social_acceptance_impact_pct > 0.0
                        or social_acceptance_allocation_priority_pct > 0.0
                    ),
                )
                st.caption(
                    f"Testdata: värden 0-1 på H3 R{int(social_manifest.get('hex_resolution') or 0)} "
                    "med max tre decimaler. Inte verkliga forskningsresultat."
                )
            st.markdown(f"[IVL Svenska Miljöinstitutet]({IVL_PROVIDER_URL})")

    display_geometry_path = _h3_display_geometry_path(region, h3_resolution)
    analysis_display_geometry_path = _h3_display_geometry_path(region, analysis_h3_resolution)
    resolution_info = _hex_display_rule(region, h3_resolution, zoom_family_enabled)
    st.session_state["solar_builder_params"] = solar_params
    st.session_state["wind_builder_params"] = wind_ui_params
    wind_visual_options = _wind_visual_options_from_state(wind_selected_layers)
    if energy_model_state.get("available"):
        energy_model_state["region_id"] = str(region.get("region_id", "region") or "region")
        energy_model_state["analysis_h3_resolution"] = int(analysis_h3_resolution)
        energy_model_state["analysis_hex_area_km2"] = float(analysis_hex_area_km2)
        energy_model_state["display_h3_resolution"] = int(h3_resolution)
        energy_model_state["display_hex_area_km2"] = float(h3_hex_area_km2(h3_resolution))
        energy_model_state["social_acceptance_allocation_priority_pct"] = float(social_acceptance_allocation_priority_pct or 0.0)
        energy_model_state["wind_ui_params"] = dict(wind_ui_params)
        energy_model_state["wind_visual_options"] = dict(wind_visual_options)
        energy_model_state["wind_active_source_count"] = sum(
            len(layer_ids) for layer_ids in normalize_group_layer_map(wind_selected_layers).values()
        )
        energy_model_state["solar_params"] = dict(solar_params)
        energy_model_state["solar_large_population_active"] = bool(solar_large_population_active)
        energy_model_state["solar_large_unfiltered_land_active"] = bool(applied_solar_config.get("large_unfiltered_land_active", False))
        energy_model_state["solar_large_protected_active"] = bool(solar_large_protected_active)
        energy_model_state["solar_large_protected_layer_count"] = int(len(solar_large_protected_layer_ids))
        energy_model_state["solar_large_filter_configs"] = list(solar_large_filter_configs)

    workspace_fingerprint = _workspace_calculation_fingerprint(
        region,
        scenario_state,
        h3_resolution,
        analysis_h3_resolution,
        zoom_family_enabled,
        show_user_solar,
        show_solar_v1,
        show_user_wind,
        show_v10,
        show_pdf_types,
        show_cluster,
        show_factor,
        show_social_acceptance,
        social_acceptance_scenario,
        social_acceptance_impact_pct,
        social_acceptance_allocation_priority_pct,
        selected_factor,
        applied_solar_config,
        solar_params,
        solar_large_filter_configs,
        wind_selected_layers,
        wind_ui_params,
        wind_visual_options,
        energy_model_state,
    )
    if _ui_only_rerun_requested():
        cached_workspace = _cached_workspace_payload(workspace_fingerprint)
        if cached_workspace is not None:
            _render_reused_workspace_outputs(
                cached_workspace,
                region,
                scenario_state,
                opacity,
                preserve_map_view,
                map_reset_token,
                right_panel,
            )
            _clear_ui_only_rerun()
            return
        _clear_ui_only_rerun()

    calc_steps = _calculation_progress_steps(
        show_user_solar,
        show_solar_v1,
        show_user_wind,
        energy_model_state,
        bool(show_v10 or show_cluster or show_factor),
        bool(
            show_social_acceptance
            or social_acceptance_impact_pct > 0.0
            or social_acceptance_allocation_priority_pct > 0.0
        ),
    )
    performance_bucket = _performance_history_bucket(region, h3_resolution, zoom_family_enabled)
    performance_estimates = _performance_step_estimates(performance_bucket, calc_steps)
    calc_progress = _start_calculation_progress(calc_steps, performance_estimates)

    layers: list[dict[str, Any]] = []
    potential_frames: list[dict[str, Any]] = []
    unified_notes: list[str] = []
    user_solar_frame = pd.DataFrame()
    user_solar_analysis_frame = pd.DataFrame()
    solar_v1_frame = pd.DataFrame()
    solar_v1_analysis_frame = pd.DataFrame()
    combined_solar_potential_frame = pd.DataFrame()
    combined_solar_analysis_frame = pd.DataFrame()
    custom_wind_summary_frame = pd.DataFrame()
    custom_wind_analysis_frame = pd.DataFrame()
    solar_small_buffer_geojson: dict[str, Any] | None = None
    solar_large_polygon_geojson: dict[str, Any] | None = None

    if show_user_solar:
        perf_started = _perf_start()
        solar_unfiltered_land_active = bool(applied_solar_config.get("large_unfiltered_land_active", False))
        large_population_buffer_m = float(solar_params.get("population_buffer_m", 250.0) or 250.0) if solar_large_population_active else 0.0
        large_protected_buffer_m = float(solar_params.get("protected_buffer_m", 0.0) or 0.0) if solar_large_protected_layer_ids else None
        user_solar_frame = _solar_large_scale_frame(
            region,
            landscape_manifest,
            h3_resolution,
            large_population_buffer_m,
            large_protected_buffer_m,
            solar_large_protected_layer_ids,
            solar_unfiltered_land_active,
            solar_large_filter_configs,
        )
        user_solar_analysis_frame = (
            user_solar_frame.copy()
            if int(h3_resolution) == int(analysis_h3_resolution)
            else _solar_large_scale_frame(
                region,
                landscape_manifest,
                analysis_h3_resolution,
                large_population_buffer_m,
                large_protected_buffer_m,
                solar_large_protected_layer_ids,
                solar_unfiltered_land_active,
                solar_large_filter_configs,
            )
        )
        active_solar_filter_count = int(bool(solar_large_population_active)) + len(solar_large_filter_configs)
        if active_solar_filter_count > 0:
            solar_unfiltered_analysis_frame = _solar_large_scale_frame(
                region,
                landscape_manifest,
                analysis_h3_resolution,
                0.0,
                None,
                [],
                False,
                [],
            )
            unfiltered_solar_area_km2 = float(
                pd.to_numeric(
                    solar_unfiltered_analysis_frame.get("potential_area_km2", pd.Series(dtype=float)),
                    errors="coerce",
                ).fillna(0.0).sum()
            )
            filtered_solar_area_km2 = float(
                pd.to_numeric(
                    user_solar_analysis_frame.get("potential_area_km2", pd.Series(dtype=float)),
                    errors="coerce",
                ).fillna(0.0).sum()
            )
            removed_solar_area_km2 = max(0.0, unfiltered_solar_area_km2 - filtered_solar_area_km2)
            energy_model_state["solar_filter_impact"] = {
                "active_filter_count": active_solar_filter_count,
                "unfiltered_area_km2": unfiltered_solar_area_km2,
                "filtered_area_km2": filtered_solar_area_km2,
                "removed_area_km2": removed_solar_area_km2,
                "removed_share_pct": (
                    removed_solar_area_km2 / max(unfiltered_solar_area_km2, 1e-9) * 100.0
                    if unfiltered_solar_area_km2 > 0
                    else 0.0
                ),
            }
        solar_large_polygon_geojson = None
        if solar_large_population_active:
            if _solar_visual_enabled(applied_solar_config, "source", SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID):
                _append_unique_layer(layers, _layer_visible_by_default(_solar_population_source_layer()))
            if _solar_visual_enabled(applied_solar_config, "buffer", SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID):
                _append_unique_layer(
                    layers,
                    _layer_visible_by_default(_solar_population_buffer_layer(region, h3_resolution, large_population_buffer_m)),
                )
        for filter_config in solar_large_filter_configs:
            group_id = str(filter_config.get("group_id", ""))
            layer_ids = list(filter_config.get("layer_ids") or [])
            buffer_m = float(filter_config.get("buffer_m", 0.0) or 0.0)
            if _solar_visual_enabled(applied_solar_config, "source", group_id):
                for source_layer in _solar_filter_source_layers(group_id, layer_ids):
                    _append_unique_layer(layers, _layer_visible_by_default(source_layer))
            if _solar_visual_enabled(applied_solar_config, "buffer", group_id):
                _append_unique_layer(layers, _layer_visible_by_default(_solar_filter_buffer_layer(group_id, buffer_m, layer_ids)))
        if solar_unfiltered_land_active:
            unified_notes.append(
                f"Startläge: {SOLAR_LARGE_SCALE_LABEL} är ofiltrerad över kartans landskapsunderlag för att visa gemensam sol- och vindpotential."
            )
        else:
            unified_notes.append(
                f"{SOLAR_LARGE_SCALE_LABEL} använder hela landskapsunderlaget som kandidatbas. Aktiva filter drar bort yta från den basen."
            )
        if solar_large_population_active:
            unified_notes.append(
                f"Befolkningslagret tar bort potential inom {large_population_buffer_m:.0f} m från befolkningspunkter."
            )
        for filter_config in solar_large_filter_configs:
            group_id = str(filter_config.get("group_id", ""))
            spec = SOLAR_FILTER_GROUP_SPECS.get(group_id, {})
            label = str(spec.get("label", filter_config.get("label", group_id)))
            layer_labels = [str(value) for value in (filter_config.get("layer_labels") or [])]
            layer_text = f" ({', '.join(layer_labels[:3])}{'...' if len(layer_labels) > 3 else ''})" if layer_labels else ""
            if str(filter_config.get("effect", spec.get("effect", "exclusion"))) == "feasibility":
                unified_notes.append(
                    f"{label}{layer_text} begränsar solpotentialen till yta inom {float(filter_config.get('buffer_m', 0.0) or 0.0):.0f} m från nätobjekt."
                )
            else:
                unified_notes.append(
                    f"{label}{layer_text} drar av potential med {float(filter_config.get('buffer_m', 0.0) or 0.0):.0f} m buffert."
                )
        if solar_controls_applied:
            unified_notes.append(f"{SOLAR_LANDSCAPE_POTENTIAL_LABEL}: ändringar tillämpade.")
        _add_perf_timing(
            performance_log,
            "Sol storskalig",
            perf_started,
            f"visning R{h3_resolution}: {len(user_solar_frame)} hex; analys R{analysis_h3_resolution}: {len(user_solar_analysis_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Sol storskalig")

    if show_solar_v1:
        perf_started = _perf_start()
        solar_v1_frame = _solar_v1_frame(region, landscape_manifest, h3_resolution, solar_v1_area_m2_per_person)
        solar_v1_analysis_frame = (
            solar_v1_frame.copy()
            if int(h3_resolution) == int(analysis_h3_resolution)
            else _solar_v1_frame(region, landscape_manifest, analysis_h3_resolution, solar_v1_area_m2_per_person)
        )
        if solar_small_population_active:
            if _solar_visual_enabled(applied_solar_config, "buffer", SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID):
                solar_small_buffer_geojson = _solar_population_buffer_geojson(100.0)
            if _solar_visual_enabled(applied_solar_config, "source", SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID):
                _append_unique_layer(layers, _layer_visible_by_default(_solar_population_source_layer()))
            if _solar_visual_enabled(applied_solar_config, "buffer", SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID):
                _append_unique_layer(layers, _layer_visible_by_default(_solar_population_buffer_layer(region, h3_resolution, 100.0)))
        layers.extend(
            _hex_family_layers(
                region,
                h3_resolution,
                zoom_family_enabled,
                "solar_v1_schematic",
                f"{SOLAR_SMALL_SCALE_LABEL} (schablonhex)",
                lambda resolution: _solar_v1_layer(
                    f"{SOLAR_SMALL_SCALE_LABEL} (schablonhex)",
                    solar_v1_frame if int(resolution) == int(h3_resolution) else _solar_v1_frame(region, landscape_manifest, int(resolution), solar_v1_area_m2_per_person),
                    int(resolution),
                ),
            )
        )
        energy_model_state["solar_v1_stats"] = _solar_v1_stats(solar_v1_analysis_frame, energy_model_state)
        unified_notes.append(_solar_v1_formula_text(region, solar_v1_area_m2_per_person))
        unified_notes.append(
            f"{SOLAR_SMALL_SCALE_LABEL} visas som separata gula schablonhexar för att inte läsas som sammanhängande markyta."
        )
        unified_notes.append(_solar_v1_population_source_status(region))
        _add_perf_timing(
            performance_log,
            "Sol småskalig",
            perf_started,
            f"visning R{h3_resolution}: {len(solar_v1_frame)} hex; analys R{analysis_h3_resolution}: {len(solar_v1_analysis_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Sol småskalig")

    if show_solar_v1 or show_user_solar:
        perf_started = _perf_start()
        combined_solar_frame = _combined_solar_hex_frame(
            region,
            landscape_manifest,
            h3_resolution,
            solar_v1_frame if show_solar_v1 and solar_small_population_active else pd.DataFrame(),
            user_solar_frame if show_user_solar else pd.DataFrame(),
        )
        combined_solar_analysis_frame = (
            combined_solar_frame.copy()
            if int(h3_resolution) == int(analysis_h3_resolution)
            else _combined_solar_hex_frame(
                region,
                landscape_manifest,
                analysis_h3_resolution,
                solar_v1_analysis_frame if show_solar_v1 and solar_small_population_active else pd.DataFrame(),
                user_solar_analysis_frame if show_user_solar else pd.DataFrame(),
            )
        )
        solar_establishment_potential_frame = _solar_establishment_potential_source_frame(
            region,
            landscape_manifest,
            analysis_h3_resolution,
            user_solar_analysis_frame if show_user_solar else pd.DataFrame(),
        )
        _append_unique_layer(
            layers,
            _solar_potential_polygon_layer(
                solar_small_buffer_geojson
                if (
                    show_solar_v1
                    and solar_small_population_active
                    and _solar_visual_enabled(applied_solar_config, "buffer", SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID)
                )
                else None,
                user_solar_frame if show_user_solar else pd.DataFrame(),
                solar_large_polygon_geojson,
            ),
        )
        combined_solar_potential_frame = solar_establishment_potential_frame.copy()
        potential_frames.append(
            {
                "label": SOLAR_LANDSCAPE_POTENTIAL_LABEL,
                "technology": "solar",
                "frame": combined_solar_frame,
                "resolution": h3_resolution,
            }
        )
        if energy_model_state.get("available"):
            solar_proposal_frame, solar_proposal_stats = _solar_establishment_frame(
                region,
                solar_v1_analysis_frame if show_solar_v1 and solar_small_population_active else pd.DataFrame(),
                user_solar_analysis_frame if show_user_solar else pd.DataFrame(),
                float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0),
                float(energy_model_state.get("solar_twh", 0.0) or 0.0),
                float(energy_model_state.get("solar_km2_per_twh", math.nan) or math.nan),
                analysis_hex_area_km2,
                int(analysis_h3_resolution),
                social_manifest,
                social_acceptance_scenario,
                social_acceptance_allocation_priority_pct,
            )
            solar_expansion_source_frame = _apply_landscape_priority_to_allocation_frame(
                combined_solar_analysis_frame,
                region,
                "solar",
                analysis_h3_resolution,
            )
            solar_proposal_frame, solar_proposal_stats = _expand_solar_area_outside_lp(
                solar_expansion_source_frame,
                solar_proposal_frame,
                solar_proposal_stats,
                analysis_display_geometry_path,
                analysis_hex_area_km2,
                float(energy_model_state.get("solar_twh", 0.0) or 0.0),
                float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0),
                float(energy_model_state.get("solar_km2_per_twh", math.nan) or math.nan),
            )
            energy_model_state["solar_proposal_frame"] = solar_proposal_frame
            energy_model_state["solar_proposal_stats"] = solar_proposal_stats
            if not solar_proposal_frame.empty:
                unified_notes.append(
                    f"Solens scenarioyta använder en intern landskaps-/teknikranking inom etableringshex; placeringen visas med små child-hex."
                )
        _add_perf_timing(
            performance_log,
            "Sol samlad etablering",
            perf_started,
            f"visning R{h3_resolution}: {len(combined_solar_frame)} hex; analys R{analysis_h3_resolution}: {len(combined_solar_analysis_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Sol samlad etablering")

    custom_wind_preview_state: dict[str, Any] | None = None
    if show_user_wind:
        perf_started = _perf_start()
        custom_wind_preview_state = _wind_polygon_preview_state(
            region,
            wind_ui_params,
            wind_selected_layers,
            h3_resolution,
            zoom_family_enabled,
            family_key="user_wind_landscape_potential",
            control_name=WIND_POTENTIAL_HEX_LABEL,
            visual_options=wind_visual_options,
        )
        wind_preview_layers = _wind_preview_layers_for_map(
            region,
            energy_model_state,
            list(custom_wind_preview_state["layers"]),
        )
        layers.extend(wind_preview_layers)
        if custom_wind_preview_state["runtime_error"]:
            unified_notes.append(f"Vindruntime kunde inte köras: {custom_wind_preview_state['runtime_error']}")
        else:
            custom_wind_runtime_result = custom_wind_preview_state["runtime_result"]
            custom_wind_summary = _wind_polygon_summary_frame(
                region,
                landscape_manifest,
                custom_wind_runtime_result,
                h3_resolution,
            )
            custom_wind_analysis_runtime_result = custom_wind_runtime_result
            if int(h3_resolution) != int(analysis_h3_resolution) and bool(custom_wind_runtime_result.get("fast_distance")):
                analysis_runtime_result = _wind_fast_distance_runtime_result(
                    region,
                    wind_ui_params,
                    wind_selected_layers,
                    analysis_h3_resolution,
                )
                if analysis_runtime_result is not None:
                    custom_wind_analysis_runtime_result = analysis_runtime_result
            custom_wind_analysis_frame = (
                custom_wind_summary.copy()
                if int(h3_resolution) == int(analysis_h3_resolution)
                else _wind_polygon_summary_frame(
                    region,
                    landscape_manifest,
                    custom_wind_analysis_runtime_result,
                    analysis_h3_resolution,
                )
            )
            custom_wind_summary_frame = custom_wind_analysis_frame.copy()
            potential_frames.append(
                {
                    "label": WIND_LANDSCAPE_POTENTIAL_LABEL,
                    "technology": "wind",
                    "frame": custom_wind_summary,
                    "resolution": h3_resolution,
                }
            )
            if zoom_family_enabled:
                unified_notes.append(
                    f"{WIND_LANDSCAPE_POTENTIAL_LABEL} beräknas i R{analysis_h3_resolution}. Hexvisningen är zoomanpassad för granskning."
                )
            else:
                unified_notes.append(
                    f"{WIND_LANDSCAPE_POTENTIAL_LABEL} beräknas i R{analysis_h3_resolution}. Kartan visar vald H3-upplösning."
                )
            if str(region.get("region_id", "")).lower() == "trondelag" and energy_model_state.get("available"):
                unified_notes.append(
                    f"I Trøndelag visas vindberäkningen i första hand genom {COMBINED_ESTABLISHMENT_LAYER_LABEL}, inte som separat vind-hexlager."
                )
            unified_notes.append(
                "Vindens interna hexberäkning används för att prioritera kärnområden i den gemensamma etableringsytan."
            )
            if (
                energy_model_state.get("available")
                and energy_model_state.get("show_proposal")
                and energy_model_state.get("placement_mode") == "auto"
            ):
                wind_area_need = float(energy_model_state.get("wind_area_need_km2", 0.0) or 0.0)
                wind_twh_need = float(energy_model_state.get("wind_twh", 0.0) or 0.0)
                wind_factor = float(energy_model_state.get("wind_km2_per_twh", math.nan) or math.nan)
                solar_reserved_hex_ids = set()
                solar_reserved_frame = energy_model_state.get("solar_proposal_frame", pd.DataFrame())
                if isinstance(solar_reserved_frame, pd.DataFrame) and not solar_reserved_frame.empty and "hex_id" in solar_reserved_frame.columns:
                    solar_reserved_hex_ids = set(solar_reserved_frame["hex_id"].astype(str))
                wind_allocation_frame = _apply_landscape_priority_to_allocation_frame(
                    custom_wind_analysis_frame,
                    region,
                    "wind",
                    analysis_h3_resolution,
                )
                wind_allocation_frame = _apply_social_acceptance_priority_to_wind_allocation_frame(
                    wind_allocation_frame,
                    social_manifest,
                    social_acceptance_scenario,
                    analysis_h3_resolution,
                    social_acceptance_allocation_priority_pct,
                )
                proposal_frame, proposal_stats = allocate_wind_area_from_core_hexes(
                    wind_allocation_frame,
                    wind_area_need,
                    analysis_hex_area_km2,
                    float(energy_model_state.get("auto_min_potential_share_pct", 65.0) or 65.0),
                    avoid_hex_ids=solar_reserved_hex_ids,
                )
                proposal_frame, proposal_stats = _expand_wind_area_outside_et(
                    wind_allocation_frame,
                    proposal_frame,
                    proposal_stats,
                    analysis_display_geometry_path,
                    analysis_hex_area_km2,
                    avoid_hex_ids=solar_reserved_hex_ids,
                )
                if not proposal_frame.empty:
                    if wind_factor > 0 and math.isfinite(wind_factor):
                        proposal_frame["allocated_twh"] = proposal_frame["allocated_area_km2"].astype(float) / wind_factor
                    elif wind_area_need > 0:
                        proposal_frame["allocated_twh"] = wind_twh_need * proposal_frame["allocated_area_km2"].astype(float) / wind_area_need
                    else:
                        proposal_frame["allocated_twh"] = 0.0
                    proposal_frame["allocated_gwh"] = proposal_frame["allocated_twh"].astype(float) * 1000.0
                    proposal_frame["allocated_share_of_need_pct"] = (
                        proposal_frame["allocated_area_km2"].astype(float) / max(wind_area_need, 1e-9) * 100.0
                    )
                    proposal_stats["selected_twh"] = float(proposal_frame["allocated_twh"].sum())
                energy_model_state["proposal_frame"] = proposal_frame
                energy_model_state["proposal_stats"] = proposal_stats
                if not proposal_frame.empty:
                    unified_notes.append(
                        "Vindens scenarioyta använder en intern landskaps-/teknikranking inom etableringshex och väljer de starkaste vindlägena även när sol redan valt samma hex. Separata ytor vinner bara vid lika lämplighet."
                    )
                elif wind_area_need > 0:
                    unified_notes.append("Energimodelleringen hittade inga vindceller som uppfyller minsta kärn-/potentialkrav.")
        _add_perf_timing(
            performance_log,
            "Vindpotential och vindetablering",
            perf_started,
            f"visning R{h3_resolution}, analys R{analysis_h3_resolution}; {int(custom_wind_preview_state.get('active_source_count', 0) or 0)} källager",
        )
        _advance_calculation_progress(calc_progress, "Vindpotential och vindetablering")

    if (
        energy_model_state.get("available")
        and energy_model_state.get("show_proposal")
        and energy_model_state.get("placement_mode") == "auto"
    ):
        energy_model_state["establishment_layer_visible"] = False
        perf_started = _perf_start()
        selected_establishment_frame = _combined_establishment_frame(
            region,
            energy_model_state.get("proposal_frame", pd.DataFrame()),
            energy_model_state.get("solar_proposal_frame", pd.DataFrame()),
            analysis_h3_resolution,
            analysis_h3_resolution,
        )
        wind_stats_for_outside = energy_model_state.get("proposal_stats") if isinstance(energy_model_state.get("proposal_stats"), dict) else {}
        solar_stats_for_outside = energy_model_state.get("solar_proposal_stats") if isinstance(energy_model_state.get("solar_proposal_stats"), dict) else {}
        class_counts = selected_establishment_frame.get("establishment_class", pd.Series(dtype=str)).astype(str).value_counts()
        potential_establishment_frame = _combined_potential_establishment_frame(
            region,
            custom_wind_summary_frame,
            combined_solar_potential_frame,
            energy_model_state.get("proposal_frame", pd.DataFrame()),
            energy_model_state.get("solar_proposal_frame", pd.DataFrame()),
            analysis_h3_resolution,
            analysis_h3_resolution,
        )
        if not potential_establishment_frame.empty:
            class_counts = potential_establishment_frame.get("establishment_class", pd.Series(dtype=str)).astype(str).value_counts()
        energy_model_state["social_acceptance_summary"] = _social_acceptance_establishment_summary(
            potential_establishment_frame if not potential_establishment_frame.empty else selected_establishment_frame,
            social_manifest,
            social_acceptance_scenario,
            analysis_h3_resolution,
            analysis_hex_area_km2,
            social_acceptance_impact_pct,
        )
        energy_model_state["acceptance_adjusted_capacity"] = _acceptance_adjusted_capacity_metrics(
            float(energy_model_state.get("wind_area_need_km2", 0.0) or 0.0),
            float(wind_stats_for_outside.get("available_candidate_area_km2", 0.0) or 0.0),
            float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0),
            float(solar_stats_for_outside.get("available_candidate_area_km2", 0.0) or 0.0),
            energy_model_state.get("social_acceptance_summary") if isinstance(energy_model_state.get("social_acceptance_summary"), dict) else {},
        )
        adjusted_capacity = energy_model_state["acceptance_adjusted_capacity"]
        adjusted_wind = adjusted_capacity.get("wind", {}) if isinstance(adjusted_capacity.get("wind"), dict) else {}
        adjusted_solar = adjusted_capacity.get("solar", {}) if isinstance(adjusted_capacity.get("solar"), dict) else {}
        wind_outside_need_area = float(adjusted_wind.get("outside_need_km2", 0.0) or 0.0)
        solar_outside_need_area = float(adjusted_solar.get("outside_need_km2", 0.0) or 0.0)
        energy_model_state["outside_lp_shortage_stats"] = _outside_need_stats_from_areas(
            wind_outside_need_area,
            solar_outside_need_area,
            analysis_hex_area_km2,
        )
        energy_model_state["establishment_hex_stats"] = {
            "total_hex_count": int(len(selected_establishment_frame)),
            "black_hex_count": int(energy_model_state["outside_lp_shortage_stats"].get("total_shortage_hex_count", 0) or 0),
            "red_hex_count": int(class_counts.get("not_suitable", 0)),
            "wind_and_solar_hex_count": int(class_counts.get("wind_and_solar", 0)),
            "wind_only_hex_count": int(class_counts.get("wind_only", 0)),
            "solar_only_hex_count": int(class_counts.get("solar_only", 0)),
            "hex_area_km2": float(analysis_hex_area_km2),
            "h3_resolution": int(analysis_h3_resolution),
            "display_h3_resolution": int(h3_resolution),
        }
        combined_establishment_layers = _combined_potential_establishment_family_layers(
            region,
            custom_wind_summary_frame,
            combined_solar_potential_frame,
            energy_model_state.get("proposal_frame", pd.DataFrame()),
            energy_model_state.get("solar_proposal_frame", pd.DataFrame()),
            h3_resolution,
            zoom_family_enabled,
            analysis_h3_resolution,
            social_acceptance_manifest=social_manifest,
            social_acceptance_scenario=social_acceptance_scenario,
            social_acceptance_impact_pct=social_acceptance_impact_pct,
        )
        if combined_establishment_layers:
            energy_model_state["establishment_layer_visible"] = True
            layers.extend(combined_establishment_layers)
            unified_notes.append(
                f"{COMBINED_ESTABLISHMENT_LAYER_LABEL} visar potential efter aktiva filter: blå = vind, gul = sol, grön = båda, röd = inte lämplig."
            )
            if social_manifest is not None and float(social_acceptance_impact_pct or 0.0) > 0.0:
                unified_notes.append(
                    f"Acceptanspåverkan {float(social_acceptance_impact_pct):.0f}% tonar samma etableringsyta mot rött där syntetisk social acceptans är låg."
                )
            if social_manifest is not None and float(social_acceptance_allocation_priority_pct or 0.0) > 0.0:
                unified_notes.append(
                    f"Acceptansstyrning {float(social_acceptance_allocation_priority_pct):.0f}% prioriterar scenariohexar med hög syntetisk social acceptans."
                )
        allocation_marker_layers = _scenario_allocation_marker_family_layers(
            region,
            energy_model_state.get("proposal_frame", pd.DataFrame()),
            energy_model_state.get("solar_proposal_frame", pd.DataFrame()),
            h3_resolution,
            zoom_family_enabled,
            analysis_h3_resolution,
        )
        if allocation_marker_layers:
            layers.extend(allocation_marker_layers)
            if str(region.get("region_id", "")).lower() == "trondelag":
                unified_notes.append(
                    f"{SCENARIO_ALLOCATION_LAYER_LABEL} finns i lagerkontrollen men är släckt från start för snabbare Trøndelag-visning."
                )
            else:
                unified_notes.append(
                    f"{SCENARIO_ALLOCATION_LAYER_LABEL} visar scenariots placering som teknikfärgade child-hex. Blå markerar vind, gul markerar sol och grön markerar verkligt överlapp i samma scenariohex."
                )
        outside_lp_need_layers = _outside_lp_need_family_layers(
            region,
            energy_model_state.get("proposal_frame", pd.DataFrame()),
            energy_model_state.get("solar_proposal_frame", pd.DataFrame()),
            h3_resolution,
            zoom_family_enabled,
            analysis_h3_resolution,
            wind_outside_need_area,
            solar_outside_need_area,
        )
        if outside_lp_need_layers:
            layers.extend(outside_lp_need_layers)
            unified_notes.append(
                f"{OUTSIDE_LP_NEED_LAYER_LABEL} visas som separata schematiska fält ute till havs när scenariot inte ryms inom landskapets potential."
            )
        _add_perf_timing(
            performance_log,
            "Gemensam etableringsyta",
            perf_started,
            f"visning R{h3_resolution}; analys R{analysis_h3_resolution}: {len(selected_establishment_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Gemensam etableringsyta")

    if energy_model_state.get("available") and energy_model_state.get("establishment_layer_visible"):
        perf_started = _perf_start()
        energy_model_state["combined_establishment_stats"] = _combined_establishment_stats(energy_model_state)
        _add_perf_timing(performance_log, "Etableringsstatistik", perf_started)
        _advance_calculation_progress(calc_progress, "Etableringsstatistik")

    if show_v10 or show_pdf_types or show_cluster or show_factor:
        perf_started = _perf_start()
        landscape_frame = _landscape_frame(region, landscape_manifest, h3_resolution)
        if show_v10:
            layers.extend(
                _hex_family_layers(
                    region,
                    h3_resolution,
                    zoom_family_enabled,
                    "landscape_types_hex",
                    "Landskapstyper",
                    lambda resolution: _landscape_type_layer(
                        "Landskapstyper",
                        _landscape_frame(region, landscape_manifest, int(resolution)),
                        landscape_manifest,
                        _h3_display_geometry_path(region, int(resolution)),
                    ),
                )
            )
        if show_pdf_types:
            pdf_manifest = _pdf_landscape_manifest(landscape_manifest)
            if pdf_manifest is not None:
                layers.extend(
                    _hex_family_layers(
                    region,
                    h3_resolution,
                    zoom_family_enabled,
                    "landscape_pdf_types_hex",
                    _t("Landskapstyper"),
                    lambda resolution: _landscape_type_layer(
                        _t("Landskapstyper"),
                        _unclipped_landscape_frame(pdf_manifest, int(resolution)),
                        pdf_manifest,
                        _landscape_display_geometry_path_for_manifest(region, pdf_manifest, int(resolution)),
                        ),
                    )
                )
        _add_perf_timing(performance_log, "Landskapslager", perf_started, f"R{h3_resolution}; {len(landscape_frame)} hex")
        _advance_calculation_progress(calc_progress, "Landskapslager")
        if show_cluster:
            layers.extend(
                _hex_family_layers(
                    region,
                    h3_resolution,
                    zoom_family_enabled,
                    "landscape_structures_hex",
                    "Landskapstrukturer",
                    lambda resolution: _landscape_layer(
                        "Landskapstrukturer",
                        _landscape_frame(region, landscape_manifest, int(resolution)),
                        landscape_manifest,
                        factors[0],
                        _h3_display_geometry_path(region, int(resolution)),
                        "cluster",
                    ),
                )
            )
        if show_factor:
            layers.extend(
                _hex_family_layers(
                    region,
                    h3_resolution,
                    zoom_family_enabled,
                    f"landscape_factor_{selected_factor}",
                    "Landskapsfaktorer",
                    lambda resolution: _landscape_layer(
                        "Landskapsfaktorer",
                        _landscape_frame(region, landscape_manifest, int(resolution)),
                        landscape_manifest,
                        selected_factor,
                        _h3_display_geometry_path(region, int(resolution)),
                        "factor",
                    ),
                )
            )

    if show_social_acceptance and social_manifest is not None:
        perf_started = _perf_start()
        social_label = social_acceptance_scenario_label(social_manifest, social_acceptance_scenario)
        layers.extend(
            _hex_family_layers(
                region,
                h3_resolution,
                zoom_family_enabled,
                "synthetic_social_acceptance_hex",
                f"Social acceptans: {social_label}",
                lambda resolution: social_acceptance_layer(
                    social_manifest,
                    social_acceptance_scenario,
                    int(resolution),
                    _h3_display_geometry_path(region, int(resolution)),
                ),
            )
        )
        unified_notes.append("Social acceptans är syntetiskt testdata på hexnivå och ska inte tolkas som IVL-resultat.")
        _add_perf_timing(
            performance_log,
            "Social acceptans",
            perf_started,
            f"visning R{h3_resolution}; {social_acceptance_scenario}",
        )
        _advance_calculation_progress(calc_progress, "Social acceptans")

    layers = _dedupe_layers(layers)
    if isinstance(energy_model_state, dict) and energy_model_state.get("available"):
        energy_model_state["map_layer_debug_rows"] = _map_layer_debug_rows(layers)
        energy_model_state["debug_layer_count"] = int(len(layers))
        energy_model_state["debug_counts"] = {
            "wind_proposal_hex": int(len(energy_model_state.get("proposal_frame", pd.DataFrame()))),
            "solar_proposal_hex": int(len(energy_model_state.get("solar_proposal_frame", pd.DataFrame()))),
            "solar_schematic_hex": int(len(solar_v1_analysis_frame)) if show_solar_v1 else 0,
            "solar_schematic_features": _feature_count(
                _solar_v1_layer(
                    f"{SOLAR_SMALL_SCALE_LABEL} (schablonhex)",
                    solar_v1_frame if show_solar_v1 else pd.DataFrame(),
                    h3_resolution,
                ).get("feature_collection")
            )
            if show_solar_v1
            else 0,
        }
    layer_control_count = len(_layer_control_rows(layers, "combined"))
    note_body = (
        "Kartan visar möjlig etableringsyta och scenariofördelning utifrån nuvarande val."
        if layer_control_count
        else "Kartan uppdateras när minst ett potentiallager är aktivt."
    )
    proposal_stats_for_note = energy_model_state.get("proposal_stats") if isinstance(energy_model_state, dict) else None
    solar_stats_for_note = energy_model_state.get("solar_proposal_stats") if isinstance(energy_model_state, dict) else None
    outside_parts: list[str] = []
    wind_outside_for_note = 0.0
    solar_outside_for_note = 0.0
    adjusted_capacity_for_note = (
        energy_model_state.get("acceptance_adjusted_capacity")
        if isinstance(energy_model_state.get("acceptance_adjusted_capacity"), dict)
        else {}
    )
    adjusted_wind_for_note = adjusted_capacity_for_note.get("wind", {}) if isinstance(adjusted_capacity_for_note.get("wind"), dict) else {}
    adjusted_solar_for_note = adjusted_capacity_for_note.get("solar", {}) if isinstance(adjusted_capacity_for_note.get("solar"), dict) else {}
    if adjusted_wind_for_note:
        wind_outside_for_note = float(adjusted_wind_for_note.get("outside_need_km2", 0.0) or 0.0)
    elif isinstance(proposal_stats_for_note, dict):
        wind_outside_for_note = max(
            0.0,
            float(energy_model_state.get("wind_area_need_km2", 0.0) or 0.0)
            - _lp_selected_area_from_stats(proposal_stats_for_note),
        )
    if adjusted_solar_for_note:
        solar_outside_for_note = float(adjusted_solar_for_note.get("outside_need_km2", 0.0) or 0.0)
    elif isinstance(solar_stats_for_note, dict):
        solar_outside_for_note = max(
            0.0,
            float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0)
            - _lp_selected_area_from_stats(solar_stats_for_note),
        )
    if wind_outside_for_note > 1e-6:
        outside_parts.append(f"vind {wind_outside_for_note:.0f} km²")
    if solar_outside_for_note > 1e-6:
        outside_parts.append(f"sol {solar_outside_for_note:.0f} km²")
    if outside_parts:
        outside_total_for_note = wind_outside_for_note + solar_outside_for_note
        note_body = (
            "<strong style='color:#be123c;'>Varning:</strong> "
            f"Vald energimix ryms inte helt: ytbehov utanför potential ca {outside_total_for_note:.0f} km² "
            f"({', '.join(outside_parts)})."
        )
    perf_started = _perf_start()
    _render_layers(
        region,
        layers,
        opacity,
        map_state_key=f"{region.get('region_id', 'region')}:workspace:{MAP_STATE_VERSION}" if preserve_map_view else None,
        map_reset_token=map_reset_token,
        opacity_key_prefix="combined",
        note_title="Gemensam potentialvy",
        note_body=note_body,
        after_map_renderer=lambda: _render_energy_mix_card(st, region, energy_model_state),
    )
    _add_perf_timing(performance_log, "Karta HTML och rendering", perf_started, f"{len(layers)} lager")
    _advance_calculation_progress(calc_progress, "Karta HTML och rendering")
    _finish_calculation_progress(calc_progress, performance_log)
    _record_performance_history(performance_bucket, performance_log)
    energy_model_state["performance_diagnostics"] = _performance_diagnostic_rows(performance_log, performance_estimates)
    geography_filter_notes = _geography_filter_notes(
        show_user_wind=bool(show_user_wind),
        wind_selected_layers=wind_selected_layers,
        wind_ui_params=wind_ui_params,
        wind_unfiltered_land=bool(custom_wind_preview_state.get("unfiltered_land", False)) if isinstance(custom_wind_preview_state, dict) else False,
        show_user_solar=bool(show_user_solar),
        show_solar_v1=bool(show_solar_v1),
        solar_large_population_active=bool(solar_large_population_active),
        solar_large_unfiltered_land_active=bool(applied_solar_config.get("large_unfiltered_land_active", False)),
        solar_params=solar_params,
        solar_large_filter_configs=solar_large_filter_configs,
        solar_v1_area_m2_per_person=float(solar_v1_area_m2_per_person or 0.0),
    )
    geography_effect_notes = _geography_effect_notes(energy_model_state)
    st.session_state[WORKSPACE_RENDER_CACHE_KEY] = {
        "fingerprint": workspace_fingerprint,
        "layers": layers,
        "note_body": note_body,
        "performance_log": performance_log,
        "energy_model_state": energy_model_state,
        "map_state": {
            "layers": layers,
            "potential_frames": potential_frames,
            "landscape_manifest": landscape_manifest,
            "landscape_factors": factors,
            "resolution": h3_resolution,
            "analysis_resolution": analysis_h3_resolution,
            "resolution_info": resolution_info,
            "landscape_active": bool(show_v10 or show_cluster or show_factor),
            "opacity_key_prefix": "combined",
            "geography_filter_notes": geography_filter_notes,
            "geography_effect_notes": geography_effect_notes,
            "establishment_hex_stats": energy_model_state.get("establishment_hex_stats"),
        },
    }

    summary_target = right_panel or st.container()
    with summary_target:
        st.markdown('<span data-potential-tutorial-anchor="right-panel"></span>', unsafe_allow_html=True)
        _render_establishment_focus(
            energy_model_state,
            lambda: _combined_summary(
                {
                    "layers": layers,
                    "potential_frames": potential_frames,
                    "landscape_manifest": landscape_manifest,
                    "landscape_factors": factors,
                    "resolution": h3_resolution,
                    "analysis_resolution": analysis_h3_resolution,
                    "resolution_info": resolution_info,
                    "landscape_active": bool(show_v10 or show_cluster or show_factor),
                    "opacity_key_prefix": "combined",
                    "geography_filter_notes": geography_filter_notes,
                    "geography_effect_notes": geography_effect_notes,
                    "establishment_hex_stats": energy_model_state.get("establishment_hex_stats"),
                },
                scenario_state,
            ),
        )
        _data_method(region)
        with st.expander(_t("Debug och prestanda"), expanded=False):
            _render_performance_log(performance_log)
            st.markdown(f"**{_t('Aktiva beräkningar')}**")
            performance_diagnostics = energy_model_state.get("performance_diagnostics") if isinstance(energy_model_state, dict) else None
            if isinstance(performance_diagnostics, list) and performance_diagnostics:
                diagnostic_frame = pd.DataFrame(performance_diagnostics)
                st.caption(
                    "Prestandadiagnostik för optimering. Faktisk tid visas per steg och jämförs med historisk median när appen har hunnit samla körhistorik."
                )
                st.dataframe(
                    diagnostic_frame.head(8),
                    width="stretch",
                    hide_index=True,
                    height=min(344, 72 + 32 * min(8, len(diagnostic_frame))),
                )
                slowest_step = performance_diagnostics[0]
                st.caption(
                    f"Långsammaste steg denna körning: {slowest_step.get('steg', '-')} "
                    f"({float(slowest_step.get('tid_s', 0.0) or 0.0):.1f} s)."
                )
            if isinstance(energy_model_state, dict) and energy_model_state.get("available"):
                st.caption(
                    f"Senaste energiberäkning: {energy_model_state.get('debug_run_id', '-')} · "
                    f"scenario {energy_model_state.get('scenario', '-')} · "
                    f"mix {float(energy_model_state.get('wind_share_pct', 0.0) or 0.0):.0f}% vind / "
                    f"{float(energy_model_state.get('solar_share_pct', 0.0) or 0.0):.0f}% sol."
                )
                debug_counts = energy_model_state.get("debug_counts")
                if isinstance(debug_counts, dict):
                    count_rows = [
                        {"mått": "vindförslag hex", "antal": int(debug_counts.get("wind_proposal_hex", 0) or 0)},
                        {"mått": "solförslag hex", "antal": int(debug_counts.get("solar_proposal_hex", 0) or 0)},
                        {"mått": "småskalig schablon rader", "antal": int(debug_counts.get("solar_schematic_hex", 0) or 0)},
                        {"mått": "småskalig schablon features i karta", "antal": int(debug_counts.get("solar_schematic_features", 0) or 0)},
                    ]
                    st.dataframe(pd.DataFrame(count_rows), width="stretch", hide_index=True, height=176)
                layer_debug_rows = energy_model_state.get("map_layer_debug_rows")
                if isinstance(layer_debug_rows, list) and layer_debug_rows:
                    debug_frame = pd.DataFrame(layer_debug_rows)
                    st.caption("Kartlager i senaste HTML-renderingen.")
                    st.dataframe(debug_frame, width="stretch", hide_index=True, height=min(360, 72 + 32 * len(debug_frame)))
            if show_user_solar:
                st.metric(f"Aktiv {_t(SOLAR_LARGE_SCALE_LABEL)}", _t("På"))
                st.caption(f"{_t(SOLAR_LARGE_SCALE_LABEL)} visas som solpolygon och kan ingå i {_t(COMBINED_ESTABLISHMENT_LAYER_LABEL)}.")
            if show_solar_v1:
                stats = energy_model_state.get("solar_v1_stats") if isinstance(energy_model_state, dict) else None
                st.metric(f"Aktiv {_t(SOLAR_SMALL_SCALE_LABEL)}", _t("På"))
                st.caption(_solar_v1_formula_text(region, solar_v1_area_m2_per_person))
                st.caption(_solar_v1_population_source_status(region))
                if isinstance(stats, dict):
                    st.caption(
                        f"Total småskalig solyta: {float(stats.get('total_area_km2', 0.0) or 0.0):.2f} km²; "
                        f"solbehov efter tak: {float(stats.get('remaining_area_km2', 0.0) or 0.0):.2f} km²."
                    )
            if show_user_solar:
                if solar_large_population_active:
                    st.caption(
                        f"Avstånd till befolkning är {float(solar_params.get('population_buffer_m', 250.0) or 250.0):.0f} m för storskalig sol."
                    )
                for filter_config in solar_large_filter_configs:
                    group_id = str(filter_config.get("group_id", ""))
                    label = str(SOLAR_FILTER_GROUP_SPECS.get(group_id, {}).get("label", filter_config.get("label", group_id)))
                    layer_count = len(list(filter_config.get("layer_ids") or []))
                    layer_labels = [str(value) for value in (filter_config.get("layer_labels") or [])]
                    layer_text = f": {', '.join(layer_labels[:4])}{'...' if len(layer_labels) > 4 else ''}" if layer_labels else ""
                    st.caption(
                        f"{label}: {layer_count} del-lager är aktiva med {float(filter_config.get('buffer_m', 0.0) or 0.0):.0f} m buffert{layer_text}."
                    )
            if show_user_wind and custom_wind_preview_state is not None:
                left_metric, right_metric = st.columns(2)
                left_metric.metric("Vind: aktiva källager", int(custom_wind_preview_state["active_source_count"]))
                right_metric.metric("Vind: buffertgrupper", int(custom_wind_preview_state["active_group_count"]))
                combined_share = custom_wind_preview_state["combined_land_share_pct"]
                st.metric("Vind: potentiell landandel", "-" if combined_share is None else f"{float(combined_share):.1f}%")
                if wind_controls_applied:
                    st.caption(ui_text("controls_applied", WIND_CONTROL_LANGUAGE))
            for note in unified_notes:
                st.caption(note)


def main() -> None:
    st.session_state.setdefault(APP_LANGUAGE_KEY, "sv")
    st.set_page_config(page_title=f"{_t(PAGE_TITLE)} · {APP_RELEASE_STAGE}", layout="wide", initial_sidebar_state="expanded")
    if _should_show_region_landing():
        _render_region_landing()
        return

    region = _active_region()
    scenario_state = _scenario_state(region, None)
    context = _load_context(region)
    left_panel, main_panel, right_panel = _workspace_shell()

    default_display_resolution = int(region.get("default_display_h3_resolution") or region.get("default_h3_resolution") or 8)
    h3_resolution = _session_h3_resolution(region, "combined_h3_resolution", default_display_resolution)
    with main_panel:
        _workspace_header(region, scenario_state, h3_resolution)
        _unified_workspace_tab(region, scenario_state, context, left_panel, right_panel)
    _render_region_switcher(region)
    force_tutorial_open = _render_tutorial_launcher(region, st.sidebar)
    _render_language_switcher(st.sidebar)
    _render_tutorial_component(region, force_open=force_tutorial_open)


if __name__ == "__main__":
    main()
