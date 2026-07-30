from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PORT_APPS = ROOT / "apps" / "v2_port" / "apps"
V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
EXPECTED_REGION_IDS = ["bornholm", "trondelag", "skaraborg"]
EXPECTED_REGISTRY_PATHS = {
    "bornholm": "apps/acceptance_model/registry_bornholm.json",
    "trondelag": "apps/acceptance_model/registry_trondelag.json",
}
EXPECTED_RUNTIME_STRATEGIES = {
    "bornholm": "precomputed_polygon",
    "trondelag": "fast_distance",
}
EXPECTED_LAYER_READINESS = {
    "bornholm": (26, 27),
    "trondelag": (14, 14),
}
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

for import_root in (ROOT, PORT_APPS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from acceptance_model.layers import (  # noqa: E402
    asset_dir,
    layer_status_table,
    load_registry,
    registry_path,
    resolve_registry_path,
)
from potential_model import manifests  # noqa: E402
from speedlocal.catalogs import load_region as load_delivery_region  # noqa: E402


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

        delivery_region = load_delivery_region(region_id)
        runtime = delivery_region.get("runtime") or {}
        sources = runtime.get("sources") or {}
        registry_source = sources.get("acceptance_registry") or {}
        expected_registry_path = EXPECTED_REGISTRY_PATHS[region_id]
        expected_strategy = EXPECTED_RUNTIME_STRATEGIES[region_id]
        source_contract_valid = (
            registry_source.get("provider") == "v2_archive"
            and registry_source.get("path") == expected_registry_path
            and registry_source.get("runtime_strategy") == expected_strategy
            and registry_source.get("evidence_role")
            == (
                "frozen_v2_parity_reference"
                if region_id == "trondelag"
                else "diagnostic_only"
            )
        )
        if region_id == "trondelag":
            source_contract_valid = (
                source_contract_valid
                and registry_source.get("distance_conflict_semantics")
                == "soft_ramp"
                and "artifact_root" not in registry_source
                and "validated_fixtures" not in registry_source
            )
        else:
            fixtures = registry_source.get("validated_fixtures")
            source_contract_valid = (
                source_contract_valid
                and registry_source.get("artifact_root")
                == "docs/geocontext/acceptance_framework/data/prototype_runtime"
                and isinstance(fixtures, list)
                and {str(item.get("id") or "") for item in fixtures}
                == {"frozen_default_roads_300m", "frozen_roads_400m"}
                and all(
                    isinstance(item.get("files_sha256"), dict)
                    and len(item["files_sha256"]) == 7
                    and all(
                        len(str(value)) == 64
                        for value in item["files_sha256"].values()
                    )
                    for item in fixtures
                )
            )
        report.check(
            source_contract_valid,
            f"{region_id}: acceptance registry runtime strategy is manifest-declared.",
            f"{region_id}: invalid acceptance registry source: {registry_source!r}",
        )
        try:
            external_registry_path = registry_path(region_id)
            _, _, registry_meta = load_registry(region_id)
            status = layer_status_table(registry_meta)
        except Exception as exc:
            report.check(False, "", f"{region_id}: cannot load external acceptance registry: {exc}")
            continue

        report.check(
            manifests._path_within(source_root, external_registry_path)
            and external_registry_path == (source_root / expected_registry_path).resolve(),
            f"{region_id}: acceptance registry resolves inside the V2 archive.",
            f"{region_id}: acceptance registry resolved incorrectly: {external_registry_path}",
        )
        report.check(
            registry_meta.get("_source_provider") == "v2_archive"
            and registry_meta.get("_region_id") == region_id
            and registry_meta.get("_runtime_strategy") == expected_strategy
            and (
                registry_meta.get("_distance_conflict_semantics")
                == "soft_ramp"
                if region_id == "trondelag"
                else bool(registry_meta.get("_runtime_artifact_root"))
                and len(registry_meta.get("_runtime_validated_fixtures") or [])
                == 2
            ),
            f"{region_id}: registry metadata carries provider, region, and runtime strategy.",
            f"{region_id}: incomplete registry provenance: {registry_meta.get('_source_provider')!r}, "
            f"{registry_meta.get('_region_id')!r}, "
            f"{registry_meta.get('_distance_conflict_semantics')!r}",
        )
        report.check(
            manifests._path_within(source_root, asset_dir(registry_meta)),
            f"{region_id}: acceptance assets resolve inside the V2 archive.",
            f"{region_id}: acceptance asset directory escapes the V2 archive.",
        )
        ready = (
            status["geojson_ready"].astype(bool)
            & status["distance_ready"].astype(bool)
            & status["source_exists"].astype(bool)
            & status["feature_count"].astype(int).gt(0)
            & status["status"].astype(str).eq("ok")
        )
        expected_ready, expected_total = EXPECTED_LAYER_READINESS[region_id]
        report.check(
            int(ready.sum()) == expected_ready and len(status) == expected_total,
            f"{region_id}: {expected_ready}/{expected_total} acceptance layers are runtime-ready.",
            f"{region_id}: readiness is {int(ready.sum())}/{len(status)}, "
            f"expected {expected_ready}/{expected_total}.",
        )
        try:
            resolve_registry_path(registry_meta, "../outside-v2-archive")
        except ValueError:
            report.check(
                True,
                f"{region_id}: registry asset paths fail closed outside the provider root.",
                "",
            )
        else:
            report.check(
                False,
                "",
                f"{region_id}: registry asset resolver accepted a path outside the provider root.",
            )

        local_registry = (
            ROOT
            / "apps"
            / "v2_port"
            / "apps"
            / "acceptance_model"
            / f"registry_{region_id}.json"
        )
        report.check(
            not local_registry.exists(),
            f"{region_id}: no duplicate registry remains in V2 Final.",
            f"{region_id}: duplicate local registry remains: {local_registry}",
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
    bornholm_delivery = load_delivery_region("bornholm")
    bornholm_reference = bornholm_delivery.get("behavior_reference") or {}
    report.check(
        bornholm_delivery.get("status") == "onboarding"
        and not bool((bornholm_delivery.get("landing_card") or {}).get("enabled"))
        and bornholm_reference.get("status") == "diagnostic_only"
        and bornholm_reference.get("frozen_v2_parity") is False,
        "Bornholm source assets remain diagnostic while its V2 Final route is disabled.",
        "Bornholm source assets are incorrectly exposed as an active parity baseline.",
    )
    trondelag_delivery = load_delivery_region("trondelag")
    trondelag_reference = trondelag_delivery.get("behavior_reference") or {}
    report.check(
        trondelag_delivery.get("status") == "active"
        and trondelag_reference.get("status") == "authoritative"
        and trondelag_reference.get("scope") == "trondelag_only",
        "Trondelag is the active authoritative V2 behavior reference.",
        "Trondelag behavior authority is not declared correctly.",
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
