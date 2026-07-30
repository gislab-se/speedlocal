# SpeedLocal delivery plan

Status: active
Start: 2026-07-29
Target acceptance review: 2026-08-26

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
| 29–31 Jul | Roads | Trøndelag V2 characterization, dynamic road layers, contract validation, generic UI path |
| 3–5 Aug | Population | Point/grid/polygon dispatch and Trøndelag V2 parity |
| 6–7 Aug | Nature | Dynamic nature layers and hard-exclusion parity |
| 10–11 Aug | Culture | Dynamic culture layers and hard-exclusion parity |
| 12–13 Aug | Grid infrastructure | Proximity-feasibility operation and parity |
| 14–17 Aug | Combined result | Common restriction composition and explanations |
| 18–19 Aug | Wind and solar | Shared potential outputs and continuous technology mix |
| 20–21 Aug | Energy scenarios and social acceptance | Scenario-to-area flow and acceptance overlay |
| 24 Aug | Region onboarding | Bornholm V1 acceptance gate plus Skaraborg manifests, adapters, validation, and visible state |
| 25 Aug | Product cleanup | Remove replaced V2 paths, simplify UI, update copy and labels |
| 26 Aug | Acceptance review | Full regression, delivery docs, known limitations, release candidate |

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
  cold start and the real root entrypoint; authenticated Streamlit Cloud smoke
  verification is the remaining publication gate.
- Bornholm catalog/source onboarding: in progress. Its 300/400 m polygon
  fixtures are diagnostic replay, not public parity.
- Bornholm V1 characterization and technical pinning: not started.
- `roads_large` R7 canonical integration: automated gate and localhost visual
  approval complete; external deployment verification remains.
- `roads_large` full promotion: canonical R6/R5 rollups and their remaining
  legacy-path removal remain.
- Complete roads promotion: canonical `roads_medium`, combined-roads behavior,
  and removal of the temporary road-group adapter remain.

## Slice gates

Each slice has six explicit gates:

1. **Characterized:** V2 inputs, outputs, and UI behavior are recorded.
2. **Generic:** analysis runs without region-name branches.
3. **Engine contract:** generic layer and group calculations match their
   declared legacy calculation contracts.
4. **Accepted-reference checkpoints:** selected automated numeric, artifact,
   and rendered-UI values match the active region's secured reference within
   the stated tolerance. Currently this is frozen V2 for Trøndelag only.
5. **Continuous behavior:** the full declared control domain executes; a small
   set of frozen fixtures is evidence but does not complete this gate.
6. **Promoted:** UI uses the generic path, localhost visual review passes, and
   the replaced path is removed.

Do not begin the next thematic slice before the current one reaches the
promoted gate. Each slice must be integrated into V2 Final and its replaced
hardcoded path removed before work starts on the next thematic slice.

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
- **5 Aug:** confirm that geometry-driven population adapters are sufficient.
- **17 Aug:** confirm that the common restriction result supports both wind and
  solar.
- **21 Aug:** confirm that scenario and acceptance inputs are delivery-quality.
- **24 Aug:** decide whether Skaraborg is active or visibly limited by missing
  reviewed data.
