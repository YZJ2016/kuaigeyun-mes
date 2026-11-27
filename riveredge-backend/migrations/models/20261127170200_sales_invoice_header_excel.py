"""销项发票：结账日、部门、立账方式（对称采购发票表头）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_invoices"
        ADD COLUMN IF NOT EXISTS "settlement_closing_date" DATE NULL;
        ALTER TABLE "apps_kuaicaiwu_invoices"
        ADD COLUMN IF NOT EXISTS "department_id" INT NULL;
        ALTER TABLE "apps_kuaicaiwu_invoices"
        ADD COLUMN IF NOT EXISTS "department_name" VARCHAR(200) NULL;
        ALTER TABLE "apps_kuaicaiwu_invoices"
        ADD COLUMN IF NOT EXISTS "ledger_posting_mode" VARCHAR(16) NULL;
        COMMENT ON COLUMN "apps_kuaicaiwu_invoices"."settlement_closing_date" IS '结账日期';
        COMMENT ON COLUMN "apps_kuaicaiwu_invoices"."ledger_posting_mode" IS '立账方式 immediate 或 by_invoice';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_invoices"
        DROP COLUMN IF EXISTS "settlement_closing_date";
        ALTER TABLE "apps_kuaicaiwu_invoices"
        DROP COLUMN IF EXISTS "department_id";
        ALTER TABLE "apps_kuaicaiwu_invoices"
        DROP COLUMN IF EXISTS "department_name";
        ALTER TABLE "apps_kuaicaiwu_invoices"
        DROP COLUMN IF EXISTS "ledger_posting_mode";
    """