from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal.paths import resolve_source_path  # noqa: E402
from speedlocal.runtime_bundle import (  # noqa: E402
    MAX_EXPANDED_BYTES,
    MAX_FILE_COUNT,
    RUNTIME_BUNDLE_SHA_ENV,
    RuntimeBundleError,
    ensure_v2_source_root,
)


URL = "https://example.invalid/runtime.zip"
PREFIX = "tiny-runtime"
FILES = {
    "data/value.txt": b"abc",
    "regions/trondelag/region.json": b"{}\n",
}
RELEASE_CONTRACT = (
    ROOT
    / "data"
    / "runtime"
    / "manifests"
    / "trondelag"
    / "v2-final-runtime-r7-2026-07-30.1.json"
)


class Report:
    def __init__(self) -> None:
        self.passes: list[str] = []
        self.failures: list[str] = []

    def check(self, condition: bool, ok: str, fail: str) -> None:
        (self.passes if condition else self.failures).append(ok if condition else fail)

    def emit(self) -> int:
        print("SpeedLocal runtime bundle validation")
        print("=" * 36)
        print("\nBLOCKERS")
        if self.failures:
            for index, item in enumerate(self.failures, start=1):
                print(f"{index}. FAIL {item}")
        else:
            print("None")
        print("\nCHECKS")
        for item in self.passes:
            print(f"- PASS {item}")
        status = "FAIL" if self.failures else "PASS"
        print(
            f"\nRESULT: {status} "
            f"({len(self.passes)} passed, {len(self.failures)} blocker(s))"
        )
        return 1 if self.failures else 0


