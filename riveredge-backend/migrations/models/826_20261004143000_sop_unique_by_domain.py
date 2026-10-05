"""SOP 编码唯一改为组织 + 业务域 + 编码 + 版本。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_apps_master_data_sop_tenant_code";
        DROP INDEX IF EXISTS "idx_apps_master_data_sop_tenant_code_version";
        CREATE UNIQUE INDEX IF NOT EXISTS "idx_apps_master_data_sop_tenant_domain_code_version"
            ON "apps_master_data_sop" ("tenant_id", "sop_domain", "code", "version")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_apps_master_data_sop_tenant_domain_code_version";
        CREATE UNIQUE INDEX IF NOT EXISTS "idx_apps_master_data_sop_tenant_code_version"
            ON "apps_master_data_sop" ("tenant_id", "code", "version")
            WHERE "deleted_at" IS NULL;
    """
