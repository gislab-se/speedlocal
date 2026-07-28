# SpeedLocal agent instructions

## Product direction

- `docs/GENERAL_PROGRAM_PLAN.md` is the authoritative implementation plan.
- Build one manifest-driven geospatial program, not one app branch per region.
- V2 is a read-only behavior and data archive. Do not develop new product
  features inside `apps/v2_port/`; replace it one validated vertical slice at a
  time.
- Do not import V3 as a baseline.

## Current scope

- Implement the five standard groups in this order: roads, population, nature,
  culture, grid infrastructure.
- The current vertical slice is `roads_large`.
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

## Validation

Run the generic-engine validator after contract, region, source, or engine
changes:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\gislab\data\landskapsanalys-v2-multiregion"
& ".\.venv\Scripts\python.exe" -B scripts\validate_generic_engine.py
```

Also run the existing delivery and V2 guardrail validators for changes that
touch their scope.
