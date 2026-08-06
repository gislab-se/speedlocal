# Solar potential slice

## Current boundary

Trøndelag's large-scale solar area result uses the validated `solar` analysis
manifest, which extends the five canonical standard constraints and declares
`roads`, `population`, `nature`, `culture`, and `grid_infrastructure` as its
applicable groups. Its exact R7 establishment area is the public source for map
classification, hover, result capacity, and scenario allocation; R6/R5 derive
from the R7 result.

The 2026-08-05 map-review increment migrates the presentation boundary for
those five groups. Solar source availability, selected source ids, readiness,
provider resolution, group semantics, colors, and operation now come from the
validated solar manifest. Each enabled buffer review uses the same metric
source geometry and exact R7 domain clipping as the solar area-result contract.
Grid proximity therefore displays real partial geometry rather than whole
analysis hexagons.

Existing public visual ids (`transport`, `protected`, `culture`, `electrical`,
and `large_population`) remain only as session/UI compatibility keys. They map
to canonical manifest ids at the boundary and do not select an algorithm.
Unsupported or wrong-group requests fail closed.

Small-scale rooftop solar remains a separate schematic population layer. It is
not an area restriction and is deliberately not routed through the large-scale
area-group preview.

## Rooftop-energy accounting

The rooftop control now has a typed, manifest-declared planning-proxy contract
under `distributed_generation.rooftop_solar`. The contract pins the population
source and checksum, the R8-to-canonical-R7 aggregation, the slider range, and
the annual-yield assumptions. Its map-review binding resolves the canonical
`population_points` source and that layer's declared 100 m default buffer from
the inherited solar analysis; no rooftop source id or distance is selected in
the Streamlit code. The count source contains 477,978 people. Its map
schematic is clipped at canonical R7 before R6/R5 rollup and therefore shows
477,755 people at every supported display resolution; the declared accounting
policy deliberately uses the full source total before that cartographic clip.

At the default 10 m² panel area per person, the declared PVGIS planning yield
of 167.649167 kWh/m²/year gives 0.801326 TWh of rooftop electricity. This is
capped at the gross solar target and subtracted from the energy and area still
requiring ground-mounted solar:

```text
rooftop TWh = min(gross solar TWh,
                  population × panel m²/person × annual kWh/m² / 1e9)
ground solar TWh = gross solar TWh - rooftop TWh
ground area need km² = ground solar TWh × declared km²/TWh
```

The gross scenario energy remains unchanged. Rooftop solar does not alter the
exact geographic solar potential, per-hex hover values, acceptance capacity,
or the set of ground-establishment candidates. It changes only the residual
ground-solar demand and the amount allocated from those candidates. A zero
panel-area selection reproduces the pre-accounting result.

## Code classification

- **Keep:** public widget/session keys and the separate rooftop schematic map
  layer.
- **Extract:** analysis-aware applicable-group, control, source, and exact-area
  preview bridge functions.
- **Configure:** applicable groups, layer ids, source paths, readiness, labels,
  colors, distance contracts, operations, area semantics, rooftop population,
  slider bounds, yield assumptions, and accounting policy from the solar
  manifest.
- **Rewrite:** standard solar source/buffer map-review factories and their
  availability controls.
- **Remove:** solar protected-source/buffer wrappers and the registry-backed
  map-review path they replaced.

## Gates

- Every applicable solar group exposes provider-resolved non-empty source
  GeoJSON and an exact `exact_area_clip` buffer preview.
- Solar and wind grid review agree at 2,000 m, including 23,137.469491933643
  km² model area and 3,815 partial R7 cells.
- Wrong-group and non-applicable requests fail closed.
- A real Streamlit run enables source and buffer controls for all five active
  solar groups, builds every selected review layer, and leaves the applied
  analysis configuration unchanged apart from map-only visibility state.
- Rooftop source checksum, source total, canonical R7 clip, R6/R5 rollups, zero
  selection, target cap, energy conservation, and monotonic residual-ground
  demand are validated independently of Streamlit.
- A real Streamlit run proves that enabling rooftop solar reduces the table's
  ground-area demand while gross solar energy, exact geographic potential, and
  land-candidate semantics remain unchanged.
- The existing generic-engine, combined-result, runtime, guardrail, delivery,
  and complete real-app regressions remain green.

## Deferred work

This increment does not claim the entire historical solar UI is dismantled.
Some legacy public ids and form-state adapters remain while the later solar
potential and continuous-allocation slices are migrated. In particular,
slider minimum/maximum/step values still come from
`SOLAR_FILTER_GROUP_SPECS`; the roads form currently permits 0–500 m while the
canonical manifest declares 100–2,000 m. Moving those form contracts to the
manifest is a later solar-control increment, not part of this map-only repair.
The rooftop map remains a population-based schematic rather than measured roof
geometry. Its yield is a regional planning proxy, not a building-level
production forecast. Replacing it with roof-register geometry, shading,
orientation, ownership, grid-capacity, and adoption constraints is later work.
The declared six-site PVGIS mean is currently an accepted planning assumption:
the repository pins the method and one representative query, but not yet the
six individual query inputs and results. That evidence should be added before
the proxy is presented as a reproducible production estimate.

The map-review increment remains a candidate until clean-process localhost
review passes. Publication is a separate checkpoint.
