"""权限版本：租户级（user_id IS NULL）去重并补部分唯一索引。

PostgreSQL 普通 UNIQUE(tenant_id, user_id) 允许多条 NULL user_id，
导致 PermissionVersion.get_or_none / bump 抛 MultipleObjectsReturned，
角色功能权限保存等路径 500。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 非空 user_id：保留 version 最大、同 version 保留 id 最大
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, user_id
                       ORDER BY version DESC, id DESC
                   ) AS rn
            FROM core_permission_versions
            WHERE user_id IS NOT NULL
        )
        DELETE FROM core_permission_versions AS p
        USING ranked AS r
        WHERE p.id = r.id AND r.rn > 1;

        -- 租户级（user_id IS NULL）：同上规则去重
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id
                       ORDER BY version DESC, id DESC
                   ) AS rn
            FROM core_permission_versions
            WHERE user_id IS NULL
        )
        DELETE FROM core_permission_versions AS p
        USING ranked AS r
        WHERE p.id = r.id AND r.rn > 1;

        CREATE UNIQUE INDEX IF NOT EXISTS "uq_permission_versions_tenant_null_user"
            ON "core_permission_versions" ("tenant_id")
            WHERE "user_id" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uq_permission_versions_tenant_null_user";
    """
