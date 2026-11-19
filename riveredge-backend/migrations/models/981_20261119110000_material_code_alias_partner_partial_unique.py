"""物料编号别名唯一：客商类型纳入 external_entity_id，并改为软删 partial unique。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_material_code_aliases"
            DROP CONSTRAINT IF EXISTS "uid_apps_master_tenant__2e2957";
        DROP INDEX IF EXISTS "uid_apps_master_tenant__2e2957";

        CREATE UNIQUE INDEX IF NOT EXISTS "uid_material_code_alias_dept_active"
        ON "apps_master_data_material_code_aliases" ("tenant_id", "code_type", "code")
        WHERE "deleted_at" IS NULL
          AND "code_type" NOT IN ('CUSTOMER', 'SUPPLIER');

        CREATE UNIQUE INDEX IF NOT EXISTS "uid_material_code_alias_partner_active"
        ON "apps_master_data_material_code_aliases"
            ("tenant_id", "code_type", "code", "external_entity_id")
        WHERE "deleted_at" IS NULL
          AND "code_type" IN ('CUSTOMER', 'SUPPLIER')
          AND "external_entity_id" IS NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_material_code_alias_partner_active";
        DROP INDEX IF EXISTS "uid_material_code_alias_dept_active";
        ALTER TABLE "apps_master_data_material_code_aliases"
            DROP CONSTRAINT IF EXISTS "uid_apps_master_tenant__2e2957";
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_apps_master_tenant__2e2957"
        ON "apps_master_data_material_code_aliases" ("tenant_id", "code_type", "code");
    """
