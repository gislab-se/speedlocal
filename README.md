# speedlocal

Bornholm-repo med en ny förenklad Streamlit-app för sol och vind.

## Aktiv app

- Entry point: `app.py`
- Aktiv app: `apps/solochvind/app_solochvind.py`
- Legacy/appreferens: `apps/gc4/app_gc4_energy.py`

## Data som används av nya appen

- `data/gc4/bornholm_vindacceptans_stage1_v4_res9_hex.geojson`
- `data/processed/speedlocal_times.duckdb`
- `data/raw/AreaDemand.xlsx`

## Kör lokalt

```powershell
cd C:\gislab\speedlocal
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502
```

Öppna: http://127.0.0.1:8502

## Vad nya appen innehåller

- 3.1 Scenario
- 3.2 Markintensitet
- 3.3.1 Landskaps-acceptans-vind
- 3.3.2 Landskaps-acceptans-sol
- Elmix med bara vind och sol
- Hexurval med manuella tillägg och borttag

## Noteringar

- Den nya appen läser bara `NRG_WIN` och `NRG_SOL` från DuckDB.
- `res9` är standardkartan. `res8` används inte längre i aktiv app.
- `HEX_POINTS_PATH` och `DUCKDB_PATH` kan fortfarande användas som explicita overrides.
- GeoJSON används i repot eftersom det är enklare att deploya än `.gpkg` i Streamlit Cloud.
