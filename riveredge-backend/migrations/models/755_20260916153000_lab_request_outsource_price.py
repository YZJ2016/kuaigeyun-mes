"""委外试验申请价格字段（R-02 #64）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_lab_requests"
            ADD COLUMN IF NOT EXISTS "outsource_price" DECIMAL(18,4),
            ADD COLUMN IF NOT EXISTS "price_filled_by" INT,
            ADD COLUMN IF NOT EXISTS "price_filled_by_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "price_filled_at" TIMESTAMPTZ;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_lab_requests"
            DROP COLUMN IF EXISTS "outsource_price",
            DROP COLUMN IF EXISTS "price_filled_by",
            DROP COLUMN IF EXISTS "price_filled_by_name",
            DROP COLUMN IF EXISTS "price_filled_at";
    """
