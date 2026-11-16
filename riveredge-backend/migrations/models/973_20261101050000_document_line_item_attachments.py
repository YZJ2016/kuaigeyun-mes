"""六类业务单据明细行 attachments JSON。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_requisition_items"
            ADD COLUMN IF NOT EXISTS "attachments" JSONB;
        ALTER TABLE "apps_kuaizhizao_purchase_order_items"
            ADD COLUMN IF NOT EXISTS "attachments" JSONB;
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ADD COLUMN IF NOT EXISTS "attachments" JSONB;
        ALTER TABLE "apps_kuaizhizao_quotation_items"
            ADD COLUMN IF NOT EXISTS "attachments" JSONB;
        ALTER TABLE "apps_kuaizhizao_sales_order_items"
            ADD COLUMN IF NOT EXISTS "attachments" JSONB;
        ALTER TABLE "apps_kuaizhizao_sales_delivery_items"
            ADD COLUMN IF NOT EXISTS "attachments" JSONB;

        COMMENT ON COLUMN "apps_kuaizhizao_purchase_requisition_items"."attachments"
            IS '行附件 JSON（与表头 documentAttachments 形态一致）';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_order_items"."attachments"
            IS '行附件 JSON';
        COMMENT ON COLUMN "apps_kuaizhizao_purchase_receipt_items"."attachments"
            IS '行附件 JSON';
        COMMENT ON COLUMN "apps_kuaizhizao_quotation_items"."attachments"
            IS '行附件 JSON';
        COMMENT ON COLUMN "apps_kuaizhizao_sales_order_items"."attachments"
            IS '行附件 JSON';
        COMMENT ON COLUMN "apps_kuaizhizao_sales_delivery_items"."attachments"
            IS '行附件 JSON';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_requisition_items"
            DROP COLUMN IF EXISTS "attachments";
        ALTER TABLE "apps_kuaizhizao_purchase_order_items"
            DROP COLUMN IF EXISTS "attachments";
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            DROP COLUMN IF EXISTS "attachments";
        ALTER TABLE "apps_kuaizhizao_quotation_items"
            DROP COLUMN IF EXISTS "attachments";
        ALTER TABLE "apps_kuaizhizao_sales_order_items"
            DROP COLUMN IF EXISTS "attachments";
        ALTER TABLE "apps_kuaizhizao_sales_delivery_items"
            DROP COLUMN IF EXISTS "attachments";
    """
