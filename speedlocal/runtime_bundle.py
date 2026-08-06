from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import threading
import uuid
import zipfile
from collections.abc import Callable, MutableMapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .paths import GENERATED_RUNTIME_ROOT_ENV


V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
RUNTIME_BUNDLE_URL_ENV = "SPEEDLOCAL_RUNTIME_BUNDLE_URL"
RUNTIME_CACHE_ROOT_ENV = "SPEEDLOCAL_RUNTIME_CACHE_ROOT"
RUNTIME_BUNDLE_SHA_ENV = "SPEEDLOCAL_RUNTIME_BUNDLE_SHA256"
DEFAULT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "runtime"
    / "manifests"
    / "trondelag"
    / "v2-final-runtime-r7-2026-08-06.1.json"
)

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_FILE_COUNT = 512
DOWNLOAD_TIMEOUT_SECONDS = 120
DOWNLOAD_CHUNK_BYTES = 1024 * 1024

Downloader = Callable[[str, Path, int, str], None]

_MATERIALIZE_LOCK = threading.Lock()


def _configure_runtime_roots(
    environment: MutableMapping[str, str],
    root: Path,
    archive_sha256: str | None = None,
) -> None:
    environment[V2_SOURCE_ROOT_ENV] = str(root)
    if not str(environment.get(GENERATED_RUNTIME_ROOT_ENV, "") or "").strip():
        environment[GENERATED_RUNTIME_ROOT_ENV] = str(root)
    if archive_sha256 is not None:
        environment[RUNTIME_BUNDLE_SHA_ENV] = str(archive_sha256)


