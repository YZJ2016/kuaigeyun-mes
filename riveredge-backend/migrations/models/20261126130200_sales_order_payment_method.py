"""销售订单头增加付款方式，与付款周期（原付款条件）并列。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        ADD COLUMN IF NOT EXISTS "payment_method_code" VARCHAR(50);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        DROP COLUMN IF EXISTS "payment_method_code";
    """

# 对应上游 920_20261022192000_sales_order_payment_method.py
