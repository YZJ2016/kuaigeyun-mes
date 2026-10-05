"""
继电器行业包：自动报工配置 / 设备绑定 / 运行日志。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_ind_relay_auto_report_configs" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "deleted_by" INT,
            "deleted_by_name" VARCHAR(100),
            "is_enabled" BOOL NOT NULL DEFAULT False,
            "match_by_device" BOOL NOT NULL DEFAULT False,
            "interval_minutes" INT NOT NULL DEFAULT 5,
            "report_mode" VARCHAR(40) NOT NULL DEFAULT 'REALTIME_INCREMENT',
            "offline_threshold_seconds" INT NOT NULL DEFAULT 180,
            "reporter_user_id" INT,
            "reporter_user_name" VARCHAR(100),
            "remarks" TEXT,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_cfg_tenant"
            ON "apps_ind_relay_auto_report_configs" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_cfg_uuid"
            ON "apps_ind_relay_auto_report_configs" ("uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_ind_relay_ar_cfg_active"
            ON "apps_ind_relay_auto_report_configs" ("tenant_id")
            WHERE "deleted_at" IS NULL;
        COMMENT ON TABLE "apps_ind_relay_auto_report_configs" IS '继电器行业 - 自动报工配置';

        CREATE TABLE IF NOT EXISTS "apps_ind_relay_auto_report_bindings" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "deleted_by" INT,
            "deleted_by_name" VARCHAR(100),
            "iot_device_id" INT NOT NULL,
            "iot_device_uuid" VARCHAR(36),
            "iot_device_code" VARCHAR(50),
            "iot_device_name" VARCHAR(100),
            "external_device_id" VARCHAR(100),
            "equipment_uuid" VARCHAR(36) NOT NULL,
            "equipment_id" INT,
            "equipment_code" VARCHAR(50),
            "equipment_name" VARCHAR(100),
            "is_enabled" BOOL NOT NULL DEFAULT True,
            "last_zscl" NUMERIC(18,6),
            "pending_quantity" NUMERIC(18,6) NOT NULL DEFAULT 0,
            "baseline_aligned" BOOL NOT NULL DEFAULT False,
            "bound_work_order_id" INT,
            "bound_work_order_code" VARCHAR(50),
            "bound_operation_id" INT,
            "bound_operation_name" VARCHAR(200),
            "last_settle_at" TIMESTAMPTZ,
            "last_seen_at" TIMESTAMPTZ,
            "offline_flushed" BOOL NOT NULL DEFAULT False,
            "remarks" TEXT,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_bind_tenant"
            ON "apps_ind_relay_auto_report_bindings" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_bind_iot"
            ON "apps_ind_relay_auto_report_bindings" ("iot_device_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_bind_eq"
            ON "apps_ind_relay_auto_report_bindings" ("equipment_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_bind_uuid"
            ON "apps_ind_relay_auto_report_bindings" ("uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_ind_relay_ar_bind_active"
            ON "apps_ind_relay_auto_report_bindings" ("tenant_id", "iot_device_id")
            WHERE "deleted_at" IS NULL;
        COMMENT ON TABLE "apps_ind_relay_auto_report_bindings" IS '继电器行业 - 自动报工设备绑定';

        CREATE TABLE IF NOT EXISTS "apps_ind_relay_auto_report_logs" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "deleted_by" INT,
            "deleted_by_name" VARCHAR(100),
            "binding_id" INT,
            "iot_device_id" INT,
            "level" VARCHAR(20) NOT NULL DEFAULT 'info',
            "event" VARCHAR(50) NOT NULL,
            "message" TEXT,
            "zscl" NUMERIC(18,6),
            "increment_qty" NUMERIC(18,6),
            "work_order_id" INT,
            "work_order_code" VARCHAR(50),
            "operation_id" INT,
            "reporting_record_id" INT,
            "extra" JSONB,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_log_tenant_created"
            ON "apps_ind_relay_auto_report_logs" ("tenant_id", "created_at");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_log_binding"
            ON "apps_ind_relay_auto_report_logs" ("binding_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_ar_log_uuid"
            ON "apps_ind_relay_auto_report_logs" ("uuid");
        COMMENT ON TABLE "apps_ind_relay_auto_report_logs" IS '继电器行业 - 自动报工日志';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_ind_relay_auto_report_logs";
        DROP TABLE IF EXISTS "apps_ind_relay_auto_report_bindings";
        DROP TABLE IF EXISTS "apps_ind_relay_auto_report_configs";
    """
