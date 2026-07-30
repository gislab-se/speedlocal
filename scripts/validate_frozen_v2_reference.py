from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = ROOT / "docs" / "frozen_v2_reference.json"
SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
EXPECTED_REPOSITORY = "gislab-se/landskapsanalys"
EXPECTED_REPOSITORY_URL = "https://github.com/gislab-se/landskapsanalys"
EXPECTED_COMMIT = "75ba14871100c208cbf8eedb794d56c165340811"
EXPECTED_SOURCE_BRANCH = "potential-v2-multiregion"
EXPECTED_FROZEN_BRANCH = "frozen-v2-reference-2026-07-30"
EXPECTED_FROZEN_TAG = "v2-frozen-reference-2026-07-30"
EXPECTED_DEPLOYMENT_URL = "https://landskapsanalys-potential-v2-test.streamlit.app/"
EXPECTED_STREAMLIT_APP_ID = "63561ff3-f8c2-4c09-a9e7-ea110c51dc4a"
EXPECTED_PYTHON_VERSION = "3.11"
EXPECTED_VERIFIED_DATE = "2026-07-30"
EXPECTED_TAG_RULESET_ID = 20038506
EXPECTED_CORE_ARCHIVE_FILES = {
    "streamlit_app.py",
    "potential_app.py",
    "apps/acceptance_model/layers.py",
    "apps/acceptance_model/registry_trondelag.json",
    "apps/acceptance_model/registry_bornholm.json",
    "regions/trondelag/region.json",
    "regions/bornholm/region.json",
    "requirements.txt",
    "docs/geocontext/acceptance_framework/data/trondelag_prototype_assets/asset_manifest.csv",
    "docs/geocontext/acceptance_framework/data/prototype_assets_dagi_landsdel/asset_manifest.csv",
}


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        (self.passes if condition else self.failures).append(ok if condition else fail)

    def emit(self) -> int:
        print("Frozen V2 reference validation")
        print("=" * 30)
        print("\nBLOCKERS")
        if self.failures:
            for index, failure in enumerate(self.failures, start=1):
                print(f"{index}. FAIL {failure}")
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


def _load_reference() -> dict[str, Any]:
    with REFERENCE_PATH.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {REFERENCE_PATH}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _is_read_only(path: Path) -> bool:
    details = path.stat()
    file_attributes = getattr(details, "st_file_attributes", None)
    if file_attributes is not None:
        return bool(file_attributes & stat.FILE_ATTRIBUTE_READONLY)
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    return not bool(details.st_mode & write_bits)


