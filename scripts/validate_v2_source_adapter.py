from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PORT_APPS = ROOT / "apps" / "v2_port" / "apps"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
EXPECTED_REGION_IDS = ["bornholm", "trondelag", "skaraborg"]
EXPECTED_LINKS = {
    "bornholm": (
        "landscape_manifest",
        "potential_manifest",
        "scenario_manifest",
        "social_acceptance_manifest",
        "acceptance_registry",
    ),
    "trondelag": (
        "landscape_manifest",
        "potential_manifest",
        "scenario_manifest",
        "social_acceptance_manifest",
        "acceptance_registry",
    ),
}

if str(PORT_APPS) not in sys.path:
    sys.path.insert(0, str(PORT_APPS))

from potential_model import manifests  # noqa: E402


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
        print("SpeedLocal V2 source adapter")
        print("=" * 28)
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


def _resolved_links(region: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Path | None]:
    return {
        key: manifests.resolve_region_path(region, str(region.get(key) or ""))
        for key in keys
    }


def main() -> int:
    report = Report()
    source_value = os.environ.get(V2_SOURCE_ROOT_ENV, "").strip()
    source_root = manifests.v2_source_root()
    report.note(f"{V2_SOURCE_ROOT_ENV}: {source_value or '<not set>'}")
    report.check(
        bool(source_value),
        f"{V2_SOURCE_ROOT_ENV} is set.",
        f"{V2_SOURCE_ROOT_ENV} is not set.",
    )
    report.check(
        bool(source_root and source_root.is_dir()),
        "V2 source root exists.",
        f"V2 source root does not exist: {source_root}",
    )
    if source_root is None or not source_root.is_dir():
        return report.emit()

    regions = manifests.list_regions()
    region_ids = [str(region.get("region_id") or "").lower() for region in regions]
    report.check(
        region_ids == EXPECTED_REGION_IDS,
        f"Public region discovery is exactly {EXPECTED_REGION_IDS}.",
        f"Public region discovery is {region_ids}.",
    )
    report.check(
        not {"vara", "skara"}.intersection(region_ids),
        "Legacy Vara/skara regions are unavailable.",
        f"Legacy regions are exposed: {sorted({'vara', 'skara'}.intersection(region_ids))}",
    )

    by_id = {str(region.get("region_id") or "").lower(): region for region in regions}
    for region_id, keys in EXPECTED_LINKS.items():
        region = by_id.get(region_id) or {}
        report.check(
            region.get("_v2_source_available") is True,
            f"{region_id}: V2 source manifest is loaded.",
            f"{region_id}: V2 source manifest is unavailable.",
        )
        report.check(
            Path(str(region.get("_speedlocal_manifest_path") or "")).is_file(),
            f"{region_id}: SpeedLocal delivery manifest remains authoritative.",
            f"{region_id}: SpeedLocal delivery manifest provenance is missing.",
        )
        resolved = _resolved_links(region, keys)
        missing = [
            f"{key}={path}"
            for key, path in resolved.items()
            if path is None or not path.is_file()
        ]
        report.check(
            not missing,
            f"{region_id}: detailed linked manifests resolve inside the V2 archive.",
            f"{region_id}: missing linked manifests: {missing}",
        )
        outside = [
            f"{key}={path}"
            for key, path in resolved.items()
            if path is not None and not manifests._path_within(source_root, path)
        ]
        report.check(
            not outside,
            f"{region_id}: linked manifests stay inside the V2 source root.",
            f"{region_id}: linked manifests escape the V2 source root: {outside}",
        )

    trondelag = by_id.get("trondelag") or {}
    report.check(
        trondelag.get("available_h3_resolutions") == [7, 6, 5],
        "Trondelag exposes R7/R6/R5 only.",
        f"Trondelag resolutions are {trondelag.get('available_h3_resolutions')!r}.",
    )
    bornholm = by_id.get("bornholm") or {}
    report.check(
        bornholm.get("available_h3_resolutions") == [6, 7, 8, 9],
        "Bornholm exposes R6/R7/R8/R9.",
        f"Bornholm resolutions are {bornholm.get('available_h3_resolutions')!r}.",
    )
    skaraborg = by_id.get("skaraborg") or {}
    report.check(
        skaraborg.get("status") == "planned"
        and not bool((skaraborg.get("landing_card") or {}).get("enabled"))
        and skaraborg.get("_v2_source_available") is False,
        "Skaraborg remains planned, disabled, and unbound to V2.",
        "Skaraborg was activated or bound to a V2 source.",
    )

    outside_probe = source_root.parent / "outside-speedlocal-v2-probe.json"
    report.check(
        manifests.resolve_v2_source_path(str(outside_probe)) is None
        and manifests.resolve_v2_source_path("../outside-speedlocal-v2-probe.json") is None,
        "Paths outside the V2 source root fail closed.",
        "The V2 adapter accepted a path outside its source root.",
    )

    try:
        manifests.load_region("vara")
    except FileNotFoundError:
        report.check(True, "Unknown/legacy regions fail closed.", "")
    else:
        report.check(False, "", "Legacy Vara region unexpectedly loaded.")

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
