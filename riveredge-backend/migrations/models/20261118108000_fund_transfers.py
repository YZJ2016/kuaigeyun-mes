"""快财务资金调拨单表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_fund_transfers" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "transfer_code" VARCHAR(50) NOT NULL,
            "transfer_date" DATE NOT NULL,
            "transfer_type" VARCHAR(20) NOT NULL,
            "from_bank_account_id" INT,
            "to_bank_account_id" INT,
            "external_account_name" VARCHAR(200),
            "external_bank_name" VARCHAR(200),
            "external_account_number" VARCHAR(64),
            "amount" NUMERIC(16,4) NOT NULL,
            "currency" VARCHAR(10) NOT NULL DEFAULT 'CNY',
            "status" VARCHAR(20) NOT NULL DEFAULT 'Draft',
            "notes" TEXT,
            "attachments" JSONB,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "deleted_by" INT,
            "deleted_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_kuaicaiwu_fund_transfers_tenant_date"
            ON "apps_kuaicaiwu_fund_transfers" ("tenant_id", "transfer_date");
        CREATE INDEX IF NOT EXISTS "idx_kuaicaiwu_fund_transfers_tenant_status"
            ON "apps_kuaicaiwu_fund_transfers" ("tenant_id", "status");
        CREATE INDEX IF NOT EXISTS "idx_kuaicaiwu_fund_transfers_tenant_type"
            ON "apps_kuaicaiwu_fund_transfers" ("tenant_id", "transfer_type");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaicaiwu_fund_transfers_code"
            ON "apps_kuaicaiwu_fund_transfers" ("tenant_id", "transfer_code")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaicaiwu_fund_transfers";
    """
