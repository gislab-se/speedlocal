# SpeedLocal V2 Final plan

Status: authoritative
Strategy selected: 2026-07-29

## Product goal

Deliver one landscape-analysis program for Bornholm, Trøndelag, and Skaraborg
that shows how:

- wind and solar allocation;
- energy-model scenarios;
- landscape restrictions;
- proximity to grid infrastructure; and
- social acceptance

change possible establishment area and landscape impact.

The same program must later accept another bounded area mainly through data
mapping, manifests, and validation rather than copied application code.

## Chosen strategy: V2 Final

V2 remains the running behavior reference while it is dismantled one complete
user-visible slice at a time.

For each slice:

1. characterize the current V2 behavior for Bornholm and Trøndelag;
2. identify every function, UI control, data source, parameter, and regional
   assumption involved;
3. classify code as keep, extract, configure, rewrite, or remove;
4. move reusable analysis out of Streamlit and into `speedlocal/`;
5. replace hardcoded data choices with validated manifests or data adapters;
6. compare the new result with V2;
7. connect the generic result to the existing UI;
8. remove the replaced V2 path after parity is proven.

We do not mechanically clean all 14,000 lines function by function. We inspect
functions within a complete behavior slice so that obsolete features can be
deleted instead of polished.

## Product baseline

Implement the common baseline in this order:

1. roads;
2. population and settlement;
3. nature;
4. culture;
5. grid infrastructure;
6. combined restriction result;
7. wind potential;
8. solar potential;
9. continuous wind/solar allocation;
10. energy scenarios;
11. social acceptance;
12. result explanation, map, and summary.

Regional extra groups are deferred until the common baseline works. They must
later use common operations or explicit capabilities rather than region-name
branches.

## Architecture destination

```text
Region manifests + mapped source data
                 ↓
      contracts and validation
                 ↓
       run_analysis(request)
                 ↓
    wind, solar, scenario, acceptance
                 ↓
          AnalysisResult
                 ↓
         thin Streamlit UI
```

The final Streamlit flow should approach:

```python
request = build_analysis_request(ui_state)
result = run_analysis(request)
render_result(result)
```

Streamlit owns interaction and presentation. `speedlocal/` owns contracts,
source resolution, validation, and analysis.

## Data-driven rules

- Public regions come only from `regions/index.json`.
- Region and analysis availability come from manifests.
- Algorithms may branch on validated geometry and data representation, never
  on region names.
- Population may select point, grid, or polygon processing.
- CRS normalization belongs in shared source/adaptation code.
- Missing or ambiguous data fails closed.
- Large runtime data remains outside Git.
- V2 remains read-only.

## Code classification

Every function touched by a slice receives one decision:

- **Keep:** already small, general, and testable.
- **Extract:** reusable analysis that belongs outside Streamlit.
- **Configure:** paths, layers, labels, or parameters that belong in manifests.
- **Rewrite:** mixed UI/analysis code or code with unclear responsibilities.
- **Remove:** duplicate, debug, prototype, obsolete, or nonessential behavior.

## Current status

Implemented foundation:

- generic contracts, catalog loading, source resolution, and validation under
  `speedlocal/`;
- manifest-driven `roads_large` for Bornholm and Trøndelag;
- geometry-driven line adapter;
- generic distance-exclusion execution;
- validation against both V2 runtime archives.

Current slice:

- complete the public roads behavior;
- characterization: complete;
- dynamic medium and large road layers: complete;
- generic group result and V2 parity: complete;
- temporary Streamlit parity surface: complete;
- remaining promotion work: connect the result to the public V2 flow, then
  remove only the replaced road code.

## Definition of done for a slice

- Current V2 inputs and outputs are documented.
- Code classification is recorded in the daily log.
- No region name selects the new algorithm.
- All paths use the shared resolver.
- Contract and runtime validators pass.
- V2 parity passes within a documented tolerance.
- The public UI still works for both active regions.
- Obsolete code is removed after parity.
- Documentation and the daily log describe what changed.

## Delivery plan and daily control

- `DELIVERY_PLAN.md` contains the dated route to delivery.
- `DAILY_WORKFLOW.md` defines the daily planning and handoff routine.
- `daily/YYYY-MM-DD.md` records each workday's subplan, decisions, completed
  work, validation, blockers, and next starting point.

If work reveals that the delivery sequence or estimate is wrong, update
`DELIVERY_PLAN.md` explicitly. Do not silently drift from the plan.

## Stop and reassess when

- a slice cannot reproduce V2 behavior;
- two consecutive workdays pass without a testable slice result;
- every new layer requires new UI code;
- region names enter the generic analysis engine;
- contract work grows without visible functionality;
- required Skaraborg data is unavailable;
- the same old and new implementation remain active after parity.

## Explicit non-goals

- A line-by-line beautification of the complete monolith.
- Importing V3 as the product baseline.
- Copying large runtime datasets into this repository.
- PostGIS work before file-backed feature parity.
- Regional extras before the common baseline works.
