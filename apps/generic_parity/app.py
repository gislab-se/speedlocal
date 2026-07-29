from __future__ import annotations

import streamlit as st

from speedlocal import run_analysis
from speedlocal.catalogs import list_regions, load_analysis


st.set_page_config(page_title="SpeedLocal vägparitet", layout="wide")

regions = [
    region
    for region in list_regions()
    if region.get("status") == "active"
    and "wind" in (region.get("analysis_manifests") or {})
]
region_by_id = {str(region["region_id"]): region for region in regions}
query_region = str(st.query_params.get("region", ""))
default_index = (
    list(region_by_id).index(query_region)
    if query_region in region_by_id
    else 0
)

st.title("V2 Final: vägparitet")
st.caption(
    "Tillfällig verifieringsyta för den manifeststyrda väggruppen. "
    "Den ordinarie V2-appen är oförändrad när feature-flaggan är av."
)

region_id = st.selectbox(
    "Region",
    options=list(region_by_id),
    index=default_index,
    format_func=lambda value: str(region_by_id[value].get("display_name") or value),
    key="generic_roads_region",
)
contract = load_analysis(region_id, "wind")
road_layers = [
    layer for layer in contract.layers.values() if layer.group_id == "roads"
]
layer_by_id = {layer.id: layer for layer in road_layers}

with st.form("generic_roads_controls", border=True):
    selected_layers = st.multiselect(
        "Väglager",
        options=list(layer_by_id),
        default=list(layer_by_id),
        format_func=lambda value: layer_by_id[value].label,
        key="generic_roads_layers",
    )
    buffer_m = st.slider(
        "Minsta avstånd till vägar (m)",
        min_value=0,
        max_value=2000,
        value=100,
        step=25,
        key="generic_roads_buffer_m",
    )
    submitted = st.form_submit_button(
        "Beräkna vägresultat",
        type="primary",
        icon=":material/route:",
    )

if not selected_layers:
    st.warning("Välj minst ett väglager.")
    st.stop()

parameters = {
    layer_id: {"buffer_m": buffer_m}
    for layer_id in selected_layers
}
try:
    result = run_analysis(
        region=region_id,
        analysis="wind",
        layers=selected_layers,
        parameters=parameters,
    )
except (FileNotFoundError, KeyError, ValueError) as error:
    st.error(f"Vägresultatet kunde inte valideras: {error}")
    st.stop()

group = result.groups[0]
metric_row = st.container(horizontal=True)
metric_row.metric("Analyserade H3-celler", f"{group.cell_count:,}".replace(",", " "))
metric_row.metric("Blockerade celler", f"{group.blocked_cell_count:,}".replace(",", " "))
blocked_share = (
    group.blocked_cell_count / group.cell_count * 100.0
    if group.cell_count
    else 0.0
)
metric_row.metric("Blockerad andel", f"{blocked_share:.1f} %")
metric_row.metric("Medelacceptans", f"{group.mean_acceptance:.3f}")

st.dataframe(
    [
        {
            "lager": layer_by_id[item.layer_id].label,
            "geometri": item.geometry_family,
            "adapter": item.processing_adapter,
            "geometrivalidering": item.geometry_validation,
            "källfeatures": item.source_feature_count,
            "H3-celler": item.cell_count,
            "blockerade": item.blocked_cell_count,
            "buffert_m": item.threshold_m,
        }
        for item in result.layers
    ],
    hide_index=True,
    width="stretch",
)

if any(item.geometry_validation != "detected" for item in result.layers):
    st.info(
        "Minst ett lager deltar via en validerad avståndstabell men saknar "
        "ritbar källgeometri. Analysen fungerar, men källagret kan inte visas "
        "som linje förrän displaygeometrin har reparerats."
    )

if submitted:
    st.success("Det generella vägresultatet har beräknats från regionens manifest.")
