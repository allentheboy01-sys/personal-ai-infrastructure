BEGIN;

CREATE TABLE assets (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE blobs (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL,
    hash TEXT NOT NULL,
    size BIGINT,
    mime_type TEXT,

    CONSTRAINT fk_blobs_asset
        FOREIGN KEY (asset_id)
        REFERENCES assets(id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_blobs_asset_hash
        UNIQUE (asset_id, hash)
);

CREATE INDEX ix_blobs_hash
    ON blobs(hash);

CREATE TABLE asset_sources (
    id UUID PRIMARY KEY,
    blob_id UUID NOT NULL,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    path TEXT,
    name TEXT,
    version_tag TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT fk_asset_sources_blob
        FOREIGN KEY (blob_id)
        REFERENCES blobs(id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_asset_sources_provider_external_id
        UNIQUE (provider, external_id)
);

COMMIT;