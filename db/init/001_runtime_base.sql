\set ON_ERROR_STOP on

CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS runtime;

COMMENT ON SCHEMA meta IS 'Metadata, import runs, dataset versions, manifests, and validation status.';
COMMENT ON SCHEMA raw IS 'Imported source snapshots and staging data. Not the app runtime contract.';
COMMENT ON SCHEMA runtime IS 'Validated app read-model tables shared by all regions.';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'
    ) THEN
        CREATE EXTENSION IF NOT EXISTS postgis;
    ELSE
        RAISE NOTICE 'PostGIS extension is not available in this PostgreSQL image.';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS meta.schema_migrations (
    migration_id text PRIMARY KEY,
    description text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime.regions (
    region_id text PRIMARY KEY,
    display_name text NOT NULL,
    native_crs text NOT NULL,
    app_status text NOT NULL DEFAULT 'planned',
    data_status text NOT NULL DEFAULT 'unknown',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT regions_region_id_format CHECK (region_id ~ '^[a-z0-9_]+$'),
    CONSTRAINT regions_native_crs_format CHECK (native_crs ~ '^EPSG:[0-9]+$')
);

INSERT INTO runtime.regions (
    region_id, display_name, native_crs, app_status, data_status, notes
) VALUES
    ('bornholm', 'Bornholm', 'EPSG:25833', 'active', 'file_fallback_until_speedlocal_runtime_import', 'Active pilot; file fallback until database import is validated.'),
    ('trondelag', 'Trondelag', 'EPSG:25832', 'active', 'file_fallback_until_speedlocal_runtime_import', 'Active pilot; R7/R6/R5 only.'),
    ('skaraborg', 'Skaraborg', 'EPSG:3006', 'planned', 'catalog_slot_only', 'Planned/disabled until reviewed runtime data exists.')
ON CONFLICT (region_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    native_crs = EXCLUDED.native_crs,
    app_status = EXCLUDED.app_status,
    data_status = EXCLUDED.data_status,
    notes = EXCLUDED.notes,
    updated_at = now();

INSERT INTO meta.schema_migrations (
    migration_id, description
) VALUES (
    '001_runtime_base',
    'Create SpeedLocal shared schemas and seed regional registry.'
)
ON CONFLICT (migration_id) DO NOTHING;
