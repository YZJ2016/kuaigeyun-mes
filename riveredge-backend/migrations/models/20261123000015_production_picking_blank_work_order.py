"""生产领料：空白建单时表头工单可空（与销售出库无来源订单对齐）。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_production_pickings"
            ALTER COLUMN "work_order_id" DROP NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_production_pickings"
            ALTER COLUMN "work_order_id" SET NOT NULL;
    """
