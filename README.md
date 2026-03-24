# speedlocal

Clean migration repo for Bornholm geocontext work.

## Included now

- Streamlit app: `apps/gc4/app_gc4_energy.py`
- App data:
  - `data/gc4/bornholm_vindacceptans_stage1_v4_res9_hex.geojson`
  - `data/processed/speedlocal_times.duckdb`
  - `data/raw/AreaDemand.xlsx`
- Geocontext pipeline core (Phase 2 assets):
  - `script/05_finalize_bornholm_r8_geocontext_features.R`
  - `script/06_build_bornholm_r8_geocontext_score.R`
  - `script/07_create_bornholm_r8_qgis_views.R`
  - `script/config/bornholm_r8_geocontext_feature_map.csv`
  - `script/config/bornholm_r8_geocontext_scoring.csv`
  - `docs/geocontext/bornholm_37_lager_svenska.csv`
  - `R/db_connect.R`

## Run app locally

```powershell
cd C:\gislab\speedlocal
python -m venv .venv
.\.venv\Scripts\python -m pip install -r apps\gc4\requirements.txt
.\.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

Open: http://127.0.0.1:8502

## Notes

- The GC4 app is now strict by default. It should use:
  - `data/gc4/bornholm_vindacceptans_stage1_v4_res9_hex.geojson`
  - `data/processed/speedlocal_times.duckdb`
  - `data/raw/AreaDemand.xlsx`
- DuckDB source can be provided in three ways:
  - local file at `data/processed/speedlocal_times.duckdb`
  - env var or Streamlit secret `DUCKDB_PATH` pointing at a `.duckdb` file
  - env var or Streamlit secret `DUCKDB_SHARE_URL` pointing at a download link for a DuckDB file
- Hexagon source can be overridden with:
  - `HEX_POINTS_PATH`
  - `HEX_SCORES_PATH`
  - `ACCEPTANCE_LAYER_PATH`
- The committed default hex source is `res9` GeoJSON, not the old `r8` CSV files.
- The app no longer silently falls back to `data/external/timesreport/compare_timesreport.csv` or the old `r8` map files.
- `TIMESREPORT_CSV_PATH` is available only as an explicit debug/override path.
- The source acceptance framework currently emits GeoPackage (`.gpkg`), but the repo carries GeoJSON for deploy simplicity:
  - easier to read in the app without GDAL/GeoPandas
  - not blocked by the repo's `*.gpkg` ignore rule
  - easier to ship to Streamlit Cloud as a normal tracked file
- The app supports both the repo-built DuckDB schema (`timesreport_raw` / `v_energy_mix`) and the shared schema (`timesreport`, `unit`, `all_ts`).
- `script/config/bornholm_r8_geocontext_layers.csv` is not yet included (to be reconstructed from 37-layer spec).
