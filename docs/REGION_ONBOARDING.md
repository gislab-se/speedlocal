# Catalog-Driven Region Onboarding

Adding a new region such as Skane should not require hardcoded app branches.
It does require a complete catalog and runtime contract.

The authoritative migration sequence is in `GENERAL_PROGRAM_PLAN.md`.
Onboarding currently covers only the five standard groups: roads, population,
nature, culture, and grid infrastructure. Regional exceptions are deferred.

An indexed region may be `onboarding` or `planned` without being publicly
enabled. `landing_card.enabled` becomes `true` only after the region's accepted
behavior reference, runtime data, and independent acceptance checks are
recorded and pass.

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

Behavior-reference gate:

- Identify the intended public reference separately for each region.
- Record repository, exact commit, entrypoint, deployment, and protected ref
  before calling a reference technically frozen.
- Separate source integrity and generic engine conformance from public
  behavioral parity.
- Trøndelag currently uses frozen V2.
- Bornholm currently uses V1 as an unpinned visual reference. Its V1-derived V2
  archive material is diagnostic only.
- A region with no trusted historical reference receives explicit,
  reviewable acceptance fixtures rather than inferred parity.

Validation:

- Region appears from `regions/index.json` only.
- Planned and onboarding regions stay disabled until all readiness gates pass.
- Active regions pass independent validation.
- Algorithms dispatch from validated data characteristics, not region ids.
- Point, grid, and polygon representations of the same theme pass independent
  adapter validation.
