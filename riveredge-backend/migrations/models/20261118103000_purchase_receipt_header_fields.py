"""采购入库单表头：采购类型、立账策略、采购员、部门、付款方式、金蝶编码、税率/币别、税额/价税合计。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ALTER COLUMN "purchase_order_id" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_purchase_receipt_items"
            ALTER COLUMN "purchase_order_item_id" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "order_type" VARCHAR(20) NOT NULL DEFAULT '标准采购';
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_receipt';
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "buyer_id" INT;
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "buyer_name" VARCHAR(100);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "buyer_operator_number" VARCHAR(64);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "department_id" INT;
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "department_name" VARCHAR(100);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "pay_mode" VARCHAR(32);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "org_number" VARCHAR(64);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "bizorg_number" VARCHAR(64);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "billtype_number" VARCHAR(64);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "biztype_number" VARCHAR(64) DEFAULT '110';
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "invscheme_number" VARCHAR(64) DEFAULT '110';
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "tax_rate" DECIMAL(5,2);
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "currency" VARCHAR(10) DEFAULT 'CNY';
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "tax_amount" DECIMAL(14,4) NOT NULL DEFAULT 0;
        ALTER TABLE "apps_kuaizhizao_purchase_receipts"
            ADD COLUMN IF NOT EXISTS "net_amount" DECIMAL(14,4) NOT NULL DEFAULT 0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "order_type";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "payable_recognition";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "buyer_id";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "buyer_name";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "buyer_operator_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "department_id";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "department_name";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "pay_mode";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "org_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "bizorg_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "billtype_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "biztype_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "invscheme_number";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "tax_rate";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "currency";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "tax_amount";
        ALTER TABLE "apps_kuaizhizao_purchase_receipts" DROP COLUMN IF EXISTS "net_amount";
    """
