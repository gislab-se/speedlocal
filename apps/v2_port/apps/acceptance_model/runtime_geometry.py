from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from .layers import registry_path as active_registry_path
from .layers import repo_root


RUNTIME_RELATIVE_DIR = "data/runtime/generated/v2_port_acceptance"
RENDER_SCRIPT = "script/acceptance/render_wind_acceptance_geometry_runtime.R"


def runtime_root() -> Path:
    root = repo_root() / RUNTIME_RELATIVE_DIR
    return root


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _runtime_revision_token() -> str:
    render_path = repo_root() / RENDER_SCRIPT
    registry_path = active_registry_path()
    return "|".join(
        [
            str(render_path),
            str(render_path.stat().st_mtime_ns if render_path.exists() else 0),
            str(registry_path),
            str(registry_path.stat().st_mtime_ns if registry_path.exists() else 0),
        ]
    )


def run_geometry_runtime(config_json: str) -> dict[str, Any]:
    raise RuntimeError(
        "The V2 acceptance geometry runtime is disabled in the SpeedLocal quarantine port. "
        "Port it deliberately before enabling generated acceptance geometry."
    )


@st.cache_data(show_spinner=False)
def _run_geometry_runtime_cached(config_json: str, revision_token: str) -> dict[str, Any]:
    raise RuntimeError(
        "The cached V2 acceptance geometry runtime is disabled in the SpeedLocal quarantine port."
    )
