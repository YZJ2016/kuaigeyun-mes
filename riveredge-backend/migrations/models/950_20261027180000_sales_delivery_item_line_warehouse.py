"""
销售出库明细增加行级出库仓库（对齐金蝶 im_saloutbill 分录）；
既有行从单据表头回填，库位仍用 location_id/location_code。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_delivery_items" ADD COLUMN IF NOT EXISTS "warehouse_id" INT;
        ALTER TABLE "apps_kuaizhizao_sales_delivery_items" ADD COLUMN IF NOT EXISTS "warehouse_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_kuaizhizao_sales_delivery_items"."warehouse_id" IS '行出库仓库ID（可与表头不同）';
        COMMENT ON COLUMN "apps_kuaizhizao_sales_delivery_items"."warehouse_name" IS '行出库仓库名称';
        CREATE INDEX IF NOT EXISTS "idx_apps_kuaizhizao_sdi_warehouse" ON "apps_kuaizhizao_sales_delivery_items" ("warehouse_id");
        UPDATE "apps_kuaizhizao_sales_delivery_items" AS i
        SET
            warehouse_id = d.warehouse_id,
            warehouse_name = d.warehouse_name
        FROM "apps_kuaizhizao_sales_deliveries" AS d
        WHERE i.delivery_id = d.id
          AND i.tenant_id = d.tenant_id
          AND i.warehouse_id IS NULL
          AND d.warehouse_id IS NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_apps_kuaizhizao_sdi_warehouse";
        ALTER TABLE "apps_kuaizhizao_sales_delivery_items" DROP COLUMN IF EXISTS "warehouse_name";
        ALTER TABLE "apps_kuaizhizao_sales_delivery_items" DROP COLUMN IF EXISTS "warehouse_id";
    """
