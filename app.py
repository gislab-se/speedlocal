from __future__ import annotations

import runpy
from pathlib import Path

from speedlocal.runtime_bundle import RuntimeBundleError, ensure_v2_source_root


ROOT = Path(__file__).resolve().parent
V2_FINAL_ENTRYPOINT = ROOT / "apps" / "v2_port" / "app.py"

try:
    ensure_v2_source_root()
except RuntimeBundleError as exc:
    import streamlit as st

    st.set_page_config(page_title="SpeedLocal V2 Final", layout="wide")
    st.error(
        "V2 Final kunde inte förbereda det verifierade "
        "Trøndelag-runtimepaketet."
    )
    st.caption(f"Teknisk kod: {exc.code}")
    st.stop()

runpy.run_path(str(V2_FINAL_ENTRYPOINT), run_name="__main__")
