from __future__ import annotations

import pandas as pd
import streamlit as st

from .catalog import CatalogError, default_region_id, list_regions, load_region
from .runtime import file_fallback_rows, selected_backend


def _status_label(region: dict) -> str:
    status = str(region.get("status") or "unknown")
    enabled = bool((region.get("landing_card") or {}).get("enabled", status == "active"))
    if not enabled:
        return "planned"
    return status


def _region_card(region: dict) -> None:
    card = region.get("landing_card") or {}
    st.subheader(card.get("title") or region.get("display_name") or region.get("region_id"))
    st.caption(card.get("subtitle") or region.get("data_status") or "")
    st.write(card.get("description") or "")
    cols = st.columns(3)
    cols[0].metric("Status", _status_label(region))
    cols[1].metric("CRS", region.get("native_crs", "TBD"))
    cols[2].metric("H3", ", ".join(str(v) for v in region.get("available_h3_resolutions") or []) or "TBD")


def _region_detail(region_id: str) -> None:
    region = load_region(region_id)
    st.header(region.get("display_name") or region_id)
    st.caption(region.get("runtime_note") or "")

    backend = selected_backend(region)
    st.info(f"Runtime backend: {backend.backend}. {backend.message}")

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

    st.subheader("Next Runtime Requirement")
    for item in region.get("readiness_requirements") or []:
        st.checkbox(str(item), value=False, disabled=True)


def main() -> None:
    st.set_page_config(page_title="SpeedLocal landskapspotential", layout="wide")
    st.title("SpeedLocal landskapspotential")
    st.caption("Catalog-driven delivery shell for landing page, regional app cards, Postgres runtime and file fallbacks.")

    try:
        regions = list_regions()
    except CatalogError as exc:
        st.error(str(exc))
        st.stop()

    query_region = st.query_params.get("region")
    selected = str(query_region or default_region_id()).lower()
    if selected not in {str(region.get("region_id")).lower() for region in regions}:
        selected = default_region_id()

    st.subheader("Regional Cards")
    columns = st.columns(len(regions))
    for column, region in zip(columns, regions):
        with column:
            _region_card(region)
            if st.button("Open", key=f"open_{region['region_id']}"):
                st.query_params["region"] = region["region_id"]
                st.rerun()

    st.divider()
    _region_detail(selected)


if __name__ == "__main__":
    main()
