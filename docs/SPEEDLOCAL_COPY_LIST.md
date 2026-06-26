# SpeedLocal Copy List And Leave-Behind Decisions

Date: 2026-06-26

Source archive: `C:\tmp\landskapsanalys-v2-multiregion`

Delivery repo: `C:\tmp\speedlocal`

## Rule

Copy the smallest runtime-critical piece from V2 only when a specific
SpeedLocal slice needs it. Prefer catalogs, validators, import scripts, and
database contracts before large generated data files.

The V2 repo is currently read-only for this migration. It also has local
uncommitted Postgres/runtime work, so candidate files from that area must be
reviewed before being treated as stable source truth.

## Current Delivery Baseline

Already present in `speedlocal`:

- Static landing page at `site/landskapspotential/index.html`.
- Pages workflow publishing `site/`.
- Catalog/status Streamlit shell in `apps/landskapspotential/`.
- Region package skeletons for `bornholm`, `trondelag`, and `skaraborg`.
- Shared Postgres schema skeleton in `db/init`.
- File fallback policy in `data/runtime/README.md`.
- Delivery and static-site validators.
- Repo hygiene rules in `docs/REPO_HYGIENE.md`.

Intentional normalization:

- V2 uses `regions/skara` and region id `skara`.
- SpeedLocal uses `regions/skaraborg` and region id `skaraborg`.
- Do not reintroduce `skara` as the active delivery id unless there is a
  compatibility adapter with tests.

## Copy Candidates

### App Shell And Shared Modules

Do not copy the full V2 `potential_app.py` monolith first. It is useful as
reference, but too broad for the slim repo.

Copy selectively when needed:

- `potential_app.py`
  - Reference only for region selection, app behavior, and UI semantics.
  - First extraction target: small catalog/status helpers, not the whole file.
- `apps/potential_model/manifests.py`
  - Candidate for manifest loading and path resolution.
  - Must remove legacy manifest discovery before promoting to SpeedLocal,
    especially fallback discovery under `apps/potential_model/manifests/regions`.
- `apps/potential_model/region_status.py`
  - Candidate for read-only region context/status once linked manifests are
    copied.
- `apps/potential_model/landscape.py`
  - Candidate after the first landscape runtime slice exists.
- `apps/potential_model/potential.py`
  - Candidate after potential-cell runtime/data contracts are explicit.
- `apps/potential_model/energy_modeling.py`
  - Candidate only after scenario and AreaDemand fallback policy is settled.
- `apps/potential_model/map_rendering.py`
  - Candidate when the interactive app needs map rendering.
- `apps/acceptance_model/*`
  - Reference for acceptance layer semantics and runtime geometry.
  - Copy only the modules required by a chosen acceptance/buffer slice.
- `apps/acceptance_app.py`
  - Reference only. Do not copy as an active app entrypoint now.
- `streamlit_app.py`
  - Wrapper reference only.
- V2 root `app.py`
  - Old GC4/Bornholm geocontext app. Leave behind.

### Region Packages

Copy or compare selectively:

- `regions/index.json`
  - Reference for default region and active region order.
  - Do not copy directly because delivery uses `skaraborg`, not `skara`.
- `regions/bornholm/region.json`
  - Candidate source for detailed Bornholm manifest paths and R10-derived R9
    PEY metadata.
- `regions/bornholm/parameter_buffers.json`
  - Candidate when acceptance/buffer UI is enabled.
- `regions/bornholm/REGIONAL_NOTES.md`
  - Candidate documentation source for Bornholm regional exceptions.
- `regions/trondelag/region.json`
  - Candidate source for EPSG:25832, R7/R6/R5 counts, and LABLAB manifest links.
- `regions/trondelag/parameter_buffers.json`
  - Candidate when Trondelag population/settlement proxy buffers are enabled.
- `regions/trondelag/REGIONAL_NOTES.md`
  - Candidate documentation source for Trondelag regional exceptions.
- `regions/skara/region.json`
  - Reference only. Merge useful readiness text into `regions/skaraborg` if
    needed, but keep the SpeedLocal id as `skaraborg`.

