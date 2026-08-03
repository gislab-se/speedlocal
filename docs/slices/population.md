# Population and settlement slice characterization

Status: locally promoted on 2026-08-03; unpublished
Behavior reference: frozen V2 for Trøndelag only
Integration target: V2 Final wind restriction flow

## Scope

The public and canonical group id is `population`. The historical
`population_points` id names the primary source, whose
validated source geometry is a dissolved polygon proxy representing occupied
250 m population-grid cells.

Two optional Trøndelag sources are also canonical: `built_centre` is a
polygon source for settlement centres and `built_low_selection` is a point
source based on leisure-home centroids. Solar population behavior is a
separate future slice and is not claimed here.

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

The numeric CSV is a different accepted artifact: 89,312 centroid-derived H3
R8 distance rows. It is intentionally sparse relative to the display domain:
256 R7, 26 R6, and 7 R5 cells have no contributing R8 row. Frozen V2 retains a
missing distance, does not mark the cells geometrically blocked, and assigns
zero acceptance. The manifest therefore declares an exact `declared_sparse`
coverage signature with `missing_policy=zero_acceptance`; other layers retain
the default complete/error contract. V2 Final must preserve that fail-closed
numeric behavior for parity while labelling the proxy honestly. Raw R8 rows
are aggregated to each requested parent before filtering to and completing the
manifest-declared R7, R6, or R5 target domain.

## Percentage interpretation and deferred shared result

The promoted population percentage is a frozen-V2 soft-distance acceptance
proxy. It is not the geometrically measured share of an R7/R6/R5 hex that
remains outside the displayed population buffer. A display hex can therefore
look partly free but receive zero wind potential when its rolled minimum
distance is at or inside the threshold, or when its signed sparse coverage is
missing. Conversely, a positive proxy value may round to `0 %` in the current
integer-only hover.

On 2026-08-03 the user confirmed the future common interpretation: wind and
solar hover percentages must each be the remaining establishment area after
all active technology-applicable restrictions, divided by the same manifest-
declared model land area for that hex. Map classification, hover, and summary
must consume that single result. This is scheduled for the combined-result
and wind/solar phases after nature, culture, and grid infrastructure are
manifest-migrated; it does not reopen or redefine this promoted parity slice.

## Frozen numeric anchors

| Resolution | Distance | Mean potential | Zero-acceptance cells | Model potential area (km²) |
|---|---:|---:|---:|---:|
| R7 | 100 m | 84.2224958864216% | 1,485 | 38,119.151592087590 |
| R7 | 500 m | 66.1171676447033% | 4,048 | 29,960.271522643929 |
| R7 | 1,000 m | 55.5979262977794% | 5,203 | 25,213.340431058976 |
| R7 | 3,000 m | 29.3628459094770% | 8,260 | 13,350.050589430422 |
| R6 | 500 m | 45.2247388811835% | 1,125 | 20,357.789476729769 |
| R5 | 500 m | 22.3069857534247% | 278 | 6,930.123791379062 |

Mean potential is the frozen unweighted mean per analysis cell. The cell-count
column records zero acceptance, not only true geometric blocks. At 500 m, the
true distance/intersection-blocked counts are 3,792/1,099/271 for R7/R6/R5;
the remaining 256/26/7 zero-acceptance cells are coverage-missing. Model area
uses the manifest-declared `display_area_m2` contract and is separate evidence.

## Generic contract

The implemented layer contracts declare:

- canonical group `population`;
- detected polygon/grid geometry for `population_points`, polygon/features
  for `built_centre`, and point/features for `built_low_selection`;
- operation `distance_exclusion`;
- numeric distance-artifact resolution R8;
- exact source/target coverage signatures and fail-closed zero acceptance when
  no selected layer supplies a distance observation;
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
- **Extract:** layer-level distance-resolution validation, raw-first H3 rollup,
  generic selected-distance-group execution, and vector source/buffer preview.
- **Configure:** group/layer ids, proxy representation, geometry, source paths,
  R8 artifact resolution, labels, colors, and slider bounds.
- **Rewritten:** wind selection, controls, fast-distance runtime, previews,
  and allocation ranking consume the three-layer canonical population result.
- **Removed:** all population fallthrough to the legacy distance loader, the
  public wind `settlement` alias, the redundant population group checkbox,
  the Trøndelag-specific wind population preview path, and the dead
  population cases in the legacy wind source/buffer renderers.

`settlement_distance_m` remains an internal saved-state/model parameter key
until a versioned state migration can rename it. It is not a public group id
or a manifest availability contract. Solar's separate registry-backed
population helpers remain intentionally deferred to the solar slice.

## First-increment gates

- Validate the manifest layer as `population_grid` with detected polygon
  geometry and declared R8 numeric resolution.
- Reject invalid or mixed-resolution artifacts and undeclared upward rollups;
  reject incomplete target coverage unless the layer explicitly declares and
  exactly matches its sparse-coverage signature.
- Compare every target cell at 100, 500, 1,000 and 3,000 m for R7/R6/R5 with
  an independent raw-CSV oracle.
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

## Allocation-ranking increment

The wind allocation-ranking consumer obtains all three population sources'
distance/intersection observations from the canonical manifest engine at
R7/R6/R5. It keeps the accepted ranking formula and combines selected sources
by minimum distance and any intersection. Any attempt to load a canonical
population source through the legacy registry is an automated failure.

The immutable canonical ranking frame is cached per region, selected canonical
layer set, manifest default ranking threshold, and target resolution so normal
Streamlit reruns do not repeatedly process the 89,312-row source artifact.
Accepted-reference validation compares every R7/R6/R5 ranking score with the
previous frozen-registry path and reports zero drift.

## Optional-source completion

`built_centre` and `built_low_selection` were migrated rather than removed. Both
are explicit accepted Trøndelag public options, are off by default, and are
already present in the checksum-pinned runtime package. `built_centre` resolves
to one `MultiPolygon`; `built_low_selection` resolves to 10,966 points. Each
has a complete 89,312-row R8 distance artifact over the same signed source-cell
universe as the primary layer, so the shared geometry-driven adapters and
sparse R8-to-R7/R6/R5 contract are sufficient without a regional algorithm.
Both are now declared in the analysis manifest, have individual and combined
accepted-reference and vector-preview gates, and have no remaining wind
registry adapter path.
