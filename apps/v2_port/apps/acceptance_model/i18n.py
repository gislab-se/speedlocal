from __future__ import annotations

from typing import Any

LANGUAGE_LABELS = {
    "sv": "Svenska",
    "en": "English",
}

TEXTS = {
    "sv": {
        "app_title": "Vindacceptans Bornholm",
        "app_caption": "Geometriförst-prototyp. Kartan använder nu verkliga buffrade och upplösta källgeometrier i stället för hexagoner.",
        "language_toggle": "Språk / Language",
        "groups_header": "Grupper",
        "groups_caption": "Välj källager per grupp. Grupplagren är upplösta buffertar i verklig geometri, inte hexagonceller.",
        "apply_hint": "Kartan uppdateras när du klickar på Använd ändringar. Det gör att geometrimotorn inte kör om för varje sliderrörelse.",
        "analysis_slider_help": "Analysvärde. Det här ändrar den verkliga buffert- eller genomförbarhetsgeometrin.",
        "display_blend": "Visa / blanda",
        "display_blend_help": "Visning endast. 0 = källager, 100 = grupplager.",
        "group_inactive": "Gruppen är inaktiv. Välj ett eller flera källager ovan.",
        "apply_changes": "Använd ändringar",
        "geometry_runtime_failed": "Geometrikörningen misslyckades",
        "updating_geometry": "Uppdaterar geometri...",
        "tab_prototype": "Prototyp",
        "tab_review": "Modellgranskning",
        "tab_data": "Datastatus",
        "metric_selectable_source_layers": "Valbara källager",
        "metric_active_source_layers": "Aktiva källager",
        "metric_active_groups": "Aktiva grupper",
        "metric_combined_acceptance": "Kombinerad acceptans",
        "off": "Av",
        "controls_applied": "Uppdaterad med de senaste valda lagren och slidervärdena.",
        "group_summary": "Gruppsammanfattning",
        "map_panel_caption": "Grupplagren är verkliga upplösta buffertar eller genomförbarhetsytor byggda från valda källager. Det kombinerade lagret visar alltid kvarvarande möjlig mark efter att de aktiva reglerna har tillämpats, och det är det enda overlaylagret som är på som standard.",
        "map_reading_guide": "Kartguide",
        "map_guide_source": "Källager är verkliga källgeometrier. Befolkningspunkter visas som en upplöst visningsbuffert på 100 m.",
        "map_guide_group": "Grupplager är upplösta analysbuffertar eller genomförbarhetsytor byggda från valda källager. Elgruppen visar marken som ligger inom valt maximalt anslutningsavstånd.",
        "map_guide_combined": "Det kombinerade lagret visar alltid kvarvarande acceptansyta inom Bornholm efter att aktiva gruppregler tillämpats.",
        "map_guide_default": "Det kombinerade acceptanslagret är på som standard. Källager och grupplager finns fortfarande i kartkontrollen men startar dolda.",
        "map_guide_v4": "Fem valbara V4-referenslager finns också i kartkontrollen: hög, mellan, låg, mellanscore och landskapskluster. Kartan har även egen V4-opacitet och legend.",
        "map_guide_basemap": "Bakgrundskartan växlas i kartkontrollen: OSM eller Satellit.",
        "runtime_cache_key": "Runtime-cache-nyckel",
        "critical_review": "Kritisk genomgång",
        "hexagon_note": "Hexagonsnot",
        "layer_asset_status": "Status för lagerassets",
        "data_status_caption": "Statisk GeoJSON för källager och beredskap exporteras av `script/acceptance/export_wind_acceptance_prototype_assets.R`. Dynamiska grupplager renderas av `script/acceptance/render_wind_acceptance_geometry_runtime.R`.",
        "data_status_warning": "Vissa källager är inte klara. Inaktiverade kryssrutor i sidpanelen kommer från den här tabellen.",
        "data_status_success": "Alla källager som krävs för den nuvarande prototypen är tillgängliga.",
        "summary_group": "Grupp",
        "summary_type": "Typ",
        "summary_active": "Aktiv",
        "summary_sources": "Källor",
        "summary_analysis_m": "Analys (m)",
        "summary_blend": "Blandning",
        "summary_land_share": "Landandel",
        "summary_role": "Roll",
        "none": "Inga",
        "role_conflict": "Konflikt",
        "role_feasible": "Genomförbar",
        "hex": "Hex",
        "high_acceptance": "Hög acceptans",
        "medium_acceptance": "Mellan acceptans",
        "low_acceptance": "Låg acceptans",
        "settlement_distance": "Bostäder / fastboende",
        "large_road_distance": "Stora vägar",
        "medium_road_distance": "Mellanvägar",
        "nearest_electrical": "Närmaste elinfrastruktur",
        "landscape_cluster": "Landskapskluster",
        "source_prefix": "Källa",
        "group_prefix": "Grupp",
        "combined_overlay_name": "Kombinerad: acceptans",
        "v4_opacity": "V4-opacitet",
        "v4_legend": "V4-legend",
        "scenario_class": "Scenarioklass",
        "medium_scenario_score": "Mellan scenarioscore",
        "v4_cluster_legend": "V4-klusterlegend",
        "basemap_osm": "OSM",
        "basemap_satellite": "Satellit",
        "critical_review_items": [
            "Det här skedet bör vara geometriförst. Bebyggelse, vägar, stationer och skyddade områden betyder något som verkliga källgeometrier, så livekartan bör visa och buffra just dessa geometrier i stället för att för tidigt kollapsa dem till hex.",
            "Bebyggelseproxyer överlappar fortfarande kraftigt, så grupp-logiken bör använda upplösta unioner och delade buffertar i stället för additiv poängsättning. Det minskar dubbelräkning av samma byggda struktur.",
            "Elinfrastruktur behöver fortsatt annan semantik: buffring av valda nätobjekt med ett maximalt anslutningsavstånd är en genomförbarhetsregel, inte en klassisk no-go-buffert.",
            "Befolkningspunkter blir visuellt brusiga som råa punkter i den här skalan, så prototypen visar dem som en upplöst 100 m-buffertpolygon.",
            "Alla källager, grupplager och kombinerade geometrier klipps mot en landmask för Bornholm, så buffertar inte spiller ut i havet.",
            "Kombinerad acceptans ska alltid visas som den mark som återstår inom polygonen. Utan genomförbarhetsgrupp betyder det Bornholms landmassa minus aktiva konfliktlager. Med genomförbarhetsgrupp betyder det genomförbar mark minus aktiva konflikter.",
        ],
        "hexagon_note_items": [
            "Hexagoner används inte längre i livekartan i den här prototypen.",
            "De är fortfarande användbara senare för rapportering, rangordning, jämförelse mot landskapskluster eller summering av hur mycket mark som återstår efter geometriförst-filtrering.",
            "Om ni vill tillbaka till ett hexlager senare bör det komma efter geometribaserade buffertar och snitt, inte före.",
        ],
    },
    "en": {
        "app_title": "Bornholm Wind-Acceptance Prototype",
        "app_caption": "Geometry-first prototype. The live map now uses real buffered and dissolved source geometries instead of hexagons.",
        "language_toggle": "Language / Språk",
        "groups_header": "Groups",
        "groups_caption": "Select source layers per group. Group polygons are dissolved real-geometry buffers, not hex cells.",
        "apply_hint": "The map updates when you click Apply changes. This avoids rerunning the geometry engine on every slider move.",
        "analysis_slider_help": "Analysis only. This value changes the real buffer or feasibility geometry.",
        "display_blend": "Display / blend",
        "display_blend_help": "Display only. 0 = source layers, 100 = group layer.",
        "group_inactive": "Group inactive. Select one or more source layers above.",
        "apply_changes": "Apply changes",
        "geometry_runtime_failed": "Geometry runtime failed",
        "updating_geometry": "Updating geometry...",
        "tab_prototype": "Prototype",
        "tab_review": "Model review",
        "tab_data": "Data status",
        "metric_selectable_source_layers": "Selectable source layers",
        "metric_active_source_layers": "Active source layers",
        "metric_active_groups": "Active groups",
        "metric_combined_acceptance": "Combined acceptance",
        "off": "Off",
        "controls_applied": "Updated with the latest selected layers and slider values.",
        "group_summary": "Group summary",
        "map_panel_caption": "Group polygons are real dissolved buffers or feasibility areas derived from the selected source layers. The combined layer always shows accepted land that remains after the active rules are applied, and it is the only overlay shown by default.",
        "map_reading_guide": "Map reading guide",
        "map_guide_source": "Source layers are real source geometries. Population points are shown as a dissolved 100 m display buffer.",
        "map_guide_group": "Group layers are dissolved analysis buffers or feasibility polygons built from the selected source layers. Electrical shows the land area that remains within the selected maximum connection distance.",
        "map_guide_combined": "The combined layer always shows accepted land that remains inside Bornholm after the active group rules are applied.",
        "map_guide_default": "The combined acceptance layer is turned on by default. Source and group layers are still available in the map control, but start hidden.",
        "map_guide_v4": "Five optional V4 reference layers are also available in the map control: high, medium, low, medium score, and landscape clusters. The map now includes a separate V4 opacity slider and legend.",
        "map_guide_basemap": "The basemap toggle is inside the map control: OSM or Satellite.",
        "runtime_cache_key": "Runtime cache key",
        "critical_review": "Critical review",
        "hexagon_note": "Hexagon note",
        "layer_asset_status": "Layer asset status",
        "data_status_caption": "Static source GeoJSON and readiness are exported by `script/acceptance/export_wind_acceptance_prototype_assets.R`. Dynamic group polygons are rendered by `script/acceptance/render_wind_acceptance_geometry_runtime.R`.",
        "data_status_warning": "Some source assets are not ready. Disabled checkboxes in the sidebar come from this table.",
        "data_status_success": "All source assets required by the current prototype are available.",
        "summary_group": "Group",
        "summary_type": "Type",
        "summary_active": "Active",
        "summary_sources": "Sources",
        "summary_analysis_m": "Analysis (m)",
        "summary_blend": "Blend",
        "summary_land_share": "Land share",
        "summary_role": "Role",
        "none": "None",
        "role_conflict": "Conflict",
        "role_feasible": "Feasible",
        "hex": "Hex",
        "high_acceptance": "High acceptance",
        "medium_acceptance": "Medium acceptance",
        "low_acceptance": "Low acceptance",
        "settlement_distance": "Settlement / residents",
        "large_road_distance": "Large roads",
        "medium_road_distance": "Medium roads",
        "nearest_electrical": "Nearest electrical infrastructure",
        "landscape_cluster": "Landscape cluster",
        "source_prefix": "Source",
        "group_prefix": "Group",
        "combined_overlay_name": "Combined: acceptance",
        "v4_opacity": "V4 opacity",
        "v4_legend": "V4 legend",
        "scenario_class": "Scenario class",
        "medium_scenario_score": "Medium scenario score",
        "v4_cluster_legend": "V4 cluster legend",
        "basemap_osm": "OSM",
        "basemap_satellite": "Satellite",
        "critical_review_items": [
            "This stage should stay geometry-first. Settlement, roads, substations, and protected areas mean something as real source geometries, so the live map should show and buffer those geometries directly instead of collapsing them to hexes too early.",
            "Settlement proxies still overlap heavily, so group logic should use dissolved unions and shared buffers rather than additive scoring. That avoids counting the same built structure multiple times.",
            "Electrical infrastructure still needs different semantics: buffering selected grid assets by a maximum connection distance is a feasibility rule, not a classic no-go buffer.",
            "Population points are visually noisy as raw points at this scale, so the prototype now displays them as a dissolved 100 m buffer polygon.",
            "All source, group, and combined geometries are clipped to a Bornholm landmask so buffers do not spill into the sea.",
            "Combined acceptance should always be shown as the land that remains available inside a polygon. Without a feasibility group, that means Bornholm landmass minus the active conflict layers. With a feasibility group, it means feasible land minus active conflicts.",
        ],
        "hexagon_note_items": [
            "Hexagons are no longer used in the live map stage of this prototype.",
            "They can still be useful later for reporting, ranking, comparison with the landscape-analysis clusters, or summarising how much land remains after geometry-first filtering.",
            "If you later want a hex view again, it should come after the geometry-based buffers and intersections, not before them.",
        ],
    },
}

