"""采购变更明细增加变更前/后副数量。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_order_change_items"
        ADD COLUMN IF NOT EXISTS "before_aux_quantity" DECIMAL(18,4) NULL;

        ALTER TABLE "apps_kuaizhizao_purchase_order_change_items"
        ADD COLUMN IF NOT EXISTS "after_aux_quantity" DECIMAL(18,4) NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_order_change_items"
        DROP COLUMN IF EXISTS "after_aux_quantity";

        ALTER TABLE "apps_kuaizhizao_purchase_order_change_items"
        DROP COLUMN IF EXISTS "before_aux_quantity";
    """