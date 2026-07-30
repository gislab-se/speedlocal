from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
V2_FINAL_ENTRYPOINT = ROOT / "apps" / "v2_port" / "app.py"

runpy.run_path(str(V2_FINAL_ENTRYPOINT), run_name="__main__")
