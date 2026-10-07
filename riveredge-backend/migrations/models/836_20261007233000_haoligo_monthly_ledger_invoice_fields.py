"""月度工厂台账：本月开票明细、发票号。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haolisales_monthly_factory_ledger"
            ADD COLUMN IF NOT EXISTS "monthly_invoice_qty" NUMERIC(18,4);

        ALTER TABLE "haolisales_monthly_factory_ledger"
            ADD COLUMN IF NOT EXISTS "invoice_no" VARCHAR(100);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haolisales_monthly_factory_ledger"
            DROP COLUMN IF EXISTS "invoice_no";

        ALTER TABLE "haolisales_monthly_factory_ledger"
            DROP COLUMN IF EXISTS "monthly_invoice_qty";
    """
