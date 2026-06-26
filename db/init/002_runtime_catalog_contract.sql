\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS meta.runtime_datasets (
    dataset_id text PRIMARY KEY,
    region_id text REFERENCES runtime.regions (region_id),
    dataset_kind text NOT NULL,
    dataset_version text NOT NULL,
    source_status text NOT NULL,
    validation_status text NOT NULL DEFAULT 'not_validated',
    source_path text,
    source_manifest text,
    expected_feature_count integer,
    actual_feature_count integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS runtime_datasets_region_kind_idx
    ON meta.runtime_datasets (region_id, dataset_kind);

CREATE TABLE IF NOT EXISTS runtime.region_catalogs (
    region_id text PRIMARY KEY REFERENCES runtime.regions (region_id),
    catalog_version text NOT NULL,
    catalog jsonb NOT NULL,
    validation_status text NOT NULL DEFAULT 'not_validated',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime.h3_display_cells (
    region_id text NOT NULL REFERENCES runtime.regions (region_id),
    h3_resolution smallint NOT NULL,
    hex_id text NOT NULL,
    dataset_id text REFERENCES meta.runtime_datasets (dataset_id),
    dataset_version text NOT NULL,
    source_status text NOT NULL,
    validation_status text NOT NULL DEFAULT 'not_validated',
    geom geometry(Geometry, 4326),
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (region_id, h3_resolution, hex_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS h3_display_cells_region_resolution_idx
    ON runtime.h3_display_cells (region_id, h3_resolution);

CREATE INDEX IF NOT EXISTS h3_display_cells_geom_gix
    ON runtime.h3_display_cells USING gist (geom);

CREATE TABLE IF NOT EXISTS runtime.landscape_cells (
    region_id text NOT NULL REFERENCES runtime.regions (region_id),
    h3_resolution smallint NOT NULL,
    hex_id text NOT NULL,
    dataset_id text REFERENCES meta.runtime_datasets (dataset_id),
    dataset_version text NOT NULL,
    landscape_type_id text,
    landscape_type_name text,
    class_km integer,
    source_status text NOT NULL,
    validation_status text NOT NULL DEFAULT 'not_validated',
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (region_id, h3_resolution, hex_id, dataset_version)
);

CREATE INDEX IF NOT EXISTS landscape_cells_region_resolution_idx
    ON runtime.landscape_cells (region_id, h3_resolution);

INSERT INTO meta.schema_migrations (
    migration_id, description
) VALUES (
    '002_runtime_catalog_contract',
    'Create SpeedLocal catalog, dataset, H3 display and landscape runtime contracts.'
)
ON CONFLICT (migration_id) DO NOTHING;
