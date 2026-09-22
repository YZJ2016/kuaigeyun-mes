"""人事 Excel 剩余：结算行扩展、岗位补贴、最低工资、产线分摊字段。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_payroll_settlement_lines"
            ADD COLUMN IF NOT EXISTS "heat_subsidy" NUMERIC(12,2) NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS "post_allowance" NUMERIC(12,2) NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS "compensation" NUMERIC(12,2) NOT NULL DEFAULT 0;

        ALTER TABLE "apps_kuaioa_payroll_settlements"
            ADD COLUMN IF NOT EXISTS "line_total_output" NUMERIC(14,2),
            ADD COLUMN IF NOT EXISTS "line_total_hours" NUMERIC(12,2),
            ADD COLUMN IF NOT EXISTS "line_total_wage" NUMERIC(14,2),
            ADD COLUMN IF NOT EXISTS "line_bonus_rate" NUMERIC(8,4) DEFAULT 0.01;

        CREATE TABLE IF NOT EXISTS "apps_kuaioa_post_subsidies" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "subsidy_code" VARCHAR(50) NOT NULL,
            "year_month" VARCHAR(7) NOT NULL,
            "employee_id" INT NOT NULL,
            "employee_code" VARCHAR(50),
            "employee_name" VARCHAR(100) NOT NULL,
            "workshop_name" VARCHAR(100),
            "item_name" VARCHAR(100) NOT NULL,
            "amount" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_post_subsidy_code"
            ON "apps_kuaioa_post_subsidies" ("tenant_id", "subsidy_code")
            WHERE "deleted_at" IS NULL;

        CREATE TABLE IF NOT EXISTS "apps_kuaioa_minimum_wage_configs" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "amount" NUMERIC(12,2) NOT NULL,
            "effective_date" DATE NOT NULL,
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_min_wage_tenant_eff"
            ON "apps_kuaioa_minimum_wage_configs" ("tenant_id", "effective_date");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaioa_minimum_wage_configs";
        DROP TABLE IF EXISTS "apps_kuaioa_post_subsidies";
        ALTER TABLE "apps_kuaioa_payroll_settlements"
            DROP COLUMN IF EXISTS "line_bonus_rate",
            DROP COLUMN IF EXISTS "line_total_wage",
            DROP COLUMN IF EXISTS "line_total_hours",
            DROP COLUMN IF EXISTS "line_total_output";
        ALTER TABLE "apps_kuaioa_payroll_settlement_lines"
            DROP COLUMN IF EXISTS "compensation",
            DROP COLUMN IF EXISTS "post_allowance",
            DROP COLUMN IF EXISTS "heat_subsidy";
    """
