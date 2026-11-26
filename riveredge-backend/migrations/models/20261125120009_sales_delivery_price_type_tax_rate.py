"""
销售出库头价类与明细行税率，与销售订单价税字段对齐。
历史行税率记 0，不按配置猜测。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
            ADD COLUMN IF NOT EXISTS "price_type" VARCHAR(20) NOT NULL DEFAULT 'tax_inclusive';
        COMMENT ON COLUMN "apps_kuaizhizao_sales_deliveries"."price_type"
            IS '价格类型：含税(tax_inclusive)/不含税(tax_exclusive)';

        ALTER TABLE "apps_kuaizhizao_sales_delivery_items"
            ADD COLUMN IF NOT EXISTS "tax_rate" DECIMAL(6,2) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_kuaizhizao_sales_delivery_items"."tax_rate"
            IS '税率（%）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_delivery_items" DROP COLUMN IF EXISTS "tax_rate";
        ALTER TABLE "apps_kuaizhizao_sales_deliveries" DROP COLUMN IF EXISTS "price_type";
    """
