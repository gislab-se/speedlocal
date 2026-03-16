# TIMES Integration Status And Plan

## What We Have Done So Far

Date: 2026-03-03

1. Repository and workspace setup
- Flattened nested folder structure from `C:\gislab\speedlocal\speedlocal` to `C:\gislab\speedlocal`.
- Fixed Streamlit config parsing issue by removing BOM in `.streamlit/config.toml`.

2. Partner repo integration
- Fork strategy established (safe workflow without changing upstream directly).
- Partner repo cloned locally at:
  - `C:\gislab\speedlocal\external\DemoS_012_timesreport`

3. TIMESreport output understanding
- Identified exported CSV schema from partner pipeline:
  - `filename,timesmodel,scen,sow,sector,subsector,service,techgroup,comgroup,topic,attr,prc,com,timeslice,regionFrom,regionTo,year,vntg,units,cur,value`
- Verified model group definitions from `Sets-DemoModels.xlsx`:
  - `comgroup` examples: `NRG_ELC, NRG_GAS, NRG_NUK, NRG_RNW, ...`
  - `techgroup` examples: `TG_BIO, TG_ELC, TG_GAS, TG_NUC, TG_REW, ...`

4. App upgrades completed
- Added support for reading TIMESreport-style CSV input.
- Added UI preview section: `TIMESreport output preview`.
- Made energy sliders dynamic based on detected energy categories.
- Implemented linked sliders (sum constrained to 100%).
- Added robust year selector handling (single-year scenarios no longer crash).
- Added improved mock TIMESreport CSV:
  - `data/external/timesreport/compare_timesreport.csv`

5. Current behavior
- App now runs with multi-energy dynamic sliders using the mock CSV.
- If real TIMESreport CSV becomes available, app can consume it directly.

## Goal Ahead

Move from file-based integration to database-backed integration using DuckDB:

1. Build a local DuckDB database in `data/processed/`.
2. Create ETL script to ingest:
- `compare_timesreport.csv`
- `AreaDemand.xlsx`
3. Update Streamlit app to read from DuckDB (SQL first), with fallback to CSV.

## Execution Plan (Next)

1. **Database bootstrap**
- Create `data/processed/speedlocal_times.duckdb`.
- Add normalized tables/views for energy mix and area factors.

2. **ETL script**
- New script (Python) in `script/` to:
  - Load TIMESreport CSV
  - Map technology labels
  - Convert units to TWh
  - Parse AreaDemand Excel to `area_factors`
  - Write curated tables/views in DuckDB

3. **App SQL integration**
- In app:
  - Try DuckDB first (`timesreport` + `area_factors` tables/views)
  - Fall back to CSV/existing logic if DB unavailable
- Keep UI behavior unchanged for users (same controls, better data source).

4. **Future UX step: Geocontext companion app**
- Build a separate Streamlit app focused on geocontext (cluster definitions, factor logic, geospatial context).
- Add a clear link/button in the energy app to open the geocontext app.
- Purpose: when users have questions about clusters/geocontext assumptions, they can jump to a dedicated explainer/analysis view without leaving the workflow.

## Notes / Risks

- `duckdb` Python package is currently missing in `.venv`.
- ETL and app code can be added now, but runtime DB steps require installing `duckdb`.

## Session Continuity Note (Short)

Use this section if we need to resume quickly in a later session.

1. Technical summary
- Current operational flow in this repo is primarily:
  - `TIMESreport CSV -> Python ETL -> DuckDB -> Streamlit`
- App supports dynamic energy categories, linked sliders, and DB-first data loading with CSV fallback.

2. Integration spec (minimum)
- Input:
  - `timesreport_raw` (from `compare_timesreport.csv`)
  - `area_factors` (from `AreaDemand.xlsx`)
- Core filters:
  - `topic = 'energy'`
  - `attr IN ('f_out', 'comnet')`
  - `timeslice = 'annual'`
- Core outputs:
  - `v_energy_mix(scen, year, energy_key, value_twh)`
  - `v_energy_totals(scen, year, total_twh)`

3. Most relevant TIMES columns for landscape allocation
- Core:
  - `scen, year, topic, attr, value, units`
  - `techgroup, comgroup, prc, com` (for technology mapping)
- Context:
  - `timeslice` (annual selection)
  - `sector` (sector-specific analyses)
- Usually secondary:
  - `regfrom, regto, vntg`

4. Practical status
- If `filename` in source data is `mock_timesreport.gdx`, we are still on enhanced dummy data.
- To switch to real data:
  - Replace `data/external/timesreport/compare_timesreport.csv`
  - Rebuild DB: `.\.venv\Scripts\python script\build_times_duckdb.py`
  - Restart Streamlit app.
