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
- Validators pass locally.
- V2 repo remains untouched.
- `speedlocal` remains small and delivery-focused.
