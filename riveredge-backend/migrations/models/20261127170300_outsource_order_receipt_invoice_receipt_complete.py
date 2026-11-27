"""工序委外收货批次：收票结束标记（明细收票满额后过滤取单）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_order_receipts"
        ADD COLUMN IF NOT EXISTS "invoice_receipt_complete" BOOLEAN NOT NULL DEFAULT FALSE;
        COMMENT ON COLUMN "apps_kuaizhizao_outsource_order_receipts"."invoice_receipt_complete"
            IS '收票结束：该批次可收票价税合计已全部占用';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_order_receipts"
        DROP COLUMN IF EXISTS "invoice_receipt_complete";
    """