from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS core_mobile_submissions (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    operation_key VARCHAR(128) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    method VARCHAR(8) NOT NULL,
    path VARCHAR(512) NOT NULL,
    response_body TEXT,
    response_status INTEGER NOT NULL DEFAULT 200,
    entity_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    created_by_name VARCHAR(100),
    updated_by INTEGER,
    updated_by_name VARCHAR(100),
    UNIQUE (tenant_id, user_id, operation_key)
);
CREATE INDEX IF NOT EXISTS idx_mobile_submission_tenant ON core_mobile_submissions (tenant_id);
CREATE TABLE IF NOT EXISTS core_mobile_submission_effects (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL,
    tenant_id INTEGER NOT NULL,
    submission_id INTEGER NOT NULL REFERENCES core_mobile_submissions(id),
    effect_type VARCHAR(64) NOT NULL,
    entity_id INTEGER NOT NULL,
    acting_user_id INTEGER NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    last_error_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    created_by_name VARCHAR(100),
    updated_by INTEGER,
    updated_by_name VARCHAR(100),
    UNIQUE (tenant_id, submission_id, effect_type, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_mobile_effect_due ON core_mobile_submission_effects (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_mobile_effect_tenant ON core_mobile_submission_effects (tenant_id);
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS core_mobile_submission_effects;
DROP TABLE IF EXISTS core_mobile_submissions;
"""