class CopyDownloader:
    def __init__(
        self,
        archive: Path,
        *,
        delay: float = 0.0,
        failure: Exception | None = None,
    ) -> None:
        self.archive = archive
        self.delay = delay
        self.failure = failure
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(
        self,
        url: str,
        destination: Path,
        expected_bytes: int,
        expected_sha256: str,
    ) -> None:
        del url, expected_bytes, expected_sha256
        with self._lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.failure is not None:
            raise self.failure
        shutil.copyfile(self.archive, destination)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aggregate(files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda current: current["path"]):
        digest.update(item["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(item["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _write_case(
    directory: Path,
    *,
    members: list[tuple[str, bytes, int]] | None = None,
    contract_transform: Any = None,
) -> tuple[Path, Path]:
    archive_path = directory / "runtime.zip"
    file_entries = [
        {
            "path": path,
            "bytes": len(content),
            "sha256": _sha256_bytes(content),
        }
        for path, content in sorted(FILES.items())
    ]
    if members is None:
        members = [
            (f"{PREFIX}/{path}", content, stat.S_IFREG | 0o644)
            for path, content in sorted(FILES.items())
        ]
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for name, content, mode in members:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, content)

    contract = {
        "schema_version": "1.0",
        "bundle_id": "tiny-runtime-test",
        "logical_provider": "v2_archive",
        "region_id": "trondelag",
        "source_root_env": "SPEEDLOCAL_V2_SOURCE_ROOT",
        "release": {
            "asset_download_base_url": "https://example.invalid/releases",
            "assets": {"archive": "runtime.zip"},
        },
        "archive": {
            "format": "zip",
            "root_prefix": PREFIX,
            "file_count": len(file_entries),
            "uncompressed_bytes": sum(item["bytes"] for item in file_entries),
            "bytes": archive_path.stat().st_size,
            "sha256": _sha256_file(archive_path),
        },
        "content_aggregate": {"sha256": _aggregate(file_entries)},
        "file_count": len(file_entries),
        "total_uncompressed_bytes": sum(item["bytes"] for item in file_entries),
        "files": file_entries,
    }
    if contract_transform is not None:
        contract_transform(contract)
    contract_path = directory / "contract.json"
    contract_path.write_text(
        json.dumps(contract, indent=2) + "\n",
        encoding="utf-8",
    )
    return contract_path, archive_path


def _failure_code(call: Any) -> str | None:
    try:
        call()
    except RuntimeBundleError as exc:
        return exc.code
    return None


def _chmod_writable(path: Path) -> None:
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--release-archive",
        type=Path,
        default=None,
        help="Also materialize and validate the real untracked release ZIP.",
    )
    args = parser.parse_args()
    report = Report()

    with tempfile.TemporaryDirectory(prefix="speedlocal-bundle-local-") as value:
        work = Path(value)
        contract, archive = _write_case(work)
        root = work / "explicit"
        for relative, content in FILES.items():
            candidate = root.joinpath(*Path(relative).parts)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(content)
        (root / "allowed-extra.txt").write_text("extra\n", encoding="utf-8")
        environment = {"SPEEDLOCAL_V2_SOURCE_ROOT": str(root)}
        downloader = CopyDownloader(archive, failure=AssertionError())
        resolved = ensure_v2_source_root(
            contract,
            environ=environment,
            downloader=downloader,
        )
        report.check(
            resolved == root.resolve() and downloader.calls == 0,
            "A valid explicit local V2 root bypasses remote materialization.",
            "A valid explicit local V2 root did not bypass the downloader.",
        )

        invalid_environment = {
            "SPEEDLOCAL_V2_SOURCE_ROOT": str(root / "missing")
        }
        code = _failure_code(
            lambda: ensure_v2_source_root(
                contract,
                environ=invalid_environment,
                downloader=downloader,
            )
        )
        report.check(
            code == "explicit_source_root_invalid" and downloader.calls == 0,
            "An invalid explicit root fails without a silent remote fallback.",
            f"Invalid explicit-root handling drifted: {code!r}.",
        )
        incomplete_environment = {
            "SPEEDLOCAL_V2_SOURCE_ROOT": str(work / "empty")
        }
        (work / "empty").mkdir()
        code = _failure_code(
            lambda: ensure_v2_source_root(
                contract,
                environ=incomplete_environment,
                downloader=downloader,
            )
        )
        report.check(
            code == "explicit_source_root_incomplete" and downloader.calls == 0,
            "An existing but incomplete explicit root fails closed.",
            f"Incomplete explicit-root handling drifted: {code!r}.",
        )
        tampered = work / "tampered"
        shutil.copytree(root, tampered)
        (tampered / "data" / "value.txt").write_bytes(b"bad")
        code = _failure_code(
            lambda: ensure_v2_source_root(
                contract,
                environ={"SPEEDLOCAL_V2_SOURCE_ROOT": str(tampered)},
                downloader=downloader,
            )
        )
        report.check(
            code == "explicit_source_root_incomplete" and downloader.calls == 0,
            "A tampered explicit root fails without a remote fallback.",
            f"Tampered explicit-root handling drifted: {code!r}.",
        )

    with tempfile.TemporaryDirectory(prefix="speedlocal-bundle-valid-") as value:
        work = Path(value)
        contract, archive = _write_case(work)
        cache = work / "cache"
        downloader = CopyDownloader(archive)
        first_environment: dict[str, str] = {}
        installed = ensure_v2_source_root(
            contract,
            environ=first_environment,
            cache_root=cache,
            downloader=downloader,
        )
        report.check(
            downloader.calls == 1
            and first_environment.get("SPEEDLOCAL_V2_SOURCE_ROOT")
            == str(installed)
            and all(
                installed.joinpath(*Path(path).parts).read_bytes() == content
                for path, content in FILES.items()
            ),
            "Cold materialization verifies, installs, and configures the bundle.",
            "Cold materialization did not produce the exact configured runtime.",
        )

        disabled = CopyDownloader(
            archive,
            failure=AssertionError("warm cache must not download"),
        )
        warm_environment: dict[str, str] = {}
        warm = ensure_v2_source_root(
            contract,
            environ=warm_environment,
            cache_root=cache,
            downloader=disabled,
        )
        report.check(
            warm == installed and disabled.calls == 0,
            "A valid warm cache is reused without downloading.",
            "Warm-cache reuse unexpectedly downloaded or changed roots.",
        )

        damaged = installed / "data" / "value.txt"
        _chmod_writable(damaged)
        damaged.write_bytes(b"bad")
        repair = CopyDownloader(archive)
        repaired = ensure_v2_source_root(
            contract,
            environ=first_environment,
            cache_root=cache,
            downloader=repair,
        )
        report.check(
            repair.calls == 1
            and repaired.joinpath("data", "value.txt").read_bytes() == b"abc",
            "A corrupt managed cache is rejected and rebuilt in the same environment.",
            "A corrupt same-environment managed cache was reused or not repaired.",
        )

        confinement_environment = {
            "SPEEDLOCAL_V2_SOURCE_ROOT": str(repaired)
        }
        previous = dict()
        for key in ("SPEEDLOCAL_V2_SOURCE_ROOT",):
            previous[key] = os.environ.get(key)
            os.environ[key] = confinement_environment[key]
        try:
            confined = False
            try:
                resolve_source_path("v2_archive", "../escape.txt")
            except ValueError:
                confined = True
        finally:
            for key, old in previous.items():
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old
        report.check(
            confined,
            "The materialized provider root still rejects path escapes.",
            "Provider confinement failed for the materialized runtime.",
        )

    for label, transform, expected in (
        (
            "outer checksum",
            lambda contract: contract["archive"].update({"sha256": "0" * 64}),
            "archive_checksum_mismatch",
        ),
        (
            "outer byte count",
            lambda contract: contract["archive"].update(
                {"bytes": contract["archive"]["bytes"] + 1}
            ),
            "archive_size_mismatch",
        ),
    ):
        with tempfile.TemporaryDirectory(prefix="speedlocal-bundle-outer-") as value:
            work = Path(value)
            contract, archive = _write_case(work, contract_transform=transform)
            code = _failure_code(
                lambda: ensure_v2_source_root(
                    contract,
                    environ={},
                    cache_root=work / "cache",
                    downloader=CopyDownloader(archive),
                )
            )
            report.check(
                code == expected,
                f"A bad {label} is rejected.",
                f"Bad {label} produced {code!r}, expected {expected!r}.",
            )

    malicious_cases = [
        (
            "missing or extra member",
            [
                (
                    f"{PREFIX}/data/value.txt",
                    FILES["data/value.txt"],
                    stat.S_IFREG | 0o644,
                ),
                (
                    f"{PREFIX}/extra.txt",
                    b"{}\n",
                    stat.S_IFREG | 0o644,
                ),
            ],
            "archive_inventory_mismatch",
        ),
        (
            "tampered member",
            [
                (
                    f"{PREFIX}/{path}",
                    b"abd" if path == "data/value.txt" else content,
                    stat.S_IFREG | 0o644,
                )
                for path, content in sorted(FILES.items())
            ],
            "runtime_file_checksum_mismatch",
        ),
        (
            "path traversal",
            [
                (
                    f"{PREFIX}/../escape.txt",
                    FILES["data/value.txt"],
                    stat.S_IFREG | 0o644,
                ),
                (
                    f"{PREFIX}/regions/trondelag/region.json",
                    FILES["regions/trondelag/region.json"],
                    stat.S_IFREG | 0o644,
                ),
            ],
            "archive_unsafe_member",
        ),
        (
            "Windows separator",
            [
                (
                    f"{PREFIX}\\data\\value.txt",
                    FILES["data/value.txt"],
                    stat.S_IFREG | 0o644,
                ),
                (
                    f"{PREFIX}/regions/trondelag/region.json",
                    FILES["regions/trondelag/region.json"],
                    stat.S_IFREG | 0o644,
                ),
            ],
            "archive_unsafe_member",
        ),
        (
            "symbolic link",
            [
                (
                    f"{PREFIX}/data/value.txt",
                    FILES["data/value.txt"],
                    stat.S_IFLNK | 0o777,
                ),
                (
                    f"{PREFIX}/regions/trondelag/region.json",
                    FILES["regions/trondelag/region.json"],
                    stat.S_IFREG | 0o644,
                ),
            ],
            "archive_unsafe_member",
        ),
        (
            "case-fold collision",
            [
                (
                    f"{PREFIX}/data/value.txt",
                    FILES["data/value.txt"],
                    stat.S_IFREG | 0o644,
                ),
                (
                    f"{PREFIX}/DATA/VALUE.TXT",
                    FILES["regions/trondelag/region.json"],
                    stat.S_IFREG | 0o644,
                ),
            ],
            "archive_duplicate_member",
        ),
    ]
    for label, members, expected in malicious_cases:
        with tempfile.TemporaryDirectory(prefix="speedlocal-bundle-unsafe-") as value:
            work = Path(value)
            contract, archive = _write_case(work, members=members)
            if label == "Windows separator":
                archive_bytes = archive.read_bytes()
                normalized = b"tiny-runtime/data/value.txt"
                windows_name = b"tiny-runtime\\data\\value.txt"
                if normalized not in archive_bytes:
                    raise RuntimeError("Cannot create Windows-separator ZIP fixture.")
                archive.write_bytes(archive_bytes.replace(normalized, windows_name))
                contract_value = json.loads(contract.read_text(encoding="utf-8"))
                contract_value["archive"]["bytes"] = archive.stat().st_size
                contract_value["archive"]["sha256"] = _sha256_file(archive)
                contract.write_text(
                    json.dumps(contract_value, indent=2) + "\n",
                    encoding="utf-8",
                )
            code = _failure_code(
                lambda: ensure_v2_source_root(
                    contract,
                    environ={},
                    cache_root=work / "cache",
                    downloader=CopyDownloader(archive),
                )
            )
            report.check(
                code == expected,
                f"Archive {label} is rejected.",
                f"Archive {label} produced {code!r}, expected {expected!r}.",
            )

    for label, transform in (
        (
            "file-count cap",
            lambda contract: contract["archive"].update(
                {"file_count": MAX_FILE_COUNT + 1}
            ),
        ),
        (
            "expanded-byte cap",
            lambda contract: contract["archive"].update(
                {"uncompressed_bytes": MAX_EXPANDED_BYTES + 1}
            ),
        ),
    ):
        with tempfile.TemporaryDirectory(prefix="speedlocal-bundle-cap-") as value:
            work = Path(value)
            contract, archive = _write_case(work, contract_transform=transform)
            code = _failure_code(
                lambda: ensure_v2_source_root(
                    contract,
                    environ={},
                    cache_root=work / "cache",
                    downloader=CopyDownloader(archive),
                )
            )
            report.check(
                code == "contract_invalid",
                f"The contract {label} is enforced.",
                f"Contract {label} produced {code!r}.",
            )

    with tempfile.TemporaryDirectory(prefix="speedlocal-bundle-concurrent-") as value:
        work = Path(value)
        contract, archive = _write_case(work)
        downloader = CopyDownloader(archive, delay=0.05)
        environments = [{}, {}]
        with ThreadPoolExecutor(max_workers=2) as pool:
            roots = list(
                pool.map(
                    lambda environment: ensure_v2_source_root(
                        contract,
                        environ=environment,
                        cache_root=work / "cache",
                        downloader=downloader,
                    ),
                    environments,
                )
            )
        report.check(
            roots[0] == roots[1]
            and downloader.calls == 1
            and all(
                environment.get("SPEEDLOCAL_V2_SOURCE_ROOT") == str(roots[0])
                for environment in environments
            ),
            "Concurrent callers share one verified materialization.",
            "Concurrent callers downloaded twice or received different roots.",
        )

    with tempfile.TemporaryDirectory(prefix="speedlocal-bundle-redact-") as value:
        work = Path(value)
        contract, archive = _write_case(work)
        secret_url = "https://user:secret@example.invalid/runtime.zip?token=sensitive"
        try:
            ensure_v2_source_root(
                contract,
                environ={"SPEEDLOCAL_RUNTIME_BUNDLE_URL": secret_url},
                cache_root=work / "cache",
                downloader=CopyDownloader(
                    archive,
                    failure=RuntimeError(secret_url),
                ),
            )
        except RuntimeBundleError as exc:
            formatted = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            redacted = (
                "secret" not in str(exc)
                and "sensitive" not in str(exc)
                and "secret" not in formatted
                and "sensitive" not in formatted
                and exc.__cause__ is None
                and exc.code == "runtime_materialization_failed"
            )
        else:
            redacted = False
        report.check(
            redacted,
            "Runtime errors expose only a safe code, never URL credentials.",
            "A runtime error leaked a URL credential or used an unsafe code.",
        )

    if args.release_archive is not None:
        release_archive = args.release_archive.expanduser().resolve()
        with tempfile.TemporaryDirectory(
            prefix="speedlocal-release-artifact-"
        ) as value:
            environment: dict[str, str] = {}
            installed: Path | None = None
            try:
                installed = ensure_v2_source_root(
                    RELEASE_CONTRACT,
                    environ=environment,
                    cache_root=Path(value) / "cache",
                    downloader=CopyDownloader(release_archive),
                )
                release_contract = json.loads(
                    RELEASE_CONTRACT.read_text(encoding="utf-8")
                )
                actual_paths = {
                    path.relative_to(installed).as_posix()
                    for path in installed.rglob("*")
                    if path.is_file()
                }
                expected_paths = {
                    str(item["path"]) for item in release_contract["files"]
                }
                release_valid = (
                    actual_paths == expected_paths
                    and len(actual_paths) == 45
                    and environment.get("SPEEDLOCAL_V2_SOURCE_ROOT")
                    == str(installed)
                )
                previous_root = os.environ.get("SPEEDLOCAL_V2_SOURCE_ROOT")
                previous_sha = os.environ.get(RUNTIME_BUNDLE_SHA_ENV)
                os.environ["SPEEDLOCAL_V2_SOURCE_ROOT"] = str(installed)
                os.environ[RUNTIME_BUNDLE_SHA_ENV] = str(
                    release_contract["archive"]["sha256"]
                )
                try:
                    root_app = AppTest.from_file(
                        str(ROOT / "app.py"),
                        default_timeout=120,
                    )
                    root_app.query_params["region"] = "trondelag"
                    root_app.run(timeout=120)
                    root_app_valid = (
                        not list(root_app.exception)
                        and not list(root_app.error)
                        and any(
                            metric.label
                            == "Vind: genomsnittlig potential per analyscell"
                            for metric in root_app.metric
                        )
                    )
                finally:
                    if previous_root is None:
                        os.environ.pop("SPEEDLOCAL_V2_SOURCE_ROOT", None)
                    else:
                        os.environ["SPEEDLOCAL_V2_SOURCE_ROOT"] = previous_root
                    if previous_sha is None:
                        os.environ.pop(RUNTIME_BUNDLE_SHA_ENV, None)
                    else:
                        os.environ[RUNTIME_BUNDLE_SHA_ENV] = previous_sha
            except Exception:
                release_valid = False
                root_app_valid = False
            report.check(
                release_valid,
                "The real 45-file release ZIP safely materializes from its tracked contract.",
                "The real release ZIP does not match or safely materialize from its contract.",
            )
            report.check(
                root_app_valid,
                "The real root Streamlit entrypoint renders from the release bundle.",
                "The root Streamlit entrypoint failed against the release bundle.",
            )
            package_environment = os.environ.copy()
            if installed is not None:
                package_environment["SPEEDLOCAL_V2_SOURCE_ROOT"] = str(installed)
            package_environment.pop(RUNTIME_BUNDLE_SHA_ENV, None)
            for script_name, label in (
                (
                    "validate_trondelag_runtime_sources.py",
                    "Trøndelag runtime-source gate",
                ),
                (
                    "validate_v2_final_baseline_parity.py",
                    "V2 Final numeric baseline gate",
                ),
                (
                    "validate_v2_port_app.py",
                    "interactive 300-to-1000 m V2 Final gate",
                ),
            ):
                result = (
                    subprocess.run(
                        [
                            sys.executable,
                            "-B",
                            str(ROOT / "scripts" / script_name),
                        ],
                        cwd=ROOT,
                        env=package_environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if release_valid and installed is not None
                    else None
                )
                report.check(
                    result is not None and result.returncode == 0,
                    f"The release bundle passes the {label}.",
                    (
                        f"The release bundle failed the {label}: "
                        f"{(result.stderr or result.stdout)[-1200:]}"
                        if result is not None
                        else f"The release bundle could not run the {label}."
                    ),
                )

    return report.emit()


if __name__ == "__main__":
    raise SystemExit(main())
