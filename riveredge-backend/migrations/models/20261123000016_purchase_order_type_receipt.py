"""采购入库 order_type；采购订单框架协议回填为标准采购。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "order_type" VARCHAR(20) NOT NULL DEFAULT '标准采购';

        UPDATE "apps_kuaizhizao_purchase_orders"
            SET "order_type" = '标准采购'
            WHERE "order_type" = '框架协议';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            DROP COLUMN IF EXISTS "order_type";
    """
