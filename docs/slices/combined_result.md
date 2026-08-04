# Combined-result slice characterization

Status: wind-area increment locally promoted on 2026-08-04; full
two-technology slice remains in progress and unpublished
Behavior reference: accepted area contract plus explicit Trøndelag review
Integration target: the existing V2 Final combined map, hover, table, and
scenario-allocation flow

## Result contract

For each technology and analysis cell:

```text
potential % =
    remaining establishment area after applicable active restrictions
    / manifest-declared model area
    * 100
```

The Trøndelag wind manifest declares all five canonical groups as applicable,
the R7 analysis domain as denominator, exact vector clipping as geometry
semantics, and `feasibility_then_exclusion` as execution order. Proximity
sources first form the allowed connection domain. The overlap-safe union of
roads, population, nature, and culture restrictions is then removed. This is
the literal area model; the promoted group-specific soft-distance results
remain unchanged as their own regression and explanation surfaces.

R7 is the only calculation level. R6 and R5 percentages are derived from the
R7 child model and remaining areas and then applied to each rollup's declared
model-area denominator. Region ids never choose the algorithm.

## Current consumer inventory

- `_wind_fast_distance_runtime_result` currently produces the wind
  soft-distance proxy used for group parity and internal context.
- `_wind_polygon_summary_frame` adapts that proxy to the wind potential and
  allocation frames.
- `_combined_potential_establishment_frame` joins the wind and solar
  technology frames and assigns the four map classes.
- `_combined_establishment_feature_collection` creates the client-side
  integer hover values and detailed popup from that same combined frame.
- `_render_establishment_focus` renders `potential after filter`, scenario
  coverage, unused potential, and outside-potential need.
- `_social_acceptance_establishment_summary` and
  `_acceptance_adjusted_capacity_metrics` adjust the technology areas after
  the geographical result.
- `allocate_wind_area_from_core_hexes`, the outside-potential expansion, and
  `_combined_establishment_stats` consume the wind frame for scenario
  placement and coverage.
- `_combined_summary` derives wind class, core, and landscape tables from the
  calculation frame stored in the map state.

The integration boundary replaces only the proxy area columns before those
combined-result consumers. Context and landscape-ranking fields may remain,
but map class, hover, available area, acceptance capacity, and allocation must
all read the exact `potential_area_km2` and `potential_area_share_pct` values.

## Performance contract

- Geometry work runs only after the form's Apply action changes the immutable
  selection, thresholds, region, or resolution.
- Streamlit caches the resulting technology frame. Map zoom, layer visibility,
  opacity, language, and hover do not rerun the geometry calculation.
- Per-cell clipping queries only locally intersecting buffered parts. A cold
  population-only R7 calculation is about two seconds on the development
  machine. The current worst-case all-eleven-source calculation is about
  sixteen seconds and must be reviewed in localhost before promotion. Very
  wide feasibility buffers with at least 1,000 source parts are dissolved
  before cell clipping; this preserves the exact union while avoiding repeated
  local unions of heavily overlapping network buffers.
- Hover is presentation-only over properties already embedded in the map
  feature collection.

## Candidate evidence

- A synthetic 2 km² cell with overlapping exclusions leaves exactly 0.4 km²
  (20%); reversing source order produces the same result.
- Combining an exclusion and a feasibility domain leaves exactly 0.6 km²
  (30%) in the synthetic contract.
- Trøndelag population 250 m cells at 100 m leave
  42,096.717936 km² of 45,213.188644 km², or 93.107164523%, at R7.
- R6 and R5 gates independently verify that every rollup percentage is derived
  from its contributing R7 model and remaining areas.

## Code classification

- **Keep:** promoted five-group controls, calculations, previews, and
  regression gates; existing combined map/popup/table presentation structure.
- **Extract:** generic technology-area contract, source normalization, local
  vector clipping, overlap union, feasibility intersection, and R7 rollup.
- **Configure:** technology applicability, model denominator, operation order,
  geometry semantics, source operations, and resolution.
- **Rewrite:** combined wind area columns and all available-area consumers to
  use the exact shared result.
- **Remove later:** the proxy-derived area path only after the exact result is
  validated in every combined consumer. Keep proxy fields still required by a
  separately accepted group explanation or ranking behavior.

## Promotion gates

- Validate manifest failures, overlap safety, denominator consistency, and
  R7-derived R6/R5 values.
- Prove map class, integer hover, popup area, result table, acceptance capacity,
  and scenario allocation consume one exact wind frame.
- Preserve every promoted roads, population, nature, culture, and grid gate.
- Pass the full real Streamlit AppTest and clean-process localhost review,
  including performance with one source and all five groups.
- Characterize solar's current area frame explicitly; do not claim a shared
  two-technology result until solar has the same validated contract.

## Wind-increment local promotion

The automated gates pass on 2026-08-04: generic engine 6,642/6,642, baseline
133/133, real Streamlit AppTest 75/75, vector preview 29/29, V2 port
guardrails 17/17, and delivery repository 82/82. Clean-process localhost
review approved the population and solar-regression views, exact hover/popup
areas, and overall performance.

One presentation edge case remains explicitly deferred: a cell with 0.5%
literal wind potential is correctly positive and therefore classed as
wind-only, while the compact integer hover displays 0%. Before product
completion, choose and validate either a minimum suitability threshold (for
example greater than 1%) or a `<1%` hover label. Do not silently change the
classification or rounding while the solar contract is being migrated.
