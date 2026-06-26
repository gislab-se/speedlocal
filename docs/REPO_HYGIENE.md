# SpeedLocal Repo Hygiene

Date: 2026-06-26

This repo is the delivery repo, not the exploratory archive. Keep it small,
deployable, and easy to validate. The V2 `landskapsanalys` checkout remains the
source archive.

## Current Block

The Day-1 baseline is complete:

- GitHub Pages landing page is live.
- Streamlit Cloud status app is linked from the landing page.
- Region catalog discovery is limited to Bornholm, Trondelag, and Skaraborg.
- Bornholm has a file-backed runtime source summary against the V2 archive,
  including R10-derived R9 PEY labelling.
- Trondelag has a file-backed runtime source summary against the V2 archive.
- Postgres is prepared as the preferred future runtime, but file fallbacks stay
  documented until database-backed reads validate.

Next block: prepare a quarantined V2 app port for the first real regional
surface. See `docs/APP_MIGRATION_STRATEGY_2026-06-26.md`. The port should run
first and then be reduced behind SpeedLocal catalogs; do not rebuild the app
from scratch and do not copy V3 as the baseline.

## Keep In This Repo

- `site/landskapspotential/index.html` and Pages workflow.
- `app.py` and `apps/landskapspotential/` status/app shell.
- `regions/index.json` and the three region packages.
- `db/init/` schema and runtime contract SQL.
- `scripts/validate_*.py`, `scripts/check_runtime_db.py`, and small import or
  metadata helpers.
- `docs/` files that explain delivery, deployment, runtime import, region
  onboarding, and copy/leave-behind decisions.
- `data/runtime/README.md` and small runtime contract notes.

## Keep Out

Delete or leave out:

- Python caches: `__pycache__/`, `*.pyc`.
- Local working output: `tmp/`, `artifacts/`, `.streamlit/*.log`.
- Mounted or generated runtime data: `data/runtime/generated/`,
  `data/runtime/mounted/`.
- Broad V2 folders copied wholesale.
- QGIS review packages, rendered reports, map export folders, and old report
  archives.
- Large `.gpkg`, `.tif`, `.duckdb`, `.xlsx`, `.geojson`, and rendered HTML
  bundles unless a later runtime decision explicitly promotes one.
- Legacy app folders such as old GC4, solochvind, or inactive region fallback
  manifests.
- Legacy region exposure for Vara or `skara` unless a compatibility adapter and
  validator are added first.
- V3 `data/incoming/`, promoted runtime GeoJSON/CSV, caches, logs, or its new
  app architecture as a delivery baseline.

## Copy Rule

Before copying anything from V2 into `speedlocal`:

1. Add it to `docs/SPEEDLOCAL_COPY_LIST.md` as a candidate or accepted file.
2. Explain why it is needed for the current slice.
3. Prefer manifests, validators, import scripts, and small metadata files before
   generated data.
4. Add or update a validator when the file affects app behavior, runtime
   contracts, region discovery, or public links.
5. Keep V2 read-only during this migration.

If a file cannot pass those checks, leave it in V2 and read it as a source
archive or file fallback.

If `potential_app.py` is copied, copy it only as a quarantined baseline under a
clearly named V2-port area. It is allowed as a working source to shrink, not as
clean final architecture.

## Cleanup Checklist

Run before committing:

```powershell
git status --short --branch
python -B scripts\validate_delivery_repo.py
python -B scripts\validate_static_site.py
python -B scripts\validate_region_readiness.py
python -B scripts\validate_file_runtime_summary.py
python -B scripts\validate_trondelag_runtime_sources.py
python -B scripts\prepare_trondelag_runtime_metadata.py
```

Remove local generated clutter when needed:

```powershell
Remove-Item -Recurse -Force -LiteralPath apps\__pycache__,apps\landskapspotential\__pycache__,tmp -ErrorAction SilentlyContinue
```

If Streamlit is running locally, stop it before deleting Python cache files.

## Acceptance Rule

A change is ready only when:

- The repo stays small and delivery-focused.
- Validators pass.
- Public Pages and Streamlit links remain clear.
- No large generated runtime data is committed by accident.
- V2 remains untouched except for read-only inspection.
