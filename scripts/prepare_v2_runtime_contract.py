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
    / "v2-final-runtime-r7-2026-08-04.1.json"
)
OUTPUT_CONTRACT = (
    ROOT
    / "data"
    / "runtime"
    / "manifests"
    / "trondelag"
    / "v2-final-runtime-r7-2026-08-06.1.json"
)
VERSION = "2026-08-06.1"
GENERATED_PATHS = (
    "data/generated/eligible_surface/trondelag_onshore_land_r7.geojson",
    "data/generated/eligible_surface/trondelag_onshore_land_r6.geojson",
    "data/generated/eligible_surface/trondelag_onshore_land_r5.geojson",
    "data/generated/eligible_surface/trondelag_onshore_land_metadata.json",
)
SOURCE_PATHS = (
    "data/processed/trondelag/mask/trondelag_land_region_mask_wgs84.geojson",
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


def _file_entry(root: Path, relative: str, role: str) -> dict[str, Any]:
    source = root.joinpath(*Path(relative).parts)
    if not source.is_file():
        raise SystemExit(f"Runtime file is missing: {relative}")
    return {
        "role": role,
        "path": relative,
        "bytes": source.stat().st_size,
        "sha256": _sha256(source),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the tracked Trøndelag runtime contract from the prior "
            "reviewed bundle plus the eligible-surface source and artifacts."
        )
    )
    parser.add_argument("--base-contract", type=Path, default=BASE_CONTRACT)
    parser.add_argument("--generated-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
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
    source_root = args.source_root.expanduser().resolve()
    output_path = args.output_contract.expanduser().resolve()
    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite contract: {output_path}")
    for label, root in (
        ("Generated root", generated_root),
        ("Source root", source_root),
    ):
        if not root.is_dir():
            raise SystemExit(f"{label} does not exist: {root}")

    contract = json.loads(base_path.read_text(encoding="utf-8"))
    identity = f"speedlocal-v2-final-runtime-trondelag-r7-{VERSION}"
    release_tag = f"v2-final-runtime-trondelag-r7-{VERSION}"
    contract["bundle_id"] = identity
    contract["bundle_version"] = VERSION
    contract["release"].update(
        {
            "tag": release_tag,
            "title": f"SpeedLocal V2 Final — Trøndelag R7 runtime — {VERSION}",
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

    replaced_paths = set(GENERATED_PATHS) | set(SOURCE_PATHS)
    files = [
        dict(item)
        for item in contract["files"]
        if str(item.get("path")) not in replaced_paths
    ]
    for relative in GENERATED_PATHS:
        role = (
            "eligible_surface_evidence"
            if relative.endswith("_metadata.json")
            else "eligible_surface_geometry"
        )
        files.append(_file_entry(generated_root, relative, role))
    for relative in SOURCE_PATHS:
        files.append(_file_entry(source_root, relative, "eligible_surface_source"))

    total_bytes = sum(int(item["bytes"]) for item in files)
    contract["files"] = files
    contract["file_count"] = len(files)
    contract["total_uncompressed_bytes"] = total_bytes
    contract["archive"]["file_count"] = len(files)
    contract["archive"]["uncompressed_bytes"] = total_bytes
    contract["archive"]["bytes"] = None
    contract["archive"]["sha256"] = ""
    contract["content_aggregate"]["sha256"] = _aggregate(files)
    contract["source"]["reviewed_utc_date"] = "2026-08-06"
    contract["source"]["note"] = (
        "The 2026-08-04 reviewed runtime remains the byte authority for its "
        "48 files. This revision adds the checksum-pinned Trøndelag onshore "
        "land mask plus reproducible R7/R6/R5 eligible-surface artifacts."
    )
    contract["eligible_surface_evidence"] = {
        "surface_id": "onshore_land",
        "technologies": ["wind", "solar"],
        "analysis_resolution": 7,
        "derived_resolutions": [6, 5],
        "geometry_operation": "analysis_cell intersection onshore_land_mask",
        "water_policy": "exclude_sea_retain_inland_water",
        "outside_region_policy": "exclude",
        "source_paths": list(SOURCE_PATHS),
        "generated_paths": list(GENERATED_PATHS),
        "expected_total_area_km2": 41826.93063562673,
        "known_limitation": (
            "The reviewed mask excludes sea but retains inland water; a later "
            "hydrographic refinement may exclude lakes and rivers."
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
