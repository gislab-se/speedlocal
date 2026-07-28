from __future__ import annotations

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parent
V2_PORT_ENTRYPOINT = ROOT / "apps" / "v2_port" / "app.py"

runpy.run_path(str(V2_PORT_ENTRYPOINT), run_name="__main__")
