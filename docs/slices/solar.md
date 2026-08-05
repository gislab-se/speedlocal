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

## Code classification

- **Keep:** public widget/session keys and the separate rooftop schematic map
  layer.
- **Extract:** analysis-aware applicable-group, control, source, and exact-area
  preview bridge functions.
- **Configure:** applicable groups, layer ids, source paths, readiness, labels,
  colors, distance contracts, operations, and area semantics from the solar
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
Small-scale rooftop output is also still a schematic display and does not reduce
residual ground-mounted solar demand. That accounting is the next independent
increment and requires a declared, validated energy-yield contract.

The map-review increment remains a candidate until clean-process localhost
review passes. Publication is a separate checkpoint.
