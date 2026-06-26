from __future__ import annotations

from pathlib import Path
import runpy
import sys


PORT_ROOT = Path(__file__).resolve().parent
APPS_ROOT = PORT_ROOT / "apps"

if str(APPS_ROOT) not in sys.path:
    sys.path.insert(0, str(APPS_ROOT))

runpy.run_path(str(PORT_ROOT / "potential_app.py"), run_name="__main__")
