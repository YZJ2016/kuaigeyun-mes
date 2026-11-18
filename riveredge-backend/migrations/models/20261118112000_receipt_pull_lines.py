"""收款单加载明细表 apps_kuaicaiwu_receipt_pull_lines。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_receipt_pull_lines" (
            "id" SERIAL PRIMARY KEY,
            "uuid" UUID NOT NULL UNIQUE,
            "tenant_id" INT NOT NULL,
            "receipt_id" INT NOT NULL,
            "line_no" INT NOT NULL,
            "source_type" VARCHAR(50) NOT NULL,
            "source_id" INT NOT NULL,
            "source_code" VARCHAR(50),
            "amount" DECIMAL(16,4) NOT NULL,
            "deleted_at" TIMESTAMPTZ,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS "idx_receipt_pull_lines_tenant_receipt"
            ON "apps_kuaicaiwu_receipt_pull_lines" ("tenant_id", "receipt_id");
        CREATE INDEX IF NOT EXISTS "idx_receipt_pull_lines_tenant_source"
            ON "apps_kuaicaiwu_receipt_pull_lines" ("tenant_id", "source_type", "source_id");
        COMMENT ON TABLE "apps_kuaicaiwu_receipt_pull_lines" IS '收款单加载明细';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaicaiwu_receipt_pull_lines";
    """
