from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
V2_PORT_ENTRYPOINT = ROOT / "apps" / "v2_port" / "app.py"
GENERIC_ROADS_PARITY_ENTRYPOINT = ROOT / "apps" / "generic_parity" / "app.py"
GENERIC_ROADS_PARITY_ENV = "SPEEDLOCAL_GENERIC_ROADS_PARITY"

parity_enabled = os.environ.get(GENERIC_ROADS_PARITY_ENV, "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
entrypoint = GENERIC_ROADS_PARITY_ENTRYPOINT if parity_enabled else V2_PORT_ENTRYPOINT
runpy.run_path(str(entrypoint), run_name="__main__")
