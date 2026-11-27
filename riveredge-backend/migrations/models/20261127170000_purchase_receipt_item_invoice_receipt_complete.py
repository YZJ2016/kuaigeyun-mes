"""采购入库明细：收票结束标记（明细收票满额后过滤取单）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
        ADD COLUMN IF NOT EXISTS "invoice_receipt_complete" BOOLEAN NOT NULL DEFAULT FALSE;
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."invoice_receipt_complete"
            IS '收票结束：该行可收票价税合计已全部占用';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
        DROP COLUMN IF EXISTS "invoice_receipt_complete";
    """