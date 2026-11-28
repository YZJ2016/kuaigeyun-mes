"""收款单/付款单补 post_on_approval 标记列。

合并结算（merge settlement）立收/立付语义：合并创建后先走提交审核，
审批通过回调中自动过账并写银行流水。启用审核的租户下该标记为真时，
审核通过即触发过账；未启用审核的单据提交即自动通过不受影响。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_receipts"
            ADD COLUMN IF NOT EXISTS "post_on_approval" BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE "apps_kuaicaiwu_payments"
            ADD COLUMN IF NOT EXISTS "post_on_approval" BOOLEAN NOT NULL DEFAULT FALSE;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_receipts"
            DROP COLUMN IF EXISTS "post_on_approval";
        ALTER TABLE "apps_kuaicaiwu_payments"
            DROP COLUMN IF EXISTS "post_on_approval";
    """
