"""
资金调拨单：付款方式（转账 / 承兑 / 现金）
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_fund_transfers"
        ADD COLUMN IF NOT EXISTS "payment_method" VARCHAR(50) NOT NULL DEFAULT '转账';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_fund_transfers"
        DROP COLUMN IF EXISTS "payment_method";
    """