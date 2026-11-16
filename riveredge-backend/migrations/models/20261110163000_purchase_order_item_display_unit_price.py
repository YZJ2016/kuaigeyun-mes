"""
采购订单明细：固化表单录入单价，编辑/详情只读展示禁止由未税单价反算含税单价。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_order_items"
            ADD COLUMN IF NOT EXISTS "display_unit_price" DECIMAL(12,4);

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_order_items"."display_unit_price"
            IS '录入单价（表单口径，只读展示）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_order_items" DROP COLUMN IF EXISTS "display_unit_price";
    """
