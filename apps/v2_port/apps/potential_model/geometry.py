from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

try:
    import h3
except Exception:  # pragma: no cover
    h3 = None


def _full_h3_geometry(hex_id: str) -> dict[str, Any] | None:
    if h3 is None:
        return None
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


@st.cache_data(show_spinner=False)
def load_h3_display_geometries(path_str: str) -> dict[str, dict[str, Any]]:
    path = Path(path_str)
    data = json.loads(path.read_text(encoding="utf-8"))
    geometries: dict[str, dict[str, Any]] = {}
    for feature in data.get("features") or []:
        properties = feature.get("properties") or {}
        hex_id = properties.get("hex_id") or properties.get("h3_address")
        geometry = feature.get("geometry")
        if hex_id and geometry and geometry.get("coordinates"):
            geometries[str(hex_id)] = _full_h3_geometry(str(hex_id)) or geometry
    return geometries


def geometry_for_hex(
    hex_id: str,
    display_geometries: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not display_geometries:
        return None
    return display_geometries.get(str(hex_id))
