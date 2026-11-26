from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_invoices"
        ADD COLUMN IF NOT EXISTS "settlement_mode" VARCHAR(16) NOT NULL DEFAULT 'summary';

        ALTER TABLE "apps_kuaicaiwu_invoice_items"
        ADD COLUMN IF NOT EXISTS "source_doc_type" VARCHAR(50);
        ALTER TABLE "apps_kuaicaiwu_invoice_items"
        ADD COLUMN IF NOT EXISTS "source_doc_id" INT;
        ALTER TABLE "apps_kuaicaiwu_invoice_items"
        ADD COLUMN IF NOT EXISTS "source_line_id" INT;
        ALTER TABLE "apps_kuaicaiwu_invoice_items"
        ADD COLUMN IF NOT EXISTS "partner_statement_line_id" INT;

        ALTER TABLE "apps_kuaicaiwu_purchase_invoices"
        ADD COLUMN IF NOT EXISTS "settlement_mode" VARCHAR(16) NOT NULL DEFAULT 'summary';

        ALTER TABLE "apps_kuaicaiwu_partner_statements"
        ADD COLUMN IF NOT EXISTS "statement_line_granularity" VARCHAR(20) NOT NULL DEFAULT 'material_line';

        ALTER TABLE "apps_kuaicaiwu_gl_book_settings"
        ADD COLUMN IF NOT EXISTS "invoice_settlement_mode_default" VARCHAR(16) NOT NULL DEFAULT 'summary';
        ALTER TABLE "apps_kuaicaiwu_gl_book_settings"
        ADD COLUMN IF NOT EXISTS "statement_line_granularity" VARCHAR(20) NOT NULL DEFAULT 'material_line';

        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_partner_statement_lines" (
            "id" SERIAL PRIMARY KEY,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "uuid" UUID,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "tenant_id" INT NOT NULL,
            "statement_id" INT NOT NULL REFERENCES "apps_kuaicaiwu_partner_statements" ("id") ON DELETE CASCADE,
            "line_kind" VARCHAR(16) NOT NULL DEFAULT 'material',
            "source_doc_type" VARCHAR(50) NOT NULL,
            "source_doc_id" INT NOT NULL,
            "source_line_id" INT NOT NULL DEFAULT 0,
            "doc_code" VARCHAR(50),
            "doc_date" DATE,
            "material_id" INT,
            "material_code" VARCHAR(50),
            "material_name" VARCHAR(200),
            "material_spec" VARCHAR(200),
            "unit" VARCHAR(20),
            "quantity" DECIMAL(12,4),
            "amount_basis" VARCHAR(20) NOT NULL DEFAULT 'tax_inclusive',
            "doc_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "prior_stated_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "statement_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "remaining_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "invoice_occupied_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "invoiceable_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "debit" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "credit" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "doc_type_label" VARCHAR(50),
            "is_read_only" BOOL NOT NULL DEFAULT FALSE,
            "sort_index" INT NOT NULL DEFAULT 0,
            "line_snapshot" JSONB,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_partner_stmt_line_src"
            ON "apps_kuaicaiwu_partner_statement_lines"
            ("statement_id", "source_doc_type", "source_doc_id", "source_line_id")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_partner_stmt_line_tenant_stmt"
            ON "apps_kuaicaiwu_partner_statement_lines" ("tenant_id", "statement_id");
        CREATE INDEX IF NOT EXISTS "idx_partner_stmt_line_source"
            ON "apps_kuaicaiwu_partner_statement_lines"
            ("tenant_id", "source_doc_type", "source_doc_id", "source_line_id");

        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_purchase_invoice_items" (
            "id" SERIAL PRIMARY KEY,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "uuid" UUID,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "tenant_id" INT NOT NULL,
            "purchase_invoice_id" INT NOT NULL REFERENCES "apps_kuaicaiwu_purchase_invoices" ("id") ON DELETE CASCADE,
            "item_name" VARCHAR(200) NOT NULL,
            "spec_model" VARCHAR(100),
            "unit" VARCHAR(20),
            "quantity" DECIMAL(12,4),
            "unit_price" DECIMAL(12,4),
            "amount" DECIMAL(16,4) NOT NULL,
            "tax_rate" DECIMAL(6,4) NOT NULL,
            "tax_amount" DECIMAL(16,4) NOT NULL,
            "source_doc_type" VARCHAR(50),
            "source_doc_id" INT,
            "source_line_id" INT,
            "partner_statement_line_id" INT,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_pi_item_tenant_inv"
            ON "apps_kuaicaiwu_purchase_invoice_items" ("tenant_id", "purchase_invoice_id");

        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_sales_delivery_line_finance_occupancies" (
            "id" SERIAL PRIMARY KEY,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "uuid" UUID,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "tenant_id" INT NOT NULL,
            "sales_delivery_id" INT NOT NULL,
            "sales_delivery_item_id" INT NOT NULL,
            "occupancy_kind" VARCHAR(16) NOT NULL,
            "quantity" DECIMAL(12,4) NOT NULL,
            "amount" DECIMAL(14,4) NOT NULL,
            "target_doc_type" VARCHAR(32) NOT NULL,
            "target_doc_id" INT NOT NULL,
            "target_item_id" INT,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_sd_occ_item_kind"
            ON "apps_kuaicaiwu_sales_delivery_line_finance_occupancies"
            ("tenant_id", "sales_delivery_item_id", "occupancy_kind");
        CREATE INDEX IF NOT EXISTS "idx_sd_occ_target"
            ON "apps_kuaicaiwu_sales_delivery_line_finance_occupancies"
            ("tenant_id", "target_doc_type", "target_doc_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaicaiwu_sales_delivery_line_finance_occupancies";
        DROP TABLE IF EXISTS "apps_kuaicaiwu_purchase_invoice_items";
        DROP TABLE IF EXISTS "apps_kuaicaiwu_partner_statement_lines";
        ALTER TABLE "apps_kuaicaiwu_gl_book_settings" DROP COLUMN IF EXISTS "statement_line_granularity";
        ALTER TABLE "apps_kuaicaiwu_gl_book_settings" DROP COLUMN IF EXISTS "invoice_settlement_mode_default";
        ALTER TABLE "apps_kuaicaiwu_partner_statements" DROP COLUMN IF EXISTS "statement_line_granularity";
        ALTER TABLE "apps_kuaicaiwu_purchase_invoices" DROP COLUMN IF EXISTS "settlement_mode";
        ALTER TABLE "apps_kuaicaiwu_invoice_items" DROP COLUMN IF EXISTS "partner_statement_line_id";
        ALTER TABLE "apps_kuaicaiwu_invoice_items" DROP COLUMN IF EXISTS "source_line_id";
        ALTER TABLE "apps_kuaicaiwu_invoice_items" DROP COLUMN IF EXISTS "source_doc_id";
        ALTER TABLE "apps_kuaicaiwu_invoice_items" DROP COLUMN IF EXISTS "source_doc_type";
        ALTER TABLE "apps_kuaicaiwu_invoices" DROP COLUMN IF EXISTS "settlement_mode";
    """