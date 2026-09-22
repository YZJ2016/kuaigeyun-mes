"""委外结算二三期：行类型、红字结算、成本快照、发料单价快照。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_settlements"
        ADD COLUMN IF NOT EXISTS "settlement_kind" VARCHAR(20) NOT NULL DEFAULT 'normal';
        ALTER TABLE "apps_kuaizhizao_outsource_settlements"
        ADD COLUMN IF NOT EXISTS "source_settlement_id" INT;
        ALTER TABLE "apps_kuaizhizao_outsource_settlements"
        ADD COLUMN IF NOT EXISTS "auto_generated" BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE "apps_kuaizhizao_outsource_settlements"
        ADD COLUMN IF NOT EXISTS "source_doc_type" VARCHAR(50);
        ALTER TABLE "apps_kuaizhizao_outsource_settlements"
        ADD COLUMN IF NOT EXISTS "source_doc_id" INT;

        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ADD COLUMN IF NOT EXISTS "line_type" VARCHAR(30) NOT NULL DEFAULT 'processing';
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ADD COLUMN IF NOT EXISTS "outsource_product_return_id" INT;
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ADD COLUMN IF NOT EXISTS "deduction_basis_qty" NUMERIC(14,4);
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ADD COLUMN IF NOT EXISTS "deduction_basis_amount" NUMERIC(16,4);

        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ALTER COLUMN "outsource_material_receipt_id" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ALTER COLUMN "receipt_code" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ALTER COLUMN "outsource_work_order_id" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ALTER COLUMN "outsource_work_order_code" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ALTER COLUMN "product_code" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ALTER COLUMN "product_name" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items"
        ALTER COLUMN "unit" DROP NOT NULL;

        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts"
        ADD COLUMN IF NOT EXISTS "inventory_unit_cost" NUMERIC(14,4);
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts"
        ADD COLUMN IF NOT EXISTS "processing_unit_cost" NUMERIC(14,4);
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts"
        ADD COLUMN IF NOT EXISTS "cost_posted_at" TIMESTAMPTZ;

        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
        ADD COLUMN IF NOT EXISTS "issue_unit_cost" NUMERIC(14,4);

        ALTER TABLE "apps_kuaizhizao_outsource_product_returns"
        ADD COLUMN IF NOT EXISTS "credit_settlement_id" INT;
        ALTER TABLE "apps_kuaizhizao_outsource_product_returns"
        ADD COLUMN IF NOT EXISTS "finance_offset_applied" BOOLEAN NOT NULL DEFAULT FALSE;

        CREATE INDEX IF NOT EXISTS "idx_outsource_settlements_tenant_kind"
            ON "apps_kuaizhizao_outsource_settlements" ("tenant_id", "settlement_kind");
        CREATE INDEX IF NOT EXISTS "idx_outsource_settlement_items_tenant_line_type"
            ON "apps_kuaizhizao_outsource_settlement_items" ("tenant_id", "line_type");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_outsource_settlement_items_tenant_line_type";
        DROP INDEX IF EXISTS "idx_outsource_settlements_tenant_kind";

        ALTER TABLE "apps_kuaizhizao_outsource_product_returns" DROP COLUMN IF EXISTS "finance_offset_applied";
        ALTER TABLE "apps_kuaizhizao_outsource_product_returns" DROP COLUMN IF EXISTS "credit_settlement_id";

        ALTER TABLE "apps_kuaizhizao_outsource_material_issues" DROP COLUMN IF EXISTS "issue_unit_cost";

        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts" DROP COLUMN IF EXISTS "cost_posted_at";
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts" DROP COLUMN IF EXISTS "processing_unit_cost";
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts" DROP COLUMN IF EXISTS "inventory_unit_cost";

        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items" DROP COLUMN IF EXISTS "deduction_basis_amount";
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items" DROP COLUMN IF EXISTS "deduction_basis_qty";
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items" DROP COLUMN IF EXISTS "outsource_product_return_id";
        ALTER TABLE "apps_kuaizhizao_outsource_settlement_items" DROP COLUMN IF EXISTS "line_type";

        ALTER TABLE "apps_kuaizhizao_outsource_settlements" DROP COLUMN IF EXISTS "source_doc_id";
        ALTER TABLE "apps_kuaizhizao_outsource_settlements" DROP COLUMN IF EXISTS "source_doc_type";
        ALTER TABLE "apps_kuaizhizao_outsource_settlements" DROP COLUMN IF EXISTS "auto_generated";
        ALTER TABLE "apps_kuaizhizao_outsource_settlements" DROP COLUMN IF EXISTS "source_settlement_id";
        ALTER TABLE "apps_kuaizhizao_outsource_settlements" DROP COLUMN IF EXISTS "settlement_kind";
    """
