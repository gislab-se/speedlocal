# Roads slice characterization

Status: Trøndelag `roads_large` canonical R7/R6/R5 checkpoint implemented; R7 approved and published, R6/R5 automated gates pass and visual approval is pending
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
For Trøndelag R7/R6/R5, `roads_large` is connected to the actual V2 Final
result flow and tested against the frozen V2 cell universes. Bornholm's
generic engine execution remains contract/diagnostic evidence, not behavioral
parity.

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

The R7/R6/R5 `roads_large` replacement now reads its slider contract and cell
result from the common contract. The surrounding legacy group UI remains a
transitional adapter until `roads_medium` is migrated.

### Remove after promotion

- road entries in `WIND_GROUP_LAYER_DEFAULTS`;
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
- V2 Final sends `roads_large` through `speedlocal.run_analysis` at R7/R6/R5,
  including when it is combined with the still-legacy `roads_medium`;
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
at 1000 m in V2 Final.

The same full-flow values and isolated `roads_large` values pass when V2 Final
is started from the reviewed 45-file cloud runtime package. That deployment
artifact is transport evidence only; frozen V2 remains the behavior oracle.

This is an automated R7/R6/R5 checkpoint, not full roads promotion:

1. visually approve and publish the R6/R5 `roads_large` views;
2. migrate `roads_medium` at R7/R6/R5;
3. validate combined roads behavior;
4. remove the temporary `transport`-to-`roads` UI adapter only when the whole
   roads group is canonical.
