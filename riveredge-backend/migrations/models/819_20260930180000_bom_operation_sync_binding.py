"""工程 BOM / 工序同步绑定表 + external_sync_at。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS "apps_master_data_engineering_bom_sync_binding" (
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "id" SERIAL NOT NULL PRIMARY KEY,
    "source_type" VARCHAR(20),
    "api_uuid" VARCHAR(36),
    "dataset_uuid" VARCHAR(36),
    "field_mapping" JSONB,
    "sources" JSONB,
    "match_key_field" VARCHAR(64) NOT NULL DEFAULT 'line_key',
    "sync_mode" VARCHAR(32) NOT NULL DEFAULT 'manual_full',
    "schedule_interval_minutes" INT NOT NULL DEFAULT 15,
    "last_success_at" TIMESTAMPTZ,
    "last_attempt_at" TIMESTAMPTZ,
    "last_error" TEXT,
    "deleted_at" TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS "idx_eng_bom_sync_binding_tenant"
    ON "apps_master_data_engineering_bom_sync_binding" ("tenant_id");

CREATE TABLE IF NOT EXISTS "apps_master_data_operation_sync_binding" (
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "id" SERIAL NOT NULL PRIMARY KEY,
    "source_type" VARCHAR(20),
    "api_uuid" VARCHAR(36),
    "dataset_uuid" VARCHAR(36),
    "field_mapping" JSONB,
    "sources" JSONB,
    "match_key_field" VARCHAR(64) NOT NULL DEFAULT 'code',
    "sync_mode" VARCHAR(32) NOT NULL DEFAULT 'manual_full',
    "schedule_interval_minutes" INT NOT NULL DEFAULT 15,
    "last_success_at" TIMESTAMPTZ,
    "last_attempt_at" TIMESTAMPTZ,
    "last_error" TEXT,
    "deleted_at" TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS "idx_operation_sync_binding_tenant"
    ON "apps_master_data_operation_sync_binding" ("tenant_id");

ALTER TABLE "apps_master_data_bom"
    ADD COLUMN IF NOT EXISTS "external_sync_at" TIMESTAMPTZ;
ALTER TABLE "apps_master_data_operations"
    ADD COLUMN IF NOT EXISTS "external_sync_at" TIMESTAMPTZ;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_master_data_operations" DROP COLUMN IF EXISTS "external_sync_at";
ALTER TABLE "apps_master_data_bom" DROP COLUMN IF EXISTS "external_sync_at";
DROP TABLE IF EXISTS "apps_master_data_operation_sync_binding" CASCADE;
DROP TABLE IF EXISTS "apps_master_data_engineering_bom_sync_binding" CASCADE;
"""
