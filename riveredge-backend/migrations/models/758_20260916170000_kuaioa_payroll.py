"""轻办公薪酬相关表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaioa_living_advances" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "advance_code" VARCHAR(50) NOT NULL,
            "year_month" VARCHAR(7) NOT NULL,
            "employee_id" INT NOT NULL,
            "employee_code" VARCHAR(50),
            "employee_name" VARCHAR(100) NOT NULL,
            "workshop_name" VARCHAR(100),
            "base_living" NUMERIC(12,2),
            "amount" NUMERIC(12,2) NOT NULL,
            "reason" VARCHAR(200),
            "status" VARCHAR(20) NOT NULL DEFAULT 'confirmed',
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_living_adv_code"
            ON "apps_kuaioa_living_advances" ("tenant_id", "advance_code")
            WHERE "deleted_at" IS NULL;

        CREATE TABLE IF NOT EXISTS "apps_kuaioa_reward_records" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "reward_code" VARCHAR(50) NOT NULL,
            "year_month" VARCHAR(7) NOT NULL,
            "employee_id" INT NOT NULL,
            "employee_code" VARCHAR(50),
            "employee_name" VARCHAR(100) NOT NULL,
            "workshop_name" VARCHAR(100),
            "amount" NUMERIC(12,2) NOT NULL,
            "reason" VARCHAR(200),
            "status" VARCHAR(20) NOT NULL DEFAULT 'confirmed',
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_reward_code"
            ON "apps_kuaioa_reward_records" ("tenant_id", "reward_code")
            WHERE "deleted_at" IS NULL;

        CREATE TABLE IF NOT EXISTS "apps_kuaioa_payroll_settlements" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "settlement_code" VARCHAR(50) NOT NULL,
            "year_month" VARCHAR(7) NOT NULL,
            "workshop_name" VARCHAR(100) NOT NULL,
            "ot_multiplier" NUMERIC(6,2) NOT NULL DEFAULT 3,
            "status" VARCHAR(20) NOT NULL DEFAULT 'draft',
            "confirmed_at" TIMESTAMPTZ,
            "confirmed_by" INT,
            "confirmed_by_name" VARCHAR(100),
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_payroll_code"
            ON "apps_kuaioa_payroll_settlements" ("tenant_id", "settlement_code")
            WHERE "deleted_at" IS NULL;

        CREATE TABLE IF NOT EXISTS "apps_kuaioa_payroll_settlement_lines" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "settlement_id" INT NOT NULL,
            "employee_id" INT NOT NULL,
            "employee_code" VARCHAR(50),
            "employee_name" VARCHAR(100) NOT NULL,
            "bank_name" VARCHAR(100),
            "bank_account" VARCHAR(50),
            "basic_wage" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "post_wage" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "time_wage" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "piece_wage" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "night_subsidy" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "allowance" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "earning_subtotal" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "living_deduct" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "insurance_deduct" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "leave_deduct" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "tax_deduct" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "deduct_subtotal" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "card_pay" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "balance" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "regular_hours" NUMERIC(10,2),
            "ot_hours" NUMERIC(10,2),
            "night_count" INT,
            "hourly_rate" NUMERIC(12,4),
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_payroll_line"
            ON "apps_kuaioa_payroll_settlement_lines"
            ("tenant_id", "settlement_id", "employee_id")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaioa_payroll_settlement_lines";
        DROP TABLE IF EXISTS "apps_kuaioa_payroll_settlements";
        DROP TABLE IF EXISTS "apps_kuaioa_reward_records";
        DROP TABLE IF EXISTS "apps_kuaioa_living_advances";
    """
