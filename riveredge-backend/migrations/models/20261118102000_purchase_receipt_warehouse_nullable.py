"""
采购入库单表头仓库可空：服务采购不入库存，允许不填仓库。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ALTER COLUMN "warehouse_id" DROP NOT NULL;

        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ALTER COLUMN "warehouse_name" DROP NOT NULL;

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipts"."warehouse_id"
            IS '入库仓库ID（服务采购可空）';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipts"."warehouse_name"
            IS '入库仓库名称（服务采购可空）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_purchase_receipts"
        SET "warehouse_id" = 0
        WHERE "warehouse_id" IS NULL;

        UPDATE "apps_kuaizhizao_purchase_receipts"
        SET "warehouse_name" = ''
        WHERE "warehouse_name" IS NULL;

        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ALTER COLUMN "warehouse_id" SET NOT NULL;

        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ALTER COLUMN "warehouse_name" SET NOT NULL;
    """
