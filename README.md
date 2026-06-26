# speedlocal

Bare-minimum delivery repo for SpeedLocal landscape potential.

This public repo is intentionally slim. The old exploratory material has been
removed from the delivery tree. The V2 `landskapsanalys` repo remains the source
archive: when something is missing, copy only the smallest runtime-critical
piece.

## Surfaces

- Static landing page: `site/landskapspotential/index.html`
- GitHub Pages workflow: `.github/workflows/pages.yml`
- Streamlit app shell: `app.py`
- Region catalogs: `regions/`
- Runtime database scaffold: `db/` plus `docker-compose.yml`
- File fallbacks: documented under `data/runtime/`

## Regions

- Bornholm: active catalog, file fallback until database coverage is validated.
- Trondelag: active catalog, R7/R6/R5 only, file fallback until database coverage is validated.
- Skaraborg: planned/disabled catalog slot for forward design.

The app must discover regions from `regions/index.json` only. Do not reintroduce
legacy fallback region manifests that can expose old regions unintentionally.

## Run Locally

```powershell
cd C:\tmp\speedlocal
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

Open: `http://127.0.0.1:8502`

## Validate

```powershell
python scripts\validate_delivery_repo.py
python scripts\validate_static_site.py
python scripts\validate_region_readiness.py
python scripts\validate_trondelag_runtime_sources.py
```

`validate_trondelag_runtime_sources.py` reads the V2 source archive without
copying large data files. Override the default source path with
`SPEEDLOCAL_V2_SOURCE_ROOT` if needed.

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
