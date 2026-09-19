"""委外结算单表与委外收货已结算数量字段。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts"
        ADD COLUMN IF NOT EXISTS "settled_quantity" NUMERIC(14,4) NOT NULL DEFAULT 0;

        COMMENT ON COLUMN "apps_kuaizhizao_outsource_material_receipts"."settled_quantity"
            IS '已审核委外结算数量';

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_outsource_settlements" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "settlement_code" VARCHAR(50) NOT NULL,
            "supplier_id" INT NOT NULL,
            "supplier_code" VARCHAR(50) NOT NULL,
            "supplier_name" VARCHAR(200) NOT NULL,
            "business_date" DATE,
            "total_amount" NUMERIC(16,4) NOT NULL DEFAULT 0,
            "status" VARCHAR(20) NOT NULL DEFAULT '草稿',
            "reviewer_id" INT,
            "reviewer_name" VARCHAR(100),
            "reviewed_at" TIMESTAMPTZ,
            "review_remarks" TEXT,
            "payable_id" INT,
            "payable_code" VARCHAR(50),
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS "idx_outsource_settlements_tenant_code"
            ON "apps_kuaizhizao_outsource_settlements" ("tenant_id", "settlement_code");
        CREATE INDEX IF NOT EXISTS "idx_outsource_settlements_tenant_supplier"
            ON "apps_kuaizhizao_outsource_settlements" ("tenant_id", "supplier_id");
        CREATE INDEX IF NOT EXISTS "idx_outsource_settlements_tenant_status"
            ON "apps_kuaizhizao_outsource_settlements" ("tenant_id", "status");

        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_outsource_settlement_items" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "settlement_id" INT NOT NULL,
            "line_no" INT NOT NULL,
            "outsource_material_receipt_id" INT NOT NULL,
            "receipt_code" VARCHAR(50) NOT NULL,
            "outsource_work_order_id" INT NOT NULL,
            "outsource_work_order_code" VARCHAR(50) NOT NULL,
            "product_code" VARCHAR(50) NOT NULL,
            "product_name" VARCHAR(200) NOT NULL,
            "unit" VARCHAR(20) NOT NULL,
            "settlement_quantity" NUMERIC(14,4) NOT NULL DEFAULT 0,
            "unit_price" NUMERIC(14,4) NOT NULL DEFAULT 0,
            "amount" NUMERIC(16,4) NOT NULL DEFAULT 0,
            "notes" TEXT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS "idx_outsource_settlement_items_tenant_settlement"
            ON "apps_kuaizhizao_outsource_settlement_items" ("tenant_id", "settlement_id");
        CREATE INDEX IF NOT EXISTS "idx_outsource_settlement_items_tenant_receipt"
            ON "apps_kuaizhizao_outsource_settlement_items" ("tenant_id", "outsource_material_receipt_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaizhizao_outsource_settlement_items";
        DROP TABLE IF EXISTS "apps_kuaizhizao_outsource_settlements";
        ALTER TABLE "apps_kuaizhizao_outsource_material_receipts"
        DROP COLUMN IF EXISTS "settled_quantity";
    """
