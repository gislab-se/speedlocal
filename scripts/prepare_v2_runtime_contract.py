from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_CONTRACT = (
    ROOT
    / "data"
    / "runtime"
    / "manifests"
    / "trondelag"
    / "v2-final-runtime-r7-2026-07-30.1.json"
)
OUTPUT_CONTRACT = (
    ROOT
    / "data"
    / "runtime"
    / "manifests"
    / "trondelag"
    / "v2-final-runtime-r7-2026-08-04.1.json"
)
VERSION = "2026-08-04.1"
GENERATED_PATHS = (
    "data/generated/population_r7/population_points.csv",
    "data/generated/population_r7/built_centre.csv",
    "data/generated/population_r7/built_low_selection.csv",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aggregate(files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda current: str(current["path"])):
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the tracked Trøndelag runtime contract from the prior "
            "reviewed bundle plus generated direct-R7 population tables."
        )
    )
    parser.add_argument("--base-contract", type=Path, default=BASE_CONTRACT)
    parser.add_argument("--generated-root", type=Path, required=True)
    parser.add_argument("--output-contract", type=Path, default=OUTPUT_CONTRACT)
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="Final deterministic ZIP whose byte count and hash should be pinned.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    base_path = args.base_contract.expanduser().resolve()
    generated_root = args.generated_root.expanduser().resolve()
    output_path = args.output_contract.expanduser().resolve()
    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite contract: {output_path}")
    if not generated_root.is_dir():
        raise SystemExit(f"Generated root does not exist: {generated_root}")

    contract = json.loads(base_path.read_text(encoding="utf-8"))
    identity = f"speedlocal-v2-final-runtime-trondelag-r7-{VERSION}"
    release_tag = f"v2-final-runtime-trondelag-r7-{VERSION}"
    contract["bundle_id"] = identity
    contract["bundle_version"] = VERSION
    contract["release"].update(
        {
            "tag": release_tag,
            "title": (
                "SpeedLocal V2 Final — Trøndelag R7 runtime — " + VERSION
            ),
            "url": f"https://github.com/gislab-se/speedlocal/releases/tag/{release_tag}",
            "asset_download_base_url": (
                "https://github.com/gislab-se/speedlocal/releases/download/"
                + release_tag
            ),
        }
    )
    contract["release"]["assets"] = {
        "archive": f"{identity}.zip",
        "manifest": f"{identity}.manifest.json",
        "checksums": f"{identity}.sha256",
    }
    contract["archive"]["root_prefix"] = identity

    generated_set = set(GENERATED_PATHS)
    files = [
        dict(item)
        for item in contract["files"]
        if str(item.get("path")) not in generated_set
    ]
    for relative in GENERATED_PATHS:
        source = generated_root.joinpath(*Path(relative).parts)
        if not source.is_file():
            raise SystemExit(f"Generated runtime file is missing: {relative}")
        files.append(
            {
                "role": "generated_distance_table",
                "path": relative,
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )
    contract["files"] = files
    total_bytes = sum(int(item["bytes"]) for item in files)
    contract["file_count"] = len(files)
    contract["total_uncompressed_bytes"] = total_bytes
    contract["archive"]["file_count"] = len(files)
    contract["archive"]["uncompressed_bytes"] = total_bytes
    contract["archive"]["bytes"] = None
    contract["archive"]["sha256"] = ""
    contract["content_aggregate"]["sha256"] = _aggregate(files)
    contract["source"]["reviewed_utc_date"] = "2026-08-04"
    contract["source"]["note"] = (
        "The 2026-07-30 reviewed runtime remains the byte authority for its "
        "45 files. This revision adds three reproducible direct-R7 population "
        "distance tables; R6 and R5 are derived from that declared R7 domain."
    )
    contract["population_distance_evidence"] = {
        "analysis_resolution": 7,
        "derived_resolutions": [6, 5],
        "semantics": (
            "representative-point distance plus full-cell source intersection"
        ),
        "generated_paths": list(GENERATED_PATHS),
        "accepted_drift": (
            "intentional replacement of frozen-V2 R8-to-R7 aggregation; "
            "quantified by scripts/analyze_direct_distance_drift.py"
        ),
    }

    if args.archive is not None:
        archive = args.archive.expanduser().resolve()
        if not archive.is_file():
            raise SystemExit(f"Archive does not exist: {archive}")
        contract["archive"]["bytes"] = archive.stat().st_size
        contract["archive"]["sha256"] = _sha256(archive)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "contract": str(output_path),
                "file_count": len(files),
                "uncompressed_bytes": total_bytes,
                "archive_pinned": args.archive is not None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
