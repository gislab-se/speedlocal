# Runtime Data Policy

This repo prefers SpeedLocal Postgres runtime tables. File paths stay as
fallbacks until database-backed data exists and validates against the file
backend.

Allowed here:

- Small fallback manifests.
- Small sample fixtures for validators.
- Explicit placeholders documenting where runtime data will be mounted.

Not allowed here by default:

- QGIS review packages.
- Rendered report folders.
- Exploratory model outputs.
- Large GeoJSON, GPKG, TIF, DuckDB, XLSX or generated cache files without a
  documented runtime reason.

Expected fallback mount location:

- `data/runtime/fallbacks/<region>/...`

Generated or mounted local runtime data should stay ignored unless explicitly
promoted as a reviewed delivery artifact.