GROUP_TRANSLATIONS_SV = {
    "settlement": {
        "label": "Bebyggelse / befolkning / byggd miljö",
        "analysis_label": "Minsta avstånd",
        "interpretation": "För nära är dåligt. Prototypen använder minsta avstånd över valda bebyggelseproxyer så att överlappande lager inte naivt läggs ihop.",
    },
    "transport": {
        "label": "Transportinfrastruktur",
        "analysis_label": "Minsta avstånd",
        "interpretation": "För nära är dåligt. Transportlagret är uppdelat i små, mellan och stora vägar utifrån den befintliga vägklassningen i det semi-manuella flödet.",
    },
    "electrical": {
        "label": "Elinfrastruktur / nätanslutning",
        "analysis_label": "Största anslutningsavstånd",
        "interpretation": "För långt bort är dåligt. Grupplagret visar mark som ligger inom valt maximalt anslutningsavstånd till vald elinfrastruktur, inklusive ledningar, kablar, stationer och befintliga vindkraftverk om de valts.",
    },
    "culture": {
        "label": "Värdefulla kulturmiljöer",
        "analysis_label": "Valfri buffert",
        "interpretation": "Hantera som hård exkludering i denna första prototyp eftersom det ligger nära nuvarande scenariologik.",
    },
    "protected": {
        "label": "Skyddade områden",
        "analysis_label": "Valfri buffert",
        "interpretation": "Hård exkludering. Det håller lagstadgade naturskydd separata från bebyggelse och transport så att det kombinerade resultatet kan skära dem rent.",
    },
    "aviation_approach": {
        "label": "Flygplatsinflygning / flygrestriktioner",
        "analysis_label": "Valfri buffert",
        "interpretation": "Hård exkludering. Inflygningszoner fungerar som planeringsrestriktioner snarare än som mjuk preferensyta.",
    },
    "aviation_bird": {
        "label": "Fågelkollisionskänslighet för luftfart",
        "analysis_label": "Minsta avstånd",
        "interpretation": "Avståndsbaserad konflikt. Det nuvarande stage-1-spåret behandlar redan detta lager som en graderad klareringsfaktor.",
    },
    "military": {
        "label": "Militära områden",
        "analysis_label": "Valfri buffert",
        "interpretation": "Hård exkludering. De här områdena fungerar bättre som ren mask än som viktad känslighetsyta.",
    },
    "coastal": {
        "label": "Kust / strandskydd",
        "analysis_label": "Valfri buffert",
        "interpretation": "Hård exkludering. Gruppen kan visa både direkt strandskydd och den bredare Kystnærhedszonen 3 km som separata kustbegränsningar.",
    },
}

