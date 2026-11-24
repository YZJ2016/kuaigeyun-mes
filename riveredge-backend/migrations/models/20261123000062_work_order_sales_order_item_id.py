"""工单增加 sales_order_item_id，销售订单同料多行按行统计已转工单。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_work_orders"
        ADD COLUMN IF NOT EXISTS "sales_order_item_id" INT;

        CREATE INDEX IF NOT EXISTS "idx_work_orders_tenant_so_item"
        ON "apps_kuaizhizao_work_orders" ("tenant_id", "sales_order_item_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_work_orders_tenant_so_item";
        ALTER TABLE "apps_kuaizhizao_work_orders"
        DROP COLUMN IF EXISTS "sales_order_item_id";
    """