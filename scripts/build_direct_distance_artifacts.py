from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speedlocal.catalogs import load_analysis, load_region
from speedlocal.geometry import build_direct_distance_artifact
from speedlocal.validation import validate_contract


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _id_set_sha256(cell_ids: list[str]) -> str:
    payload = "".join(f"{cell_id}\n" for cell_id in sorted(cell_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _format_distance(value: float) -> str:
    text = f"{value:.12f}".rstrip("0").rstrip(".")
    return text or "0"


def _output_path(output_dir: Path, name: str, overwrite: bool) -> Path:
    path = output_dir / name
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {path}. Pass --overwrite to replace it."
        )
    return path


def _write_csv(path: Path, artifact: Any) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("hex_id", "distance_m", "intersects"))
        for row in artifact.rows:
            writer.writerow(
                (
                    row.cell_id,
                    _format_distance(row.distance_m),
                    "true" if row.intersects else "false",
                )
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic source-to-analysis-cell distance artifacts "
            "from canonical manifest geometry."
        )
    )
    parser.add_argument("--region", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--layer",
        action="append",
        dest="layers",
        help="Optional layer id; repeat to build a subset of the group.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    try:
        output_dir.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError(
            "Generated distance artifacts must stay outside the Git workspace."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    region = load_region(args.region)
    contract = load_analysis(args.region, args.analysis)
    validate_contract(contract)
    if contract.analysis_domain is None:
        raise ValueError(
            f"{args.region}/{args.analysis} has no declared analysis domain."
        )
    group_layers = [
        layer
        for layer in contract.layers.values()
        if layer.group_id == args.group
    ]
    if not group_layers:
        raise KeyError(
            f"Group {args.group!r} has no layers in {args.region}/{args.analysis}."
        )
    requested = list(args.layers or [layer.id for layer in group_layers])
    if len(requested) != len(set(requested)):
        raise ValueError("Layer selections must be unique.")
    available = {layer.id: layer for layer in group_layers}
    unknown = set(requested) - set(available)
    if unknown:
        raise KeyError(
            f"Layers are not declared in group {args.group!r}: {sorted(unknown)}"
        )

    native_crs = str(region.get("native_crs") or "").strip()
    metadata: dict[str, Any] = {
        "schema_version": "1.0",
        "region_id": args.region,
        "analysis_id": args.analysis,
        "group_id": args.group,
        "analysis_resolution": contract.analysis_domain.resolution,
        "native_crs": native_crs,
        "distance_semantics": "analysis_cell_representative_point_to_source",
        "intersection_semantics": "full_analysis_cell_intersects_source",
        "layers": [],
    }
    print(
        f"Building {len(requested)} direct R{contract.analysis_domain.resolution} "
        f"distance artifact(s) in {output_dir}"
    )
    for layer_id in requested:
        print(f"- {layer_id}: building", flush=True)
        artifact = build_direct_distance_artifact(
            available[layer_id],
            analysis_domain=contract.analysis_domain,
            native_crs=native_crs,
        )
        csv_path = _output_path(
            output_dir,
            f"{layer_id}.csv",
            args.overwrite,
        )
        _write_csv(csv_path, artifact)
        cell_ids = [row.cell_id for row in artifact.rows]
        layer_metadata = {
            "layer_id": artifact.layer_id,
            "resolution": artifact.resolution,
            "row_count": len(artifact.rows),
            "cell_ids_sha256": _id_set_sha256(cell_ids),
            "intersecting_cell_count": sum(
                int(row.intersects) for row in artifact.rows
            ),
            "source_geometry_count": artifact.source_geometry_count,
            "source_part_count": artifact.source_part_count,
            "declared_feature_count": artifact.declared_feature_count,
            "path": csv_path.name,
            "bytes": csv_path.stat().st_size,
            "sha256": _sha256(csv_path),
        }
        metadata["layers"].append(layer_metadata)
        print(
            f"  {len(artifact.rows):,} rows; "
            f"{layer_metadata['intersecting_cell_count']:,} intersections; "
            f"sha256={layer_metadata['sha256']}"
        )

    metadata_path = _output_path(
        output_dir,
        "direct_distance_artifacts.json",
        args.overwrite,
    )
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
