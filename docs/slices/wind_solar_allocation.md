# Continuous wind/solar allocation slice

Status: characterized; implementation is the next planned slice
Behavior reference: accepted Trøndelag V2 Final mix and allocation behavior,
plus the locally promoted exact-area and `onshore_land` contracts
Integration target: the existing V2 Final energy-mix, result-table, and map
flow

## Behavior boundary

The continuous mix redistributes one selected scenario's combined wind and
solar energy without changing its total:

```text
solar TWh = combined wind/solar TWh × selected solar share
wind TWh = combined wind/solar TWh - solar TWh
technology area need = technology TWh × declared km²/TWh
```

The control covers every integer solar share from 0 through 100 percent. The
0/100 endpoints must produce exact zero demand, zero selected area, and zero
unmet area for the technology with no demand. Changing the mix must not change
the exact geographic wind or solar potential produced by the active filters.

Rooftop solar remains separate planning-proxy accounting. Its declared output
reduces residual ground-solar TWh and area demand after the gross scenario mix
is calculated; it never adds establishment candidates or changes geographic
large-scale solar potential.

## Allocation contract

- Allocation is calculated at canonical R7. R6/R5 views sum R7 allocated area
  and energy; they do not rerun or re-rank the allocation.
- Wind and ground solar consume the exact positive
  `potential_area_km2` returned by their manifest-driven area analyses.
- Per-cell capacity is bounded by the same checksum-pinned `onshore_land`
  eligible area used by map, hover, and result capacity. Full theoretical H3
  area is not an allocation capacity near coasts or the regional boundary.
- Current landscape and social-acceptance ranking may order candidates, but
  may not manufacture capacity or change the promoted five-group metrics.
- Solar is currently placed first. Wind receives solar-selected ids as a
  last-resort overlap signal; genuine co-use remains allowed where the accepted
  priority behavior selects the same eligible cell.
- Demand that does not fit inside positive technology potential is displayed
  as schematic **outside landscape potential** allocation. It may use only
  remaining cells from the same eligible `onshore_land` display geometry and
  must remain explicitly marked as outside potential. It must never cross the
  eligible-surface boundary.
- Selected area, selected TWh, unmet area, table coverage, map classes, and
  hover details must reconcile from the same allocation frames.

The current Trøndelag scenario manifest is explicitly a Bornholm-derived
placeholder. This slice preserves that declared provisional input and does not
claim regional energy-scenario acceptance; replacing scenario inputs belongs
to the following energy-scenario slice.

## Current path and replacement boundary

- `rebalance_wind_solar_mix` in
  `apps/v2_port/apps/potential_model/energy_modeling.py` changes the mix while
  preserving total TWh.
- `_build_energy_model_state` in `apps/v2_port/potential_app.py` converts that
  mix to technology demand and applies rooftop accounting.
- `_solar_establishment_frame` and `_expand_solar_area_outside_lp` place the
  residual ground-solar demand.
- `allocate_wind_area_from_core_hexes` and `_expand_wind_area_outside_et` place
  wind demand after the solar selection is known.
- `_combined_establishment_frame`, result-table helpers, and map-layer helpers
  consume the two frames.

The replacement slice will move technology-neutral mix, demand, capacity,
selection, overlap, and rollup rules into `speedlocal/`. Streamlit will retain
widget/session state and presentation only. The old app-local allocation path
will be removed after the generic result passes the gates below in the actual
V2 Final flow.

## Code classification

- **Keep:** the continuous slider, current public labels, current ranking
  inputs, rooftop planning-proxy boundary, result-table structure, and map
  presentation.
- **Extract:** total-preserving mix, technology demand, eligible-capacity
  selection, overlap policy, outside-potential classification, and R7-derived
  rollup into `speedlocal/`.
- **Configure:** supported technologies, mix step and endpoints, allocation
  order, overlap policy, minimum core threshold, eligible surface, and
  provisional scenario source through validated contracts.
- **Rewrite:** wind and solar allocation adapters so both call one generic
  engine result and every consumer reads that result.
- **Remove:** duplicated app-local allocation calculations and implicit
  theoretical-H3 capacity after parity and localhost approval.

## Promotion gates

- Independent synthetic checks at 0%, 50%, and 100% solar prove constant total
  TWh and exact zero-demand behavior.
- Partial coastal cells can allocate no more than their declared eligible area
  for either technology.
- Selected area plus unmet area equals technology area demand, and selected
  TWh reconciles through the declared km²/TWh factor.
- Solar-first ordering, allowed last-resort co-use, and outside-potential
  classification are deterministic under reversed input row order.
- R6/R5 allocated area and TWh equal sums of their R7 children.
- Map, hover, table, and acceptance-capacity consumers agree with the generic
  allocation result.
- The five promoted standard-group metrics and source/buffer previews remain
  unchanged.
- Generic engine, accepted baseline, real Streamlit app, runtime bundle,
  guardrail, delivery, and clean-process localhost review pass before local
  promotion.

## First implementation checkpoint

Open the pure mix, demand, and allocation functions named above together with
`speedlocal/contracts.py`. Define a technology-neutral typed result and
synthetic endpoint/capacity oracle before changing the Streamlit call sites.

## First engine checkpoint candidate — 2026-08-07

`speedlocal/allocation.py` now defines immutable, pandas-free types for energy,
demand, allocation candidates, selected cells, technology results, and parent
rollups. Its pure operations:

- rebalance any declared technology set while conserving its combined TWh;
- convert TWh to area through explicit positive km²/TWh factors;
- select positive-potential capacity before explicitly classified
  outside-potential capacity;
- cap every selection by declared eligible area;
- preserve accepted co-use ordering by treating the other technology's
  reservation as the final tie-break after supplied priority fields; and
- sum selected fine children to parents without reranking.

The existing V2 Final pandas functions now adapt mix and area-demand inputs to
this engine. Their duplicate arithmetic is removed. Solar and wind candidate
preparation and selection loops remain unchanged and are the next integration
boundary; this checkpoint is therefore a validated candidate, not local
promotion of the complete allocation slice.

Candidate evidence: independent allocation validator 12/12; exact legacy
adapter compatibility at 0/50/100; eligible-surface gate PASS; generic engine
PASS; accepted baseline PASS; real Streamlit app PASS with no blockers,
including all continuous-mix and cross-control reruns; delivery repository
84/84. No standard-group metric, source/buffer preview, manifest, runtime
transport, or eligible-surface geometry changed.
