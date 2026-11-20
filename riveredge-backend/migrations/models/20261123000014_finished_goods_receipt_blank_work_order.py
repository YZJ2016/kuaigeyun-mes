"""成品/半成品入库：空白建单时工单可空（与采购入库无来源订单对齐）。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_finished_goods_receipts"
            ALTER COLUMN "work_order_id" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_semi_finished_goods_receipts"
            ALTER COLUMN "work_order_id" DROP NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_finished_goods_receipts"
            ALTER COLUMN "work_order_id" SET NOT NULL;
        ALTER TABLE "apps_kuaizhizao_semi_finished_goods_receipts"
            ALTER COLUMN "work_order_id" SET NOT NULL;
    """
