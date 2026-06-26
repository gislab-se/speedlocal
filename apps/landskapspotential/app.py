from __future__ import annotations

import pandas as pd
import streamlit as st

from .catalog import CatalogError, default_region_id, list_regions, load_region
from .file_runtime import dataset_rows, runtime_source_summary
from .runtime import file_fallback_rows, selected_backend


def _status_label(region: dict) -> str:
    status = str(region.get("status") or "unknown")
    enabled = bool((region.get("landing_card") or {}).get("enabled", status == "active"))
    if not enabled:
        return "planned"
    return status


def _h3_label(region: dict) -> str:
    values = region.get("available_h3_resolutions") or []
    return ", ".join(f"R{value}" for value in values) or "TBD"


def _region_card(region: dict) -> bool:
    card = region.get("landing_card") or {}
    region_id = str(region.get("region_id") or "")
    enabled = bool(card.get("enabled", region.get("status") == "active"))

    st.subheader(card.get("title") or region.get("display_name") or region_id)
    st.caption(card.get("subtitle") or region.get("data_status") or "")
    st.write(card.get("description") or "")
    cols = st.columns(3)
    cols[0].markdown(f"**Status**  \n{_status_label(region)}")
    cols[1].markdown(f"**CRS**  \n`{region.get('native_crs', 'TBD')}`")
    cols[2].markdown(f"**H3**  \n{_h3_label(region)}")
    if not enabled:
        st.button("Planerad", key=f"planned_{region_id}", disabled=True)
        return False
    return st.button("Visa runtime-status", key=f"open_{region_id}")


def _region_detail(region_id: str) -> None:
    region = load_region(region_id)
    display_name = region.get("display_name") or region_id
    st.header(f"{display_name} runtime-status")
    st.caption(region.get("runtime_note") or "")

    backend = selected_backend(region)
    st.info(f"Runtime backend: {backend.backend}. {backend.message}")
    if backend.backend == "file_fallback":
        st.warning(
            "Den fulla interaktiva regionala appen är inte migrerad hit än. "
            "Den här vyn visar katalog, fallback-sökvägar och validerad källstatus under tiden."
        )

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Catalog")
        st.json(
            {
                "region_id": region.get("region_id"),
                "status": region.get("status"),
                "data_status": region.get("data_status"),
                "native_crs": region.get("native_crs"),
                "available_h3_resolutions": region.get("available_h3_resolutions"),
                "default_h3_resolution": region.get("default_h3_resolution"),
            },
            expanded=False,
        )
    with right:
        st.subheader("Runtime Fallbacks")
        rows = file_fallback_rows(region)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No file fallbacks required for this planned region yet.")

    source_summary = runtime_source_summary(region_id)
    st.subheader("File Runtime Source")
    if source_summary.datasets:
        st.caption(f"{source_summary.message} Source root: {source_summary.source_root}")
        st.dataframe(pd.DataFrame(dataset_rows(source_summary)), use_container_width=True, hide_index=True)
    else:
        st.caption(source_summary.message)

    st.subheader("Next Runtime Requirement")
    for item in region.get("readiness_requirements") or []:
        st.checkbox(str(item), value=False, disabled=True)


def main() -> None:
    st.set_page_config(page_title="SpeedLocal landskapspotential", layout="wide")
    st.title("SpeedLocal landskapspotential")
    st.caption(
        "Migreringsskal för regionala appytor, Postgres runtime och filfallbacks. "
        "Publik landing page finns på GitHub Pages; Python/Streamlit körs separat tills Flowcore tar över."
    )

    try:
        regions = list_regions()
    except CatalogError as exc:
        st.error(str(exc))
        st.stop()

    query_region = st.query_params.get("region")
    selected = str(query_region or default_region_id()).lower()
    if selected not in {str(region.get("region_id")).lower() for region in regions}:
        selected = default_region_id()

    st.subheader("Regionala ytor")
    st.caption("Korten väljer regionens runtime-status i det nya repo-skalet. De öppnar ännu inte den fulla regionala appen.")
    columns = st.columns(len(regions))
    for column, region in zip(columns, regions):
        with column:
            if _region_card(region):
                st.query_params["region"] = region["region_id"]
                st.rerun()

    st.divider()
    _region_detail(selected)


if __name__ == "__main__":
    main()
