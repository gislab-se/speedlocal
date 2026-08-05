# Population and settlement slice characterization

Status: direct-R7 correction locally promoted on 2026-08-04; unpublished
Behavior reference: frozen V2 for Trøndelag only
Integration target: V2 Final wind restriction flow

## Scope

The public and canonical group id is `population`. The historical
`population_points` id names the primary source, whose
validated source geometry is a dissolved polygon proxy representing occupied
250 m population-grid cells.

Two optional Trøndelag sources are also canonical: `built_centre` is a
polygon source for settlement centres. `built_low_selection` is technically a
point source, but its 10,966 points are centroids of populated SSB 1 km cells
with a `bui2hol` count, not individual leisure-home locations. Solar population
behavior is a separate future slice and is not claimed here.

Manifest layer order is the public control-layout contract. The first
declared population source is shown as the primary source, and later declared
sources are shown under `Fler datakällor`. No source id is hardcoded as the
primary UI option.

## Accepted Trøndelag behavior

- Public canonical group: `population`; the former public `settlement` alias
  is removed from the wind flow.
- Source ids: `population_points`, `built_centre`, and
  `built_low_selection`.
- Analysis kind: minimum-distance conflict with frozen V2 soft acceptance.
- Slider: 100–3,000 m in 50 m steps.
- V2 Final control default: 100 m; the frozen comparison checkpoint is 500 m.
- Acceptance is 0 at or inside the selected distance, increases linearly to 1
  at twice that distance, and remains 1 beyond it.

The source GeoJSON contains one dissolved `MultiPolygon` constructed from
26,029 occupied 250 m grid-cell centroids. Its properties explicitly declare
`proxy_type=250m_grid_cell_from_centroid` and `cell_size_m=250`.

### Known leisure-home proxy limitation

`built_low_selection` exposes point geometry because the accepted archive
contains cell centroids. Semantically it is a coarse 1 km grid proxy: distance
is measured from each cell centre, each point represents the cell's `bui2hol`
count, and the locations of individual leisure homes inside the cell are
unknown. This is especially approximate relative to a 100 m buffer. The
control therefore carries a manifest-driven `caution` quality flag and an
explicit tooltip. This promotion preserves the declared calculation and does
not claim address-level accuracy; a future source-model correction requires
separate accepted evidence.

The corrected numeric contract contains one complete 13,735-row R7 table per
source. For every declared R7 analysis cell, the offline generic builder
records distance from the cell representative point to the source plus an
independent full-cell/source intersection flag. R6 and R5 are derived only by
minimum R7 child distance and any R7 child intersection. Coverage is
`complete` and fails closed on a missing, extra, or duplicate cell.

## Direct-R7 correction and accepted frozen-reference drift

Frozen V2 starts from 89,312 R8 observations and aggregates them to the public
domain. The 2026-08-04 correction intentionally replaces that sampling basis
with the declared R7 model above. `analyze_direct_distance_drift.py` compares
all seven non-empty layer combinations at R7/R6/R5 and 100, 500, 1,000, and
3,000 m: 84 complete aggregate comparisons. The independent baseline oracle
recomputes the same source-to-R7 relationship from the checksum-declared
source geometry rather than trusting the generated CSV or generic engine.

For the primary layer at R7, mean-potential drift from frozen V2 is -13.491
percentage points at 100 m, +4.586 at 500 m, +7.636 at 1,000 m, and +3.709 at
3,000 m. The old 256/26/7 R7/R6/R5 coverage gaps are eliminated. This drift
is accepted as the intended consequence of measuring the declared R7 domain
directly; frozen V2 remains the historical behavioral reference, not the
numeric oracle for this corrected increment.

## Percentage interpretation and deferred shared result

The population percentage remains a soft-distance acceptance proxy. It is not
the geometrically measured share of an R7/R6/R5 hex that
remains outside the displayed population buffer. A display hex can therefore
look partly free but receive zero wind potential when its representative-point
distance is at or inside the threshold or its full cell intersects the source.
Conversely, a positive proxy value may round to `0 %` in the current integer-
only hover.

On 2026-08-03 the user confirmed the future common interpretation: wind and
solar hover percentages must each be the remaining establishment area after
all active technology-applicable restrictions, divided by the same manifest-
declared model land area for that hex. Map classification, hover, and summary
must consume that single result. This is scheduled for the combined-result
and wind/solar phases after nature, culture, and grid infrastructure are
manifest-migrated; it does not reopen or redefine this promoted parity slice.

## Direct-R7 accepted numeric anchors

| Resolution | Distance | Mean potential | Zero-acceptance cells | Model potential area (km²) |
|---|---:|---:|---:|---:|
| R7 | 100 m | 70.7317073170732% | 4,020 | 32,033.294765366558 |
| R7 | 500 m | 70.7032070555904% | 4,020 | 32,020.544812344022 |
| R7 | 1,000 m | 63.2341415952041% | 4,083 | 28,655.258106115540 |
| R7 | 3,000 m | 33.0719673584432% | 7,588 | 15,028.059399211797 |
| R6 | 500 m | 47.8346551550441% | 1,128 | 21,293.754330461623 |
| R5 | 500 m | 24.3557477936959% | 276 | 7,504.290681082110 |

