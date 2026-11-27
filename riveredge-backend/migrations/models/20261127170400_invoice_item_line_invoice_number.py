"""明细发票行：行级发票号码（购销对称）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_purchase_invoice_items"
        ADD COLUMN IF NOT EXISTS "invoice_number" VARCHAR(100) NULL;
        COMMENT ON COLUMN "apps_kuaicaiwu_purchase_invoice_items"."invoice_number"
            IS '行级发票号码（明细收票）';

        ALTER TABLE "apps_kuaicaiwu_invoice_items"
        ADD COLUMN IF NOT EXISTS "invoice_number" VARCHAR(100) NULL;
        COMMENT ON COLUMN "apps_kuaicaiwu_invoice_items"."invoice_number"
            IS '行级发票号码（明细开票）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_purchase_invoice_items"
        DROP COLUMN IF EXISTS "invoice_number";
        ALTER TABLE "apps_kuaicaiwu_invoice_items"
        DROP COLUMN IF EXISTS "invoice_number";
    """