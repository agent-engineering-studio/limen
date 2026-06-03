-- 004_raster_refs.sql
--
-- Raster references. PostGIS only stores metadata + bounding box; the raw
-- bytes live in the ObjectStore (filesystem/S3/Azure Blob). This keeps the
-- DB small and lets us move blobs between storages without touching SQL.

CREATE TABLE IF NOT EXISTS raster_refs (
    id              bigserial PRIMARY KEY,
    kind            text        NOT NULL,
    bucket          text,
    prefix          text,
    path            text        NOT NULL,
    bbox            geometry(Polygon, 4326) NOT NULL,
    crs             text        NOT NULL,
    checksum_sha256 text,
    size_bytes      bigint,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    dataset_version_id bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, path)
);

CREATE INDEX IF NOT EXISTS raster_refs_bbox_gix ON raster_refs USING GIST (bbox);
CREATE INDEX IF NOT EXISTS raster_refs_kind_idx ON raster_refs (kind);