### Linked Manifests

Bornholm candidates:

- `apps/potential_model/manifests/scenarios/bornholm_scenarios_placeholder.json`
- `apps/potential_model/manifests/potential/bornholm_potential_v0.json`
- `apps/potential_model/manifests/potential/bornholm_solar_rules_v0.json`
- `apps/potential_model/manifests/potential/bornholm_wind_rules_v0.json`
- `exports/v2_multiregion/bornholm/bornholm_lablab_landscape_r9.json`
- `exports/v2_multiregion/bornholm/bornholm_establishment_placement_score_r9_manifest.json`
- `exports/v2_multiregion/bornholm/bornholm_synthetic_social_acceptance_r9_manifest.json`

Trondelag candidates:

- `apps/potential_model/manifests/scenarios/trondelag_scenarios_placeholder.json`
- `apps/potential_model/manifests/potential/trondelag_potential_placeholder.json`
- `apps/potential_model/manifests/potential/trondelag_solar_rules_placeholder.json`
- `apps/potential_model/manifests/potential/trondelag_wind_rules_placeholder.json`
- `apps/potential_model/manifests/landscape/trondelag_lablab_landscape_r7.json`
- `apps/potential_model/manifests/social_acceptance/trondelag_synthetic_acceptance_v0.json`

Do not copy:

- `apps/potential_model/manifests/regions/vara.json`
- old region fallback manifests under `apps/potential_model/manifests/regions`
  unless a compatibility test proves they cannot expose inactive regions.

### Runtime Data Candidates

Do not copy large runtime files blindly. Prefer importing or mounting them as
file fallbacks until Postgres tables validate.

Bornholm app-ready candidates:

- `exports/v2_multiregion/bornholm/bornholm_lablab_landscape_r9_dagi_landsdel_app.geojson`
  - about 30.5 MB
  - active app landscape GeoJSON
- `exports/v2_multiregion/bornholm/h3_display_geometries/bornholm_h3_res_9_dagi_landsdel_land_clipped.geojson`
  - about 9.2 MB
  - R9 display geometry
- `exports/v2_multiregion/bornholm/h3_display_geometries/bornholm_h3_res_8_dagi_landsdel_land_clipped.geojson`
  - about 3.1 MB
  - R8 display geometry
- `exports/v2_multiregion/bornholm/h3_display_geometries/bornholm_h3_res_7_dagi_landsdel_land_clipped.geojson`
  - about 2.1 MB
  - R7 display geometry
- `exports/v2_multiregion/bornholm/h3_display_geometries/bornholm_h3_res_6_dagi_landsdel_land_clipped.geojson`
  - about 2.0 MB
  - R6 display geometry
- `exports/v2_multiregion/bornholm/bornholm_lablab_landscape_r9.csv`
  - about 5.3 MB
- `exports/v2_multiregion/bornholm/bornholm_establishment_placement_score_r9.csv`
  - about 2.1 MB
- `exports/v2_multiregion/bornholm/bornholm_synthetic_social_acceptance_r9.csv`
  - about 0.3 MB

Trondelag app-ready candidates:

- `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/hex.geojson`
  - about 16.7 MB
  - R7 display geometry bundle
- `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/h3/trondelag_landscape_h3_r6_rollup.geojson`
  - about 3.8 MB
- `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/h3/trondelag_landscape_h3_r5_rollup.geojson`
  - about 1.1 MB
- `docs/geocontext/potential_framework/data/trondelag_lablab_landscape_h3_r7/trondelag_lablab_landskapsanalys_h3_r7_app_extent.geojson`
  - app-ready LABLAB R7 landscape source referenced by the manifest.

Scenario fallback candidates:

- `data/processed/speedlocal_times.duckdb`
  - file fallback only until Postgres or Flowcore data is available.
- `data/raw/AreaDemand.xlsx`
  - file fallback only until AreaDemand is converted to runtime tables.

### Database And Import Candidates

Already partly represented in SpeedLocal, but V2 has more detailed local work:

