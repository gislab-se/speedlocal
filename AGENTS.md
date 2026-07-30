# SpeedLocal V2 Final agent instructions

## Product direction

- `docs/GENERAL_PROGRAM_PLAN.md` is the authoritative implementation plan.
- Follow the V2 Final strategy: dismantle the active V2 Final monolith one
  complete behavior slice at a time. Frozen V2 is the behavioral parity
  reference for Trøndelag only.
- Frozen V2 is an immutable external reference deployment. V2 Final is the
  active working monolith and must remain the only product surface in this
  repository.
- Frozen V2 is exactly
  `gislab-se/landskapsanalys@75ba14871100c208cbf8eedb794d56c165340811`,
  branch `frozen-v2-reference-2026-07-30`, tag
  `v2-frozen-reference-2026-07-30`. Never move, delete, or develop on either
  frozen ref. See `docs/FROZEN_V2_REFERENCE.md`.
- The frozen snapshot contains Bornholm files, but they are V1-derived
  diagnostic/provenance material, not an accepted Bornholm V2 parity baseline.
- Bornholm remains a delivery region in onboarding. Its intended behavior
  reference is V1 plus explicit regional acceptance evidence; do not enable
  its V2 Final route until that baseline is pinned and validated.
- Build one manifest-driven geospatial program, not one app branch per region.
- Frozen V2 is a read-only Trøndelag behavior reference and a multi-region data
  archive. Modify
  `apps/v2_port/` only to integrate a validated V2 Final slice and remove the
  hardcoded path that slice replaces.
- Do not import V3 as a baseline.

## Required planning routine

- `docs/DELIVERY_PLAN.md` is the dated route to delivery.
- `docs/DAILY_WORKFLOW.md` defines the mandatory daily routine.
- At the start of every workday, create or update
  `docs/daily/YYYY-MM-DD.md` with one testable outcome and three to five tasks.
- At the end of every workday, record completed work, validation, blockers,
  code classification, exact next starting point, and the work-checkpoint
  commit hash.
- After local validation and localhost review, commit and push the session.
  Verify the GitHub commit and external V2 Final deployment before marking the
  session published. Record that verification in a small publication-record
  commit and push it. Verify GitHub Pages too when `site/**` changed.
- Update the delivery plan when dates, order, assumptions, or milestone status
  change. Do not silently drift from the plan.

## Current scope

- Implement the five standard groups in this order: roads, population, nature,
  culture, grid infrastructure.
- The current slice is the complete public roads behavior. `roads_large` has
  reached a canonical Trøndelag R7 checkpoint; do not call it fully promoted
  until visual approval and canonical R6/R5 rollups pass. The complete roads
  slice also requires canonical `roads_medium` and combined-roads behavior.
- Bornholm source and engine contracts may validate in parallel as onboarding
  diagnostics, but they do not block Trøndelag slice promotion.
- Do not implement regional exceptions yet.
- Adapt behavior from declared and detected data characteristics. For example,
  population may use point, grid, or polygon processing. Region ids must not
  select analysis algorithms.

## Architecture rules

- Keep Streamlit UI separate from `speedlocal/` business logic.
- Public regions come only from `regions/index.json`.
- Analysis and layer availability come from region manifests.
- All source paths go through the shared provider resolver.
- Keep large runtime data outside Git. Use `SPEEDLOCAL_V2_SOURCE_ROOT` for the
  complete read-only local V2 archive. With that variable unset, V2 Final may
  materialize only the checksum-pinned public runtime package declared under
  `data/runtime/manifests/`; never commit its ZIP or extracted cache.
- Fail closed on missing manifests, unsupported geometry, invalid paths, or
  incomplete runtime assets.
- Every migrated slice needs a validator and evidence against the accepted
  reference for each active region before old code is removed.
- Keep engine-contract conformance separate from public behavioral parity.
  A generic result is not parity until it is compared with that region's
  technically secured public reference.
- Runtime strategy comes from a validated source contract, never a region-name
  branch. Bornholm's checksum-declared polygon fixtures are diagnostic
  integrity evidence only; undeclared combinations must fail closed.
- Inspect functions within a complete behavior slice. Classify touched code as
  keep, extract, configure, rewrite, or remove.
- Do not polish obsolete monolith code. Remove it after the replacement reaches
  parity and is promoted.
- Do not create a parallel replacement or parity app. Generic modules must be
  integrated into the actual V2 Final monolith flow.

## Validation

Run the generic-engine validator after contract, region, source, or engine
changes:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\gislab\data\landskapsanalys-v2-multiregion"
& ".\.venv\Scripts\python.exe" -B scripts\validate_generic_engine.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_v2_final_baseline_parity.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_v2_port_app.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_runtime_bundle.py
```

Also run the existing delivery and V2 guardrail validators for changes that
touch their scope.

When the runtime package or bootstrap changes, rebuild the ZIP outside Git and
run `validate_runtime_bundle.py --release-archive <zip>` before publication.
Full-archive validators still use the complete local V2 archive; the
Trøndelag-only cloud package is not a Bornholm diagnostic fixture.

`scripts/validate_bornholm_v2_diagnostics.py` is a separate onboarding and
archive-integrity check. Passing it must never be reported as Bornholm product
parity or readiness.

Run `scripts/validate_frozen_v2_reference.py` whenever the frozen reference or
the external runtime archive is used. Add `--remote` during publication.
