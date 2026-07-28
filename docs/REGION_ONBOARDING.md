# Catalog-Driven Region Onboarding

Adding a new region such as Skane should not require hardcoded app branches.
It does require a complete catalog and runtime contract.

The authoritative migration sequence is in `GENERAL_PROGRAM_PLAN.md`.
Onboarding currently covers only the five standard groups: roads, population,
nature, culture, and grid infrastructure. Regional exceptions are deferred.

Minimum catalog:

- `regions/index.json` entry.
- `regions/<region>/region.json`.
- Region id, display name, status, country, native CRS, web CRS.
- Landing-card metadata.
- Supported H3 display resolutions and default resolution.
- Runtime backend preference.
- Required Postgres tables.
- File fallback paths while Postgres imports are incomplete.
- Readiness requirements and known data limitations.

Minimum data:

- Validated region boundary or display geometry.
- H3 display cells at declared resolutions.
- Landscape cells or explicit unavailable status.
- Potential/scenario/acceptance manifests or explicit planned/placeholder status.
- Region-specific CRS and proxy notes.
- Declared acceptable geometry families per layer.
- Data representation metadata where geometry alone is insufficient, such as a
  population point source versus a population grid.

Validation:

- Region appears from `regions/index.json` only.
- Planned regions stay disabled until required runtime data exists.
- Active regions pass independent validation.
- Algorithms dispatch from validated data characteristics, not region ids.
- Point, grid, and polygon representations of the same theme pass independent
  adapter validation.
