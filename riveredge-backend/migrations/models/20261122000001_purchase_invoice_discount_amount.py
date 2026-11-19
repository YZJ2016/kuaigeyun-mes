from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_purchase_invoices"
        ADD COLUMN IF NOT EXISTS "discount_amount" NUMERIC(14,4) NOT NULL DEFAULT 0;
        ALTER TABLE "apps_kuaicaiwu_purchase_invoices"
        ADD COLUMN IF NOT EXISTS "adjust_payable" BOOLEAN NOT NULL DEFAULT FALSE;
        COMMENT ON COLUMN "apps_kuaicaiwu_purchase_invoices"."discount_amount" IS '收票优惠金额(含税,可正可负)';
        COMMENT ON COLUMN "apps_kuaicaiwu_purchase_invoices"."adjust_payable" IS '从应付收票时是否生成优惠调整应付';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_purchase_invoices" DROP COLUMN IF EXISTS "adjust_payable";
        ALTER TABLE "apps_kuaicaiwu_purchase_invoices" DROP COLUMN IF EXISTS "discount_amount";
    """
