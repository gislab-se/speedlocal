# Roads slice characterization

Status: Trøndelag `roads_large` and verification cleanup are locally approved but the new development checkpoint is unpublished; `roads_medium` and combined roads are canonical with automated R7/R6/R5 gates, pending localhost visual review and removal of the temporary legacy road UI/data adapter
Behavior reference: frozen V2 for Trøndelag; Bornholm V1 acceptance baseline pending
Integration target: V2 Final

## User-visible behavior

For wind analysis, the user:

- enables available road layers;
- sets one minimum road distance for the complete road group;
- applies the controls;
- sees road restrictions affect acceptance, wind score, possible
  establishment area, map layers, and summaries.

The Trøndelag V2 Final surface currently exposes medium and large roads.
Bornholm's catalog also declares those layers for onboarding diagnostics.
Bornholm's small-road source is empty after filtering and is not part of the
generic contract.

Bornholm's medium-road distance table is complete, but its source GeoJSON has
one null geometry. The layer can participate in analysis through the validated
precomputed-distance artifact, but cannot be drawn as a source line until that
display asset is repaired. This limitation is explicit in the layer contract.

## Historical calculation contracts

The frozen archive contains two runtime representations:

- Trøndelag uses precomputed H3 distances and soft acceptance: 0 at or inside
  the buffer, a linear ramp to 1 at twice the buffer, and 1 beyond it.
- Bornholm uses buffered polygons, subtracts their union from the region, and
  converts the remaining polygon area to partial H3 shares for display. This
  V1-derived representation is diagnostic evidence, not an accepted Bornholm
  V2 behavior baseline.

The canonical `speedlocal` roads engine validates the internal H3 distance
contract: minimum distance across selected layers, any-intersection
composition, `distance <= buffer_m` blocking, and the soft acceptance ramp.
For Trøndelag R7/R6/R5, medium-only, large-only, and combined roads are
connected to the actual V2 Final result flow and tested against the frozen V2
cell universes. Bornholm's generic engine execution remains
contract/diagnostic evidence, not behavioral parity.

## Relevant V2 code classification

### Keep as Trøndelag behavior reference

- `_group_distance_frame`
- `_distance_conflict_acceptance`
- road-related output semantics from `_build_wind_acceptance_frame_cached`

### Extract or reproduce generically

- minimum-distance composition across selected road layers;
- intersection composition;
- blocked-cell rule;
- soft acceptance ramp.

These belong in `speedlocal/engine.py`, independent of Streamlit.

### Configure

- available road layers;
- source and distance-table paths;
- labels;
- geometry/data representation;
- minimum, maximum, step, and default buffer.

These belong in each region's `analyses/wind.json`.

### Rewrite for promotion

- road portion of `_wind_group_controls`;
- mapping from Streamlit state to an analysis request;
- road result presentation.

The R7/R6/R5 road replacement now reads its slider contract, selected layer
set, and cell result from the common contract. The surrounding legacy
`transport` UI, labels, readiness, and source-display path remain a
transitional adapter until the complete road slice is promoted.

### Remove after promotion

- road entries in `WIND_GROUP_LAYER_DEFAULTS` after the canonical road UI is
  connected;
- road filtering performed by `normalize_group_layer_map`;
- road-specific dependence on `GROUP_PARAM_MAP`;
- duplicate road selector paths no longer used by the public UI.

## Trøndelag parity and shared-contract requirements

- `distance == buffer_m` is blocked.
- Increasing the buffer cannot reduce blocked-cell count.
- Combined medium+large result uses minimum distance and any intersection.
- Generic per-layer and group cell counts match the legacy distance tables.
- Trøndelag's frozen-public UI checkpoints are tested separately from the
  generic distance-engine contract.
- Bornholm source/engine and polygon-fixture checks run separately as
  onboarding diagnostics and must not be labelled parity.

## Promotion boundary

No remaining V2 road code is removed until:

- generic medium and large road layers validate;
- the affected resolution uses the generic result in the actual V2 Final
  Streamlit surface;
- combined group parity passes before the complete legacy road group is
  removed;
- the V2 Final public-flow smoke test still passes;
- Trøndelag localhost behavior and output match its frozen V2 reference.

Bornholm onboarding does not block removal of a Trøndelag-specific legacy path.
No shared path may be removed if the generic catalog or diagnostic contracts
still depend on it.

## Baseline repair evidence

Completed 2026-07-30 before calculation-level promotion:

