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

Updated decision after inspecting V3:

Do not rebuild the app from scratch and do not copy V3 as the baseline. A full
V2 `potential_app.py` copy is acceptable only as a quarantined working baseline
that runs first and is then reduced. It should not be promoted as final
architecture.

Copy selectively when needed, or copy into a quarantined V2-port area when real
app behavior is the current slice:

- `potential_app.py`
  - Candidate quarantine baseline for region selection, app behavior, and UI
    semantics.
  - If copied, place under a clearly named V2-port area such as `apps/v2_port/`
    and immediately disable legacy Vara/skara discovery.
  - Shrink after it runs; do not build new app abstractions around it first.
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

V3 repo `C:\tmp\landskapspotential`:

- Reference only for lessons learned.
- Do not copy its `data/incoming/`, `data/regions/`, caches, logs, or app
  architecture into SpeedLocal.
- Useful ideas to reuse later: V2-behavior-as-source-of-truth rule, Leaflet
  renderer direction, visible missing/proxy status, and draft/applied state
  after the baseline app runs.

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

## Completed Slice - Bornholm File Runtime Summary

The Bornholm file-runtime summary is complete.

What was promoted:

- The app reads Bornholm source status from the V2 archive as a file fallback.
- The validator checks R6/R7/R8/R9 display counts, LABLAB R9 landscape extent,
  landscape CSV rows, establishment placement score rows, and synthetic social
  acceptance rows.
- R10-derived R9 PEY labelling is preserved in metadata and validation output.
- No large Bornholm GeoJSON, CSV, or report output was copied into this repo.

## Next Accepted Slice

The next accepted slice is the V2 quarantine-port preparation for the first real
regional surface.

Status: first guarded baseline copied to `apps/v2_port/`.

Inventory and guardrails are documented in
`docs/V2_QUARANTINE_PORT_INVENTORY_2026-06-26.md`. Run
`scripts/validate_v2_port_guardrails.py` after every V2 port change.

Rules for that slice:

- Start from the working V2 app behavior, not a new V3-style architecture.
- Copy the V2 monolith only into quarantine, then scale it back.
- Reuse manifests and file-fallback paths before copying generated data.
- Keep the first standard layer groups to roads, population, nature, culture,
  and grid infrastructure.
- Put regional extras such as Trondelag reindeer husbandry in the catalog.
- Keep Bornholm and Trondelag validation independent.
- Add validator coverage before promoting any behavior to the public Streamlit
  app.

## Completed Slice - Guarded V2 Quarantine Port

The first guarded V2 baseline is copied under `apps/v2_port/`.

Accepted code files:

- `potential_app.py`
- `apps/potential_model/__init__.py`
- `apps/potential_model/geometry.py`
- `apps/potential_model/landscape.py`
- `apps/potential_model/manifests.py`
- `apps/potential_model/region_status.py`
- `apps/potential_model/map_rendering.py`
- `apps/potential_model/energy_modeling.py`
- `apps/potential_model/potential.py`
- `apps/potential_model/social_acceptance.py`
- `apps/potential_model/wind_acceptance.py`
- `apps/acceptance_model/__init__.py`
- `apps/acceptance_model/i18n.py`
- `apps/acceptance_model/layers.py`
- `apps/acceptance_model/runtime_geometry.py`

Accepted small runtime metadata:

- `apps/acceptance_model/registry_bornholm.json`
- `apps/acceptance_model/registry_trondelag.json`
- selected small manifests under:
  - `apps/potential_model/manifests/landscape/`
  - `apps/potential_model/manifests/potential/`
  - `apps/potential_model/manifests/scenarios/`
  - `apps/potential_model/manifests/social_acceptance/`

Guardrail patches applied in the copied port:

- `potential_model.manifests` reads region discovery from the SpeedLocal
  `regions/index.json` only.
- V2 legacy region manifest discovery is removed.
- `acceptance_model.layers` has explicit Bornholm/Trondelag registry selection
  and fails closed for planned or unknown regions.
- `acceptance_model.runtime_geometry` does not run the old generated R runtime.

Still intentionally left behind:

- `apps/potential_model/manifests/regions/`
- `apps/acceptance_model/registry.json`
- V2 `regions/`
- V2 `data/`, `exports/`, `artifacts/`, `tmp/`, and generated GIS output

Validation status:

- `scripts/validate_v2_port_guardrails.py` passes after the copy.
- Syntax parsing passes for all copied port Python files.
- Manifest import resolves the SpeedLocal region index as
  `bornholm,trondelag,skaraborg`.
