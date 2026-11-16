"""价格本增加数量阶梯价 JSON 字段。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_partner_price_books"
            ADD COLUMN IF NOT EXISTS "tier_prices" JSONB;

        COMMENT ON COLUMN "apps_master_data_partner_price_books"."tier_prices"
            IS '数量阶梯单价 JSON：[{"minQuantity":1,"maxQuantity":99,"unitPrice":"10.5"}]';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_partner_price_books"
            DROP COLUMN IF EXISTS "tier_prices";
    """
