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
- `v2-final-dev` is the daily development and integration branch. `main` is
  the published branch watched by the external V2 Final deployment. Normal
  development must not happen directly on `main`.
- At the start of every workday, create or update
  `docs/daily/YYYY-MM-DD.md` with one testable outcome and three to five tasks.
- At the end of every workday, record completed work, validation, blockers,
  code classification, exact next starting point, and the work-checkpoint
  commit hash.
- End each workday with one coherent validated checkpoint committed and pushed
  to `v2-final-dev`. This is a development checkpoint, not an external
  publication.
- A slice or increment is **locally promoted** after its required automated
  gates and localhost visual review pass and any replaced path in that
  promotion boundary is removed. Local promotion allows the next planned work
  to begin; it does not mean that colleagues can see the change externally.
- `main` is updated only in a publication window: Friday is the normal
  window, with Tuesday available when a coherent locally promoted increment is
  ready. Publish the exact reviewed development checkpoint, verify GitHub and
  the external V2 Final deployment, and record that evidence in a small
  publication-record commit. Verify GitHub Pages too when `site/**` changed.
- An emergency publication outside Tuesday or Friday requires an explicit
  reason in the current daily log and the same validation and external
  verification as a normal publication.
- Update the delivery plan when dates, order, assumptions, or milestone status
  change. Do not silently drift from the plan.

## Current scope

- Implement the five standard groups in this order: roads, population, nature,
  culture, grid infrastructure.
- The complete public roads, population, nature, culture, and grid-
  infrastructure behaviors are locally promoted but unpublished. Their
  canonical Trøndelag R7/R6/R5 controls, calculations, source/buffer previews,
  and regression gates must remain unchanged.
- The complete current Trøndelag `protected_areas` source is manifest-declared
  under canonical `nature`, and its generic binary hard-exclusion behavior is
  locally promoted after approved localhost review on 2026-08-03. The public
  wind `protected` adapter is removed for Trøndelag. A reliable result hover
  and literal technology-specific establishment-area percentages remain
  deferred to the combined-result and wind/solar phases.
- Both complete current Trøndelag culture sources are
  manifest-declared under canonical `culture`; their generic binary
  hard-exclusion automated gates pass at R7/R6/R5. The redundant wind culture
  group toggle, advanced-source adapter, and legacy distance paths are removed
  for Trøndelag. Localhost visual review was approved on 2026-08-03, so the
  slice is locally promoted.
- The complete current Trøndelag grid-infrastructure slice is
  manifest-declared under canonical `grid_infrastructure` with three sources
  and generic `proximity_feasibility` at R7/R6/R5. Its automated engine,
  frozen-reference, preview, and real-app gates pass on 2026-08-04. The legacy
  wind `electrical` path is removed for Trøndelag. Clean-process localhost
  review was approved on 2026-08-04, so the slice is locally promoted.
- The promoted population parity path currently aggregates frozen-V2 R8
  distance observations to R7/R6/R5. Treat the use of R8 as a known potential
  modeling problem: before the combined-result slice is locally promoted,
  evaluate and replace it with a direct calculation against the declared R7
  analysis domain, derive R6/R5 from R7, quantify any intentional frozen-V2
  drift, and secure new accepted-reference evidence.
- The population R8-to-direct-R7 correction is the next planned increment.
  The combined-result slice follows only after that corrective gate passes.
- Bornholm source and engine contracts may validate in parallel as onboarding
  diagnostics, but they do not block Trøndelag slice promotion.
- Do not implement regional exceptions yet.
- Adapt behavior from declared and detected data characteristics. For example,
  population may use point, grid, or polygon processing. Region ids must not
  select analysis algorithms.

## Architecture rules

- Keep Streamlit UI separate from `speedlocal/` business logic.
- Public regions come only from `regions/index.json`.
- Canonical analysis and migrated-layer availability come from region
  manifests.
- During the roads slice only, unmigrated standard groups may still read
  options and readiness from the external acceptance registry declared by the
  region manifest. The wind manifest's five-group list is a transitional
  public-product whitelist for the current wind and solar panels, not a solar
  analysis contract and not canonical layer availability. Do not add new
  registry-only product behavior; replace this adapter slice by slice.
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
& ".\.venv\Scripts\python.exe" -B scripts\validate_vector_buffer_preview.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_v2_port_app.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_runtime_bundle.py
```

The vector-buffer validator is required when provider paths, vector geometry,
native CRS, buffer contracts, or map-review integration change.

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