LAYER_TRANSLATIONS_SV = {
    "population_points": {"label": "Befolkningspunkter", "note": "Integritetssäker representation av fastboende."},
    "buildings_low": {"label": "Byggnader låg", "note": "Allmän lägre bebyggelsestruktur."},
    "buildings_high": {"label": "Byggnader hög", "note": "Tätare eller högre bebyggelsestruktur som redan används i dagens hårda bosättningslogik."},
    "built_centre": {"label": "Bebyggelsekärna", "note": "Stadskärnefotavtryck."},
    "built_low_selection": {"label": "Bebyggelse låg (urval)", "note": "Urvalsbaserad proxy för låg bebyggelse."},
    "roads_small": {"label": "Små vägar", "note": "Härledd från vägkategori i befintlig vägklassning. Kan vara tom om lokala vägar saknas i källan."},
    "roads_medium": {"label": "Mellanvägar", "note": "Härledd från vägkategori i befintlig vägklassning."},
    "roads_large": {"label": "Stora vägar", "note": "Större vägstråk från förenklad vägkälla."},
    "high_voltage_lines": {"label": "Högspänningsledningar", "note": "Luftburna högspänningsledningar."},
    "underground_cables": {"label": "Markkablar", "note": "Nedgrävda elkablar."},
    "power_substations": {"label": "Transformatorstationer", "note": "Stationer och kopplingspunkter."},
    "existing_wind_turbines": {"label": "Befintliga vindkraftverk", "note": "Punktlager med redan etablerade vindkraftverk."},
    "cultural_preservation": {"label": "Kulturbevarande", "note": "Områden med kulturbevarandevärde."},
    "valuable_cultural_environment": {"label": "Värdefull kulturmiljö", "note": "Sammanhållen kulturmiljö av särskilt värde."},
    "cultural_conservation_values": {"label": "Kulturvårdsvärden", "note": "Ytor med kulturvårdsintresse."},
    "protected_areas": {"label": "Skyddade områden", "note": "Skyddad natur som no-go-yta."},
    "natura_designated_land": {"label": "Natura 2000-områden", "note": "Utsedda Natura 2000-områden."},
    "natura_bird_protection": {"label": "Natura fågelskydd", "note": "Fågelskyddsområden inom Natura 2000."},
    "natura_habitat_areas": {"label": "Natura habitatområden", "note": "Habitatområden inom Natura 2000."},
    "natura_ramsar": {"label": "Natura Ramsar", "note": "Ramsarrelaterat våtmarksskydd."},
    "nature_wildlife_reserve": {"label": "Natur- och viltreservat", "note": "Natur- och viltreservatsytor."},
    "nature_area_forest": {"label": "Naturareal skog/plantage", "note": "Danskt naturareal-lager filtrerat till skovPlantage."},
    "aviation_approach_zones": {"label": "Inflygningszoner", "note": "Restriktionsytor för inflygning."},
    "aviation_bird_collision": {"label": "Fågelkollisionszoner", "note": "Känslighetszoner för fågelkollision."},
    "military_areas": {"label": "Militära områden", "note": "Militära tränings- eller skyddszoner."},
    "coastal_zone_3km": {"label": "Kustzon 3 km", "note": "Kystnærhedszonen 3 km från Miljøministeriet / PLST."},
    "strand_protection": {"label": "Strandskydd", "note": "Nuvarande strandskyddslager som no-go-yta."},
}

