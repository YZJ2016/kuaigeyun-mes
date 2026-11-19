"""采购入库单出站绑定表 apps_kuaizhizao_purchase_receipt_sync_binding（上游 935+936 合并落位）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_purchase_receipt_sync_binding" (
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
            "push_targets" JSONB,
            "trigger_actions" JSONB,
            "match_key_field" VARCHAR(64) NOT NULL DEFAULT 'receipt_code',
            "sync_mode" VARCHAR(32) NOT NULL DEFAULT 'manual_full',
            "sync_direction" VARCHAR(20) NOT NULL DEFAULT 'push',
            "schedule_interval_minutes" INT NOT NULL DEFAULT 15,
            "last_success_at" TIMESTAMPTZ,
            "last_attempt_at" TIMESTAMPTZ,
            "last_error" TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "ux_kuaizhizao_pr_sync_bind_tenant"
            ON "apps_kuaizhizao_purchase_receipt_sync_binding" ("tenant_id");
        COMMENT ON TABLE "apps_kuaizhizao_purchase_receipt_sync_binding"
            IS '快格轻制造 - 采购入库单同步/出站绑定';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaizhizao_purchase_receipt_sync_binding" CASCADE;
    """
