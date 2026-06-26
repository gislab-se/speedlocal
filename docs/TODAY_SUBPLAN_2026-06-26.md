# SpeedLocal Today Subplan - 2026-06-26

## Goal

Turn the public `gislab-se/speedlocal` skeleton into a verifiable delivery
baseline, then prepare the first minimum app/runtime copy from V2 without
bringing generated clutter back into the repo.

## Non-Goals Today

- Do not copy broad V2 folders.
- Do not import QGIS review outputs, report exports, rendered maps, caches, or
  prototype data.
- Do not remove file fallbacks until Postgres-backed reads are validated.
- Do not edit the V2 repo except as a read-only source archive.

## Block 1 - Publish the Static Baseline

- Confirm `gislab-se/speedlocal` is public.
- Re-enable the `Publish GitHub Pages` workflow on `main` pushes.
- Run delivery and static-site validators locally.
- Push the workflow/docs update.
- Confirm the Pages workflow succeeds.
- Smoke-check the target path:
  `https://gislab-se.github.io/speedlocal/landskapspotential/`

## Block 2 - Day-1 Inventory From V2

- Create a minimal copy list and leave-behind list.
- Identify the smallest required Streamlit/app entrypoints.
- Identify shared modules needed by Bornholm and Trondelag.
- Identify region catalog and manifest files needed for:
  - Bornholm active state.
  - Trondelag active state.
  - Skaraborg planned/disabled state.
- Identify required assets and static files.
- Identify runtime file fallback paths that must remain available.

Output: `docs/SPEEDLOCAL_COPY_LIST.md`

## Block 3 - Region Contract Tightening

- Compare current `regions/index.json` and each `region.json` against the V2
  assumptions.
- Make the validator explicit about:
  - Bornholm `EPSG:25833`.
  - Trondelag `EPSG:25832`.
  - Trondelag R7/R6/R5 only.
  - Skaraborg planned status.
  - Postgres preferred with file fallback.
- Draft the "new region readiness" checks needed before Skane or another region
  can be activated.

## Block 4 - Choose the First Runtime Slice

- Pick one small implementation slice after inventory, preferably:
  - app shell routing from region catalog, or
  - a read-only catalog/status screen, or
  - first file-fallback runtime contract check.
- Copy only the files needed for that slice.
- Add a smoke test or validator for the copied slice before adding more.

## Done Criteria

- Public Pages workflow succeeds.
- Static landing page is reachable at the new `/speedlocal/landskapspotential/`
  path.
- `docs/SPEEDLOCAL_COPY_LIST.md` exists with copy and leave-behind decisions.
- `scripts/validate_region_readiness.py` exists and passes.
- `scripts/validate_trondelag_runtime_sources.py` exists and passes against the
  V2 source archive.
- The app can show a file-backed Trondelag runtime source summary without
  Docker/PostGIS.
- `scripts/validate_file_runtime_summary.py` exists and passes.
- `scripts/prepare_trondelag_runtime_metadata.py` exists and can emit
  metadata-only SQL.
- `docs/SPEEDLOCAL_RUNTIME_IMPORT_PLAN.md` exists for the first DB slice.
- Validators pass locally.
- V2 repo remains untouched.
- `speedlocal` remains small and delivery-focused.

## Status Update - 2026-06-26

All four blocks are complete.

- Block 1 is complete: Pages publishes from `site/` and the public landing page
  is live at `/speedlocal/landskapspotential/`.
- Block 2 is complete: `docs/SPEEDLOCAL_COPY_LIST.md` records copy candidates
  and leave-behind decisions.
- Block 3 is complete: region readiness validation covers Bornholm, Trondelag,
  Skaraborg, CRS, H3 exposure, planned status, and Postgres-then-file runtime
  policy.
- Block 4 is complete: the first runtime slice is the catalog/status app shell
  with Trondelag file-backed source validation and metadata-only import seeds.

Extra baseline completed today:

- Streamlit Cloud status app is linked from the landing page:
  `https://speedlocal-landskapspotential.streamlit.app/`
- Region deep links are live for Bornholm, Trondelag, and Skaraborg.
- `docs/REPO_HYGIENE.md` defines keep/delete rules for keeping the repo slim.
- Local generated clutter (`__pycache__`, `tmp/`) was removed from the checkout.

## Follow-On Block - Bornholm File Runtime Summary

Complete.

- Bornholm now uses the same file-runtime summary pattern as Trondelag.
- The summary validates the smallest app-ready V2 sources without copying large
  generated files into `speedlocal`.
- R10-derived R9 PEY labelling remains explicit.
- Validator coverage was added before any real app behavior was promoted.

## Next Block

Prepare the V2 quarantine port for the first real regional surface:

1. Use V2 as the working behavior baseline; do not rebuild the app from
   scratch.
2. Do not use V3 as the delivery baseline. Reuse only lessons from
   `docs/APP_MIGRATION_STRATEGY_2026-06-26.md`.
3. If `potential_app.py` is copied, put it in quarantine and shrink it after it
   runs.
4. Keep the first standard layer groups to roads, population, nature, culture,
   and grid infrastructure.
5. Keep regional extras, such as Trondelag reindeer husbandry, catalog-driven.
6. Keep file fallbacks active until Postgres/Flowcore coverage validates.
7. Add or update validators before promoting behavior to the public Streamlit
   UI.

## Follow-On Block - V2 Port Inventory

Complete.

- `docs/V2_QUARANTINE_PORT_INVENTORY_2026-06-26.md` lists V2 imports and
  required-now/required-later/leave-behind files.
- `scripts/validate_v2_port_guardrails.py` passes before copying code.
- The validator is part of the normal delivery validation path.

Next implementation step: copy the first guarded V2 baseline into
`apps/v2_port/`, patch region discovery before exposure, and verify that the
guardrail validator still passes.
