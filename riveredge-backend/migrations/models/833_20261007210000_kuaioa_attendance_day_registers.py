"""休息 / 夜班登记记录表。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaioa_attendance_day_registers" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "register_code" VARCHAR(50) NOT NULL,
            "register_type" VARCHAR(20) NOT NULL,
            "date_from" DATE NOT NULL,
            "date_to" DATE NOT NULL,
            "workshop_name" VARCHAR(100) NOT NULL,
            "production_line_name" VARCHAR(100),
            "employee_ids" JSONB NOT NULL DEFAULT '[]'::jsonb,
            "employee_summary" VARCHAR(500),
            "marked_cell_count" INT NOT NULL DEFAULT 0,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_att_day_reg_tenant_code"
            ON "apps_kuaioa_attendance_day_registers" ("tenant_id", "register_code");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_att_day_reg_tenant_type"
            ON "apps_kuaioa_attendance_day_registers" ("tenant_id", "register_type");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_att_day_reg_tenant_from"
            ON "apps_kuaioa_attendance_day_registers" ("tenant_id", "date_from");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_att_day_reg_tenant_ws"
            ON "apps_kuaioa_attendance_day_registers" ("tenant_id", "workshop_name");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaioa_attendance_day_registers";
    """
