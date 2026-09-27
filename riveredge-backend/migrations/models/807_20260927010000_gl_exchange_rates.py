"""
总账汇率设置：按租户、币种、生效日维护相对本位币汇率。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaicaiwu_gl_exchange_rates" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "currency_code" VARCHAR(10) NOT NULL,
            "effective_date" DATE NOT NULL,
            "rate" DECIMAL(18,6) NOT NULL,
            "notes" TEXT,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_apps_kuaicaiwu_gl_exchange_rates_tenant_currency_date"
            ON "apps_kuaicaiwu_gl_exchange_rates" ("tenant_id", "currency_code", "effective_date")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_apps_kuaicaiwu_gl_exchange_rates_lookup"
            ON "apps_kuaicaiwu_gl_exchange_rates" ("tenant_id", "currency_code", "effective_date");
        COMMENT ON TABLE "apps_kuaicaiwu_gl_exchange_rates" IS '管理会计 - 汇率设置';
        COMMENT ON COLUMN "apps_kuaicaiwu_gl_exchange_rates"."rate" IS '1 单位外币 = rate 单位本位币';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaicaiwu_gl_exchange_rates";
    """
