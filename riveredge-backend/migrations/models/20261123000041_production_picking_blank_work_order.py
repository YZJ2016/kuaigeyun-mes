"""生产领料单工单字段可空（空白建单）。

上游同步：982_20261102170500_production_picking_blank_work_order
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


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
