# SpeedLocal Runtime Import Plan

Date: 2026-06-26

## Direction

Import runtime data into shared `runtime` tables keyed by `region_id`. Keep file
fallback paths available until database-backed reads validate against the file
baseline.

PostGIS/Flowcore is not required for the current app baseline. Until database
capabilities are confirmed, the app can read a validated file-backed source
summary from the V2 archive using `SPEEDLOCAL_V2_SOURCE_ROOT`.

Do not create region-specific runtime schemas. Do not import placeholder,
synthetic, QGIS review, or generated exploratory outputs unless they are clearly
marked and required for a validation slice.

## First Slice: Trondelag Display And Landscape

Trondelag is the best first import slice because V2 already has a local
metadata/import workflow for reviewed R7/R6/R5 display geometries and the
QGIS-reviewed LABLAB R7 landscape app extent.

Candidate V2 references:

- `db/init/001_runtime_base.sql`
- `db/init/002_runtime_h3_landscape_contract.sql`
- `docs/LOCAL_POSTGRES_RUNTIME_SETUP.md`
- `scripts/prepare_trondelag_runtime_import.py`
- `scripts/import_trondelag_runtime_geometries.py`
- `regions/trondelag/region.json`
- `apps/potential_model/manifests/landscape/trondelag_lablab_landscape_r7.json`

Source paths referenced by the V2 contract:

- R7 display: `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/hex.geojson`
- R6 display: `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/h3/trondelag_landscape_h3_r6_rollup.geojson`
- R5 display: `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/h3/trondelag_landscape_h3_r5_rollup.geojson`
- R7 LABLAB landscape: `docs/geocontext/potential_framework/data/trondelag_lablab_landscape_h3_r7/trondelag_lablab_landskapsanalys_h3_r7_app_extent.geojson`

Expected validation:

- `runtime.h3_display_cells`, R7: 13,735 rows.
- `runtime.h3_display_cells`, R6: 2,163 rows.
- `runtime.h3_display_cells`, R5: 365 rows.
- `runtime.landscape_cells`, LABLAB R7: 13,735 rows.
- All 9 LABLAB landscape types are present.
- `LT09 Vidstrackt fjallandskap` remains present and distinct.
- Invalid/empty imported geometries: 0.
- LABLAB R7 cells missing matching display geometry: 0.
- Trondelag R8/R9 remain absent from app runtime.

## Import Sequence

1. Keep the SpeedLocal app on file fallback mode.
2. Validate the V2 source archive with:
   `python scripts\validate_trondelag_runtime_sources.py`
3. Prepare metadata-only SQL with:
   `python scripts\prepare_trondelag_runtime_metadata.py --emit-sql`
4. Add a SpeedLocal DB validation script that can run without importing data.
5. Import metadata rows into `meta.runtime_datasets`.
6. Import R7/R6/R5 display geometries into `runtime.h3_display_cells`.
7. Import LABLAB R7 landscape cells into `runtime.landscape_cells`.
8. Validate row counts, landscape types, geometry validity, and display/landscape
   joins.
9. Add read-only runtime access functions.
10. Compare file-backed and database-backed outputs for known Trondelag views.
11. Switch default backend to Postgres only after comparison passes.

## Explicit Skips For First Slice

The source validator defaults to `C:\tmp\landskapsanalys-v2-multiregion`.
Set `SPEEDLOCAL_V2_SOURCE_ROOT` to validate another V2 archive checkout.

- Trondelag placeholder potential manifests.
- Trondelag placeholder scenario manifests.
- Synthetic social acceptance as production data.
- Population/settlement 250 m proxy buffers.
- QGIS review packages under `exports/qgis_review`.
- Full LABLAB extent outside the current app extent.

## Second Slice: Bornholm Metadata And PEY Validation

Bornholm should follow after Trondelag import plumbing exists. Start with
metadata and validation before importing large files.

Candidate V2 references:

- `regions/bornholm/region.json`
- `exports/v2_multiregion/bornholm/bornholm_lablab_landscape_r9.json`
- `exports/v2_multiregion/bornholm/bornholm_establishment_placement_score_r9_manifest.json`
- `apps/potential_model/manifests/potential/bornholm_potential_v0.json`
- `scripts/validate_bornholm_r9_pey_contract.py`

Required validation:

- Bornholm uses `EPSG:25833`.
- Active display family is R6/R7/R8/R9.
- R10 appears only as provenance/source semantics.
- PEY remains labelled `R10-derived R9` until true R9-native runtime exists.
- File fallbacks remain available until Postgres outputs match.

## App Backend Rule

The app should resolve backend per region:

1. Use Postgres only when required tables exist and validation status is passed.
2. Fall back to documented file paths when Postgres is missing, incomplete, or
   unvalidated.
3. Keep planned regions, such as Skaraborg, disabled until their catalog and
   runtime contracts are complete.
