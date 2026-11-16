"""采购订单：付款方式/结算方式/付款周期/立账策略列（dd740a61e7 域回补）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            ADD COLUMN IF NOT EXISTS "payment_method_code" VARCHAR(50);
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_orders"."payment_method_code"
            IS '付款方式（现金/转账/承兑等）';
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            ADD COLUMN IF NOT EXISTS "settlement_terms_code" VARCHAR(50);
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_orders"."settlement_terms_code"
            IS '结算方式（预付/账期/货到付款等）';
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            ADD COLUMN IF NOT EXISTS "payment_terms_days" INT;
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_orders"."payment_terms_days"
            IS '付款周期（天），对齐供应商付款账期';
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_receipt';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_orders"."payable_recognition"
            IS '立账策略（应付确认时点，单据真源）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
            DROP COLUMN IF EXISTS "payment_method_code",
            DROP COLUMN IF EXISTS "settlement_terms_code",
            DROP COLUMN IF EXISTS "payment_terms_days",
            DROP COLUMN IF EXISTS "payable_recognition";
    """
