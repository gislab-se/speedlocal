from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PORT_APPS = ROOT / "apps" / "v2_port" / "apps"
APP_PATH = ROOT / "apps" / "v2_port" / "potential_app.py"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
ACTIVE_REGION_IDS = ("trondelag", "bornholm")

if str(PORT_APPS) not in sys.path:
    sys.path.insert(0, str(PORT_APPS))

from potential_model.manifests import load_region, v2_source_root  # noqa: E402


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        if condition:
            self.passes.append(ok)
        else:
            self.failures.append(fail)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def emit(self) -> int:
        print("SpeedLocal V2 port app smoke test")
        print("=" * 33)
        print("\nBLOCKERS")
        if self.failures:
            for idx, failure in enumerate(self.failures, start=1):
                print(f"{idx}. FAIL {failure}")
        else:
            print("None")
        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")
        if self.notes:
            print("\nNOTES")
            for item in self.notes:
                print(f"- {item}")
        status = "FAIL" if self.failures else "PASS"
        print(f"\nRESULT: {status} ({len(self.passes)} passed, {len(self.failures)} blocker(s))")
        return 1 if self.failures else 0


def main() -> int:
    report = Report()
    source_root = v2_source_root()
    report.note(f"{V2_SOURCE_ROOT_ENV}: {os.environ.get(V2_SOURCE_ROOT_ENV, '<not set>')}")
    report.check(APP_PATH.is_file(), "Quarantine app entrypoint exists.", f"Missing app: {APP_PATH}")
    report.check(
        bool(source_root and source_root.is_dir()),
        "V2 source root exists.",
        f"V2 source root does not exist: {source_root}",
    )
    if not APP_PATH.is_file() or source_root is None or not source_root.is_dir():
        return report.emit()

    for region_id in ACTIVE_REGION_IDS:
        region = load_region(region_id)
        report.check(
            region.get("_v2_source_available") is True,
            f"{region_id}: detailed V2 source manifest is available.",
            f"{region_id}: detailed V2 source manifest is unavailable.",
        )
        app = AppTest.from_file(str(APP_PATH), default_timeout=120)
        app.query_params["region"] = region_id
        app.run(timeout=120)
        exceptions = [str(item.value) for item in app.exception]
        errors = [str(item.value) for item in app.error]
        report.check(
            not exceptions,
            f"{region_id}: app executes without uncaught exceptions.",
            f"{region_id}: uncaught exceptions: {exceptions}",
        )
        report.check(
            not errors,
            f"{region_id}: app renders without st.error output.",
            f"{region_id}: st.error output: {errors}",
        )
        report.check(
            len(app.button) > 0 and len(app.metric) > 0,
            f"{region_id}: interactive workspace elements render.",
            f"{region_id}: expected buttons and metrics did not render.",
        )
        report.note(f"{region_id}: {len(app.warning)} domain warning(s) rendered.")

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
