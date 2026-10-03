"""加班计划与临时调整：整厂/部门/人员适用范围。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_overtime_plans"
            ADD COLUMN IF NOT EXISTS "scope_type" VARCHAR(20) NOT NULL DEFAULT 'plant';
        ALTER TABLE "apps_master_data_overtime_plans"
            ADD COLUMN IF NOT EXISTS "department_id" INT;
        ALTER TABLE "apps_master_data_overtime_plans"
            ADD COLUMN IF NOT EXISTS "department_name" VARCHAR(200);
        ALTER TABLE "apps_master_data_overtime_plans"
            ADD COLUMN IF NOT EXISTS "employee_id" INT;
        ALTER TABLE "apps_master_data_overtime_plans"
            ADD COLUMN IF NOT EXISTS "employee_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_master_data_overtime_plans"."scope_type" IS '适用范围 plant/department/employee';

        ALTER TABLE "apps_master_data_roster_time_adjustments"
            ADD COLUMN IF NOT EXISTS "scope_type" VARCHAR(20) NOT NULL DEFAULT 'employee';
        ALTER TABLE "apps_master_data_roster_time_adjustments"
            ADD COLUMN IF NOT EXISTS "department_id" INT;
        ALTER TABLE "apps_master_data_roster_time_adjustments"
            ADD COLUMN IF NOT EXISTS "department_name" VARCHAR(200);
        ALTER TABLE "apps_master_data_roster_time_adjustments"
            ALTER COLUMN "employee_id" DROP NOT NULL;
        COMMENT ON COLUMN "apps_master_data_roster_time_adjustments"."scope_type" IS '适用范围 plant/department/employee';

        UPDATE "apps_master_data_overtime_plans"
            SET "scope_type" = 'plant'
            WHERE "scope_type" IS NULL OR TRIM("scope_type") = '';

        UPDATE "apps_master_data_roster_time_adjustments"
            SET "scope_type" = 'employee'
            WHERE "scope_type" IS NULL OR TRIM("scope_type") = '';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_roster_time_adjustments"
            DROP COLUMN IF EXISTS "department_name";
        ALTER TABLE "apps_master_data_roster_time_adjustments"
            DROP COLUMN IF EXISTS "department_id";
        ALTER TABLE "apps_master_data_roster_time_adjustments"
            DROP COLUMN IF EXISTS "scope_type";
        ALTER TABLE "apps_master_data_overtime_plans"
            DROP COLUMN IF EXISTS "employee_name";
        ALTER TABLE "apps_master_data_overtime_plans"
            DROP COLUMN IF EXISTS "employee_id";
        ALTER TABLE "apps_master_data_overtime_plans"
            DROP COLUMN IF EXISTS "department_name";
        ALTER TABLE "apps_master_data_overtime_plans"
            DROP COLUMN IF EXISTS "department_id";
        ALTER TABLE "apps_master_data_overtime_plans"
            DROP COLUMN IF EXISTS "scope_type";
    """
