"""付款申请：采购订单下推带入税率（百分比，与订单行一致）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_applications"
            ADD COLUMN IF NOT EXISTS "tax_rate" DECIMAL(6,2) NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "apps_kuaizhizao_payment_applications"."tax_rate"
            IS '税率百分比（如13表示13%）；自采购订单下推带入';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_payment_applications"
            DROP COLUMN IF EXISTS "tax_rate";
    """