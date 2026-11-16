"""付款单加载明细 + 采购入库行财务占用表（kuaicaiwu）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_payment_pull_lines" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "payment_id" INT NOT NULL,
            "line_no" INT NOT NULL,
            "source_type" VARCHAR(50) NOT NULL,
            "source_id" INT NOT NULL,
            "source_code" VARCHAR(50),
            "amount" DECIMAL(16,4) NOT NULL,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_payment_pull_lines_tenant_payment"
            ON "apps_kuaicaiwu_payment_pull_lines" ("tenant_id", "payment_id");
        CREATE INDEX IF NOT EXISTS "idx_payment_pull_lines_tenant_source"
            ON "apps_kuaicaiwu_payment_pull_lines" ("tenant_id", "source_type", "source_id");
        COMMENT ON TABLE "apps_kuaicaiwu_payment_pull_lines"
            IS '管理会计 - 付款单加载明细';

        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_purchase_receipt_line_finance_occupancies" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL,
            "updated_at" TIMESTAMPTZ NOT NULL,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "purchase_receipt_id" INT NOT NULL,
            "purchase_receipt_item_id" INT NOT NULL,
            "occupancy_kind" VARCHAR(16) NOT NULL,
            "quantity" DECIMAL(12,4) NOT NULL,
            "amount" DECIMAL(14,4) NOT NULL,
            "target_doc_type" VARCHAR(32) NOT NULL,
            "target_doc_id" INT NOT NULL,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_rcpt_line_occ_tenant_item_kind"
            ON "apps_kuaicaiwu_purchase_receipt_line_finance_occupancies"
            ("tenant_id", "purchase_receipt_item_id", "occupancy_kind");
        CREATE INDEX IF NOT EXISTS "idx_rcpt_line_occ_tenant_receipt"
            ON "apps_kuaicaiwu_purchase_receipt_line_finance_occupancies"
            ("tenant_id", "purchase_receipt_id");
        CREATE INDEX IF NOT EXISTS "idx_rcpt_line_occ_tenant_target"
            ON "apps_kuaicaiwu_purchase_receipt_line_finance_occupancies"
            ("tenant_id", "target_doc_type", "target_doc_id");
        COMMENT ON TABLE "apps_kuaicaiwu_purchase_receipt_line_finance_occupancies"
            IS '轻管理会计 - 采购入库行财务占用';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaicaiwu_purchase_receipt_line_finance_occupancies";
        DROP TABLE IF EXISTS "apps_kuaicaiwu_payment_pull_lines";
    """
