"""
生产领料明细出库仓库可空：批量下推可先生成单据，再在领料单中按行维护仓库。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_production_picking_items"
            ALTER COLUMN "warehouse_id" DROP NOT NULL;

        ALTER TABLE "apps_kuaizhizao_production_picking_items"
            ALTER COLUMN "warehouse_name" DROP NOT NULL;

        COMMENT ON COLUMN "apps_kuaizhizao_production_picking_items"."warehouse_id"
            IS '仓库ID（下推时可空，确认出库前须按行指定）';
        COMMENT ON COLUMN "apps_kuaizhizao_production_picking_items"."warehouse_name"
            IS '仓库名称（下推时可空，确认出库前须按行指定）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_production_picking_items"
        SET "warehouse_id" = 0
        WHERE "warehouse_id" IS NULL;

        UPDATE "apps_kuaizhizao_production_picking_items"
        SET "warehouse_name" = ''
        WHERE "warehouse_name" IS NULL;

        ALTER TABLE "apps_kuaizhizao_production_picking_items"
            ALTER COLUMN "warehouse_id" SET NOT NULL;

        ALTER TABLE "apps_kuaizhizao_production_picking_items"
            ALTER COLUMN "warehouse_name" SET NOT NULL;
    """
