"""
采购入库明细：固化表单录入单价，行税额/价税合计由服务端 rollup 写回，详情禁止前端反算。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ADD COLUMN IF NOT EXISTS "display_unit_price" DECIMAL(12,4);

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."display_unit_price"
            IS '录入单价（表单口径，只读展示）';

        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ADD COLUMN IF NOT EXISTS "tax_amount" DECIMAL(14,4);

        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ADD COLUMN IF NOT EXISTS "net_amount" DECIMAL(14,4);

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."tax_amount"
            IS '行税额（rollup 写回）';

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."net_amount"
            IS '行价税合计（rollup 写回）';

        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ADD COLUMN IF NOT EXISTS "tax_rate" DECIMAL(5,2);

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."tax_rate"
            IS '行税率（百分比）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items" DROP COLUMN IF EXISTS "display_unit_price";
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items" DROP COLUMN IF EXISTS "tax_amount";
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items" DROP COLUMN IF EXISTS "net_amount";
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items" DROP COLUMN IF EXISTS "tax_rate";
    """
