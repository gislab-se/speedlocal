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

Two deployments make progress visible:

- **Frozen V2:** the verified monolith, never changed, used as Trøndelag's
  visual and numerical reference and as a multi-region provenance archive.
- **V2 Final:** begins from the same working monolith and is reduced,
  streamlined, and made manifest-driven one complete user-visible slice at a
  time.

V2 Final is not a new application shell. Extracted modules must replace code in
the active monolith and be called by its existing user flow.

Normal development and integration happen on `v2-final-dev`. `main` is the
published branch connected to the external V2 Final deployment. Each workday
ends with one coherent validated development checkpoint on `v2-final-dev`.
Local promotion and publication are separate states:

- **Locally promoted:** the relevant automated gates and localhost visual
  review pass, and the replaced path inside the promotion boundary is removed.
  The next planned work may begin from this state.
- **Published:** the exact reviewed checkpoint is on `main`, the external app
  has been verified, and the result is recorded.

Friday is the normal publication window; Tuesday is optional when a coherent
locally promoted increment is ready. An emergency publication outside those
windows requires a recorded reason and the full publication gate.

The frozen reference is
`gislab-se/landskapsanalys@75ba14871100c208cbf8eedb794d56c165340811`,
secured as branch `frozen-v2-reference-2026-07-30` and tag
`v2-frozen-reference-2026-07-30`. Its complete identity, deployment metadata,
and runtime-archive checksum contract are recorded in
`FROZEN_V2_REFERENCE.md` and `frozen_v2_reference.json`.

## Regional reference policy

Reference identity, source integrity, engine-contract conformance, and public
behavioral parity are separate gates.

- Trøndelag uses the technically frozen V2 deployment as its public behavioral
  and numerical parity reference.
- Bornholm uses V1 as its intended public behavioral reference. Until V1 is
  pinned to an exact repository, commit, entrypoint, deployment, and protected
  ref, it is a visual reference rather than an immutable automated oracle.
- Bornholm files and polygon fixtures in the V2 runtime archive may be used for
  source integrity, onboarding, and legacy-fixture diagnostics. They must not
  be described as Bornholm public V2 parity.
- Generic engine results prove contract conformance. They become public parity
  evidence only when compared with that region's secured public reference.
- Skaraborg has no historical behavior reference and must receive explicit
  acceptance criteria during onboarding.

Trøndelag is currently the only active V2 Final region. Bornholm remains in the
delivery catalog with its app route disabled during onboarding. This is a
temporary readiness state, not a separate regional application branch.

For each slice:

1. characterize Trøndelag against frozen V2 and any onboarding region against
   its own accepted reference;
2. identify every function, UI control, data source, parameter, and regional
   assumption involved;
3. classify code as keep, extract, configure, rewrite, or remove;
4. move reusable analysis out of Streamlit and into `speedlocal/`;
5. replace hardcoded data choices with validated manifests or data adapters;
6. compare the new result with the active region's accepted reference;
7. connect the generic result directly to the existing V2 Final UI;
8. remove the replaced hardcoded path after parity is proven;
9. inspect localhost and mark the checkpoint locally promoted when its gate
   passes; publish the exact reviewed checkpoint in a publication window and
   then compare the affected reference and V2 Final deployments.

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

## Shared potential-area contract

The user-confirmed destination for the combined result is one comparable,
area-derived percentage per technology and display hex:

```text
technology potential % =
    remaining establishment area after active applicable restrictions
    / manifest-declared model land area in the hex
    * 100
```

- `speedlocal/` returns both potential area and potential percentage for wind
  and solar; the map class, summaries, and hover consume those same values.
- Overlapping restrictions are unioned per technology before area is removed,
  so overlap is not counted twice.
- Technology applicability, denominator, analysis resolution, and effect
  semantics are validated manifest contracts. Region ids do not select an
  algorithm.
- Point, grid, polygon, and line sources feed a common fine analysis surface
  or equivalent area calculation chosen from declared data characteristics.
- Expensive source normalization and distance surfaces are precomputed or
  cached by source identity. Applying controls thresholds the reusable surface
  and aggregates area; hovering remains a client-side presentation event.

The locally promoted Trøndelag roads and population slices intentionally keep
their frozen-V2 soft-distance cell proxy until the planned combined-result and
wind/solar phases. Their current percentages are parity values, not claims of
exact polygon-clipped free land. This decision defines the later replacement
contract without reopening those promoted slices or changing the slice order.

## Data-driven rules

- Public regions come only from `regions/index.json`.
- Region and analysis availability come from manifests.
- Algorithms may branch on validated geometry and data representation, never
  on region names.