class RuntimeBundleError(RuntimeError):
    """Safe, machine-classified failure while preparing runtime data."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        super().__init__(message or self.code)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_hex_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _safe_relative_path(value: Any) -> str:
    text = str(value or "")
    if (
        not text
        or "\x00" in text
        or "\\" in text
        or text.startswith("/")
        or text.endswith("/")
    ):
        raise RuntimeBundleError("contract_invalid_path")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or str(path) != text
        or any(part in {"", ".", ".."} or ":" in part for part in path.parts)
    ):
        raise RuntimeBundleError("contract_invalid_path")
    return text


def _load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeBundleError("contract_unavailable") from exc
    if not isinstance(value, dict):
        raise RuntimeBundleError("contract_invalid")
    bundle_id = str(value.get("bundle_id") or "")
    if (
        value.get("schema_version") != "1.0"
        or value.get("logical_provider") != "v2_archive"
        or value.get("region_id") != "trondelag"
        or not bundle_id
        or "/" in bundle_id
        or "\\" in bundle_id
        or ":" in bundle_id
    ):
        raise RuntimeBundleError("contract_identity_invalid")

    archive = value.get("archive")
    release = value.get("release")
    files = value.get("files")
    if not isinstance(archive, dict) or not isinstance(release, dict) or not isinstance(files, list):
        raise RuntimeBundleError("contract_invalid")
    if value.get("source_root_env") != V2_SOURCE_ROOT_ENV:
        raise RuntimeBundleError("contract_invalid")

    try:
        archive_bytes = int(archive["bytes"])
        file_count = int(archive["file_count"])
        expanded_bytes = int(archive["uncompressed_bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeBundleError("contract_invalid") from exc
    if (
        archive.get("format") != "zip"
        or archive_bytes <= 0
        or archive_bytes > MAX_ARCHIVE_BYTES
        or file_count <= 0
        or file_count > MAX_FILE_COUNT
        or expanded_bytes <= 0
        or expanded_bytes > MAX_EXPANDED_BYTES
        or not _is_hex_sha256(archive.get("sha256"))
    ):
        raise RuntimeBundleError("contract_invalid")

    root_prefix = _safe_relative_path(archive.get("root_prefix"))
    if "/" in root_prefix:
        raise RuntimeBundleError("contract_invalid")

    expected_paths: set[str] = set()
    expected_casefold: set[str] = set()
    total_bytes = 0
    aggregate = hashlib.sha256()
    normalized_files: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            raise RuntimeBundleError("contract_invalid")
        relative = _safe_relative_path(item.get("path"))
        folded = relative.casefold()
        if relative in expected_paths or folded in expected_casefold:
            raise RuntimeBundleError("contract_duplicate_path")
        try:
            size = int(item["bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeBundleError("contract_invalid") from exc
        file_hash = str(item.get("sha256") or "")
        if size < 0 or not _is_hex_sha256(file_hash):
            raise RuntimeBundleError("contract_invalid")
        expected_paths.add(relative)
        expected_casefold.add(folded)
        total_bytes += size
        normalized_files.append(
            {
                "path": relative,
                "bytes": size,
                "sha256": file_hash,
            }
        )

    for item in sorted(normalized_files, key=lambda current: current["path"]):
        aggregate.update(item["path"].encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(item["sha256"].encode("ascii"))
        aggregate.update(b"\n")

    aggregate_contract = value.get("content_aggregate")
    if (
        len(normalized_files) != file_count
        or int(value.get("file_count") or -1) != file_count
        or total_bytes != expanded_bytes
        or int(value.get("total_uncompressed_bytes") or -1) != expanded_bytes
        or not isinstance(aggregate_contract, dict)
        or aggregate.hexdigest() != str(aggregate_contract.get("sha256") or "")
    ):
        raise RuntimeBundleError("contract_inventory_mismatch")

    assets = release.get("assets")
    base_url = str(release.get("asset_download_base_url") or "").rstrip("/")
    if not isinstance(assets, dict) or not base_url or not assets.get("archive"):
        raise RuntimeBundleError("contract_invalid")

    normalized = dict(value)
    normalized["archive"] = dict(archive)
    normalized["archive"]["root_prefix"] = root_prefix
    normalized["archive"]["bytes"] = archive_bytes
    normalized["archive"]["file_count"] = file_count
    normalized["archive"]["uncompressed_bytes"] = expanded_bytes
    normalized["files"] = normalized_files
    normalized["_download_url"] = f"{base_url}/{assets['archive']}"
    return normalized


def _validate_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise RuntimeBundleError("download_url_invalid")


def _download_https(
    url: str,
    destination: Path,
    expected_bytes: int,
    expected_sha256: str,
) -> None:
    _validate_https_url(url)
    digest = hashlib.sha256()
    written = 0
    request = Request(url, headers={"User-Agent": "speedlocal-runtime/1"})
    try:
        with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            _validate_https_url(str(response.geturl()))
            with destination.open("xb") as output:
                while True:
                    block = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not block:
                        break
                    written += len(block)
                    if written > expected_bytes or written > MAX_ARCHIVE_BYTES:
                        raise RuntimeBundleError("archive_size_mismatch")
                    digest.update(block)
                    output.write(block)
    except RuntimeBundleError:
        raise
    except Exception:
        raise RuntimeBundleError("download_failed") from None
    if written != expected_bytes:
        raise RuntimeBundleError("archive_size_mismatch")
    if digest.hexdigest() != expected_sha256:
        raise RuntimeBundleError("archive_checksum_mismatch")


def _verify_archive(path: Path, contract: dict[str, Any]) -> None:
    archive = contract["archive"]
    try:
        actual_bytes = path.stat().st_size
    except OSError:
        raise RuntimeBundleError("archive_unavailable") from None
    if actual_bytes != archive["bytes"] or actual_bytes > MAX_ARCHIVE_BYTES:
        raise RuntimeBundleError("archive_size_mismatch")
    try:
        actual_hash = _sha256_file(path)
    except OSError:
        raise RuntimeBundleError("archive_unavailable") from None
    if actual_hash != archive["sha256"]:
        raise RuntimeBundleError("archive_checksum_mismatch")


def _zip_member_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _inventory_by_path(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["path"]): item for item in contract["files"]}


def _extract_verified_archive(
    archive_path: Path,
    destination: Path,
    contract: dict[str, Any],
) -> None:
    inventory = _inventory_by_path(contract)
    root_prefix = str(contract["archive"]["root_prefix"])
    expected_members = {
        f"{root_prefix}/{relative}": item for relative, item in inventory.items()
    }
    seen: set[str] = set()
    seen_casefold: set[str] = set()

    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeBundleError("archive_invalid_zip") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) != len(expected_members) or len(infos) > MAX_FILE_COUNT:
            raise RuntimeBundleError("archive_inventory_mismatch")
        total_bytes = 0
        for info in infos:
            name = str(getattr(info, "orig_filename", info.filename))
            if (
                info.is_dir()
                or info.flag_bits & 0x1
                or "\\" in name
                or name.startswith("/")
                or name.endswith("/")
            ):
                raise RuntimeBundleError("archive_unsafe_member")
            try:
                safe_name = _safe_relative_path(name)
            except RuntimeBundleError as exc:
                raise RuntimeBundleError("archive_unsafe_member") from exc
            folded = safe_name.casefold()
            if safe_name in seen or folded in seen_casefold:
                raise RuntimeBundleError("archive_duplicate_member")
            seen.add(safe_name)
            seen_casefold.add(folded)

            mode = _zip_member_mode(info)
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG}:
                raise RuntimeBundleError("archive_unsafe_member")
            expected = expected_members.get(safe_name)
            if expected is None or info.file_size != expected["bytes"]:
                raise RuntimeBundleError("archive_inventory_mismatch")
            total_bytes += info.file_size
            if total_bytes > contract["archive"]["uncompressed_bytes"]:
                raise RuntimeBundleError("archive_expanded_size_mismatch")

        if seen != set(expected_members):
            raise RuntimeBundleError("archive_inventory_mismatch")
        if total_bytes != contract["archive"]["uncompressed_bytes"]:
            raise RuntimeBundleError("archive_expanded_size_mismatch")

        destination.mkdir(parents=True, exist_ok=False)
        for member_name in sorted(seen):
            expected = expected_members[member_name]
            relative = member_name[len(root_prefix) + 1 :]
            output_path = destination.joinpath(*PurePosixPath(relative).parts)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            written = 0
            try:
                with archive.open(member_name, "r") as source, output_path.open("xb") as output:
                    while True:
                        block = source.read(DOWNLOAD_CHUNK_BYTES)
                        if not block:
                            break
                        written += len(block)
                        if written > expected["bytes"]:
                            raise RuntimeBundleError("archive_inventory_mismatch")
                        digest.update(block)
                        output.write(block)
            except RuntimeBundleError:
                raise
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise RuntimeBundleError("archive_extraction_failed") from exc
            if written != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
                raise RuntimeBundleError("runtime_file_checksum_mismatch")
            try:
                output_path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            except OSError:
                pass


def _verify_runtime_root(root: Path, contract: dict[str, Any]) -> None:
    try:
        if not root.is_dir():
            raise RuntimeBundleError("runtime_root_missing")
        expected = _inventory_by_path(contract)
        seen: set[str] = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise RuntimeBundleError("runtime_cache_invalid")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            seen.add(relative)
            item = expected.get(relative)
            if (
                item is None
                or path.stat().st_size != item["bytes"]
                or _sha256_file(path) != item["sha256"]
            ):
                raise RuntimeBundleError("runtime_cache_invalid")
        if seen != set(expected):
            raise RuntimeBundleError("runtime_cache_invalid")
    except RuntimeBundleError:
        raise
    except OSError:
        raise RuntimeBundleError("runtime_cache_unreadable") from None


def _validate_explicit_root(
    root: Path,
    contract: dict[str, Any],
) -> None:
    if not root.is_dir():
        raise RuntimeBundleError("explicit_source_root_invalid")
    for item in contract["files"]:
        relative = str(item["path"])
        candidate = root.joinpath(*PurePosixPath(relative).parts)
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            raise RuntimeBundleError("explicit_source_root_incomplete") from None
        try:
            valid = (
                not candidate.is_symlink()
                and resolved.is_file()
                and resolved.stat().st_size == item["bytes"]
                and _sha256_file(resolved) == item["sha256"]
            )
        except OSError:
            valid = False
        if not valid:
            raise RuntimeBundleError("explicit_source_root_incomplete")


def _cache_marker_matches(marker_path: Path, contract: dict[str, Any]) -> bool:
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(marker, dict)
        and marker.get("bundle_id") == contract.get("bundle_id")
        and marker.get("archive_sha256") == contract["archive"]["sha256"]
        and marker.get("content_sha256")
        == (contract.get("content_aggregate") or {}).get("sha256")
    )


def _validated_cache_root(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve()
    except OSError:
        raise RuntimeBundleError("cache_root_unavailable") from None
    if not resolved.is_dir():
        raise RuntimeBundleError("cache_root_unavailable")
    return resolved


def _remove_cache_entry(path: Path, cache_root: Path) -> None:
    try:
        resolved = path.resolve()
        resolved.relative_to(cache_root)
    except (OSError, ValueError) as exc:
        raise RuntimeBundleError("cache_path_invalid") from exc
    if resolved == cache_root:
        raise RuntimeBundleError("cache_path_invalid")
    if resolved.exists():
        def make_writable_and_retry(
            function: Callable[[str], None],
            value: str,
            _: Any,
        ) -> None:
            mode = stat.S_IRUSR | stat.S_IWUSR
            if os.path.isdir(value):
                mode |= stat.S_IXUSR
            os.chmod(value, mode)
            function(value)

        try:
            shutil.rmtree(resolved, onerror=make_writable_and_retry)
        except OSError:
            raise RuntimeBundleError("cache_cleanup_failed") from None


def _existing_cache_root(final_dir: Path, contract: dict[str, Any]) -> Path | None:
    data_root = final_dir / "data"
    marker = final_dir / "complete.json"
    if not _cache_marker_matches(marker, contract):
        return None
    try:
        _verify_runtime_root(data_root, contract)
    except RuntimeBundleError:
        return None
    return data_root


def ensure_v2_source_root(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    *,
    environ: MutableMapping[str, str] | None = None,
    cache_root: Path | None = None,
    downloader: Downloader | None = None,
) -> Path:
    """Return a verified V2 root and configure it for all existing resolvers."""

    environment = os.environ if environ is None else environ
    configured = str(environment.get(V2_SOURCE_ROOT_ENV, "") or "").strip()
    configured_bundle_sha = str(
        environment.get(RUNTIME_BUNDLE_SHA_ENV, "") or ""
    ).strip()
    contract: dict[str, Any] | None = None
    if configured:
        try:
            root = Path(configured).expanduser().resolve()
        except OSError:
            raise RuntimeBundleError("explicit_source_root_invalid") from None
        if not configured_bundle_sha:
            contract = _load_contract(Path(contract_path))
            _validate_explicit_root(root, contract)
            _configure_runtime_roots(environment, root)
            return root

        if contract is None:
            contract = _load_contract(Path(contract_path))
        if configured_bundle_sha == str(contract["archive"]["sha256"]):
            try:
                _verify_runtime_root(root, contract)
            except RuntimeBundleError:
                pass
            else:
                _configure_runtime_roots(
                    environment,
                    root,
                    str(contract["archive"]["sha256"]),
                )
                return root
        environment.pop(V2_SOURCE_ROOT_ENV, None)
        environment.pop(RUNTIME_BUNDLE_SHA_ENV, None)

    if contract is None:
        contract = _load_contract(Path(contract_path))
    archive = contract["archive"]
    selected_url = str(
        environment.get(RUNTIME_BUNDLE_URL_ENV, "") or contract["_download_url"]
    ).strip()
    _validate_https_url(selected_url)

    if cache_root is None:
        configured_cache = str(environment.get(RUNTIME_CACHE_ROOT_ENV, "") or "").strip()
        cache_root = (
            Path(configured_cache).expanduser()
            if configured_cache
            else Path(tempfile.gettempdir()) / "speedlocal-runtime"
        )
    resolved_cache = _validated_cache_root(Path(cache_root))
    final_dir = resolved_cache / str(archive["sha256"])[:20]

    with _MATERIALIZE_LOCK:
        existing = _existing_cache_root(final_dir, contract)
        if existing is not None:
            _configure_runtime_roots(
                environment,
                existing,
                str(archive["sha256"]),
            )
            return existing
        try:
            if final_dir.exists():
                _remove_cache_entry(final_dir, resolved_cache)
        except OSError:
            raise RuntimeBundleError("cache_cleanup_failed") from None

        stage = resolved_cache / f".stg-{uuid.uuid4().hex[:12]}"
        archive_path = stage / "runtime.zip"
        data_root = stage / "data"
        try:
            stage.mkdir(parents=False, exist_ok=False)
        except OSError:
            raise RuntimeBundleError("cache_staging_failed") from None
        try:
            active_downloader = downloader or _download_https
            active_downloader(
                selected_url,
                archive_path,
                int(archive["bytes"]),
                str(archive["sha256"]),
            )
            _verify_archive(archive_path, contract)
            _extract_verified_archive(archive_path, data_root, contract)
            _verify_runtime_root(data_root, contract)
            archive_path.unlink()
            marker = {
                "bundle_id": contract["bundle_id"],
                "archive_sha256": archive["sha256"],
                "content_sha256": contract["content_aggregate"]["sha256"],
            }
            (stage / "complete.json").write_text(
                json.dumps(marker, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            concurrent = _existing_cache_root(final_dir, contract)
            if concurrent is not None:
                _configure_runtime_roots(
                    environment,
                    concurrent,
                    str(archive["sha256"]),
                )
                return concurrent
            try:
                # os.replace() rejects directory promotion on some Windows
                # volumes even when the destination does not exist. rename()
                # is atomic on the same volume and preserves the intended
                # fail-if-another-process-won behavior for a populated target.
                os.rename(stage, final_dir)
            except OSError:
                concurrent = _existing_cache_root(final_dir, contract)
                if concurrent is None:
                    raise RuntimeBundleError("cache_promotion_failed")
                _configure_runtime_roots(
                    environment,
                    concurrent,
                    str(archive["sha256"]),
                )
                return concurrent
            installed = _existing_cache_root(final_dir, contract)
            if installed is None:
                raise RuntimeBundleError("runtime_cache_invalid")
            _configure_runtime_roots(
                environment,
                installed,
                str(archive["sha256"]),
            )
            return installed
        except RuntimeBundleError:
            raise
        except Exception:
            raise RuntimeBundleError("runtime_materialization_failed") from None
        finally:
            if stage.exists():
                _remove_cache_entry(stage, resolved_cache)
