"""对账单立账链：单据立账策略列 + 对账单立账方式 + 工序委外收货批次表。

上游子集：`917_document_ledger_recognition`（销售/采购退货/委外部分）+
`916_partner_statement_ledger_posting` + `1038_process_outsource_issue_receipt_ledger`
（立账策略与批次表部分；委外发料关联列归 E 批）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_sales_orders"
            ADD COLUMN IF NOT EXISTS "revenue_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_shipment';
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
            ADD COLUMN IF NOT EXISTS "revenue_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_shipment';
        ALTER TABLE "apps_kuaizhizao_sales_returns"
            ADD COLUMN IF NOT EXISTS "revenue_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_shipment';
        ALTER TABLE "apps_kuaizhizao_purchase_returns"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_receipt';
        ALTER TABLE "apps_kuaizhizao_outsource_work_orders"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_receipt';
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_receipt';

        ALTER TABLE "apps_kuaizhizao_outsource_orders"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(40);
        COMMENT ON COLUMN "apps_kuaizhizao_outsource_orders"."payable_recognition" IS '应付立账策略';

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_outsource_order_receipts" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL,
            "tenant_id" INT NOT NULL,
            "outsource_order_id" INT NOT NULL,
            "outsource_order_code" VARCHAR(50) NOT NULL,
            "received_quantity" DECIMAL(14,4) NOT NULL,
            "qualified_quantity" DECIMAL(14,4) NOT NULL,
            "unqualified_quantity" DECIMAL(14,4) NOT NULL,
            "payable_recognition" VARCHAR(40),
            "ledger_posted" BOOLEAN NOT NULL DEFAULT FALSE,
            "remarks" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_oo_receipt_order"
            ON "apps_kuaizhizao_outsource_order_receipts" ("tenant_id", "outsource_order_id");

        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "ledger_posting_mode" VARCHAR(20) NOT NULL DEFAULT 'immediate';
        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "ledger_posted_at" TIMESTAMPTZ;
        ALTER TABLE "apps_kuaicaiwu_partner_statements"
            ADD COLUMN IF NOT EXISTS "ledger_posted_by" INT;
        COMMENT ON COLUMN "apps_kuaicaiwu_partner_statements"."ledger_posting_mode"
            IS '立账方式 immediate/by_invoice';
        COMMENT ON COLUMN "apps_kuaicaiwu_partner_statements"."ledger_posted_at"
            IS '审核立账完成时间';
        COMMENT ON COLUMN "apps_kuaicaiwu_partner_statements"."ledger_posted_by"
            IS '审核立账操作人';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "ledger_posted_by";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "ledger_posted_at";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "ledger_posting_mode";
        DROP TABLE IF EXISTS "apps_kuaizhizao_outsource_order_receipts";
        ALTER TABLE "apps_kuaizhizao_outsource_orders" DROP COLUMN IF EXISTS "payable_recognition";
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts" DROP COLUMN IF EXISTS "payable_recognition";
        ALTER TABLE "apps_kuaizhizao_outsource_work_orders" DROP COLUMN IF EXISTS "payable_recognition";
        ALTER TABLE "apps_kuaizhizao_purchase_returns" DROP COLUMN IF EXISTS "payable_recognition";
        ALTER TABLE "apps_kuaizhizao_sales_returns" DROP COLUMN IF EXISTS "revenue_recognition";
        ALTER TABLE "apps_kuaizhizao_sales_deliveries" DROP COLUMN IF EXISTS "revenue_recognition";
        ALTER TABLE "apps_kuaizhizao_sales_orders" DROP COLUMN IF EXISTS "revenue_recognition";
    """
