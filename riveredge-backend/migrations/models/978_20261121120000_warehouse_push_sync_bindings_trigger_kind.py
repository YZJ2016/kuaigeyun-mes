"""成品入库/生产领料/销售出库出站绑表（上游 961+979 合并）+ core_sync_run_logs.trigger_kind（上游 984）。

977 已按 to_regclass 守卫尝试补 schedule_window_*（当时表未建未生效），此处建表即带上。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_finished_goods_receipt_sync_binding" (
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
            "schedule_window_start" VARCHAR(5),
            "schedule_window_end" VARCHAR(5),
            "last_success_at" TIMESTAMPTZ,
            "last_attempt_at" TIMESTAMPTZ,
            "last_error" TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "ux_kuaizhizao_fg_receipt_sync_bind_tenant"
            ON "apps_kuaizhizao_finished_goods_receipt_sync_binding" ("tenant_id");
        COMMENT ON TABLE "apps_kuaizhizao_finished_goods_receipt_sync_binding"
            IS '快格轻制造 - 成品入库单同步/出站绑定';

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_production_picking_sync_binding" (
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
            "match_key_field" VARCHAR(64) NOT NULL DEFAULT 'picking_code',
            "sync_mode" VARCHAR(32) NOT NULL DEFAULT 'manual_full',
            "sync_direction" VARCHAR(20) NOT NULL DEFAULT 'push',
            "schedule_interval_minutes" INT NOT NULL DEFAULT 15,
            "schedule_window_start" VARCHAR(5),
            "schedule_window_end" VARCHAR(5),
            "last_success_at" TIMESTAMPTZ,
            "last_attempt_at" TIMESTAMPTZ,
            "last_error" TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "ux_kuaizhizao_pp_sync_bind_tenant"
            ON "apps_kuaizhizao_production_picking_sync_binding" ("tenant_id");
        COMMENT ON TABLE "apps_kuaizhizao_production_picking_sync_binding"
            IS '快格轻制造 - 生产领料单同步/出站绑定';

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_sales_delivery_sync_binding" (
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
            "match_key_field" VARCHAR(64) NOT NULL DEFAULT 'delivery_code',
            "sync_mode" VARCHAR(32) NOT NULL DEFAULT 'manual_full',
            "sync_direction" VARCHAR(20) NOT NULL DEFAULT 'push',
            "schedule_interval_minutes" INT NOT NULL DEFAULT 15,
            "schedule_window_start" VARCHAR(5),
            "schedule_window_end" VARCHAR(5),
            "last_success_at" TIMESTAMPTZ,
            "last_attempt_at" TIMESTAMPTZ,
            "last_error" TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "ux_kuaizhizao_sd_sync_bind_tenant"
            ON "apps_kuaizhizao_sales_delivery_sync_binding" ("tenant_id");
        COMMENT ON TABLE "apps_kuaizhizao_sales_delivery_sync_binding"
            IS '快格轻制造 - 销售出库单同步/出站绑定';

        ALTER TABLE "core_sync_run_logs"
            ADD COLUMN IF NOT EXISTS "trigger_kind" VARCHAR(20) NOT NULL DEFAULT 'manual';
        COMMENT ON COLUMN "core_sync_run_logs"."trigger_kind" IS '触发方式：manual 手动 / trigger 链式触发 / scheduled 定时';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_sync_run_logs" DROP COLUMN IF EXISTS "trigger_kind";
        DROP TABLE IF EXISTS "apps_kuaizhizao_sales_delivery_sync_binding" CASCADE;
        DROP TABLE IF EXISTS "apps_kuaizhizao_production_picking_sync_binding" CASCADE;
        DROP TABLE IF EXISTS "apps_kuaizhizao_finished_goods_receipt_sync_binding" CASCADE;
    """
