"""轻办公员工档案表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaioa_employee_profiles" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "employee_code" VARCHAR(50) NOT NULL,
            "full_name" VARCHAR(100) NOT NULL,
            "phone" VARCHAR(30),
            "workshop_name" VARCHAR(100),
            "production_line_name" VARCHAR(100),
            "employment_type" VARCHAR(20) NOT NULL DEFAULT 'formal',
            "pay_method" VARCHAR(20) NOT NULL DEFAULT 'time',
            "hourly_rate" NUMERIC(12,4),
            "hire_date" DATE,
            "leave_date" DATE,
            "bank_account" VARCHAR(50),
            "bank_name" VARCHAR(100),
            "bank_branch" VARCHAR(200),
            "living_allowance" NUMERIC(12,2),
            "post_wage" NUMERIC(12,2),
            "social_insurance" NUMERIC(12,2),
            "housing_fund" NUMERIC(12,2),
            "welfare_dragon_boat" NUMERIC(12,2),
            "welfare_mid_autumn" NUMERIC(12,2),
            "welfare_spring_festival" NUMERIC(12,2),
            "user_id" INT,
            "department_name" VARCHAR(100),
            "status" VARCHAR(20) NOT NULL DEFAULT 'active',
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_employee_code"
            ON "apps_kuaioa_employee_profiles" ("tenant_id", "employee_code")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_employee_status"
            ON "apps_kuaioa_employee_profiles" ("tenant_id", "status");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_employee_workshop"
            ON "apps_kuaioa_employee_profiles" ("tenant_id", "workshop_name");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_employee_type"
            ON "apps_kuaioa_employee_profiles" ("tenant_id", "employment_type");
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_employee_user"
            ON "apps_kuaioa_employee_profiles" ("tenant_id", "user_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaioa_employee_profiles";
    """
