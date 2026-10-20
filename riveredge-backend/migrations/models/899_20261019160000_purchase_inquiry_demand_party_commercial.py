"""采购询价：需方主数据表 + 询价头商务字段 + 受邀供应商联系/邮件通知。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_purchase_demand_parties" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "tenant_id" INT NOT NULL,
            "code" VARCHAR(50) NOT NULL,
            "name" VARCHAR(200) NOT NULL,
            "contact_name" VARCHAR(100),
            "contact_phone" VARCHAR(50),
            "contact_email" VARCHAR(100),
            "address" VARCHAR(500),
            "tax_no" VARCHAR(50),
            "notes" TEXT,
            "is_active" BOOL NOT NULL DEFAULT TRUE,
            "sort_order" INT NOT NULL DEFAULT 0,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_purchase_demand_parties_tenant_code"
            ON "apps_kuaizhizao_purchase_demand_parties" ("tenant_id", "code");
        CREATE INDEX IF NOT EXISTS "idx_purchase_demand_parties_tenant_active"
            ON "apps_kuaizhizao_purchase_demand_parties" ("tenant_id", "is_active");

        ALTER TABLE "apps_kuaizhizao_purchase_inquiries"
            ADD COLUMN IF NOT EXISTS "demand_party_id" INT,
            ADD COLUMN IF NOT EXISTS "demand_party_name" VARCHAR(200),
            ADD COLUMN IF NOT EXISTS "buyer_phone" VARCHAR(50),
            ADD COLUMN IF NOT EXISTS "currency" VARCHAR(10) DEFAULT 'CNY',
            ADD COLUMN IF NOT EXISTS "exchange_rate" DECIMAL(12,6) DEFAULT 1,
            ADD COLUMN IF NOT EXISTS "invoice_type" VARCHAR(50),
            ADD COLUMN IF NOT EXISTS "tax_rate" DECIMAL(8,4) DEFAULT 0,
            ADD COLUMN IF NOT EXISTS "payment_method" VARCHAR(50),
            ADD COLUMN IF NOT EXISTS "payment_terms" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "trade_mode" VARCHAR(50);

        ALTER TABLE "apps_kuaizhizao_purchase_inquiry_vendors"
            ADD COLUMN IF NOT EXISTS "contact_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "contact_phone" VARCHAR(50),
            ADD COLUMN IF NOT EXISTS "contact_email" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "email_notify" BOOL NOT NULL DEFAULT FALSE;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_purchase_inquiry_vendors"
            DROP COLUMN IF EXISTS "contact_name",
            DROP COLUMN IF EXISTS "contact_phone",
            DROP COLUMN IF EXISTS "contact_email",
            DROP COLUMN IF EXISTS "email_notify";

        ALTER TABLE "apps_kuaizhizao_purchase_inquiries"
            DROP COLUMN IF EXISTS "demand_party_id",
            DROP COLUMN IF EXISTS "demand_party_name",
            DROP COLUMN IF EXISTS "buyer_phone",
            DROP COLUMN IF EXISTS "currency",
            DROP COLUMN IF EXISTS "exchange_rate",
            DROP COLUMN IF EXISTS "invoice_type",
            DROP COLUMN IF EXISTS "tax_rate",
            DROP COLUMN IF EXISTS "payment_method",
            DROP COLUMN IF EXISTS "payment_terms",
            DROP COLUMN IF EXISTS "trade_mode";

        DROP TABLE IF EXISTS "apps_kuaizhizao_purchase_demand_parties";
    """
