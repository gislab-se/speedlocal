# Roads slice characterization

Status: generic implementation in progress
Reference: V2 Final

## User-visible behavior

For wind analysis, the user:

- enables available road layers;
- sets one minimum road distance for the complete road group;
- applies the controls;
- sees road restrictions affect acceptance, wind score, possible
  establishment area, map layers, and summaries.

Bornholm and Trøndelag currently expose medium and large roads. Bornholm's
small-road source is empty after filtering and is not part of the public
generic contract.

Bornholm's medium-road distance table is complete, but its source GeoJSON has
one null geometry. The layer can participate in analysis through the validated
precomputed-distance artifact, but cannot be drawn as a source line until that
display asset is repaired. This limitation is explicit in the layer contract.

## V2 calculation contract

1. Load one H3 distance table per selected road layer.
2. Align H3 resolutions when needed.
3. For every analysis cell, take the minimum distance across selected layers.
4. Mark direct intersection when any selected layer intersects the cell.
5. Block when the cell intersects a road or `min_distance <= buffer_m`.
6. Calculate soft acceptance:
   - 0 at or inside the buffer;
   - linear increase between `buffer_m` and `2 * buffer_m`;
   - 1 beyond twice the buffer.
7. Multiply landscape wind score by the minimum active-group acceptance.

## Relevant V2 code classification

### Keep as behavior reference

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

The replacement should render dynamically from the common contract.

### Remove after promotion

- road entries in `WIND_GROUP_LAYER_DEFAULTS`;
- road filtering performed by `normalize_group_layer_map`;
- road-specific dependence on `GROUP_PARAM_MAP`;
- duplicate road selector paths no longer used by the public UI.

## Parity requirements

- `distance == buffer_m` is blocked.
- Increasing the buffer cannot reduce blocked-cell count.
- Combined medium+large result uses minimum distance and any intersection.
- Generic per-layer and group cell counts match the V2 runtime tables.
- Bornholm and Trøndelag pass independently.

## Promotion boundary

No V2 road code is removed until:

- generic medium and large road layers validate;
- combined group parity passes;
- a Streamlit parity surface works for both regions;
- the public V2 smoke test still passes.