ACCEPTANCE_CLASS_LABELS = {
    "Exkluderad": {"sv": "Exkluderad", "en": "Excluded"},
    "Lag": {"sv": "Låg", "en": "Low"},
    "Medel": {"sv": "Medel", "en": "Medium"},
    "Hog": {"sv": "Hög", "en": "High"},
    "Mycket hog": {"sv": "Mycket hög", "en": "Very high"},
}

CLUSTER_LABELS = {
    "1": {"sv": "Tätorts- och verksamhetskärnor", "en": "Urban and activity cores"},
    "2": {"sv": "Vardagslandskap med blandad bakgrundskaraktär", "en": "Everyday landscape with mixed background character"},
    "3": {"sv": "Flygsands- och låglänta kuststråk", "en": "Dune and low-lying coastal belt"},
    "4": {"sv": "Brant relief och dalpräglat inland", "en": "Steep relief and valley-shaped inland"},
    "5": {"sv": "Skogligt inland och habitatkärnor", "en": "Forested inland and habitat cores"},
}

REFERENCE_LAYER_NAMES = {
    "scenario_medium": {"sv": "V4: Mellan acceptansscenario", "en": "V4: Medium acceptance scenario"},
    "scenario_low": {"sv": "V4: Låg acceptansscenario", "en": "V4: Low acceptance scenario"},
    "scenario_high": {"sv": "V4: Hög acceptansscenario", "en": "V4: High acceptance scenario"},
    "scenario_score_medium": {"sv": "V4: Mellan scenarioscore", "en": "V4: Medium scenario score"},
    "clusters": {"sv": "V4: Landskapskluster", "en": "V4: Landscape clusters"},
}