- Bornholm and Trøndelag declare their external acceptance registry through
  `runtime.sources.acceptance_registry`;
- registry, asset-manifest, GeoJSON, distance-table, and GPKG paths use the
  shared provider resolver;
- duplicate registry JSON files and the duplicate V2-port path resolver are
  removed;
- Trøndelag reports 14/14 runtime-ready legacy layers;
- Bornholm reports 26/27; `roads_small` is the single intentional
  `empty_after_filter` layer;
- runtime strategy comes from each source contract, not a region-name branch:
  Trøndelag uses `fast_distance`; Bornholm's diagnostic fixture loader uses
  `precomputed_polygon`;
- in the real V2 Final UI, Trøndelag changes from 6.7% to 6.2% at 300 to
  1000 m;
- Bornholm's legacy V2 archive fixtures replay 3.9% to 3.3% for 300 to 400 m,
  which proves checksum-protected diagnostic integrity but not V1 or product
  parity;
- both Bornholm fixture inventories are checksum-validated before use, and
  their polygon-to-H3 results contain partial-area cells rather than a binary
  H3 approximation;
- a Bornholm configuration without a validated artifact produces no number and
  an actionable note instead of silently switching algorithms;
- direct Bornholm URLs fail closed on the region landing while Trøndelag
  remains directly routable.

This bridge restores the Trøndelag working baseline without copying data and
retains Bornholm provenance for later onboarding.

## `roads_large` R7/R6/R5 checkpoint

R7 was completed and published on 2026-07-30. R6/R5 were completed in code on
2026-07-31:

- `ParameterContract` now carries the UI step;
- both Trøndelag road layers declare one shared `buffer_m` contract:
  default 300 m, minimum 100 m, maximum 2000 m, step 25 m;
- `speedlocal.run_analysis` can receive an explicit analysis-cell universe and
  returns per-cell group acceptance;
- the Trøndelag analysis manifest declares the R7 domain provider, path,
  `hex_id` field, resolution, and expected 13,735-cell count;
- V2 Final's display-cell ids must match that canonical domain exactly;
- a missing requested cell fails closed;
- V2 Final sends every selected road layer through one
  `speedlocal.run_analysis` request at R7/R6/R5;
- the public slider reads its range, step, and default through the canonical
  road contract;
- no region id selects the new algorithm. The temporary adapter maps the
  legacy `transport` capability to canonical `roads`.

The source distance table has 13,851 valid R7 rows, while the public
Trøndelag R7 map has 13,735 cells. For R6/R5 parity, all 13,851 rows are first
aggregated to their H3 parent using minimum distance and any intersection.
Only then is the result restricted to the manifest-declared display domain.
The 116 non-display R7 rows change minimum distance in three public R6 parents
and two public R5 parents, so filtering them before aggregation is incorrect.

With only `roads_large` enabled:

| Buffer | Display cells | Fully blocked | Remaining potential |
|---:|---:|---:|---:|
| 300 m | 13,735 | 428 | 96.8838733163451% |
| 1000 m | 13,735 | 434 | 95.54751146705496% |

At coarser public resolutions:

| Resolution | Buffer | Display cells | Fully blocked | Remaining potential |
|---:|---:|---:|---:|---:|
| R6 | 300 m | 2,163 | 168 | 92.23300970873787% |
| R6 | 1000 m | 2,163 | 170 | 91.01944059177069% |
| R5 | 300 m | 365 | 66 | 81.91780821917808% |
| R5 | 1000 m | 365 | 66 | 80.89936986301369% |

Validation compares every `hex_id → acceptance` value with an independently
calculated frozen-V2 oracle, not only aggregate means and blocked counts.
Malformed distance rows with duplicate ids, invalid booleans, or blank
distances also fail closed. Undeclared, non-integral, or upward H3 resolutions
fail closed.

The complete frozen default selection still renders 6.7% at 300 m and 6.2%
at 1000 m in the explicit regression fixture. It is not the product startup
selection; V2 Final now starts from the manifest's empty request.

The same full-flow values and isolated `roads_large` values pass when V2 Final
is started from the reviewed 45-file cloud runtime package. That deployment
artifact is transport evidence only; frozen V2 remains the behavior oracle.

The `roads_large` R7/R6/R5 and verification-cleanup checkpoint received
localhost approval on 2026-07-31. It is locally promoted but remains
unpublished; publication is a separate Tuesday/Friday-window state.

## `roads_medium` and combined-roads checkpoint

Frozen V2 divides the same N500 source into manifest layers:

