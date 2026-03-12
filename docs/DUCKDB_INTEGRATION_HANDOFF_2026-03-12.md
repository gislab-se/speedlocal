# DuckDB Integration Handoff

Date: 2026-03-12

## What We Completed

- Inspected the shared DuckDB download and compared it with the app's existing DuckDB integration.
- Confirmed the shared database does not match the old local schema:
  - shared DB has `timesreport` plus lookup tables
  - shared DB uses `unit` instead of `units`
  - shared DB uses `all_ts` instead of `timeslice`
  - shared DB does not contain `timesreport_raw`, `v_energy_mix`, `v_energy_totals`, or `area_factors`
- Updated the app so DuckDB source resolution now works in three ways:
  - local file at `data/processed/speedlocal_times.duckdb`
  - `DUCKDB_PATH`
  - `DUCKDB_SHARE_URL`
- Added support for reading these settings from Streamlit secrets as well as environment variables.
- Updated the app so DuckDB loading supports both:
  - legacy repo-built schema (`timesreport_raw` / `v_energy_mix`)
  - shared schema (`timesreport`, `unit`, `all_ts`)
- Updated preview/status logic so the UI can report DuckDB usage instead of always implying CSV.
- Verified the patched loader against:
  - `C:\Users\henri\Downloads\260305_speedlocal_times_db_bornholm_v3.duckdb`

## Verified Result

- The app can now read scenarios dynamically from the shared DuckDB.
- The downloaded shared DB currently exposes these scenarios:
  - `BASELINE2050`
  - `BASELINE2050-4W`
  - `ENERGYISLAND2050`
- This means the app is no longer tied to the old four mock scenarios.
- If a future DB contains `low`, `medium`, and `high`, the scenario selector should follow the DB automatically.

## Known Gap

- The shared DuckDB does not contain `area_factors`.
- Current behavior is therefore:
  - TIMES scenarios and mix can come from DuckDB
  - area-demand factors still fall back to Excel/default values

## Proposed Next Steps

1. Configure the hosted Streamlit app with `DUCKDB_SHARE_URL` in secrets and redeploy.
2. Verify in the deployed UI that `TIMESreport-status` reports DuckDB, not CSV.
3. Decide whether `area_factors` should be added to the shared DuckDB or remain a separate source.
4. If desired, map raw scenario codes to friendlier labels using `scen_desc.description`.
5. Once the real scenario naming is stable, review energy-key grouping to make sure the mix categories match the intended planning story.

## Files Changed In This Session

- `apps/gc4/app_gc4_energy.py`
- `README.md`
- `docs/DUCKDB_INTEGRATION_HANDOFF_2026-03-12.md`
