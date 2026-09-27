"""
销售订单表增加 exchange_rate（相对本位币单据锁定汇率），存量回填 1。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
            ADD COLUMN IF NOT EXISTS "exchange_rate" DECIMAL(8,4) NOT NULL DEFAULT 1;
        COMMENT ON COLUMN "apps_kuaizhizao_sales_orders"."exchange_rate" IS '汇率（相对本位币）';
        UPDATE "apps_kuaizhizao_sales_orders"
            SET "exchange_rate" = 1
            WHERE "exchange_rate" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders" DROP COLUMN IF EXISTS "exchange_rate";
    """