- Population may select point, grid, or polygon processing.
- CRS normalization belongs in shared source/adaptation code.
- Missing or ambiguous data fails closed.
- Large runtime data remains outside Git.
- Frozen V2 and its runtime archive remain read-only.

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
- manifest-driven medium, large, and combined roads at Trøndelag's public
  R7/R6/R5 resolutions plus a Bornholm onboarding/diagnostic contract;
- geometry-driven line adapter;
- generic distance-exclusion and binary hard-exclusion execution;
- distance-engine contract validation against both regional datasets in the
  shared V2 runtime archive; this is conformance evidence, not two-region
  behavioral parity.

Current slice status:

- population and settlement: complete and locally promoted on 2026-08-03;
- nature: complete current Trøndelag `protected_areas` behavior locally
  promoted on 2026-08-03 and unpublished;
- culture: complete current Trøndelag behavior locally promoted on 2026-08-03
  and unpublished;
- grid infrastructure: complete current Trøndelag behavior locally promoted
  on 2026-08-04 and unpublished;
- dynamic medium and large road layers: complete;
- generic group result and distance-engine contract conformance: complete;
- the temporary separate parity app has been removed;
- the V2 Final baseline now loads external acceptance registries and assets
  through manifest-declared `v2_archive` providers;
- duplicate local registry files and their duplicate path resolver are removed;
- runtime strategy is manifest-declared rather than selected by region-name
  branches: Trøndelag retains frozen V2's fast soft-distance runtime, while
  Bornholm's checksum-validated polygon artifacts remain diagnostic only;
- Trøndelag's frozen-public checkpoints pass in the real UI: 6.7% at 300 m
  and 6.2% at 1000 m;
- Bornholm's historical 3.9% and 3.3% polygon fixtures replay correctly and
  fail closed for undeclared combinations, but they do not establish product
  parity or block Trøndelag roads promotion;
- direct Bornholm routes fail closed on the manifest-driven landing page;
- every selected Trøndelag road layer now executes in one
  `speedlocal.run_analysis` request in the actual V2 Final flow at the exact
  public R7/R6/R5 domains: 13,735, 2,163, and 365 cells;
- coarser resolutions aggregate every valid raw R7 distance row by H3 parent
  using minimum distance and any intersection before restricting the result to
  the manifest-declared display domain;
- the shared road slider reads its 300/100/2000/25 contract from the canonical
  manifest;
- V2 Final starts from the wind manifest's empty request; source and buffer
  visibility are map-review state and do not alter the numeric request;
- the five-group public whitelist is manifest-declared. Roads, all three wind
  population sources, Trøndelag `protected_areas` under canonical `nature`,
  both Trøndelag culture sources, and all three current Trøndelag grid-
  infrastructure sources are now manifest-driven; remaining unmigrated options
  still come from the region-manifest-declared legacy
  registry. That bounded adapter is not canonical manifest layer availability
  and not a solar analysis contract;
- wind potential, establishment rollups, and scenario allocation use validated
  per-cell `display_area_m2`; Frozen V2's unweighted cell mean remains the
  parity oracle, and exact polygon-clipped land area remains later work;
- the R7/R6/R5 `roads_large` and verification-cleanup checkpoint is locally
  approved but remains unpublished;
- `roads_medium` alone and medium-plus-large now pass exact frozen-V2 cell,
  aggregate, model-area, and real-Streamlit checks at 300 and 1000 m for
  R7/R6/R5; neither road layer falls through to the legacy distance loader,
  and localhost review of medium, large, combined, source, and buffer behavior
  was approved on 2026-07-31;
- the public wind road group now uses canonical id `roads`; labels, ordering,
  readiness, colors, source display, buffer display, and the shared distance
  control come from validated manifest descriptors. Road entries and the
  `transport` road parameter/label bridge are removed from the legacy wind
  Python lists;
- all automated complete-roads gates pass. The user approved reset and the
  final manifest-backed UI in a clean localhost process on 2026-07-31, so the
  complete roads slice is locally promoted. Publication remains separate and
  waits for an eligible Tuesday or Friday window;
- the primary population contract now declares polygon geometry, grid
  representation, H3 R8 numeric rows, the complete slider range, and explicit
  fail-closed zero-acceptance semantics plus exact signatures for target cells
  outside the sparse distance artifact. Independent R8-to-R7/R6/R5 cell,
  aggregate, and model-area checks pass at 100, 500, 1,000, and 3,000 m. The
  real V2 Final control, calculation, source preview, and buffer preview use
  this contract, and adversarial checks prove that a broken migrated contract
  cannot reopen the legacy primary loader. The user approved the clean
  localhost checkpoint on 2026-07-31, so this bounded primary increment is
  locally promoted. The wind allocation-ranking consumer now obtains all
  three population layers from the canonical manifest engine at R7/R6/R5 and
  matches the previous ranking values exactly. The polygon `built_centre` and
  point `built_low_selection` sources are canonical, and the public wind
  `settlement` alias and legacy optional-source path are removed. Manifest
  order controls primary-versus-optional placement, and dead population cases
  in the legacy wind renderers are removed. The user approved the final clean-
  process localhost control on 2026-08-03, so the complete population slice
  is locally promoted but unpublished;
