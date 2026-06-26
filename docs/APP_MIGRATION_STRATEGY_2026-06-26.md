# SpeedLocal App Migration Strategy

Date: 2026-06-26

This note records the decision after a read-only inspection of the V3 repo at
`C:\tmp\landskapspotential` and the current V2 source archive at
`C:\tmp\landskapsanalys-v2-multiregion`.

## Decision

Do not rebuild the app from scratch in `speedlocal`, and do not copy V3 as the
new baseline.

Use V2 as the working behavior baseline. If the next slice needs real app
behavior, prefer a quarantined V2 app port that runs first, then shrink it
behind SpeedLocal catalogs and validators.

This is different from copying the V2 monolith as final architecture. The
monolith may be copied only as a temporary, isolated baseline so we can preserve
working behavior while removing clutter deliberately.

## What Happened In V3

V3 has good ideas, but it became its own product rebuild:

- The V3 checkout is on `v3/map-placeholder-to-layer-shell`, ahead of origin
  and with many uncommitted files.
- The repo contains about 147 MB of data under `data/`, including incoming V1/V2
  exports and promoted runtime GeoJSON/CSV.
- V3 has about 10k lines in `src/` and about 5k lines in `scripts/`.
- `src/landskapspotential/app.py` is about 95 KB and carries a new app shell,
  new state model, new catalog model, and new runtime layer materialization.
- The docs correctly say V2 should be source of truth, but the implementation
  still required many new contracts before the full app behavior was available.

The likely failure mode was not bad intent. It was too much new architecture
before the user-facing V2 behavior was safely running.

## V3 Lessons To Keep

Keep these lessons:

- V2 behavior is the source of truth for calculations and user-facing analysis.
- Missing/proxy/synthetic/placeholder data must be visible and fail closed.
- Trondelag must stay EPSG:25832 and R7/R6/R5 only.
- Bornholm must keep R10-derived R9 PEY labelling until rebuilt.
- A Leaflet renderer is a good direction for real map layers.
- Draft/applied state is useful, but only after the baseline app works.
- Technical runtime status should not dominate the public UI.

Do not inherit these V3 habits:

- Do not import large incoming/runtime data into the delivery repo just to make
  the app feel complete.
- Do not create a new abstract app model before the current V2 behavior runs.
- Do not make every layer and state transition a new contract before there is a
  visible working surface.
- Do not copy V3's generated caches, logs, `data/incoming/`, or promoted
  runtime files.

## Recommended SpeedLocal Strategy

Use a "port first, shrink second" strategy:

1. Keep the current SpeedLocal landing page, catalogs, validators, and runtime
   source summaries.
2. Add a quarantined V2 app port only when we start real app behavior.
3. Make the port run through SpeedLocal's region index and file fallback paths.
4. Disable legacy region discovery before exposing the port publicly.
5. Run Bornholm and Trondelag independently.
6. Remove or hide features after they run, instead of rebuilding them before
   they run.
7. Promote each simplification with a validator.

Suggested quarantine location:

- `apps/v2_port/`

Suggested rule:

- Nothing under `apps/v2_port/` is considered clean final architecture. It is a
  working baseline to reduce, not a place to grow new features.

## Standard Layer Simplification

The first SpeedLocal app version should expose fewer standard layer groups:

- roads
- population
- nature
- culture
- grid infrastructure

These map to V2 concepts:

- roads -> `transport`
- population -> `settlement`
- nature -> `protected`
- culture -> `culture`
- grid infrastructure -> `electrical`

Everything else should be regional or advanced catalog content, for example:

- Trondelag reindeer husbandry / reindrift
- Bornholm coastal or strand-protection rules
- aviation
- military
- land-use details
- local planning layers
- project-specific layers

This keeps the public app simpler without deleting the ability to add richer
regional data later.

## First V2 Port Slice

Do not copy the full V2 repo. The first app-behavior slice should copy only:

- `potential_app.py` into a quarantine module or entrypoint.
- The minimum imported modules from `apps/potential_model/`.
- The minimum imported modules from `apps/acceptance_model/`.
- Small manifests needed for Bornholm and Trondelag.
- No large GeoJSON/CSV runtime files.

The copied app must be patched immediately to:

- read only `regions/index.json` for public region discovery;
- disable Vara and legacy `skara` exposure;
- use file fallbacks against the V2 source root until Postgres is validated;
- keep Skaraborg planned/disabled;
- expose only the simplified standard layer groups by default;
- keep regional extras catalog-driven.

## Acceptance Criteria For The Port

The quarantine port is acceptable only when:

- Bornholm opens.
- Trondelag opens.
- Skaraborg remains planned/disabled unless runtime data is complete.
- Trondelag does not expose R8/R9.
- Bornholm keeps R10-derived R9 PEY labelling.
- No large generated data is copied into `speedlocal`.
- The repo validators still pass.
- The port can be deleted or reduced module-by-module without losing the public
  landing page or SpeedLocal catalogs.

## Next Action

The quarantine port inventory now lives in
`docs/V2_QUARANTINE_PORT_INVENTORY_2026-06-26.md`. Before copying code:

1. List exact V2 imports used by `potential_app.py`.
2. Split them into required-now, required-later, and leave-behind.
3. Add a validator that fails if legacy Vara/skara discovery is reintroduced.
4. Copy the V2 app baseline into `apps/v2_port/`.
5. Make the baseline run locally.
6. Only then start removing panels, layer groups, and technical UI.

Items 1-3 are complete. The next implementation step is the first guarded copy
into `apps/v2_port/`.
