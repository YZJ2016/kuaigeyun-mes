"""
再次将物料 base_unit 从单位编码回填为名称。

876 已做过一轮；物料同步 resolve 曾误返回 unit.code，导致再次写入 004/007 等编码。
写路径已改回名称；本迁移补回填存量。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    await db.execute_script(
        """
        UPDATE "apps_master_data_materials" AS m
        SET "base_unit" = u."name"
        FROM "apps_master_data_units" AS u
        WHERE m."deleted_at" IS NULL
          AND u."deleted_at" IS NULL
          AND m."tenant_id" = u."tenant_id"
          AND m."base_unit" = u."code"
          AND u."code" IS DISTINCT FROM u."name"
          AND COALESCE(btrim(u."name"), '') <> '';
        """
    )
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "SELECT 1;"
