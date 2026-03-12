# speedlocal

Clean migration repo for Bornholm geocontext work.

## Included now

- Streamlit app: `apps/gc4/app_gc4_energy.py`
- App data:
  - `jyp_note_book_geocontext/bornholm_points_with_context_gc4.csv`
  - `jyp_note_book_geocontext/bornholm_r8_factor_scores_gc4.csv`
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
cd C:\gislab\speedlocal\speedlocal
python -m venv .venv
.\.venv\Scripts\python -m pip install -r apps\gc4\requirements.txt
.\.venv\Scripts\python -m streamlit run apps\gc4\app_gc4_energy.py --server.address 127.0.0.1 --server.port 8502
```

Open: http://127.0.0.1:8502

## Notes

- `app_gc4_energy.py` uses fallback area factors when `data/raw/AreaDemand.xlsx` is missing.
- DuckDB source can be provided in three ways:
  - local file at `data/processed/speedlocal_times.duckdb`
  - env var or Streamlit secret `DUCKDB_PATH` pointing at a `.duckdb` file
  - env var or Streamlit secret `DUCKDB_SHARE_URL` pointing at a download link for a DuckDB file
- The app supports both the repo-built DuckDB schema (`timesreport_raw` / `v_energy_mix`) and the shared schema (`timesreport`, `unit`, `all_ts`).
- `script/config/bornholm_r8_geocontext_layers.csv` is not yet included (to be reconstructed from 37-layer spec).
