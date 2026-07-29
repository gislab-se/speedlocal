from __future__ import annotations

import os
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
ACTIVE_REGIONS = ("bornholm", "trondelag")


def main() -> int:
    os.environ.setdefault(
        "SPEEDLOCAL_V2_SOURCE_ROOT",
        r"C:\gislab\data\landskapsanalys-v2-multiregion",
    )
    os.environ["SPEEDLOCAL_GENERIC_ROADS_PARITY"] = "1"
    checks = 0
    for region_id in ACTIVE_REGIONS:
        app = AppTest.from_file(str(APP_PATH), default_timeout=60)
        app.query_params["region"] = region_id
        app.run(timeout=60)
        assert not app.exception, [str(item.value) for item in app.exception]
        assert not app.error, [str(item.value) for item in app.error]
        assert len(app.metric) == 4
        assert len(app.multiselect) == 1
        assert set(app.multiselect[0].value) == {"roads_medium", "roads_large"}
        checks += 5
        print(f"PASS {region_id}: generic roads parity UI rendered")
    print(f"Generic roads app validation passed: {checks}/10 checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
