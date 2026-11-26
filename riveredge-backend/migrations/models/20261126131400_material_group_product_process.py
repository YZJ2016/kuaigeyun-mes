from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_master_data_material_group_product_process" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "material_group_id" INT NOT NULL,
            "process_route_id" INT,
            "allow_operation_jump" BOOL NOT NULL DEFAULT FALSE,
            "lines" JSONB NOT NULL DEFAULT '[]',
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_mgpp_tenant_group"
            ON "apps_master_data_material_group_product_process" ("tenant_id", "material_group_id")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_mgpp_tenant"
            ON "apps_master_data_material_group_product_process" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_mgpp_uuid"
            ON "apps_master_data_material_group_product_process" ("uuid");
        COMMENT ON TABLE "apps_master_data_material_group_product_process" IS '基础数据管理 - 物料分组产品工艺';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_master_data_material_group_product_process";
    """

# 对应上游 1033_20261115140000_material_group_product_process.py