- `roads_medium`: `vegkategor == "F"`, 2,252 line features;
- `roads_large`: `vegkategor in ["E", "R"]`, 327 line features.

Both layers use one shared distance slider. Each has 13,851 R7 distance rows.
For medium-plus-large, distance is the minimum across selected layers and
intersection is logical OR. The pinned accepted V2 Final parity and manifest
default is 300 m; the old registry contains a conflicting 100 m fallback that
does not redefine the accepted checkpoint.

Frozen unweighted mean-cell anchors are:

| Selection | Buffer | R7 | R6 | R5 |
|---|---:|---:|---:|---:|
| Medium | 300 m | 76.825627957772% | 55.016181229773% | 31.232876712329% |
| Medium | 1000 m | 69.568545322170% | 50.732810910772% | 29.520657534247% |
| Medium + large | 300 m | 75.012741172188% | 52.288488210818% | 27.123287671233% |
| Medium + large | 1000 m | 67.438307972333% | 47.875053166898% | 25.533698630137% |

V2 Final now sends medium-only and medium-plus-large through the same generic
road-group request as large-only. The generic bridge derives available road
layers and their manifest order from the wind contract; it fails closed on
empty, duplicate, or undeclared selections. No selected road layer reaches
the legacy distance loader.

Validation reads the frozen CSVs independently, rolls all raw R7 rows before
display-domain filtering, and compares every target cell at R7/R6/R5 and 300/
1000 m. It also checks fixed means, blocked counts, manifest model area, slider
endpoints, layer-order invariance, and the real Streamlit controls. R5 cell
`850803b3fffffff` pins the raw-first medium rollup at 10,560.1 m; filtering the
R7 display domain first would incorrectly produce 13,342.0 m.

This development increment has complete automated evidence, but it is not
complete roads promotion.
The remaining order is:

1. visually review medium-only and medium-plus-large at 300/1000 m and
   R7/R6/R5 in one clean localhost process;
2. move road labels, readiness, and source display from the legacy registry to
   canonical manifest descriptors;
3. remove the temporary `transport` UI/data adapter and road entries from the
   legacy Python lists;
4. run the complete roads gate, then publish only in an eligible window.

## Manifest-start, map review, and model-area checkpoint

Implemented on `v2-final-dev` on 2026-07-31 without promoting or publishing
the complete roads slice:

- both wind manifests declare `default_request.selected_layer_ids`; the
  Trøndelag product starts with an empty request and 100% unfiltered wind
  potential;
- the wind manifest's five-group list is a transitional public-product
  whitelist for both current panels. Canonical roads come from the analysis
  manifest; unmigrated population, nature, culture, and grid options still
  come from the region-manifest-declared acceptance registry. Legacy military,
  aviation, bird, coast, land-use, and reindeer sections are not rendered;
- source and buffer visibility are map-review toggles outside the analysis
  form. Changing either toggle leaves the selected layers, parameters, and
  numeric result unchanged;
- the road buffer preview resolves the selected canonical road sources through
  the shared provider resolver, dissolves and buffers them in EPSG:25832, and
  returns an EPSG:4326 map layer. `roads_large`, `roads_medium`, and their
  combined preview have explicit validator coverage;
- the wind analysis manifest declares `display_area_m2` as the area contract
  for R7/R6/R5. The generic resolver validates positive finite values, exact
  cell counts, H3 resolution, total area, and every rollup parent sum;
- Trøndelag's analysis-domain model area is 45,213.18864360976 km² at all
  three declared resolutions. With only `roads_large`, R7 model potential is
  43,798.14161191527 km² at 300 m and 43,191.99545890840 km² at 1000 m;
- the corresponding area-weighted shares are 96.87027817735104% and
  95.52963804293191%. Frozen V2's unweighted cell-parity values remain
  96.8838733163451% and 95.54751146705496%;
- the same per-cell model-area contract now continues through wind
  establishment scoring, R7-to-R6/R5 map rollups, class dominance, scenario
  allocation percentages, and selected-cell footprint statistics. Solar keeps
  its legacy area semantics until a separate solar contract exists.

This is a correction from global average-H3 area to manifest-declared model
area. It is not claimed as exact polygon-clipped available land: the current
soft-distance acceptance remains the frozen V2 cell proxy. Exact geometric
intersection belongs to a later, separately validated behavior change.

The generic road-buffer preview is currently a wind contract. It is not reused
for solar until solar declares its own technology applicability, effect
semantics, and parameter bounds.
