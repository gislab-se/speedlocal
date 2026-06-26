# V2 Quarantine Port Inventory

Date: 2026-06-26

Source archive: `C:\tmp\landskapsanalys-v2-multiregion`

Target repo: `C:\tmp\speedlocal`

This inventory prepares the V2 quarantine port before any code is copied. The
goal is to preserve working V2 behavior without recreating the V3 failure mode:
too much new architecture before the old behavior runs.

## Port Rule

The V2 app may be copied only as a quarantined working baseline, not as final
SpeedLocal architecture.

Suggested location:

- `apps/v2_port/`

Nothing in `apps/v2_port/` should grow new product features. It is a baseline
to run, patch, validate, and shrink.

Status:

- First guarded copy complete.
- Copied files are documented in `docs/SPEEDLOCAL_COPY_LIST.md`.
- Guardrail patches have been applied before public exposure.
- `scripts/validate_v2_port_guardrails.py` passes after the copy.

## Direct Imports From `potential_app.py`

Standard library:

- `collections.deque`
- `hashlib`
- `html`
- `io.StringIO`
- `json`
- `math`
- `os`
- `pathlib.Path`
- `subprocess`
- `sys`
- `time`
- `typing.Any`

Third-party:

- `h3`
- `pandas`
- `streamlit`
- optional Streamlit components via `streamlit.components.v1`

Direct local imports:

- `potential_model.geometry`
- `potential_model.landscape`
- `potential_model.manifests`
- `potential_model.region_status`
- `potential_model.map_rendering`
- `potential_model.energy_modeling`
- `potential_model.potential`
- `potential_model.social_acceptance`
- `potential_model.wind_acceptance`
- `acceptance_model.layers`
- `acceptance_model.runtime_geometry`
- `acceptance_model.i18n`

Secondary local imports found in those modules:

- `acceptance_model.group_logic`
- `acceptance_model.map_rendering`
- `acceptance_model.leaflet_map`
- `potential_model.geometry`
- `potential_model.manifests`
- `potential_model.potential`

Third-party dependencies used by secondary modules:

- `numpy`
- `duckdb` for energy model runtime
- `openpyxl` through `pandas.read_excel`
- `sqlite3` from the standard library for GPKG-like reads

`pydeck` appears only in older acceptance map rendering helpers and is not part
of the preferred SpeedLocal map direction.

## Required Now

Required to make the quarantined V2 app import and open its baseline UI:

- `potential_app.py`
- `apps/potential_model/__init__.py`
- `apps/potential_model/geometry.py`
- `apps/potential_model/landscape.py`
- `apps/potential_model/manifests.py`
- `apps/potential_model/region_status.py`
- `apps/potential_model/map_rendering.py`
- `apps/potential_model/energy_modeling.py`
- `apps/potential_model/potential.py`
- `apps/potential_model/social_acceptance.py`
- `apps/potential_model/wind_acceptance.py`
- `apps/acceptance_model/__init__.py`
- `apps/acceptance_model/i18n.py`
- `apps/acceptance_model/layers.py`
- `apps/acceptance_model/runtime_geometry.py`
- active Bornholm and Trondelag region manifests or SpeedLocal adapters
- active Bornholm and Trondelag acceptance registries
- small linked manifests needed for startup/status

Required runtime dependencies when the port is enabled:

- `h3`
- `numpy`
- `pandas`
- `streamlit`
- `duckdb`, unless scenario panels are disabled
- `openpyxl`, unless AreaDemand Excel reads are disabled

## Required Later

These should not be copied into the first quarantine port. Keep them as V2 file
fallbacks, mounted runtime data, or future Postgres imports:

- large display GeoJSON files
- large landscape GeoJSON files
- large potential/runtime CSV files
- `data/processed/speedlocal_times.duckdb`
- `data/raw/AreaDemand.xlsx`
- acceptance asset manifests and generated distance tables
- generated R runtime outputs
- scenario allocation and outside-LP runtime data
- full social acceptance runtime beyond current status/manifest validation

## Leave Behind

Do not copy:

- V2 root `app.py`, the old GC4/Bornholm geocontext app.
- V2 `regions/index.json` unchanged, because it includes `skara`.
- V2 `regions/skara/`.
- `apps/potential_model/manifests/regions/`.
- `apps/potential_model/manifests/regions/vara.json`.
- generic `apps/acceptance_model/registry.json` fallback unless an explicit
  adapter and validator proves it cannot expose the wrong region.
- V2 `exports/qgis_review/`.
- V2 `artifacts/`, `tmp/`, `__pycache__/`, rendered report folders, logs, and
  review packages.
- V3 repo files from `C:\tmp\landskapspotential`, especially `data/incoming/`,
  `data/regions/`, caches, logs, and its replacement app architecture.

## Guardrail Patches Required Before Run

Patch `potential_model.manifests` before the copied app is exposed:

- Region discovery must use the SpeedLocal `regions/index.json` only.
- Remove package glob discovery of every `regions/*/region.json`.
- Remove legacy discovery under `apps/potential_model/manifests/regions`.
- Keep `skaraborg` planned/disabled; do not map it to V2 `skara` unless a
  compatibility adapter is added and tested.

Patch `acceptance_model.layers` before the copied app is exposed:

- Registry selection must be explicit for Bornholm and Trondelag.
- Do not fall back to generic `registry.json`.
- For planned/unknown regions, fail closed with a visible status.

Patch `runtime_geometry.py` before any R runtime is enabled:

- Do not write generated geometry into V2-style docs folders.
- Keep generated runtime output out of git.
- Prefer file fallback or Postgres runtime validation before enabling writes.

Patch `potential_app.py` before public use:

- Public region choices must be Bornholm, Trondelag, and planned Skaraborg.
- Trondelag must expose only R7/R6/R5.
- Bornholm must keep R10-derived R9 PEY labelling.
- First standard layer groups should be roads, population, nature, culture, and
  grid infrastructure.
- Regional extras, such as Trondelag reindeer husbandry, must come from the
  region catalog.

## First Standard Layer Groups

Public default groups:

- roads -> V2 `transport`
- population -> V2 `settlement`
- nature -> V2 `protected`
- culture -> V2 `culture`
- grid infrastructure -> V2 `electrical`

Regional or advanced groups:

- Trondelag reindeer husbandry / reindrift
- Bornholm coastal and strand-protection rules
- aviation
- military
- detailed land use
- project-specific layers

## Acceptance For Copying Code

For every code copy into `apps/v2_port/`:

1. `scripts/validate_v2_port_guardrails.py` must pass.
2. `scripts/validate_delivery_repo.py` must pass.
3. The copy command must copy only the accepted files for this slice.
4. No generated GIS data may be copied.
5. The first copied version must be runnable locally before any shrinking work
   starts.

Current status:

- Items 1-4 pass for the first guarded copy.
- Item 5 is the next task: start the quarantine app locally and make Bornholm
  and Trondelag open through the SpeedLocal region catalog before shrinking UI
  panels or layer groups.
