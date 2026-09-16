"""轻办公节日福利发放表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaioa_welfare_batches" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "batch_code" VARCHAR(50) NOT NULL,
            "year" INT NOT NULL,
            "festival_type" VARCHAR(30) NOT NULL,
            "workshop_name" VARCHAR(100) NOT NULL,
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
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_welfare_batch_code"
            ON "apps_kuaioa_welfare_batches" ("tenant_id", "batch_code")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_welfare_batch_yf"
            ON "apps_kuaioa_welfare_batches" ("tenant_id", "year", "festival_type");

        CREATE TABLE IF NOT EXISTS "apps_kuaioa_welfare_batch_lines" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "batch_id" INT NOT NULL,
            "employee_id" INT NOT NULL,
            "employee_code" VARCHAR(50),
            "employee_name" VARCHAR(100) NOT NULL,
            "workshop_name" VARCHAR(100),
            "standard_amount" NUMERIC(12,2),
            "amount" NUMERIC(12,2) NOT NULL DEFAULT 0,
            "received" BOOLEAN NOT NULL DEFAULT FALSE,
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaioa_welfare_line_emp"
            ON "apps_kuaioa_welfare_batch_lines" ("tenant_id", "batch_id", "employee_id")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaioa_welfare_line_batch"
            ON "apps_kuaioa_welfare_batch_lines" ("tenant_id", "batch_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaioa_welfare_batch_lines";
        DROP TABLE IF EXISTS "apps_kuaioa_welfare_batches";
    """
