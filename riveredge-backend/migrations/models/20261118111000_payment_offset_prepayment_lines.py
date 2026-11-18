"""预付抵扣预付款明细表 apps_kuaicaiwu_payment_offset_prepayment_lines。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_payment_offset_prepayment_lines" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "payment_id" INT NOT NULL,
            "line_no" INT NOT NULL,
            "prepayment_payment_id" INT NOT NULL,
            "source_code" VARCHAR(50),
            "amount" NUMERIC(16,4) NOT NULL,
            "deleted_at" TIMESTAMPTZ,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS "idx_payment_offset_prep_tenant_payment"
            ON "apps_kuaicaiwu_payment_offset_prepayment_lines" ("tenant_id", "payment_id");
        CREATE INDEX IF NOT EXISTS "idx_payment_offset_prep_tenant_src"
            ON "apps_kuaicaiwu_payment_offset_prepayment_lines" ("tenant_id", "prepayment_payment_id");
        COMMENT ON TABLE "apps_kuaicaiwu_payment_offset_prepayment_lines" IS '预付抵扣预付款明细';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaicaiwu_payment_offset_prepayment_lines";
    """
