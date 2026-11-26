"""销售订单头增加结算方式，与客商 settlement_terms_code 同码表。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        ADD COLUMN IF NOT EXISTS "settlement_terms_code" VARCHAR(50);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        DROP COLUMN IF EXISTS "settlement_terms_code";
    """

# 对应上游 921_20261022193000_sales_order_settlement_terms.py
