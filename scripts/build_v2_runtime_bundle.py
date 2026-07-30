from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "data"
    / "runtime"
    / "manifests"
    / "trondelag"
    / "v2-final-runtime-r7-2026-07-30.1.json"
)
SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
CHUNK_BYTES = 1024 * 1024
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_linklike(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(details, "st_file_attributes", 0)
    return bool(path.is_symlink() or (reparse_flag and attributes & reparse_flag))


def _load_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Contract is not a JSON object: {path}")
    return value


def _relative_path(value: Any) -> str:
    text = str(value or "")
    path = PurePosixPath(text)
    if (
        not text
        or "\\" in text
        or path.is_absolute()
        or str(path) != text
        or any(part in {"", ".", ".."} or ":" in part for part in path.parts)
    ):
        raise ValueError(f"Unsafe bundle path: {text!r}")
    return text


def _asset_name(value: Any) -> str:
    text = str(value or "")
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or ":" in text
        or Path(text).name != text
    ):
        raise ValueError(f"Unsafe release asset name: {text!r}")
    return text


def _verify_source(
    source_root: Path,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    files = contract.get("files")
    if not isinstance(files, list):
        raise ValueError("Contract files must be a list.")
    normalized: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    total_bytes = 0
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Every file entry must be an object.")
        relative = _relative_path(item.get("path"))
        folded = relative.casefold()
        if relative in seen or folded in seen_casefold:
            raise ValueError(f"Duplicate or case-colliding path: {relative}")
        seen.add(relative)
        seen_casefold.add(folded)
        unresolved = source_root
        for part in PurePosixPath(relative).parts:
            unresolved /= part
            if _is_linklike(unresolved):
                raise ValueError(f"Runtime source traverses a link: {relative}")
        candidate = unresolved.resolve()
        candidate.relative_to(source_root)
        if not candidate.is_file():
            raise FileNotFoundError(f"Runtime source is missing: {relative}")
        expected_bytes = int(item["bytes"])
        expected_hash = str(item["sha256"])
        actual_bytes = candidate.stat().st_size
        actual_hash = _sha256(candidate)
        if actual_bytes != expected_bytes:
            raise ValueError(
                f"Runtime source size changed: {relative} "
                f"({actual_bytes} != {expected_bytes})"
            )
        if actual_hash != expected_hash:
            raise ValueError(
                f"Runtime source checksum changed: {relative} ({actual_hash})"
            )
        normalized.append(
            {
                "path": relative,
                "bytes": expected_bytes,
                "sha256": expected_hash,
                "source": candidate,
            }
        )
        total_bytes += expected_bytes

    for item in sorted(normalized, key=lambda current: current["path"]):
        aggregate.update(item["path"].encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(item["sha256"].encode("ascii"))
        aggregate.update(b"\n")

    archive = contract.get("archive") or {}
    aggregate_contract = contract.get("content_aggregate") or {}
    if len(normalized) != int(archive.get("file_count") or -1):
        raise ValueError("Runtime source file count does not match the contract.")
    if total_bytes != int(archive.get("uncompressed_bytes") or -1):
        raise ValueError("Runtime source byte total does not match the contract.")
    if aggregate.hexdigest() != str(aggregate_contract.get("sha256") or ""):
        raise ValueError("Runtime source aggregate checksum does not match.")
    return sorted(normalized, key=lambda current: current["path"])


def _build_zip(
    output_path: Path,
    root_prefix: str,
    files: list[dict[str, Any]],
) -> None:
    temporary = output_path.with_name(
        f".{output_path.name}.{os.getpid()}.tmp"
    )
    if temporary.exists():
        temporary.unlink()
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as archive:
            for item in files:
                member_name = f"{root_prefix}/{item['path']}"
                info = zipfile.ZipInfo(member_name, date_time=ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info._compresslevel = 9
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                with item["source"].open("rb") as source, archive.open(
                    info,
                    mode="w",
                    force_zip64=True,
                ) as destination:
                    shutil.copyfileobj(source, destination, length=CHUNK_BYTES)
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verify_built_zip(
    archive_path: Path,
    root_prefix: str,
    files: list[dict[str, Any]],
) -> None:
    expected = [
        (f"{root_prefix}/{item['path']}", item)
        for item in files
    ]
    with zipfile.ZipFile(archive_path, "r") as archive:
        infos = archive.infolist()
        if len(infos) != len(expected):
            raise ValueError("Built ZIP file count changed.")
        for info, (member_name, item) in zip(infos, expected, strict=True):
            raw_name = str(getattr(info, "orig_filename", info.filename))
            mode = (info.external_attr >> 16) & 0xFFFF
            if (
                raw_name != member_name
                or info.date_time != ZIP_TIMESTAMP
                or info.compress_type != zipfile.ZIP_DEFLATED
                or stat.S_IFMT(mode) != stat.S_IFREG
                or stat.S_IMODE(mode) != 0o644
                or info.flag_bits & 0x1
                or info.file_size != item["bytes"]
            ):
                raise ValueError(f"Built ZIP metadata changed: {member_name}")
            digest = hashlib.sha256()
            with archive.open(info, "r") as source:
                for block in iter(lambda: source.read(CHUNK_BYTES), b""):
                    digest.update(block)
            if digest.hexdigest() != item["sha256"]:
                raise ValueError(f"Built ZIP payload changed: {member_name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic, reviewed Trøndelag V2 Final runtime."
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="Tracked runtime contract.",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help=f"Reviewed V2 archive root; defaults to {SOURCE_ROOT_ENV}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "speedlocal-runtime-release",
        help="Untracked output directory for release assets.",
    )
    args = parser.parse_args()

    contract_path = args.contract.expanduser().resolve()
    contract = _load_contract(contract_path)
    configured_source = str(os.environ.get(SOURCE_ROOT_ENV, "") or "").strip()
    source_root_value = args.source_root or (
        Path(configured_source) if configured_source else None
    )
    if source_root_value is None:
        raise SystemExit(
            f"Set {SOURCE_ROOT_ENV} or pass --source-root."
        )
    source_input = source_root_value.expanduser()
    if _is_linklike(source_input):
        raise SystemExit("Runtime source root must not be a link or junction.")
    source_root = source_input.resolve()
    if not source_root.is_dir():
        raise SystemExit(f"Runtime source root does not exist: {source_root}")

    release = contract.get("release") or {}
    assets = release.get("assets") or {}
    archive_contract = contract.get("archive") or {}
    archive_name = _asset_name(assets.get("archive"))
    manifest_name = _asset_name(assets.get("manifest"))
    checksum_name = _asset_name(assets.get("checksums"))
    root_prefix = _relative_path(archive_contract.get("root_prefix"))
    if "/" in root_prefix:
        raise SystemExit("Release asset contract is incomplete.")

    files = _verify_source(source_root, contract)
    output_dir = args.output_dir.expanduser().resolve()
    overlaps_source = False
    try:
        output_dir.relative_to(source_root)
        overlaps_source = True
    except ValueError:
        pass
    try:
        source_root.relative_to(output_dir)
        overlaps_source = True
    except ValueError:
        pass
    if overlaps_source:
        raise SystemExit("Output directory must not overlap the runtime source.")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / archive_name
    manifest_path = output_dir / manifest_name
    checksum_path = output_dir / checksum_name
    existing = [
        path.name
        for path in (archive_path, manifest_path, checksum_path)
        if path.exists()
    ]
    if existing:
        raise SystemExit(
            "Refusing to overwrite release assets: " + ", ".join(existing)
        )

    with tempfile.TemporaryDirectory(
        prefix=".runtime-build-",
        dir=output_dir,
    ) as stage_value:
        stage = Path(stage_value)
        archive_candidate = stage / archive_name
        manifest_candidate = stage / manifest_name
        checksum_candidate = stage / checksum_name

        _build_zip(archive_candidate, root_prefix, files)
        _verify_built_zip(archive_candidate, root_prefix, files)
        archive_bytes = archive_candidate.stat().st_size
        archive_sha256 = _sha256(archive_candidate)

        declared_bytes = archive_contract.get("bytes")
        declared_sha256 = str(archive_contract.get("sha256") or "")
        if declared_bytes is not None and int(declared_bytes) != archive_bytes:
            raise SystemExit(
                f"Built ZIP size differs from tracked contract: "
                f"{archive_bytes} != {declared_bytes}"
            )
        if len(declared_sha256) == 64 and declared_sha256 != archive_sha256:
            raise SystemExit(
                f"Built ZIP checksum differs from tracked contract: {archive_sha256}"
            )

        release_manifest = json.loads(json.dumps(contract))
        release_manifest["archive"]["bytes"] = archive_bytes
        release_manifest["archive"]["sha256"] = archive_sha256
        manifest_candidate.write_bytes(
            (
                json.dumps(release_manifest, ensure_ascii=False, indent=2)
                + "\n"
            ).encode("utf-8")
        )
        manifest_sha256 = _sha256(manifest_candidate)
        checksum_candidate.write_bytes(
            (
                f"{archive_sha256}  {archive_name}\n"
                f"{manifest_sha256}  {manifest_name}\n"
            ).encode("ascii")
        )

        os.replace(archive_candidate, archive_path)
        os.replace(manifest_candidate, manifest_path)
        os.replace(checksum_candidate, checksum_path)

    summary = {
        "archive": str(archive_path),
        "archive_bytes": archive_bytes,
        "archive_sha256": archive_sha256,
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "checksums": str(checksum_path),
        "file_count": len(files),
        "uncompressed_bytes": sum(item["bytes"] for item in files),
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
