# speedlocal

Bare-minimum delivery repo for SpeedLocal landscape potential.

This public repo is intentionally slim. Frozen V2 is the read-only Trøndelag
behavior reference; its external `landskapsanalys` runtime archive also retains
multi-region diagnostic assets. The active `apps/v2_port/` code is V2 Final:
the working monolith being reduced and made manifest-driven one complete slice
at a time.

## Surfaces

- Static landing page: `site/landskapspotential/index.html`
- GitHub Pages workflow: `.github/workflows/pages.yml`
- V2 Final Streamlit entrypoint: `app.py`
- Active V2 Final monolith: `apps/v2_port/`
- V2 Final development deployment: `https://speedlocal-landskapspotential.streamlit.app/`
- Frozen V2 Trøndelag reference: `https://landskapsanalys-potential-v2-test.streamlit.app/`
- Bornholm V1 visual reference: `https://landskapsanalys-potential-v1.streamlit.app/`
- Technical runtime diagnostic, not a product surface: `status_app.py`
- Region catalogs: `regions/`
- Runtime database scaffold: `db/` plus `docker-compose.yml`
- File fallbacks: documented under `data/runtime/`

## Regions

- Bornholm: onboarding catalog; V2 Final route disabled until V1 and regional
  acceptance evidence are pinned and validated.
- Trondelag: only active V2 Final catalog and authoritative frozen-V2 parity
  region; R7/R6/R5 only.
- Skaraborg: planned/disabled catalog slot for forward design.

The app must discover regions from `regions/index.json` only. Do not reintroduce
legacy fallback region manifests that can expose old regions unintentionally.

## Repo Hygiene

This repo should stay delivery-focused. Do not copy broad V2 folders, generated
GIS outputs, QGIS review packages, rendered reports, caches, or local scratch
files. Before copying anything from V2, record the decision in the current
daily log and add or update a validator when behavior or runtime contracts
change.

See `docs/REPO_HYGIENE.md` for the keep/delete rules and cleanup checklist.
The authoritative product and implementation direction is
`docs/GENERAL_PROGRAM_PLAN.md`.
The dated route to delivery and daily working routine are documented in
`docs/DELIVERY_PLAN.md` and `docs/DAILY_WORKFLOW.md`.

## Run Locally

```powershell
cd C:\gislab\projekt\speedlocal
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\gislab\data\landskapsanalys-v2-multiregion"
& ".\scripts\start_app.ps1"
```

Open: `http://127.0.0.1:8502`

The explicit environment variable keeps using the complete read-only archive
for development and full-archive regression. If it is unset, the root
entrypoint materializes the checksum-pinned Trøndelag runtime package declared
in
`data/runtime/manifests/trondelag/v2-final-runtime-r7-2026-07-30.1.json`.
The 45-file package is a V2 Final data transport, not a copy or replacement of
the frozen V2 reference app.

Published Trøndelag runtime prerelease:
`https://github.com/gislab-se/speedlocal/releases/tag/v2-final-runtime-trondelag-r7-2026-07-30.1`.
The Streamlit Cloud app may require explicit reviewer access even though the
repository and runtime package are public.

The start script refuses to launch a second server when port `8502` already
has an active listener. Stop the existing V2 Final server before restarting it.

The root entrypoint opens the actual V2 Final monolith. To run the technical
runtime diagnostic separately:

```powershell
python -m streamlit run status_app.py --server.address 127.0.0.1 --server.port 8504
```

## Validate

```powershell
python scripts\validate_delivery_repo.py
python scripts\validate_static_site.py
python scripts\validate_region_readiness.py
python scripts\validate_trondelag_runtime_sources.py
python scripts\validate_file_runtime_summary.py
python scripts\validate_v2_port_guardrails.py
python scripts\validate_v2_source_adapter.py
python scripts\validate_v2_final_baseline_parity.py
python scripts\validate_v2_port_app.py
python scripts\prepare_trondelag_runtime_metadata.py
python scripts\validate_generic_engine.py
python scripts\validate_frozen_v2_reference.py
python scripts\validate_runtime_bundle.py
```

Optional Bornholm archive/onboarding diagnostic:

```powershell
python scripts\validate_bornholm_v2_diagnostics.py
```

The V2 source, app, frozen-reference, Trøndelag, and file-runtime validators
read the V2 source archive without copying large data files. Set
`SPEEDLOCAL_V2_SOURCE_ROOT` to that read-only archive before running them.
Trøndelag uses either the complete local archive or its exact reviewed cloud
runtime package until a matching Postgres/Flowcore provider is available.
Bornholm's two checksum-validated polygon checkpoints remain full-archive
diagnostic evidence only; they are not included in the Trøndelag cloud package
and do not establish Bornholm product parity or readiness.

To emit metadata-only SQL for the first Trondelag runtime import:

```powershell
python scripts\prepare_trondelag_runtime_metadata.py --emit-sql
```

Optional database check, after Docker/Postgres is running:

```powershell
python scripts\check_runtime_db.py
```

## Runtime Database

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
python scripts\check_runtime_db.py
```

The preferred runtime path is Postgres when available and validated. File paths
remain as fallbacks until the equivalent database tables exist and match.

## GitHub Pages

The canonical static page is:

`https://gislab-se.github.io/speedlocal/landskapspotential/`

The Pages workflow publishes the `site/` directory on pushes to `main` that
touch the static site or the workflow. The workflow can also be run manually.

GitHub Pages is static hosting only. Interactive Python/Streamlit apps must run
through Flowcore, Docker/server runtime, or another Streamlit-compatible host.

V2 Final development deployment:

`https://speedlocal-landskapspotential.streamlit.app/`

Active region deep link:

- `https://speedlocal-landskapspotential.streamlit.app/?region=trondelag`

Bornholm remains visible with its V1 reference but has no active V2 Final deep
link during onboarding. Skaraborg remains planned and receives a V2 Final
button only after its manifest, runtime data, and readiness checks pass.

The repository itself does not deploy Streamlit through GitHub Actions.
Streamlit Cloud auto-deployment and the checksum-pinned GitHub Release runtime
are verified separately after each work checkpoint; see `docs/DEPLOYMENT.md`.