ANALYSIS_KIND_LABELS = {
    "distance_conflict": {"sv": "Avståndskonflikt", "en": "Distance conflict"},
    "proximity_feasibility": {"sv": "Närhetsgenomförbarhet", "en": "Proximity feasibility"},
    "hard_exclusion": {"sv": "Hård exkludering", "en": "Hard exclusion"},
    "soft_weighted_sensitivity": {"sv": "Mjuk viktad känslighet", "en": "Soft weighted sensitivity"},
}


def _lang(language: str) -> str:
    return language if language in TEXTS else "en"


def _item_id(item: Any) -> str:
    return getattr(item, "id", item)


def ui_text(key: str, language: str) -> Any:
    lang = _lang(language)
    if key in TEXTS[lang]:
        return TEXTS[lang][key]
    return TEXTS["en"].get(key, key)


def language_option_label(language: str) -> str:
    return LANGUAGE_LABELS.get(language, language)


def group_label(group_or_id: Any, language: str, default: str | None = None) -> str:
    group_id = _item_id(group_or_id)
    if default is None and hasattr(group_or_id, "label"):
        default = getattr(group_or_id, "label")
    if language == "sv":
        return GROUP_TRANSLATIONS_SV.get(group_id, {}).get("label", default or str(group_id))
    return default or str(group_id)


