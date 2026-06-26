# PostGIS Runtime Import Agent Prompt - 2026-06-26

Use this prompt for an implementation agent that will import the first
SpeedLocal runtime data into Postgres/PostGIS.

```text
You are working in the delivery repo:

  C:\tmp\speedlocal

The V2 source archive is read-only:

  C:\tmp\landskapsanalys-v2-multiregion

PostGIS is now available in the SpeedLocal database. Do not spend time working
around missing geometry support. Use the shared SpeedLocal runtime schema, keep
file fallbacks, and import only reviewed/app-ready runtime data.

Main objective:

Implement the first database-backed runtime slice for SpeedLocal using PostGIS.
Start with Trondelag display geometry and LABLAB landscape runtime data. Keep
Bornholm as the second slice unless Trondelag is fully imported and validated.

Non-negotiable rules:

- Do not edit the V2 repo.
- Do not copy large GeoJSON/CSV/GPKG/TIF/XLSX files into `speedlocal`.
- Read large runtime files from the V2 source archive during import.
- Do not import QGIS review folders, rendered reports, caches, exploratory
  outputs, or inactive V3 material.
- Do not create region-specific runtime schemas. Use shared tables keyed by
  `region_id`.
- Do not expose Trondelag R8 or R9.
- Do not switch the app to Postgres-only mode. Keep documented file fallbacks
  until database-backed reads match file-backed reads.
- Do not reset or delete the database volume unless the user explicitly asks.
- Keep generated SQL or temporary output out of git, for example under `tmp/`.

Environment:

- Use `DATABASE_URL` for database connections.
- Use `SPEEDLOCAL_V2_SOURCE_ROOT` for the V2 archive root; default:
  `C:\tmp\landskapsanalys-v2-multiregion`.
- Existing local example:
  `DATABASE_URL=postgresql://speedlocal:speedlocal_local_password@127.0.0.1:55432/speedlocal`

Existing SpeedLocal schema:

- `runtime.regions`
- `runtime.region_catalogs`
- `meta.runtime_datasets`
- `runtime.h3_display_cells`
- `runtime.landscape_cells`

If the existing database was created before a migration, apply idempotent SQL
manually. Docker init files only run automatically for a fresh database volume.

First import slice: Trondelag

Import these sources from the V2 archive:

1. Region metadata
   - `regions/trondelag/region.json`
   - Region id: `trondelag`
   - Native CRS: `EPSG:25832`
   - Web/runtime geometry CRS: `EPSG:4326`
   - Active H3 display resolutions: R7, R6, R5 only

2. H3 display geometries into `runtime.h3_display_cells`
   - R7:
     `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/hex.geojson`
     expected rows: 13,735
   - R6:
     `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/h3/trondelag_landscape_h3_r6_rollup.geojson`
     expected rows: 2,163
   - R5:
     `docs/geocontext/potential_framework/data/trondelag_r7_app_bundle/h3/trondelag_landscape_h3_r5_rollup.geojson`
     expected rows: 365

3. LABLAB R7 landscape cells into `runtime.landscape_cells`
   - Manifest:
     `apps/potential_model/manifests/landscape/trondelag_lablab_landscape_r7.json`
   - GeoJSON:
     `docs/geocontext/potential_framework/data/trondelag_lablab_landscape_h3_r7/trondelag_lablab_landskapsanalys_h3_r7_app_extent.geojson`
   - Expected rows: 13,735
   - Expected landscape type ids: `LT01` through `LT09` exactly
   - Expected `LT09` count: 359
   - Landscape hex ids must match the R7 display hex ids exactly

4. Dataset metadata into `meta.runtime_datasets`
   - `trondelag_region_manifest`
   - `trondelag_h3_display_r7`
   - `trondelag_h3_display_r6`
   - `trondelag_h3_display_r5`
   - `trondelag_lablab_landscape_r7_app_extent`
   - Use `source_status='app_ready_after_qgis_review'` or the manifest status
     where appropriate.
   - Use `validation_status='validated'` only after source and database checks
     pass.

Do not import for Trondelag in the first slice:

- Placeholder potential manifest as production data.
- Placeholder scenario manifest as production data.
- Synthetic social acceptance as production data.
- Population/settlement 250 m proxy buffers.
- QGIS review outputs under `exports/qgis_review`.
- Full LABLAB data outside the current app extent.

Implementation plan:

1. Confirm clean worktree in `C:\tmp\speedlocal`.
2. Confirm database connectivity and PostGIS:
   - `python scripts\check_runtime_db.py`
   - query `select postgis_full_version();`
