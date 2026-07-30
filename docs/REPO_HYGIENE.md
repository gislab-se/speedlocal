# SpeedLocal repository boundaries

This repository is the V2 Final delivery repository. Keep it small,
deployable, and easy to validate.

## Product boundary

- Frozen V2 is an immutable external Trøndelag behavior reference and a
  multi-region diagnostic data archive.
- `C:\gislab\data\landskapsanalys-v2-multiregion` is a read-only local runtime
  archive, not application source to import wholesale.
- `app.py` launches the active V2 Final monolith under `apps/v2_port/`.
- V2 Final is reduced and generalized one promoted vertical slice at a time.
- Reusable contracts, providers, validators, and analysis belong under
  `speedlocal/`.
- Do not create another parity or replacement application.
- Do not import V3 as the product baseline.

The authoritative direction is `GENERAL_PROGRAM_PLAN.md`. The dated route and
daily routine are `DELIVERY_PLAN.md` and `DAILY_WORKFLOW.md`.

## Keep in this repository

- the static landing page under `site/` and its Pages workflow;
- the root V2 Final entrypoint and active `apps/v2_port/` monolith;
- manifest-driven business logic under `speedlocal/`;
- `regions/index.json` and validated region packages;
- small contracts, schemas, validators, tests, and import helpers;
- database/runtime scaffolding under `db/` and `data/runtime/`;
- current delivery, deployment, slice, and daily documentation.

`status_app.py` may remain as a technical diagnostic, but it is not a product
surface and must not become a parallel application.

## Keep out

- broad copies of V2 or V3 source trees;
- generated GIS data, caches, logs, exports, map bundles, and local scratch
  output;
- mounted runtime data or machine-specific data copies;
- large `.gpkg`, `.tif`, `.duckdb`, `.xlsx`, `.geojson`, or rendered outputs
  unless a documented runtime decision explicitly promotes one;
- local secrets, `.env` files, database credentials, API keys, or Streamlit
  secrets;
- legacy region discovery, inactive app branches, and duplicate application
  shells.

Large runtime data stays outside Git. Local V2 fallback paths must go through
`SPEEDLOCAL_V2_SOURCE_ROOT`; cloud deployments need a separate cloud-accessible
provider.

## Copy rule

Before copying any artifact from frozen V2:

1. prove it is required by the active slice;
2. record it in the current `daily/YYYY-MM-DD.md` log;
3. prefer a manifest, adapter, validator, or small metadata artifact;
4. add validation for any behavior, runtime contract, region, or public-link
   change;
5. leave the frozen V2 source and runtime archive untouched.

If those checks fail, resolve the artifact through the read-only provider or
leave it outside this repository.

## Required checks

After changes in their respective scopes, run:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\gislab\data\landskapsanalys-v2-multiregion"
& ".\.venv\Scripts\python.exe" -B scripts\validate_delivery_repo.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_static_site.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_region_readiness.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_v2_port_guardrails.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_v2_source_adapter.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_v2_final_baseline_parity.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_v2_port_app.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_generic_engine.py
& ".\.venv\Scripts\python.exe" -B scripts\validate_frozen_v2_reference.py
```

Before publishing, also check `git diff --check`, inspect V2 Final on localhost,
and follow the two-commit publication closeout in `DAILY_WORKFLOW.md`.

## Checkpoint rules

A daily work checkpoint is ready when:

- V2 Final remains the single active product application;
- the bounded increment has explicit automated evidence;
- validators and localhost review for that increment pass;
- no generated runtime data or secrets are tracked;
- the daily log records what remains legacy and the deployment status is
  current.

A full slice-promotion checkpoint additionally requires:

- the complete active slice meets every promotion gate;
- no calculation or UI path replaced by that complete slice remains active.