def group_analysis_label(group_or_id: Any, language: str, default: str | None = None) -> str:
    group_id = _item_id(group_or_id)
    if default is None and hasattr(group_or_id, "analysis_label"):
        default = getattr(group_or_id, "analysis_label")
    if language == "sv":
        return GROUP_TRANSLATIONS_SV.get(group_id, {}).get("analysis_label", default or str(group_id))
    return default or str(group_id)


def group_interpretation(group_or_id: Any, language: str, default: str | None = None) -> str:
    group_id = _item_id(group_or_id)
    if default is None and hasattr(group_or_id, "interpretation"):
        default = getattr(group_or_id, "interpretation")
    if language == "sv":
        return GROUP_TRANSLATIONS_SV.get(group_id, {}).get("interpretation", default or str(group_id))
    return default or str(group_id)


def layer_label(layer_or_id: Any, language: str, default: str | None = None) -> str:
    layer_id = _item_id(layer_or_id)
    if default is None and hasattr(layer_or_id, "label"):
        default = getattr(layer_or_id, "label")
    if language == "sv":
        return LAYER_TRANSLATIONS_SV.get(layer_id, {}).get("label", default or str(layer_id))
    return default or str(layer_id)


def layer_note(layer_or_id: Any, language: str, default: str | None = None) -> str:
    layer_id = _item_id(layer_or_id)
    if default is None and hasattr(layer_or_id, "note"):
        default = getattr(layer_or_id, "note")
    if language == "sv":
        return LAYER_TRANSLATIONS_SV.get(layer_id, {}).get("note", default or "")
    return default or ""


def analysis_kind_label(kind: str, language: str) -> str:
    lang = _lang(language)
    return ANALYSIS_KIND_LABELS.get(kind, {}).get(lang, kind)


def role_label(role: str | None, language: str) -> str | None:
    if role is None:
        return None
    return ui_text(f"role_{role}", language)


def acceptance_class_label(raw_class: str, language: str) -> str:
    lang = _lang(language)
    return ACCEPTANCE_CLASS_LABELS.get(str(raw_class), {}).get(lang, str(raw_class))


def cluster_label(cluster_key: str, language: str) -> str:
    lang = _lang(language)
    return CLUSTER_LABELS.get(str(cluster_key), {}).get(lang, "Unknown" if lang == "en" else "Okänd")


def reference_layer_name(key: str, language: str) -> str:
    lang = _lang(language)
    return REFERENCE_LAYER_NAMES[key][lang]


def critical_review_items(language: str) -> list[str]:
    return list(ui_text("critical_review_items", language))


def hexagon_note_items(language: str) -> list[str]:
    return list(ui_text("hexagon_note_items", language))
