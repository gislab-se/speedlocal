# SpeedLocal delivery plan

Status: active
Start: 2026-07-29
Target acceptance review: 2026-08-27

This target assumes that reviewed Skaraborg data and energy-scenario inputs are
available when their phases begin. Missing source data moves the date and must
be recorded as a blocker rather than replaced with hidden synthetic data.

## Delivery definition

The delivery is complete when:

- Bornholm, Trøndelag, and Skaraborg open from the landing page;
- roads, population, nature, culture, and grid infrastructure work through the
  common engine;
- wind and solar potential use the common restriction result;
- the user can continuously change the wind/solar allocation;
- energy scenarios change required energy and land area;
- social acceptance can be applied and explained;
- regional data differences are handled through manifests and adapters;
- results, data limitations, and provenance are visible;
- smoke, accepted-reference, and region-readiness tests pass;
- local run and deployment instructions are current.

## Schedule

| Dates | Slice | Required outcome |
|---|---|---|
| 29 Jul–3 Aug | Roads | Trøndelag V2 characterization, dynamic road layers, contract validation, generic UI path |
| 31 Jul–6 Aug | Population | Point/grid/polygon dispatch and Trøndelag V2 parity |
| 3–10 Aug | Nature | Dynamic nature layers and hard-exclusion parity |
| 3–12 Aug | Culture | Dynamic culture layers and hard-exclusion parity |
| 13–14 Aug | Grid infrastructure | Proximity-feasibility operation and parity |
| 17–18 Aug | Combined result | Common technology-applicable restriction union, model-area denominator, and explanations |
| 19–20 Aug | Wind and solar | Shared area-derived potential outputs, consistent map/hover values, and continuous technology mix |
| 21–24 Aug | Energy scenarios and social acceptance | Scenario-to-area flow and acceptance overlay |
| 25 Aug | Region onboarding | Bornholm V1 acceptance gate plus Skaraborg manifests, adapters, validation, and visible state |
| 26 Aug | Product cleanup | Remove replaced V2 paths, simplify UI, update copy and labels |
| 27 Aug | Acceptance review | Full regression, delivery docs, known limitations, release candidate |

The schedule moved one business day on 2026-07-31 because the complete roads
slice had not yet reached its locally promoted gate. Roads then passed that
gate later the same day, so a bounded primary-population increment began on
31 July. The complete population slice passed its local-promotion gate early
on 3 August, so the first bounded nature increment began the same day. The
complete nature slice passed its local-promotion gate later on 3 August, so
the complete-current-group culture candidate began the same day, ahead of its
original 11 August start. The later slice order and final culture target date
remain unchanged.

## Branch and publication cadence

- `v2-final-dev` is the daily development and integration branch. Every
  workday ends with one coherent validated checkpoint committed and pushed
  there.
- `main` is the published branch used by the external V2 Final deployment.
- Friday is the normal publication window. Tuesday is optional when a coherent
  locally promoted increment is ready.
- External publication happens only in one of those windows. An emergency
  outside Tuesday or Friday requires a reason in the daily log and the full
  publication validation.
- Local promotion is the delivery gate that permits the next planned work.
  Published status is recorded separately and requires the exact reviewed
  checkpoint on `main` plus verified external behavior.

Current milestone status:

- Roads characterization: complete.
- Roads generic gate: complete.
- Roads distance-engine contract-conformance gate: complete for the Trøndelag
  and Bornholm datasets.
- Trøndelag provider repair and automated V2 checkpoints: complete at
  300/1000 m; localhost review approved. Port 8503 is a secondary historical
  Trøndelag-only check, not a replacement for the `75ba148` full-flow gate.
- Trøndelag cloud runtime transport: 45-file, checksum-pinned Release package
  published, anonymously redownloaded, and validated through a clean public
  cold start and the real root entrypoint; authenticated Streamlit Cloud visual
  and interaction smoke review approved.
- Bornholm catalog/source onboarding: in progress. Its 300/400 m polygon
  fixtures are diagnostic replay, not public parity.
- Bornholm V1 characterization and technical pinning: not started.
- `roads_large` R7 canonical integration: automated gate, localhost visual
  approval, public-package cold start, and external deployment review complete.
- `roads_large` R6/R5 canonical integration: automated engine, accepted-
  reference, and real-app gates complete at 300/1000 m; localhost visual
  review was approved on 2026-07-31, so the increment is locally promoted but
  not yet published.
- V2 Final verification cleanup: empty manifest startup, map-only road source
  and buffer review, and manifest-cell-area propagation through wind
  establishment/allocation are locally approved on `v2-final-dev`. Unmigrated
  non-road layers still use the declared legacy-registry adapter; the primary
  population source is now the first manifest-driven exception.
- `roads_large` full local promotion: complete. Publication remains a separate
  pending state.
- `roads_medium` and combined roads: canonical calculation and automated
  R7/R6/R5 accepted-reference/real-app gates complete at 300/1000 m; localhost
  review of calculation plus map-only source/buffer behavior was approved on
  2026-07-31.
- Complete roads UI/data adapter removal: complete. The public wind group is
  canonical `roads`, its UI/source/buffer metadata is manifest-driven, and the
  complete automated roads gate passes. Clean-process localhost review was
  approved on 2026-07-31; the complete roads slice is locally promoted but
  unpublished.
