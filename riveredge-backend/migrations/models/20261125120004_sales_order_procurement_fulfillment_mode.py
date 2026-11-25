"""
销售订单采购履单路径：请购轨 purchase_requisition 与直采轨 purchase_order 二选一。
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        ADD COLUMN IF NOT EXISTS "procurement_fulfillment_mode" VARCHAR(32);
        COMMENT ON COLUMN "apps_kuaizhizao_sales_orders"."procurement_fulfillment_mode"
        IS '销售订单外购履单路径：purchase_requisition|purchase_order，首张采购下游落库后锁定';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        DROP COLUMN IF EXISTS "procurement_fulfillment_mode";
    """