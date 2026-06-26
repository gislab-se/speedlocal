# Catalog-Driven Region Onboarding

Adding a new region such as Skane should not require hardcoded app branches.
It does require a complete catalog and runtime contract.

Minimum catalog:

- `regions/index.json` entry.
- `regions/<region>/region.json`.
- Region id, display name, status, country, native CRS, web CRS.
- Landing-card metadata.
- Supported H3 display resolutions and default resolution.
- Runtime backend preference.
- Required Postgres tables.
- File fallback paths while Postgres imports are incomplete.
- Readiness requirements and known regional exceptions.

Minimum data:

- Validated region boundary or display geometry.
- H3 display cells at declared resolutions.
- Landscape cells or explicit unavailable status.
- Potential/scenario/acceptance manifests or explicit planned/placeholder status.
- Region-specific CRS and proxy notes.

Validation:

- Region appears from `regions/index.json` only.
- Planned regions stay disabled until required runtime data exists.
- Active regions pass independent validation.
- Trondelag-like constraints are documented in the region package, not hidden in
  app code.
