"""
采购入库明细：行税额/价税合计由服务端 rollup 写回，详情禁止前端反算。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ADD COLUMN IF NOT EXISTS "tax_amount" DECIMAL(14,4);

        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ADD COLUMN IF NOT EXISTS "net_amount" DECIMAL(14,4);

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."tax_amount"
            IS '行税额（rollup 写回）';

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."net_amount"
            IS '行价税合计（rollup 写回）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items" DROP COLUMN IF EXISTS "tax_amount";
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items" DROP COLUMN IF EXISTS "net_amount";
    """
