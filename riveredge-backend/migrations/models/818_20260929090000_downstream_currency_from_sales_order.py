"""发货通知/销售出库/销售退货继承销售订单币种与汇率。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_shipment_notices"
            ADD COLUMN IF NOT EXISTS "currency_code" VARCHAR(20) DEFAULT 'CNY',
            ADD COLUMN IF NOT EXISTS "exchange_rate" DECIMAL(8,4) NOT NULL DEFAULT 1;
        COMMENT ON COLUMN "apps_kuaizhizao_shipment_notices"."currency_code" IS '币种代码';
        COMMENT ON COLUMN "apps_kuaizhizao_shipment_notices"."exchange_rate" IS '汇率（相对本位币）';

        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
            ADD COLUMN IF NOT EXISTS "currency_code" VARCHAR(20) DEFAULT 'CNY',
            ADD COLUMN IF NOT EXISTS "exchange_rate" DECIMAL(8,4) NOT NULL DEFAULT 1;
        COMMENT ON COLUMN "apps_kuaizhizao_sales_deliveries"."currency_code" IS '币种代码';
        COMMENT ON COLUMN "apps_kuaizhizao_sales_deliveries"."exchange_rate" IS '汇率（相对本位币）';

        ALTER TABLE "apps_kuaizhizao_sales_returns"
            ADD COLUMN IF NOT EXISTS "currency_code" VARCHAR(20) DEFAULT 'CNY',
            ADD COLUMN IF NOT EXISTS "exchange_rate" DECIMAL(8,4) NOT NULL DEFAULT 1;
        COMMENT ON COLUMN "apps_kuaizhizao_sales_returns"."currency_code" IS '币种代码';
        COMMENT ON COLUMN "apps_kuaizhizao_sales_returns"."exchange_rate" IS '汇率（相对本位币）';

        -- 存量：按关联销售订单回填
        UPDATE "apps_kuaizhizao_shipment_notices" AS n
        SET
            currency_code = COALESCE(NULLIF(TRIM(o.currency_code), ''), 'CNY'),
            exchange_rate = COALESCE(NULLIF(o.exchange_rate, 0), 1)
        FROM "apps_kuaizhizao_sales_orders" AS o
        WHERE n.sales_order_id = o.id
          AND n.deleted_at IS NULL
          AND o.deleted_at IS NULL;

        UPDATE "apps_kuaizhizao_sales_deliveries" AS d
        SET
            currency_code = COALESCE(NULLIF(TRIM(o.currency_code), ''), 'CNY'),
            exchange_rate = COALESCE(NULLIF(o.exchange_rate, 0), 1)
        FROM "apps_kuaizhizao_sales_orders" AS o
        WHERE d.sales_order_id = o.id
          AND d.deleted_at IS NULL
          AND o.deleted_at IS NULL;

        UPDATE "apps_kuaizhizao_sales_returns" AS r
        SET
            currency_code = COALESCE(NULLIF(TRIM(o.currency_code), ''), 'CNY'),
            exchange_rate = COALESCE(NULLIF(o.exchange_rate, 0), 1)
        FROM "apps_kuaizhizao_sales_orders" AS o
        WHERE r.sales_order_id = o.id
          AND r.deleted_at IS NULL
          AND o.deleted_at IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_shipment_notices"
            DROP COLUMN IF EXISTS "currency_code",
            DROP COLUMN IF EXISTS "exchange_rate";
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
            DROP COLUMN IF EXISTS "currency_code",
            DROP COLUMN IF EXISTS "exchange_rate";
        ALTER TABLE "apps_kuaizhizao_sales_returns"
            DROP COLUMN IF EXISTS "currency_code",
            DROP COLUMN IF EXISTS "exchange_rate";
    """