3. Run source validators before importing:
   - `python -B scripts\validate_trondelag_runtime_sources.py`
   - `python -B scripts\prepare_trondelag_runtime_metadata.py`
4. Add or adapt an import script in SpeedLocal, preferably:
   - `scripts/import_trondelag_runtime_geometries.py`
   - It may be adapted from V2:
     `C:\tmp\landskapsanalys-v2-multiregion\scripts\import_trondelag_runtime_geometries.py`
5. The import script must be idempotent:
   - upsert `runtime.regions`
   - upsert `meta.runtime_datasets`
   - replace or upsert only Trondelag rows for the imported dataset ids
   - avoid broad table truncation
6. For GeoJSON geometry:
   - read features from V2
   - extract `hex_id`
   - store all source properties as `jsonb`
   - convert geometry using PostGIS, for example:
     `ST_SetSRID(ST_GeomFromGeoJSON(...), 4326)`
   - make invalid polygon input safe with `ST_MakeValid`
   - store display geometry in `runtime.h3_display_cells.geom`
7. For landscape:
   - use `hex_id`, `landscape_type_id`, `landscape_type_name`, `class_km`,
     `assignment_method`, `source_model`, `review_scope`, and full properties
   - do not add a duplicate geometry column unless there is a documented reason;
     landscape rows should join to display geometry by `region_id`,
     `h3_resolution`, and `hex_id`
8. Add a database validator, for example:
   - `scripts/validate_trondelag_postgis_runtime.py`
   - It must connect via `DATABASE_URL`.
   - It must fail when `DATABASE_URL` is set and required imported rows are
     missing or invalid.

Required database validation:

- PostGIS extension exists.
- `runtime.h3_display_cells` counts:
  - Trondelag R7 = 13,735
  - Trondelag R6 = 2,163
  - Trondelag R5 = 365
- No Trondelag R8 or R9 rows exist.
- Display geometries are not null.
- Invalid display geometries = 0.
- Empty display geometries = 0.
- Duplicate display hex ids per resolution/version = 0.
- `runtime.landscape_cells` Trondelag R7 count = 13,735.
- Landscape type ids are exactly `LT01` to `LT09`.
- `LT09` count = 359.
- Landscape R7 hex ids missing matching display geometry = 0.
- Dataset metadata rows exist and are marked validated only after checks pass.

After Trondelag passes:

- Add read-only runtime access functions, but keep backend selection conservative:
  use Postgres only when required rows exist and validation passes, otherwise
  fall back to files.
- Compare a file-backed Trondelag summary to database-backed counts.
- Update docs with exact import command, validation command, and known gaps.

Second slice: Bornholm, only after Trondelag is green

Bornholm source data to prepare/import later:

- Region metadata:
  `regions/bornholm/region.json`
- H3 display geometries into `runtime.h3_display_cells`:
  - R6 expected rows: 32
  - R7 expected rows: 166
  - R8 expected rows: 1,035
  - R9 expected rows: 6,852
  - source folder:
    `exports/v2_multiregion/bornholm/h3_display_geometries`
- LABLAB R9 landscape app extent into `runtime.landscape_cells`:
  - source manifest:
    `exports/v2_multiregion/bornholm/bornholm_lablab_landscape_r9.json`
  - expected app rows: 6,852
  - expected landscape types: `LT01` through `LT05`
- Landscape CSV:
  - expected rows: 6,877
  - keep as metadata or import only if a table contract is added
- Establishment placement score R9:
  - expected rows: 6,878
  - source is R10-derived R9 PEY
  - must remain labelled `R10-derived R9`, not true R9-native
- Synthetic social acceptance R9:
  - expected rows: 6,878
  - may be imported only if clearly marked `synthetic_test_data`

If Bornholm needs new tables, add separate migration(s), for example:

- `runtime.potential_cells`
- `runtime.acceptance_cells`

Do not overload `runtime.landscape_cells` with potential or acceptance values.
Keep source status and validation status explicit.

Acceptance criteria:

- All existing validators still pass:
  - `python -B scripts\validate_delivery_repo.py`
  - `python -B scripts\validate_region_readiness.py`
  - `python -B scripts\validate_file_runtime_summary.py`
  - `python -B scripts\validate_trondelag_runtime_sources.py`
  - `python -B scripts\validate_v2_port_guardrails.py`
- New PostGIS validator passes against the live database.
- No large runtime source files are committed.
- File fallbacks remain documented and active.
- Trondelag DB rows match file-backed validation counts.
- Trondelag R8/R9 remain absent.
- Docs explain:
  - database startup
  - schema application for existing DBs
  - import command
  - validation command
  - what is still file-fallback only
```
