# SpeedLocal general program plan

Status: authoritative
Started: 2026-07-28

## Objective

Build one manifest-driven geospatial analysis program that can run the same
analysis for any region whose data can be transformed into the common
contracts. Bornholm and Trondelag are the initial behavior references.
Skaraborg is the first planned onboarding target.

The program is configured with:

- a public region catalog;
- one region package per region;
- dynamic analysis and layer manifests;
- shared group, source, parameter, operation, and result contracts;
- one source resolver for external files and later PostGIS;
- validators that fail closed before data reaches the UI.

The target API is:

```python
result = run_analysis(
    region="bornholm",
    analysis="wind",
    layers=["roads_large"],
    parameters={"roads_large": {"buffer_m": 500}},
    scenario="high",
)
```

Streamlit is a client of this API. Analysis code must not depend on Streamlit.

## Standard public groups

Implement only these groups until the common baseline works:

1. roads;
2. population;
3. nature;
4. culture;
5. grid infrastructure.

Regional exceptions and additional groups are deferred. Do not add
region-id-based analysis branches in this phase.

## Data-driven adaptation

Algorithms may branch on validated data characteristics, not geography names.
The layer contract declares acceptable geometry families, and the validator
checks the actual data.

Examples:

- line roads use line-distance processing;
- point population uses point-distance or aggregation processing;
- population grids use grid-cell coverage or aggregation processing;
- population polygons use polygon intersection or aggregation processing.

Unsupported or ambiguous geometry fails closed. Adding a new data adapter must
extend the common operation contract and its validator.

## Architecture

```text
Streamlit UI
    -> run_analysis(...)
        -> region + analysis catalogs
        -> contract validation
        -> shared source resolver
        -> geometry-aware operation executor
        -> AnalysisResult
```

Current modules:

- `speedlocal/contracts.py`: common contracts and supported capabilities.
- `speedlocal/catalogs.py`: public region and analysis manifest loading.
- `speedlocal/paths.py`: provider roots and traversal-safe path resolution.
- `speedlocal/sources.py`: runtime asset lookup and geometry detection.
- `speedlocal/validation.py`: contract and runtime validation.
- `speedlocal/engine.py`: Streamlit-independent public analysis API.

## Migration sequence

### Slice 1: large roads — implemented

- Bornholm and Trondelag declare `roads_large` in `analyses/wind.json`.
- Runtime assets resolve from the external V2 archive.
- Actual GeoJSON geometry is detected and validated as line data.
- `distance_exclusion` runs against the existing V2 H3 distance tables.
- `scripts/validate_generic_engine.py` validates both regions and monotonic
  buffer behavior.

This is not yet wired into the public Streamlit surface. V2 remains the visible
behavior while the generic engine gains parity.

### Slice 2: complete roads

- Add the remaining public road layers through manifests.
- Make the dynamic layer list replace the Python road allowlist.
- Compare generic results with V2 for both active regions.
- Expose the generic roads controller in Streamlit behind a temporary parity
  flag.
- Remove the old road path only after validation.

### Slice 3: population

- Define point, grid, and polygon population adapters.
- Dispatch by validated geometry/data representation.
- Run equivalent fixtures for at least point and grid inputs.
- Migrate Bornholm and Trondelag without region-specific algorithm branches.

### Slices 4–6

Migrate nature, culture, and grid infrastructure one group at a time. Each
slice follows the same contract, parity, UI, and removal cycle.

### Slice 7: onboarding proof

- Add a small synthetic region using only manifests and test data.
- Prove that no app or engine code changes are required.
- Use the proven onboarding contract for Skaraborg.

### Later

- Add PostGIS as another source provider after file-backed parity is stable.
- Consider additional groups and regional capabilities only after all five
  standard groups work.

## Definition of done for each slice

- No region-name branch selects the algorithm.
- Contract and runtime validators pass.
- Missing data fails closed with a useful message.
- Results match the V2 behavior reference where V2 coverage exists.
- Streamlit receives a serializable result rather than performing analysis.
- The replaced V2 path can be removed without losing validated behavior.

## Explicit non-goals

- Importing V3.
- Rewriting the whole application before a working vertical slice exists.
- Copying large V2 runtime files into this repository.
- PostGIS migration before file-backed engine parity.
- Regional exception handling before the five standard groups work.
