"""继电器行业包：产线可生产自制件绑定表（上游 1048）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_ind_relay_line_products" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "production_line_id" INT NOT NULL,
            "product_id" INT NOT NULL,
            "product_code" VARCHAR(50),
            "product_name" VARCHAR(200),
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_line_prod_tenant"
            ON "apps_ind_relay_line_products" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_line_prod_line"
            ON "apps_ind_relay_line_products" ("production_line_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_line_prod_product"
            ON "apps_ind_relay_line_products" ("product_id");
        CREATE INDEX IF NOT EXISTS "idx_ind_relay_line_prod_uuid"
            ON "apps_ind_relay_line_products" ("uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_ind_relay_line_prod_active"
            ON "apps_ind_relay_line_products" ("tenant_id", "production_line_id", "product_id")
            WHERE "deleted_at" IS NULL;
        COMMENT ON TABLE "apps_ind_relay_line_products" IS '继电器行业 - 产线可生产自制件';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_ind_relay_line_products";
    """
