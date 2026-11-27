"""其他费用支出申请单 + 支出来源字段（上游 960 重映射）。

建表列含 counterparty_account_name/bank_name/bank_account
（对应上游 1005 申请单侧补充列，建表时一次到位）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_other_expense_applications" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "application_code" VARCHAR(50) NOT NULL,
            "business_date" DATE NOT NULL,
            "counterparty_kind" VARCHAR(20) NOT NULL DEFAULT 'none',
            "counterparty_id" INT,
            "counterparty_name" VARCHAR(200),
            "counterparty_account_name" VARCHAR(200),
            "counterparty_bank_name" VARCHAR(200),
            "counterparty_bank_account" VARCHAR(64),
            "total_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "pushed_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "remaining_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "payment_method" VARCHAR(50) NOT NULL,
            "bank_account_id" INT,
            "bank_account" VARCHAR(100),
            "status" VARCHAR(20) NOT NULL DEFAULT 'Draft',
            "reviewer_id" INT,
            "reviewer_name" VARCHAR(100),
            "review_time" TIMESTAMPTZ,
            "review_remarks" TEXT,
            "department_id" INT,
            "department_name" VARCHAR(200),
            "project_id" INT,
            "project_name" VARCHAR(200),
            "notes" TEXT,
            "attachments" JSONB,
            "payable_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_receipt',
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_oe_app_tenant_code"
            ON "apps_kuaicaiwu_other_expense_applications" ("tenant_id", "application_code");
        CREATE INDEX IF NOT EXISTS "idx_oe_app_tenant_status"
            ON "apps_kuaicaiwu_other_expense_applications" ("tenant_id", "status");
        CREATE INDEX IF NOT EXISTS "idx_oe_app_business_date"
            ON "apps_kuaicaiwu_other_expense_applications" ("business_date");

        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_other_expense_application_lines" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "application_id" INT NOT NULL REFERENCES "apps_kuaicaiwu_other_expense_applications" ("id") ON DELETE CASCADE,
            "line_no" INT NOT NULL DEFAULT 1,
            "category_code" VARCHAR(50) NOT NULL,
            "category_name" VARCHAR(200) NOT NULL,
            "amount" DECIMAL(16,4) NOT NULL,
            "pushed_amount" DECIMAL(16,4) NOT NULL DEFAULT 0,
            "description" TEXT,
            "gl_account_code" VARCHAR(20),
            "payee_id" INT,
            "payee_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100)
        );
        CREATE INDEX IF NOT EXISTS "idx_oe_app_line_tenant_app"
            ON "apps_kuaicaiwu_other_expense_application_lines" ("tenant_id", "application_id");

        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            ADD COLUMN IF NOT EXISTS "source_type" VARCHAR(50),
            ADD COLUMN IF NOT EXISTS "source_id" INT,
            ADD COLUMN IF NOT EXISTS "source_code" VARCHAR(50);
        CREATE INDEX IF NOT EXISTS "idx_other_expense_source"
            ON "apps_kuaicaiwu_other_expenses" ("tenant_id", "source_type", "source_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            DROP COLUMN IF EXISTS "source_code",
            DROP COLUMN IF EXISTS "source_id",
            DROP COLUMN IF EXISTS "source_type";
        DROP TABLE IF EXISTS "apps_kuaicaiwu_other_expense_application_lines";
        DROP TABLE IF EXISTS "apps_kuaicaiwu_other_expense_applications";
    """