- `db/init/001_runtime_base.sql`
  - Reference for shared schema and region registry.
- `db/init/002_runtime_h3_landscape_contract.sql`
  - Candidate improvements for constraints and status enums.
- `docs/LOCAL_POSTGRES_RUNTIME_SETUP.md`
  - Candidate documentation source for local PostGIS setup and Trondelag import.
- `scripts/prepare_trondelag_runtime_import.py`
  - Candidate validator/metadata seed generator.
  - Review before copying because it is currently local V2 work.
- `scripts/import_trondelag_runtime_geometries.py`
  - Candidate SQL emitter for Trondelag display and landscape import.
  - Review before copying because it is currently local V2 work.
- `scripts/check_local_postgres.ps1`
  - Candidate only if SpeedLocal needs a PowerShell database check wrapper.

### Validators To Port First

Highest-value candidates:

- `scripts/validate_potential_region_contract.py`
  - Broad Bornholm/Trondelag contract source.
  - Port as smaller SpeedLocal validators; do not copy whole script unchanged
    if it imports the V2 monolith.
- `scripts/validate_bornholm_r9_pey_contract.py`
  - Port once Bornholm manifests and file fallback paths exist.
- `scripts/validate_region_parameter_buffers.py`
  - Port when parameter buffer catalogs are activated.
- `scripts/prepare_trondelag_runtime_import.py`
  - Port or adapt when the first Postgres import slice starts.

## Leave Behind

Leave these out of `speedlocal` unless a later decision explicitly promotes a
specific file:

- `exports/qgis_review/**`
  - review packages, QA exports, comparison layers, and temporary QGIS outputs.
- `artifacts/**`
- `tmp/**`
- `__pycache__/**`
- `debug.log`
- `docs/archive/**`
- generated report folders under `docs/geocontext/model_comparisons/**`
- large `.gpkg`, `.tif`, `.duckdb`, `.xlsx`, and rendered map folders unless
  mounted as runtime fallback or imported into Postgres with validation.
- `data/processed/bornholm/lablab_pdf_landscape/**`
  - PDF-derived intermediate rasters and masks.
- `data/processed/trondelag/h3/trondelag_h3_r8_land_clipped.geojson`
  - R8 is not exposed for Trondelag.
- old GC4/Bornholm standalone app material from V2 root `app.py`.
- inactive legacy regions, especially Vara.

## Recommended First Runtime Slice

Do this before copying the full app:

1. Add a `scripts/validate_region_readiness.py` validator in SpeedLocal. Done.
2. Validate only the current SpeedLocal catalogs:
   - Bornholm is active, EPSG:25833, R6/R7/R8/R9.
   - Trondelag is active, EPSG:25832, R7/R6/R5 only.
   - Skaraborg is planned/disabled.
   - Postgres is preferred and file fallbacks remain documented.
3. Add a `scripts/validate_trondelag_runtime_sources.py` validator that checks
   the V2 source archive without copying large GeoJSON. Done.
4. Add a file-backed Trondelag runtime summary in the app so Docker/PostGIS is
   not required for the first runtime slice. Done.
5. Add a `docs/SPEEDLOCAL_RUNTIME_IMPORT_PLAN.md` for Trondelag first, based on
   V2 `prepare_trondelag_runtime_import.py`. Done.
6. Only then copy or adapt the Trondelag metadata/import script.
   `scripts/prepare_trondelag_runtime_metadata.py` now covers the metadata-only
   seed step without copying large GeoJSON.

This keeps the slim repo small while still moving toward a real Postgres-backed
runtime.

## Next Accepted Slice

The next accepted slice is a Bornholm file-runtime summary.

Rules for that slice:

- Validate the smallest Bornholm app-ready V2 sources first.
- Do not copy large Bornholm GeoJSON, CSV, or report outputs into this repo.
- Keep R10-derived R9 PEY labelling visible in the validator/app summary.
- Reuse the shared file-runtime summary pattern instead of creating a
  Bornholm-only app branch.
- Add validator coverage before promoting any Bornholm runtime data or app
  behavior.
