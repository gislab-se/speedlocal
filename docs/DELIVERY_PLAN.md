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
- smoke, parity, and region-readiness tests pass;
- local run and deployment instructions are current.

## Schedule

| Dates | Slice | Required outcome |
|---|---|---|
| 29–31 Jul | Roads | V2 behavior inventory, dynamic road layers, two-region parity, generic UI path |
| 3–5 Aug | Population | Point/grid/polygon dispatch, Bornholm and Trøndelag parity |
| 6–7 Aug | Nature | Dynamic nature layers and hard-exclusion parity |
| 10–11 Aug | Culture | Dynamic culture layers and hard-exclusion parity |
| 12–13 Aug | Grid infrastructure | Proximity-feasibility operation and parity |
| 14–17 Aug | Combined result | Common restriction composition and explanations |
| 18–19 Aug | Wind and solar | Shared potential outputs and continuous technology mix |
| 20–21 Aug | Energy scenarios and social acceptance | Scenario-to-area flow and acceptance overlay |
| 24 Aug | Skaraborg onboarding | Third-region manifests, adapters, validation, and visible surface |
| 25 Aug | Product cleanup | Remove replaced V2 paths, simplify UI, update copy and labels |
| 26 Aug | Acceptance review | Full regression, delivery docs, known limitations, release candidate |

## Slice gates

Each slice has four gates:

1. **Characterized:** V2 inputs, outputs, and UI behavior are recorded.
2. **Generic:** analysis runs without region-name branches.
3. **Parity:** Bornholm and Trøndelag match V2 within the stated tolerance.
4. **Promoted:** UI uses the generic path and the replaced path is removed.

Do not begin the next thematic slice before the current one reaches at least
the parity gate. Promotion may be completed immediately after parity or carried
as an explicit, dated task.

## Critical risks

- Skaraborg source data is not yet runtime-ready.
- V2 contains synthetic or placeholder scenario/acceptance inputs.
- Some V2 behaviors may not have a stable reference result.
- CRS and grid-resolution differences can look like algorithm errors.
- UI cleanup can expand beyond delivery scope.

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
