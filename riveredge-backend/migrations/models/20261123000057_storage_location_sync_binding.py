"""库位入站同步绑定表 + external_sync_at（上游 948 迁移的时间戳 remap 落位）。

含 schedule_window_start/end 列：20261123000035 对存量表做条件 ALTER，
本表在其后创建，需在建表语句中直接带上。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS "apps_master_data_storage_location_sync_binding" (
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
    "schedule_window_start" VARCHAR(5),
    "schedule_window_end" VARCHAR(5),
    "last_success_at" TIMESTAMPTZ,
    "last_attempt_at" TIMESTAMPTZ,
    "last_error" TEXT,
    "deleted_at" TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS "idx_storage_location_sync_binding_tenant"
    ON "apps_master_data_storage_location_sync_binding" ("tenant_id");

ALTER TABLE "apps_master_data_storage_locations"
    ADD COLUMN IF NOT EXISTS "external_sync_at" TIMESTAMPTZ;
COMMENT ON COLUMN "apps_master_data_storage_locations"."external_sync_at"
    IS '最近从外部接口/数据集同步时间';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_master_data_storage_locations"
    DROP COLUMN IF EXISTS "external_sync_at";
DROP TABLE IF EXISTS "apps_master_data_storage_location_sync_binding" CASCADE;
"""
