"""采购订单：头表 price_type；明细行 tax_rate（%）；历史行从订单头税率回填。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            ADD COLUMN IF NOT EXISTS "price_type" VARCHAR(20) NOT NULL DEFAULT 'tax_inclusive';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_orders"."price_type"
            IS '价格类型：含税(tax_inclusive)/不含税(tax_exclusive)';

        ALTER TABLE "apps_kuaizhizao_purchase_order_items"
            ADD COLUMN IF NOT EXISTS "tax_rate" DECIMAL(6,2) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_order_items"."tax_rate"
            IS '税率（%，与销售订单行一致）';

        UPDATE "apps_kuaizhizao_purchase_order_items" AS i
        SET "tax_rate" = CASE
            WHEN o."tax_rate" IS NULL OR o."tax_rate" <= 0 THEN 0
            WHEN o."tax_rate" <= 1 THEN ROUND(o."tax_rate" * 100, 2)
            ELSE ROUND(o."tax_rate", 2)
        END
        FROM "apps_kuaizhizao_purchase_orders" AS o
        WHERE i."order_id" = o."id"
          AND (i."tax_rate" IS NULL OR i."tax_rate" = 0)
          AND o."tax_rate" IS NOT NULL
          AND o."tax_rate" > 0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_order_items" DROP COLUMN IF EXISTS "tax_rate";
        ALTER TABLE "apps_kuaizhizao_purchase_orders" DROP COLUMN IF EXISTS "price_type";
    """
