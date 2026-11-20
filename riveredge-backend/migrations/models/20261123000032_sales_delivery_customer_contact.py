"""销售出库单表头增加客户联系人、电话，对齐销售订单/发货通知。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
        ADD COLUMN IF NOT EXISTS "customer_contact" VARCHAR(100);
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
        ADD COLUMN IF NOT EXISTS "customer_phone" VARCHAR(50);
        COMMENT ON COLUMN "apps_kuaizhizao_sales_deliveries"."customer_contact" IS '客户联系人';
        COMMENT ON COLUMN "apps_kuaizhizao_sales_deliveries"."customer_phone" IS '客户电话';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
        DROP COLUMN IF EXISTS "customer_contact";
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
        DROP COLUMN IF EXISTS "customer_phone";
    """