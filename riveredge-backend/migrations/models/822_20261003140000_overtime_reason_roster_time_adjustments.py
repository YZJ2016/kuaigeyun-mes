"""厂级加班原因 + 员工临时加班/休息调整表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_overtime_plans"
            ADD COLUMN IF NOT EXISTS "reason" VARCHAR(500);
        COMMENT ON COLUMN "apps_master_data_overtime_plans"."reason" IS '加班原因';

        CREATE TABLE IF NOT EXISTS "apps_master_data_roster_time_adjustments" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "employee_id" INT NOT NULL,
            "employee_name" VARCHAR(100),
            "work_date" DATE NOT NULL,
            "kind" VARCHAR(20) NOT NULL,
            "start_time" TIME NOT NULL,
            "end_time" TIME NOT NULL,
            "reason" VARCHAR(500) NOT NULL,
            "is_active" BOOL NOT NULL DEFAULT TRUE,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_rta_tenant"
            ON "apps_master_data_roster_time_adjustments" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_rta_employee_date"
            ON "apps_master_data_roster_time_adjustments" ("tenant_id", "employee_id", "work_date");
        CREATE INDEX IF NOT EXISTS "idx_rta_work_date"
            ON "apps_master_data_roster_time_adjustments" ("tenant_id", "work_date");
        COMMENT ON TABLE "apps_master_data_roster_time_adjustments" IS '基础数据管理 - 排班临时加班/休息';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_master_data_roster_time_adjustments";
        ALTER TABLE "apps_master_data_overtime_plans" DROP COLUMN IF EXISTS "reason";
    """