- the nature manifest declares `protected_areas` with generic binary
  `hard_exclusion`, a 0–2,000 m buffer contract, and an explicit
  highest-dimension policy for its dissolved geometry collection. Canonical
  R7/R6/R5 engine, frozen-reference, real-app, source/buffer preview,
  allocation-ranking, runtime, and repository gates pass. The public wind
  `protected` alias and legacy Trøndelag loader path are removed. The user
  approved the clean-process localhost review on 2026-08-03, so the complete
  current nature slice is locally promoted but unpublished. The unreliable
  result hover observed during review and the later literal wind/solar
  establishment-area percentages are explicitly deferred to the shared
  combined-result and wind/solar phases; the promoted nature result remains
  the accepted binary per-cell parity contract.
- the culture manifest declares `cultural_preservation` and
  `valuable_cultural_environment` with generic binary `hard_exclusion` and a
  shared 0–1,500 m buffer contract. The RA source explicitly declares the
  generic `make_valid` preview policy for its dissolved self-intersection;
  invalid geometry otherwise fails closed. Canonical R7/R6/R5 engine,
  frozen-reference, real-app, source/buffer preview, allocation-ranking,
  runtime, and repository gates pass. The redundant Trøndelag wind culture
  group toggle, advanced-source adapter, and legacy distance paths are
  removed. The user approved clean-process localhost review on 2026-08-03, so
  the complete current culture slice is locally promoted but unpublished;
- the grid-infrastructure manifest declares `high_voltage_lines`,
  `underground_cables`, and `existing_wind_turbines` under canonical
  `grid_infrastructure`, with generic `proximity_feasibility` and a shared
  500–15,000 m maximum-connection-distance contract. R7 distance observations
  roll up generically to R6/R5, and source-resolution R7 feasibility coverage
  provides the fast buffer-review layer while exact vectors remain available
  as sources. Independent engine, frozen-reference, preview, and real-app
  gates pass. The user approved clean-process localhost review on 2026-08-04,
  so the complete current grid-infrastructure slice is locally promoted but
  unpublished;
- the population parity result currently starts from frozen-V2 R8 distance
  rows and rolls them up to R7/R6/R5. This remains valid reference parity but
  is a known potential modeling problem for the intended R7 contract. Before
  the combined-result slice is locally promoted, population must be
  recalculated directly against the manifest-declared R7 domain, with R6/R5
  derived from R7, frozen-reference drift quantified and
  explicitly accepted, and new accepted-reference evidence secured.

## Definition of done for a slice

- Inputs and outputs from the accepted regional reference are documented.
- Code classification is recorded in the daily log.
- No region name selects the new algorithm.
- All paths use the shared resolver.
- Contract and runtime validators pass.
- Trøndelag frozen-V2 parity passes within a documented tolerance.
- Onboarding diagnostics are never reported as product parity.
- The public UI works for every currently enabled region, while disabled
  regions fail closed visibly.
- Obsolete code is removed after parity.
- Localhost visual review passes in V2 Final.
- The coherent checkpoint is committed and pushed to `v2-final-dev`.
- Documentation and the daily log describe what changed.

Publication is tracked separately from slice completion. A locally promoted
slice is published only after its exact checkpoint is moved to `main` during a
publication window and the external V2 Final deployment is verified.

## Delivery plan and daily control

- `DELIVERY_PLAN.md` contains the dated route to delivery.
- `DAILY_WORKFLOW.md` defines the daily planning and handoff routine.
- `daily/YYYY-MM-DD.md` records each workday's subplan, decisions, completed
  work, validation, blockers, and next starting point.

If work reveals that the delivery sequence or estimate is wrong, update
`DELIVERY_PLAN.md` explicitly. Do not silently drift from the plan.

## Stop and reassess when

- a slice cannot reproduce the active region's accepted reference behavior;
- two consecutive workdays pass without a testable slice result;
- every new layer requires new UI code;
- region names enter the generic analysis engine;
- contract work grows without visible functionality;
- required Skaraborg data is unavailable;
- the same old and new implementation remain active after parity.
- a new parallel product surface grows outside the V2 Final monolith.

## Explicit non-goals

- A line-by-line beautification of the complete monolith.
- A separate replacement app that recreates V2 behavior.
- Importing V3 as the product baseline.
- Copying large runtime datasets into this repository.
- PostGIS work before file-backed feature parity.
- Regional extras before the common baseline works.
