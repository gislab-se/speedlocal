# Grid-infrastructure slice characterization

Status: locally promoted on 2026-08-04; unpublished
Behavior reference: frozen V2 for Trøndelag only
Integration target: V2 Final wind feasibility flow

## Scope

The public and canonical group id is `grid_infrastructure`. The complete
current Trøndelag group contains three independently selectable sources:

- `high_voltage_lines`, a 16,932-feature transmission-line source;
- `underground_cables`, a 330-feature underwater-cable line source;
- `existing_wind_turbines`, a 470-feature point source.

The transitional registry also names `power_substations`, but Trøndelag has no
verified source or runtime asset for it. It is not a public Trøndelag option
and must fail closed if requested. Since 2026-08-05, solar retains
`electrical` only as a public session/UI key and maps it to canonical
`grid_infrastructure` for source review and exact domain-clipped buffer review.

## Accepted Trøndelag behavior

- Analysis kind: proximity feasibility; too far away is bad.
- Slider: 500–15,000 m in 250 m steps; default 2,000 m.
- Selected sources combine by minimum distance and any intersection.
- Acceptance is 1 for an intersecting cell, otherwise
  `clip(1 - minimum_distance / maximum_connection_distance, 0, 1)`.
- A cell beyond the maximum connection distance has zero acceptance.
- All three accepted distance artifacts contain exactly 13,735 unique R7
  observations. R6 and R5 use the minimum distance and any intersection among
  contributing R7 children before the feasibility formula is applied.

The vector sources are valid non-empty CRS84 `MultiLineString`,
`MultiLineString`, and `MultiPoint` geometries. The source preview renders
those exact vectors. The original locally promoted buffer review rendered
whole feasible R7 cells as a fast diagnostic of the soft-distance group
engine. Review on 2026-08-05 established that this was visually inconsistent
with the already promoted public wind/solar area contract. The correction
candidate now buffers the selected vectors in the native metric CRS, clips the
result locally to every R7 analysis cell, and dissolves those exact clipped
parts for display. The same fractions and manifest-declared cell areas drive
technology potential, hover, table, and allocation; the five-group
soft-distance metric and its frozen anchors remain unchanged.

## Frozen numeric anchors

| Sources | Resolution | Maximum distance | Mean acceptance | Zero cells | Model potential area (km²) |
|---|---:|---:|---:|---:|---:|
| Transmission | R7 | 500 m | 34.692391700036% | 8,970 | 15,626.037306365233 |
| Transmission | R7 | 2,000 m | 38.929144521296% | 6,732 | 17,534.576905796115 |
| Transmission | R7 | 15,000 m | 78.842961970635% | 364 | 35,596.448814965464 |
| Transmission | R6 | 2,000 m | 60.600873786408% | 711 | 28,150.881843896183 |
| Transmission | R5 | 2,000 m | 79.991726027397% | 61 | 39,981.102141200048 |
| All three | R7 | 2,000 m | 39.481352384419% | 6,673 | 17,780.848461686470 |
| All three | R6 | 2,000 m | 61.125457697642% | 702 | 28,295.255871122208 |
| All three | R5 | 2,000 m | 80.542534246575% | 59 | 40,000.610596470484 |

The anchors are independent calculations over the accepted distance tables
and the manifest-declared `display_area_m2` domain. They are frozen behavior
evidence, not a claim of literal cable-connection engineering capacity.

## Exact technology-area anchors

These separate anchors describe the literal geometric feasibility area used
by both wind and solar. They must not replace or be compared as though they
were the soft-distance group scores above.

| Sources | Resolution | Maximum distance | Exact model area (km²) | Exact share | Positive cells |
|---|---:|---:|---:|---:|---:|
| All three | R7 | 500 m | 8,992.417252706564 | 19.888925162056% | 6,170 |
| All three | R7 | 2,000 m | 23,137.469491933643 | 51.174159987506% | 8,669 |
| All three | R7 | 15,000 m | 43,995.631502075770 | 97.307075262638% | 13,458 |

At 2,000 m the exact total is unchanged when R7 is rolled to R6/R5;
positive-cell counts are 8,669/1,611/311. Wind and solar have identical
per-cell grid geometry under the shared manifest contract.

## Generic contract

The slice adds `proximity_feasibility` as a distance-based operation. Runtime
selection depends on declared and detected source characteristics; no region
id chooses an algorithm. The operation shares the validated source resolver,
exact R7/R6/R5 domain, distance rollup, form/session behavior, and vector
preview pipeline with the already promoted groups, while its acceptance
direction is explicitly opposite to distance exclusion.

## Code classification

- **Keep:** frozen proximity formula, common analysis domain, minimum-distance
  source composition, form-batched controls, map-review behavior, and
  downstream result consumers.
- **Extract:** generic proximity operation, canonical group bridge, and shared
  exact area-group preview built from the technology-area primitives.
- **Configure:** group/layer ids, line/point representations, source paths,
  R7 distance resolution, labels, colors, ordering, and slider contract.
- **Rewrite:** wind selection, controls, calculation, source/buffer previews,
  and allocation-ranking input consume the canonical group result.
- **Remove:** the public wind `electrical` alias, its registry availability and
  data adapter, legacy distance-loader fallthrough, and dead wind-only
  electrical rendering cases after parity is proven.

## Promotion gates

- Validate every source and its complete R7 artifact through the manifest.
- Compare individual and combined R7/R6/R5 cells with an independent raw-CSV
  proximity oracle at 500, 2,000, and 15,000 m.
- Prove invalid, blank, duplicate, undeclared, and legacy `electrical`
  selections fail before registry loading.
- Prove V2 Final calculation and wind allocation ranking never load a migrated
  electrical source through the legacy registry.
- Validate exact line/point source previews and monotonically growing,
  domain-clipped metric buffers at 500/2,000/15,000 m; require partial cells
  and equality with the accepted exact technology-area anchors.
- Validate direct manifest controls, form batching, map-review toggles, and
  R7/R6/R5 values in the real Streamlit app.
- Preserve every promoted roads, population, nature, and culture gate.

All automated gates above pass on 2026-08-04. The user approved the corrected
clean-process localhost controls, calculation, source preview, and feasibility
review on the same date, so the complete current slice is locally promoted.
The 2026-08-05 exact-preview correction remains a candidate until its updated
automated gates and clean-process localhost review pass. Publication remains a
separate checkpoint.
