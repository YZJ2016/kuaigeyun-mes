"""付款单/付款申请：员工垫付领款人 + 垫付审计台账。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_payments"
            ADD COLUMN IF NOT EXISTS "advance_payee_id" INT;
        ALTER TABLE "apps_kuaicaiwu_payments"
            ADD COLUMN IF NOT EXISTS "advance_payee_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_kuaicaiwu_payments"."advance_payee_id" IS '员工垫付领款人ID';
        COMMENT ON COLUMN "apps_kuaicaiwu_payments"."advance_payee_name" IS '员工垫付领款人姓名';

        ALTER TABLE "apps_kuaizhizao_payment_applications"
            ADD COLUMN IF NOT EXISTS "advance_payee_id" INT;
        ALTER TABLE "apps_kuaizhizao_payment_applications"
            ADD COLUMN IF NOT EXISTS "advance_payee_name" VARCHAR(100);
        COMMENT ON COLUMN "apps_kuaizhizao_payment_applications"."advance_payee_id" IS '员工垫付领款人ID';
        COMMENT ON COLUMN "apps_kuaizhizao_payment_applications"."advance_payee_name" IS '员工垫付领款人姓名';

        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_payment_advance_records" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "payment_id" INT NOT NULL,
            "payment_code" VARCHAR(50) NOT NULL,
            "payee_id" INT NOT NULL,
            "payee_name" VARCHAR(100) NOT NULL,
            "supplier_id" INT NOT NULL,
            "supplier_name" VARCHAR(200) NOT NULL,
            "amount" DECIMAL(16,4) NOT NULL,
            "status" VARCHAR(20) NOT NULL DEFAULT 'cleared',
            "confirmed_at" TIMESTAMPTZ,
            "deleted_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS "idx_payment_advance_records_tenant_payment"
            ON "apps_kuaicaiwu_payment_advance_records" ("tenant_id", "payment_id");
        CREATE INDEX IF NOT EXISTS "idx_payment_advance_records_tenant_payee"
            ON "apps_kuaicaiwu_payment_advance_records" ("tenant_id", "payee_id");
        COMMENT ON TABLE "apps_kuaicaiwu_payment_advance_records" IS '付款单员工垫付审计台账';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaicaiwu_payment_advance_records";
        ALTER TABLE "apps_kuaizhizao_payment_applications"
            DROP COLUMN IF EXISTS "advance_payee_id";
        ALTER TABLE "apps_kuaizhizao_payment_applications"
            DROP COLUMN IF EXISTS "advance_payee_name";
        ALTER TABLE "apps_kuaicaiwu_payments"
            DROP COLUMN IF EXISTS "advance_payee_id";
        ALTER TABLE "apps_kuaicaiwu_payments"
            DROP COLUMN IF EXISTS "advance_payee_name";
    """
