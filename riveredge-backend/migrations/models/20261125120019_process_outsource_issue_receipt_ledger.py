"""工序委外：立账策略、发料关联、分批收货批次表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_orders"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(40);
        COMMENT ON COLUMN "apps_kuaizhizao_outsource_orders"."payable_recognition" IS '应付立账策略';

        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ALTER COLUMN "outsource_work_order_id" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ALTER COLUMN "outsource_work_order_code" DROP NOT NULL;
        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ADD COLUMN IF NOT EXISTS "outsource_order_id" INT;
        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            ADD COLUMN IF NOT EXISTS "outsource_order_code" VARCHAR(50);
        CREATE INDEX IF NOT EXISTS "idx_om_issue_outsource_order"
            ON "apps_kuaizhizao_outsource_material_issues" ("tenant_id", "outsource_order_id");

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
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaizhizao_outsource_order_receipts";
        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            DROP COLUMN IF EXISTS "outsource_order_code";
        ALTER TABLE "apps_kuaizhizao_outsource_material_issues"
            DROP COLUMN IF EXISTS "outsource_order_id";
        ALTER TABLE "apps_kuaizhizao_outsource_orders"
            DROP COLUMN IF EXISTS "payable_recognition";
    """