Mean potential is the unweighted mean per analysis cell. With complete direct-
R7 coverage, the cell-count column is also the distance/intersection-blocked
count. Model area uses the manifest-declared `display_area_m2` contract and is
separate evidence.

## Generic contract

The implemented layer contracts declare:

- canonical group `population`;
- detected polygon/grid geometry for `population_points`, polygon/features
  for `built_centre`, and point/features for `built_low_selection`;
- operation `distance_exclusion`;
- complete numeric distance-artifact resolution R7;
- exact 13,735-cell source/target coverage and fail-closed missing coverage;
- the common `buffer_m` parameter and its complete slider domain;
- provider-resolved source and distance assets;
- UI label, proxy explanation, and map-review styling.

Adapter selection must depend on validated data characteristics:

- point + non-grid representation → `population_points`;
- polygon + non-grid representation → `population_polygons`;
- point or polygon + grid representation → `population_grid`.

No region id may select an adapter or analysis algorithm.

## Code classification

- **Keep:** frozen soft-distance semantics, common analysis domain and area
  contract, shared Streamlit form/session behavior, and downstream result
  consumers.
- **Extract:** generic source-geometry-to-domain artifact building, layer-level
  distance-resolution validation, raw-first H3 rollup, generic selected-
  distance-group execution, and vector source/buffer preview.
- **Configure:** group/layer ids, proxy representation, geometry, source paths,
  direct-R7 artifact provider/path, labels, colors, and slider bounds.
- **Rewritten:** wind selection, controls, fast-distance runtime, previews,
  and allocation ranking consume the three-layer canonical population result.
- **Removed:** all population fallthrough to the legacy distance loader, the
  public wind `settlement` alias, the redundant population group checkbox,
  the Trøndelag-specific wind population preview path, and the dead
  population cases in the legacy wind source/buffer renderers.

`settlement_distance_m` remains an internal saved-state/model parameter key
until a versioned state migration can rename it. It is not a public group id
or a manifest availability contract. Since 2026-08-05, large-scale solar map
review uses this manifest source and exact area-group preview. The separate
small-scale rooftop schematic and its energy accounting remain solar-slice
concerns.

## First-increment gates

- Validate the manifest layer as `population_grid` with detected polygon
  geometry and declared R7 numeric resolution.
- Reject invalid or mixed-resolution artifacts, finer analysis requests, and
  any incomplete direct-R7 target coverage.
- Compare every target cell at 100, 500, 1,000 and 3,000 m for R7/R6/R5 with
  an independent source-geometry-to-R7 oracle.
- Compare mean, true blocked count, zero-acceptance count, and model area
  against fixed anchors.
- Prove the actual V2 Final primary layer does not call the legacy distance
  loader while all promoted road checks remain unchanged.
- Source and buffer map-review toggles must not change selection, parameters,
  or numeric results.
- Localhost review must show monotonically decreasing potential at 100, 500,
  and 1,000 m and allow inspection at R7/R6/R5.

The complete automated gates cover the generic engine, frozen-V2 V2 Final
parity, real Streamlit AppTest, and vector previews. They prove that all three
population sources stay on the canonical path at R7/R6/R5 and that promoted
roads behavior is unchanged.

The user approved the final simplified three-source control in a clean
localhost process on port 8502 on 2026-08-03. The complete population slice is
therefore locally promoted. Publication remains separate, and `main` and the
external deployment are unchanged.

The user approved the direct-R7 correction and its corrected source previews
in a clean single-process localhost review on 2026-08-04. The complete app gate
also verifies the compact 4 px leisure-home markers and the manifest-driven
caution flag. The corrected increment is locally promoted and unpublished.

## Allocation-ranking increment

The wind allocation-ranking consumer obtains all three population sources'
distance/intersection observations from the canonical manifest engine at
R7/R6/R5. It keeps the accepted ranking formula and combines selected sources
by minimum distance and any intersection. Any attempt to load a canonical
population source through the legacy registry is an automated failure.

The immutable canonical ranking frame is cached per region, selected canonical
layer set, manifest default ranking threshold, and target resolution so normal
Streamlit reruns do not repeatedly process the 13,735-row source artifact.
Accepted-reference validation compares every R7/R6/R5 ranking score with the
independent direct-R7 ranking oracle.

## Optional-source completion

`built_centre` and `built_low_selection` were migrated rather than removed. Both
are explicit accepted Trøndelag public options, are off by default, and are
included in the 48-file checksum-pinned runtime checkpoint. `built_centre` resolves
to one `MultiPolygon`; `built_low_selection` resolves to 10,966 points. Each
has a complete 13,735-row direct-R7 distance artifact over the same declared
analysis domain as the primary layer, so the shared geometry-driven builder
and R7-to-R6/R5 rollup are sufficient without a regional algorithm.
Both are now declared in the analysis manifest, have individual and combined
accepted-reference and vector-preview gates, and have no remaining wind
registry adapter path.
