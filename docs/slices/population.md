# Population and settlement slice characterization

Status: active; primary increment locally approved, ranking increment awaiting
localhost review, complete slice open
Behavior reference: frozen V2 for Trøndelag only
Integration target: V2 Final wind restriction flow

## Scope

The common group id is `population`. The first bounded increment migrates the
primary Trøndelag `population_points` source. The id is historical: the
validated source geometry is a dissolved polygon proxy representing occupied
250 m population-grid cells.

Two optional Trøndelag settlement proxies, `built_centre` and
`built_low_selection`, remain on the explicit transitional registry adapter
until later increments in this slice. Solar population behavior is a separate
future slice and is not claimed here.

## Accepted Trøndelag behavior

- Public legacy group: `settlement`.
- Primary source id: `population_points`.
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

The implemented layer contract declares:

- canonical group `population`;
- detected geometry family `polygon`;
- data representation `grid`;
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
- **Rewritten in this increment:** the primary population branch in the wind
  control and fast-distance runtime now consumes the canonical result.
- **Removed in this increment:** primary-layer fallthrough to the legacy
  distance loader and the Trøndelag-specific wind population preview path.
- **Still transitional:** optional settlement inputs and the public
  `settlement` alias.

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

The automated first-increment gates pass: generic engine 542/542, frozen-V2
V2 Final parity 65/65, real Streamlit AppTest 48/48, and vector preview 16/16.
The healthy app path and adversarial broken-contract cases both prove that the
primary source cannot fall back to the legacy distance loader.

The user approved the clean localhost checkpoint on 2026-07-31, so this
bounded primary increment is locally promoted. The source and buffer
comparison is currently defined for the canonical primary layer alone;
selecting it together with an optional transitional proxy does not yet provide
a mixed buffer preview.

This increment is not the complete population slice. Completion also requires
canonical optional settlement sources, removal of the public `settlement`
alias, final regression, and localhost approval of that complete behavior.

## Allocation-ranking increment

The wind allocation-ranking consumer now obtains `population_points`
distance/intersection observations from the canonical manifest engine at
R7/R6/R5. It keeps the accepted ranking formula and continues to combine the
primary source with optional transitional settlement proxies by minimum
distance and any intersection. The legacy registry loader is permitted only
for those still-transitional optional sources; attempting to load
`population_points` there is an automated failure.

The immutable canonical ranking frame is cached per region, selected canonical
layer set, manifest default ranking threshold, and target resolution so normal
Streamlit reruns do not repeatedly process the 89,312-row source artifact.
Accepted-reference validation compares every R7/R6/R5 ranking score with the
previous frozen-registry path and reports zero drift. The automated gate is
ready for localhost review; this increment is not yet locally promoted.

## Optional-source decision

`built_centre` and `built_low_selection` should be migrated, not removed. Both
are explicit accepted Trøndelag public options, are off by default, and are
already present in the checksum-pinned runtime package. `built_centre` resolves
to one `MultiPolygon`; `built_low_selection` resolves to 10,966 points. Each
has a complete 89,312-row R8 distance artifact over the same signed source-cell
universe as the primary layer, so the shared geometry-driven adapters and
sparse R8-to-R7/R6/R5 contract are sufficient without a regional algorithm.
The next bounded increment is to declare both in the analysis manifest, add
individual and combined accepted-reference gates, and remove their remaining
registry adapter path.