def _acceptance_asset_fingerprint(
    archive_root: Path,
    contract: dict[str, Any],
) -> tuple[int, int, str]:
    relative_paths: set[str] = set()
    fields = tuple(str(value) for value in contract.get("path_fields") or [])
    for manifest_value in contract.get("manifests") or []:
        manifest_path = (archive_root / str(manifest_value)).resolve()
        if not _within(archive_root, manifest_path) or not manifest_path.is_file():
            raise FileNotFoundError(f"Acceptance asset manifest is unavailable: {manifest_path}")
        with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                for field in fields:
                    value = str(row.get(field) or "").strip()
                    if value and value.upper() != "NA":
                        relative_paths.add(value.replace("\\", "/"))

    aggregate = hashlib.sha256()
    total_bytes = 0
    for relative_value in sorted(relative_paths):
        candidate = (archive_root / relative_value).resolve()
        if not _within(archive_root, candidate):
            raise ValueError(f"Acceptance runtime path escapes archive: {relative_value}")
        if not candidate.is_file():
            raise FileNotFoundError(f"Acceptance runtime asset is missing: {relative_value}")
        file_hash = _sha256(candidate)
        total_bytes += candidate.stat().st_size
        aggregate.update(relative_value.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(file_hash.encode("ascii"))
        aggregate.update(b"\n")
    return len(relative_paths), total_bytes, aggregate.hexdigest()


def _remote_refs(reference: dict[str, Any]) -> dict[str, str]:
    repository_url = str(reference["repository_url"]).rstrip("/") + ".git"
    source_branch = str(reference["source_branch_at_freeze"])
    branch = str(reference["frozen_branch"])
    tag = str(reference["frozen_tag"])
    command = [
        "git",
        "ls-remote",
        repository_url,
        f"refs/heads/{source_branch}",
        f"refs/heads/{branch}",
        f"refs/tags/{tag}",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, ref_name = line.split(maxsplit=1)
        refs[ref_name] = sha
    return refs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Also verify the frozen GitHub branch and tag with git ls-remote.",
    )
    args = parser.parse_args()

    report = Report()
    try:
        reference = _load_reference()
    except Exception as exc:
        report.check(False, "", f"Cannot load {REFERENCE_PATH}: {exc}")
        return report.emit()

    report.check(
        reference.get("repository") == EXPECTED_REPOSITORY,
        "Frozen repository identity is unchanged.",
        f"Unexpected repository: {reference.get('repository')!r}",
    )
    report.check(
        reference.get("repository_url") == EXPECTED_REPOSITORY_URL,
        "Frozen repository URL is unchanged.",
        f"Unexpected repository URL: {reference.get('repository_url')!r}",
    )
    report.check(
        reference.get("commit") == EXPECTED_COMMIT
        and bool(re.fullmatch(r"[0-9a-f]{40}", str(reference.get("commit") or ""))),
        "Frozen commit is the verified 40-character SHA.",
        f"Unexpected frozen commit: {reference.get('commit')!r}",
    )
    report.check(
        reference.get("frozen_branch") == EXPECTED_FROZEN_BRANCH,
        "Frozen branch name is unchanged.",
        f"Unexpected frozen branch: {reference.get('frozen_branch')!r}",
    )
    report.check(
        reference.get("frozen_tag") == EXPECTED_FROZEN_TAG,
        "Frozen tag name is unchanged.",
        f"Unexpected frozen tag: {reference.get('frozen_tag')!r}",
    )
    report.check(
        reference.get("source_branch_at_freeze") == EXPECTED_SOURCE_BRANCH
        and reference.get("source_branch_at_freeze")
        != reference.get("frozen_branch"),
        "Deployment source branch is exact and distinct from the frozen branch.",
        f"Unexpected source branch: {reference.get('source_branch_at_freeze')!r}",
    )
    report.check(
        reference.get("entrypoint") == "streamlit_app.py"
        and reference.get("launcher_target") == "potential_app.py",
        "Frozen Streamlit entrypoint chain is recorded.",
        "Frozen Streamlit entrypoint chain is invalid.",
    )
    report.check(
        reference.get("deployment_url") == EXPECTED_DEPLOYMENT_URL
        and reference.get("streamlit_app_id") == EXPECTED_STREAMLIT_APP_ID
        and reference.get("python_version") == EXPECTED_PYTHON_VERSION,
        "Frozen Streamlit deployment identity is exact.",
        "Frozen Streamlit deployment URL, app id, or Python version changed.",
    )
    report.check(
        reference.get("deployment_source_branch_at_verification")
        == EXPECTED_SOURCE_BRANCH
        and reference.get("deployment_repoint_status")
        == "not_required_current_branch_locked"
        and reference.get("deployment_access_status")
        == "private_authentication_required",
        "Deployment branch, repoint, and access states are explicit.",
        "Frozen deployment actual-state fields are incomplete.",
    )
    report.check(
        reference.get("schema_version") == EXPECTED_VERIFIED_DATE
        and reference.get("verified_utc_date") == EXPECTED_VERIFIED_DATE
        and reference.get("deployment_metadata_verified_utc_date")
        == EXPECTED_VERIFIED_DATE
        and reference.get("runtime_archive_env") == SOURCE_ROOT_ENV,
        "Freeze schema, verification dates, and archive environment are exact.",
        "Freeze dates or runtime archive environment changed.",
    )
    behavior_reference = reference.get("behavior_reference")
    report.check(
        isinstance(behavior_reference, dict)
        and behavior_reference.get("authoritative_regions") == ["trondelag"]
        and behavior_reference.get("diagnostic_only_regions") == ["bornholm"]
        and behavior_reference.get("trondelag_only_decision_commit")
        == "9095d996797a3173e7bbc5315a0beae5f712011e"
        and behavior_reference.get("trondelag_only_history_tag")
        == "stable-v2-trondelag-2026-05-19-zoom",
        "Frozen archive integrity is distinct from Trondelag-only behavior authority.",
        "Frozen archive behavior-reference classification is incomplete.",
    )
    branch_protection = reference.get("branch_protection")
    protected_branch_names = (
        str(reference.get("source_branch_at_freeze") or ""),
        str(reference.get("frozen_branch") or ""),
    )
    protection_valid = isinstance(branch_protection, dict)
    for branch_name in protected_branch_names:
        settings = (
            branch_protection.get(branch_name)
            if isinstance(branch_protection, dict)
            else None
        )
        protection_valid = bool(
            protection_valid
            and isinstance(settings, dict)
            and settings.get("locked") is True
            and settings.get("enforce_admins") is True
            and settings.get("allow_force_pushes") is False
            and settings.get("allow_deletions") is False
        )
    report.check(
        protection_valid,
        "Both deployment and dedicated frozen branches have a lock contract.",
        "Frozen branch-protection contract is incomplete.",
    )
    tag_protection = reference.get("tag_protection")
    report.check(
        isinstance(tag_protection, dict)
        and tag_protection.get("ruleset_id") == EXPECTED_TAG_RULESET_ID
        and tag_protection.get("target") == "tag"
        and tag_protection.get("enforcement") == "active"
        and tag_protection.get("included_ref")
        == f"refs/tags/{EXPECTED_FROZEN_TAG}"
        and set(tag_protection.get("rules") or []) == {"update", "deletion"},
        "Frozen tag has an active update/deletion protection contract.",
        "Frozen tag-protection contract is incomplete.",
    )

    configured_root = os.environ.get(SOURCE_ROOT_ENV, "").strip()
    report.check(
        bool(configured_root),
        f"{SOURCE_ROOT_ENV} is configured.",
        f"{SOURCE_ROOT_ENV} is not configured.",
    )
    if configured_root:
        archive_root = Path(configured_root).expanduser().resolve()
        report.check(
            archive_root.is_dir(),
            "Read-only runtime archive exists.",
            f"Runtime archive does not exist: {archive_root}",
        )
        expected_files = reference.get("runtime_archive_files")
        report.check(
            isinstance(expected_files, dict)
            and set(expected_files) == EXPECTED_CORE_ARCHIVE_FILES,
            "Runtime archive checksum contract contains the exact core file set.",
            "Runtime archive checksum contract has a missing or unexpected core file.",
        )
        if archive_root.is_dir() and isinstance(expected_files, dict):
            for relative_value, expected_hash in expected_files.items():
                relative_path = Path(str(relative_value))
                candidate = (archive_root / relative_path).resolve()
                safe = not relative_path.is_absolute() and _within(archive_root, candidate)
                report.check(
                    safe,
                    f"Archive path is confined: {relative_path.as_posix()}",
                    f"Archive path escapes root: {relative_path}",
                )
                if not safe:
                    continue
                report.check(
                    candidate.is_file(),
                    f"Archive file exists: {relative_path.as_posix()}",
                    f"Archive file is missing: {relative_path.as_posix()}",
                )
                if candidate.is_file():
                    actual_hash = _sha256(candidate)
                    report.check(
                        actual_hash == str(expected_hash),
                        f"Archive checksum matches: {relative_path.as_posix()}",
                        f"Archive checksum changed: {relative_path.as_posix()} ({actual_hash})",
                    )

            writable_files = [
                path.relative_to(archive_root).as_posix()
                for path in archive_root.rglob("*")
                if path.is_file() and not _is_read_only(path)
            ]
            report.check(
                reference.get("runtime_archive_read_only") is True
                and not writable_files,
                "Every file in the local runtime archive is read-only.",
                f"Runtime archive contains writable files: {writable_files[:8]}",
            )

            asset_contract = reference.get("acceptance_runtime_asset_set")
            if not isinstance(asset_contract, dict):
                report.check(False, "", "Acceptance runtime asset-set contract is missing.")
            else:
                try:
                    path_count, total_bytes, aggregate_hash = (
                        _acceptance_asset_fingerprint(archive_root, asset_contract)
                    )
                except Exception as exc:
                    report.check(False, "", f"Cannot fingerprint acceptance runtime assets: {exc}")
                else:
                    report.check(
                        path_count == int(asset_contract.get("expected_path_count") or -1),
                        f"Acceptance runtime asset set contains {path_count} declared files.",
                        f"Acceptance runtime asset count changed: {path_count}.",
                    )
                    report.check(
                        total_bytes == int(asset_contract.get("expected_total_bytes") or -1),
                        f"Acceptance runtime asset bytes match ({total_bytes}).",
                        f"Acceptance runtime asset size changed: {total_bytes}.",
                    )
                    report.check(
                        aggregate_hash == str(asset_contract.get("aggregate_sha256") or ""),
                        "Acceptance runtime asset aggregate checksum matches.",
                        f"Acceptance runtime aggregate checksum changed: {aggregate_hash}.",
                    )

    if args.remote:
        try:
            remote_refs = _remote_refs(reference)
        except Exception as exc:
            report.check(False, "", f"Cannot verify remote frozen refs: {exc}")
        else:
            for ref_name in (
                f"refs/heads/{EXPECTED_SOURCE_BRANCH}",
                f"refs/heads/{EXPECTED_FROZEN_BRANCH}",
                f"refs/tags/{EXPECTED_FROZEN_TAG}",
            ):
                report.check(
                    remote_refs.get(ref_name) == EXPECTED_COMMIT,
                    f"Remote {ref_name} resolves to the frozen commit.",
                    f"Remote {ref_name} resolves to {remote_refs.get(ref_name)!r}.",
                )
    else:
        report.notes.append("Remote ref check skipped; run with --remote during publication.")

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
