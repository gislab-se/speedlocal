# Deployment Notes

## Static Page

Target path:

`https://gislab-se.github.io/speedlocal/landskapspotential/`

The Pages workflow publishes the `site/` directory.

The repo is public as of 2026-06-26, so GitHub Pages can publish from this repo.
The `Publish GitHub Pages` workflow runs on pushes to `main` that touch the
static site or the workflow, and it can also be run manually.

GitHub Pages is static hosting only. If this repo is made private again before
Flowcore migration, Pages may stop publishing unless the GitHub plan supports
private Pages.

## Interactive App

Current Streamlit Cloud regional app:

`https://speedlocal-landskapspotential.streamlit.app/`

Region deep links:

- `https://speedlocal-landskapspotential.streamlit.app/?region=bornholm`
- `https://speedlocal-landskapspotential.streamlit.app/?region=trondelag`
- `https://speedlocal-landskapspotential.streamlit.app/?region=skaraborg`

The current product and migration sequence is defined in
`GENERAL_PROGRAM_PLAN.md`. PostGIS is deferred until the generic file-backed
engine has parity for the five standard public groups.

Temporary roads parity surface:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\gislab\data\landskapsanalys-v2-multiregion"
$env:SPEEDLOCAL_GENERIC_ROADS_PARITY = "1"
& ".\.venv\Scripts\python.exe" -m streamlit run app.py --server.port 8503
```

Unset `SPEEDLOCAL_GENERIC_ROADS_PARITY` to run the ordinary V2 surface.

Run locally:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\path\to\landskapsanalys-v2-multiregion"
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

The technical runtime status view remains available through `status_app.py`.

Future hosting should use Flowcore, Docker/server runtime, or a compatible
Streamlit app host.

## Runtime Data

Preferred order:

1. Validated Postgres runtime tables.
2. Documented file fallback paths.
3. Planned/disabled region state.

Do not remove file fallbacks until the database-backed path has matching
validation.
