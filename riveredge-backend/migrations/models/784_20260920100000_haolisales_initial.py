"""
销售跟踪 haolisales — 订单跟踪与月度工厂台账。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "haolisales_order_tracking" (
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "id" SERIAL NOT NULL PRIMARY KEY,
            "deleted_at" TIMESTAMPTZ,
            "customer_id" INT NOT NULL,
            "customer_name" VARCHAR(200) NOT NULL,
            "order_no" VARCHAR(128) NOT NULL,
            "material_id" INT,
            "material_code" VARCHAR(128),
            "material_name" VARCHAR(200) NOT NULL,
            "delivery_date" DATE NOT NULL,
            "order_qty" NUMERIC(18,4) NOT NULL,
            "unit_price" NUMERIC(18,4),
            "amount" NUMERIC(18,2),
            "contract_file_uuid" VARCHAR(36),
            "requirement_file_uuid" VARCHAR(36),
            "order_type" VARCHAR(32) NOT NULL DEFAULT 'domestic',
            "order_status" VARCHAR(32) NOT NULL DEFAULT 'not_scheduled',
            "payment_term_days" INT,
            "payment_term_label" VARCHAR(64),
            "settlement_type" VARCHAR(32) NOT NULL DEFAULT 'credit_term',
            "invoice_at" TIMESTAMPTZ,
            "invoice_amount_tax_included" NUMERIC(18,2),
            "payment_received_status" VARCHAR(32),
            "production_submitted" BOOLEAN NOT NULL DEFAULT FALSE,
            "production_submitted_at" TIMESTAMPTZ,
            "production_submitted_by" VARCHAR(100),
            "delivery_reminder_sent_at" TIMESTAMPTZ,
            "notes" TEXT,
            "created_by_user_id" INT,
            "created_by_name" VARCHAR(100)
        );
        CREATE INDEX IF NOT EXISTS "idx_haolisales_ot_tenant" ON "haolisales_order_tracking" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_haolisales_ot_customer" ON "haolisales_order_tracking" ("customer_id");
        CREATE INDEX IF NOT EXISTS "idx_haolisales_ot_order_no" ON "haolisales_order_tracking" ("order_no");
        CREATE INDEX IF NOT EXISTS "idx_haolisales_ot_delivery" ON "haolisales_order_tracking" ("delivery_date");

        CREATE TABLE IF NOT EXISTS "haolisales_order_tracking_delivery" (
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "id" SERIAL NOT NULL PRIMARY KEY,
            "deleted_at" TIMESTAMPTZ,
            "order_tracking_id" INT NOT NULL,
            "shipped_at" TIMESTAMPTZ NOT NULL,
            "shipped_qty" NUMERIC(18,4) NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS "idx_haolisales_otd_tenant" ON "haolisales_order_tracking_delivery" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_haolisales_otd_order" ON "haolisales_order_tracking_delivery" ("order_tracking_id");

        CREATE TABLE IF NOT EXISTS "haolisales_order_tracking_payment" (
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "id" SERIAL NOT NULL PRIMARY KEY,
            "deleted_at" TIMESTAMPTZ,
            "order_tracking_id" INT NOT NULL,
            "paid_at" TIMESTAMPTZ NOT NULL,
            "paid_amount" NUMERIC(18,2) NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS "idx_haolisales_otp_tenant" ON "haolisales_order_tracking_payment" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_haolisales_otp_order" ON "haolisales_order_tracking_payment" ("order_tracking_id");

        CREATE TABLE IF NOT EXISTS "haolisales_monthly_factory_ledger" (
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "id" SERIAL NOT NULL PRIMARY KEY,
            "deleted_at" TIMESTAMPTZ,
            "customer_id" INT NOT NULL,
            "customer_name" VARCHAR(200) NOT NULL,
            "ledger_month" VARCHAR(7) NOT NULL,
            "monthly_shipment_total" NUMERIC(18,4),
            "shipment_attachment_uuid" VARCHAR(36),
            "invoice_attachment_uuid" VARCHAR(36),
            "remarks" TEXT,
            "invoice_qty" NUMERIC(18,4),
            "invoice_amount_tax_included" NUMERIC(18,2),
            "invoice_at" TIMESTAMPTZ,
            "created_by_user_id" INT,
            "created_by_name" VARCHAR(100),
            CONSTRAINT "uq_haolisales_mfl_tenant_customer_month" UNIQUE ("tenant_id", "customer_id", "ledger_month")
        );
        CREATE INDEX IF NOT EXISTS "idx_haolisales_mfl_tenant" ON "haolisales_monthly_factory_ledger" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_haolisales_mfl_month" ON "haolisales_monthly_factory_ledger" ("ledger_month");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "haolisales_monthly_factory_ledger" CASCADE;
        DROP TABLE IF EXISTS "haolisales_order_tracking_payment" CASCADE;
        DROP TABLE IF EXISTS "haolisales_order_tracking_delivery" CASCADE;
        DROP TABLE IF EXISTS "haolisales_order_tracking" CASCADE;
    """
