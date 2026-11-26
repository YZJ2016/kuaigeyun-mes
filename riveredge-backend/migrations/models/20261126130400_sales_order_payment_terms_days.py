"""销售订单付款周期改为天数，对齐客商 payment_terms_days。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        ADD COLUMN IF NOT EXISTS "payment_terms_days" INT;

        -- 历史 PAYMENT_TERMS：NET30 / CREDIT_60 / 纯数字 → 天数
        UPDATE "apps_kuaizhizao_sales_orders"
        SET "payment_terms_days" = CAST(
            NULLIF(regexp_replace(COALESCE("payment_terms", ''), '\\D', '', 'g'), '')
            AS INTEGER
        )
        WHERE "payment_terms_days" IS NULL
          AND "payment_terms" IS NOT NULL
          AND "payment_terms" ~ '[0-9]'
          AND length(regexp_replace(COALESCE("payment_terms", ''), '\\D', '', 'g')) > 0
          AND length(regexp_replace(COALESCE("payment_terms", ''), '\\D', '', 'g')) <= 5;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        DROP COLUMN IF EXISTS "payment_terms_days";
    """

# 对应上游 922_20261022195000_sales_order_payment_terms_days.py
