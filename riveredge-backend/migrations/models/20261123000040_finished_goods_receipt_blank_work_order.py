"""成品/半成品入库单工单字段可空（空白建单）。

上游同步：981_20261102170000_finished_goods_receipt_blank_work_order
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


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
