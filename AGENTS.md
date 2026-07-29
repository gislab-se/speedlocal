# SpeedLocal V2 Final agent instructions

## Product direction

- `docs/GENERAL_PROGRAM_PLAN.md` is the authoritative implementation plan.
- Follow the V2 Final strategy: dismantle V2 one complete behavior slice at a
  time while it remains the running parity reference.
- Build one manifest-driven geospatial program, not one app branch per region.
- V2 is a read-only behavior and data archive. Do not develop new product
  features inside `apps/v2_port/`; replace it one validated vertical slice at a
  time.
- Do not import V3 as a baseline.

## Required planning routine

- `docs/DELIVERY_PLAN.md` is the dated route to delivery.
- `docs/DAILY_WORKFLOW.md` defines the mandatory daily routine.
- At the start of every workday, create or update
  `docs/daily/YYYY-MM-DD.md` with one testable outcome and three to five tasks.
- At the end of every workday, record completed work, validation, blockers,
  code classification, exact next starting point, and commit hash.
- Update the delivery plan when dates, order, assumptions, or milestone status
  change. Do not silently drift from the plan.

## Current scope

- Implement the five standard groups in this order: roads, population, nature,
  culture, grid infrastructure.
- The current slice is the complete public roads behavior. `roads_large` is the
  first implemented foundation.
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
  read-only V2 archive until another validated provider is available.
- Fail closed on missing manifests, unsupported geometry, invalid paths, or
  incomplete runtime assets.
- Every migrated slice needs a validator and parity evidence before old V2 code
  is removed.
- Inspect functions within a complete behavior slice. Classify touched code as
  keep, extract, configure, rewrite, or remove.
- Do not polish obsolete monolith code. Remove it after the replacement reaches
  parity and is promoted.

## Validation

Run the generic-engine validator after contract, region, source, or engine
changes:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\gislab\data\landskapsanalys-v2-multiregion"
& ".\.venv\Scripts\python.exe" -B scripts\validate_generic_engine.py
```

Also run the existing delivery and V2 guardrail validators for changes that
touch their scope.