- Population characterization: complete for the primary Trøndelag
  `population_points` proxy. Its manifest, generic engine, actual V2 Final
  controls, calculation, source view, and buffer view pass automated
  R8-to-R7/R6/R5 parity and real-Streamlit gates. Signed sparse-coverage drift
  and broken migrated UI/layer contracts fail closed before legacy loading.
  Clean-process localhost review was approved on 2026-07-31, so the bounded
  primary increment is locally promoted. The wind allocation-ranking consumer
  now uses canonical population distances at R7/R6/R5 with zero accepted-value
  drift. The optional polygon `built_centre` and point
  `built_low_selection` sources are manifest-declared and canonical in
  controls, calculation, previews, and ranking; no population source reaches
  the legacy loader, and the public wind `settlement` alias is removed. The
  final control uses manifest layer order for primary-versus-optional
  placement, and dead population cases in the legacy wind renderers are
  removed. Clean-process localhost review was approved on 2026-08-03, so the
  complete population slice is locally promoted but unpublished. Nature is
  now in progress.
- Nature first increment: the Trøndelag `protected_areas` polygon source is
  manifest-declared under canonical `nature` and runs through generic binary
  `hard_exclusion` at R7/R6/R5. The old public wind `protected` alias and
  legacy distance-loader path are removed for Trøndelag. Generic-engine,
  independent frozen-reference, vector-preview, and focused real-Streamlit
  gates and full repository checks pass. Clean-process localhost review was
  approved on 2026-08-03, so the complete current nature slice is locally
  promoted but unpublished. The reviewed hover limitation and the distinction
  between binary cell parity and literal free-area percentage are deferred to
  the planned combined-result and wind/solar phases.
- Culture complete current group: `cultural_preservation` and
  `valuable_cultural_environment` are manifest-declared under canonical
  `culture` and run through generic binary `hard_exclusion` at R7/R6/R5. The
  redundant group toggle, advanced-source registry adapter, and legacy
  calculation/preview/ranking paths are removed for Trøndelag. The invalid
  dissolved RA geometry uses an explicit, generic, fail-closed-by-default
  manifest repair policy. Generic-engine, independent frozen-reference,
  vector-preview, real-Streamlit, runtime, guardrail, delivery, and frozen
  archive gates pass. Clean-process localhost review was approved on
  2026-08-03, so the complete current culture slice is locally promoted but
  unpublished. Grid infrastructure is next.
- Population R7 correction: the locally promoted frozen-V2 parity path starts
  from R8 distance rows and rolls them up to R7/R6/R5. This is a known
  potential modeling problem rather than the desired final R7 contract.
  Before combined-result local promotion, calculate population directly
  against the manifest-declared R7 domain, derive R6/R5 from R7, quantify and
  explicitly accept any frozen-reference drift, and rerun the complete
  regression gate. No population calculation changes in the culture
  promotion checkpoint.
- Shared potential-area semantics: decision recorded on 2026-08-03. The
  promoted roads/population soft-distance percentages remain frozen-V2 parity
  proxies until the planned combined-result and wind/solar phases replace
  them with technology-specific remaining area divided by the common
  manifest-declared model land area. This does not change the current dates or
  thematic slice order.

## Slice gates

Each slice has seven explicit gates:

1. **Characterized:** V2 inputs, outputs, and UI behavior are recorded.
2. **Generic:** analysis runs without region-name branches.
3. **Engine contract:** generic layer and group calculations match their
   declared legacy calculation contracts.
4. **Accepted-reference checkpoints:** selected automated numeric, artifact,
   and rendered-UI values match the active region's secured reference within
   the stated tolerance. Currently this is frozen V2 for Trøndelag only.
5. **Continuous behavior:** the full declared control domain executes; a small
   set of frozen fixtures is evidence but does not complete this gate.
6. **Locally promoted:** UI uses the generic path, localhost visual review
   passes, and the replaced path inside the promotion boundary is removed.
7. **Published:** the exact locally promoted checkpoint is present on `main`
   and its external V2 Final behavior is verified and recorded.

Do not begin the next thematic slice before the current one reaches the
locally promoted gate. Publication may wait for the next Tuesday or Friday
window. Each slice must be integrated into V2 Final and its replaced hardcoded
path removed before work starts on the next thematic slice.

## Critical risks

- Skaraborg source data is not yet runtime-ready.
- Bornholm V1 is not yet pinned to an exact repository, commit, entrypoint, and
  protected reference.
- V2 contains synthetic or placeholder scenario/acceptance inputs.
- Some V2 behaviors may not have a stable reference result.
- CRS and grid-resolution differences can look like algorithm errors.
- UI cleanup can expand beyond delivery scope.
- Streamlit Cloud cold starts depend on the immutable runtime Release asset;
  its checksum, safe extraction, and external smoke test are publication gates.

## Scope control

During this plan:

- preserve the main scenario-to-landscape user journey;
- remove debug, prototype, duplicate, and technical UI when it is not needed
  for delivery;
- defer regional extras such as reindeer husbandry;
- defer PostGIS and QGIS-plugin work;
- record valuable future ideas without inserting them into the active slice.

## Decision points

- **31 Jul:** confirm that V2 Final can replace one complete road slice cleanly.
- **3 Aug (confirmed early):** geometry-driven population adapters are
  sufficient for the Trøndelag polygon-grid, polygon-feature, and
  point-feature sources without a region-name algorithm branch.
- **17 Aug:** confirm that the common restriction result supports both wind and
  solar, unions overlapping applicable restrictions once, and returns area-
  derived percentages using the manifest-declared model land denominator.
- **21 Aug:** confirm that scenario and acceptance inputs are delivery-quality.
- **24 Aug:** decide whether Skaraborg is active or visibly limited by missing
  reviewed data.
