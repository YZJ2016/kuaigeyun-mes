"""成品入库明细行挂来源工单（空白建单多工单）。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_finished_goods_receipt_items"
            ADD COLUMN IF NOT EXISTS "work_order_id" INT;
        ALTER TABLE "apps_kuaizhizao_finished_goods_receipt_items"
            ADD COLUMN IF NOT EXISTS "work_order_code" VARCHAR(50);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_finished_goods_receipt_items"
            DROP COLUMN IF EXISTS "work_order_code";
        ALTER TABLE "apps_kuaizhizao_finished_goods_receipt_items"
            DROP COLUMN IF EXISTS "work_order_id";
    """