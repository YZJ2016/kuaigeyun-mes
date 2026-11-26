"""
存量角色补 :display 授权（access_control fail-closed 配套）。

迁移 864 只为 5 个 system:* 资源补过 display；宿主页跨模块读切 fail-closed 后，
存量角色对 material/customer/warehouse 等下拉所需 ``app:resource:display``
未显式勾选时会 403。

本迁移按资源级对齐：角色在同一租户下已持有 ``app:resource:<非 display 动作>``
授权且对应 ``app:resource:display`` 权限码存在时，补插该 display 授权。
幂等（NOT EXISTS），不新建空角色授权；之后取消勾选不再被同步强制恢复。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        INSERT INTO core_role_permissions (role_id, permission_id, created_at)
        SELECT DISTINCT rp.role_id, pd.id, NOW()
        FROM core_role_permissions rp
        JOIN core_roles r
          ON r.id = rp.role_id
         AND r.deleted_at IS NULL
        JOIN core_permissions p
          ON p.id = rp.permission_id
         AND p.deleted_at IS NULL
        JOIN core_permissions pd
          ON pd.tenant_id = p.tenant_id
         AND pd.deleted_at IS NULL
         AND pd.deprecated_at IS NULL
         AND pd.code = regexp_replace(p.code, ':[^:]+$', ':display')
        WHERE p.code LIKE '%:%:%'
          AND p.code NOT LIKE '%:display'
          AND NOT EXISTS (
            SELECT 1
            FROM core_role_permissions x
            WHERE x.role_id = rp.role_id
              AND x.permission_id = pd.id
          );

        UPDATE core_permission_versions
        SET version = version + 1
        WHERE user_id IS NULL;

        -- 无租户级版本行的租户补插 version=2：get_version 对缺行恒返回 1，
        -- 不补则本次新增授权在 effective_access 缓存（1800s TTL）内不可见
        INSERT INTO core_permission_versions (tenant_id, user_id, version, updated_at)
        SELECT DISTINCT r.tenant_id, NULL, 2, NOW()
        FROM core_roles r
        WHERE r.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1
            FROM core_permission_versions v
            WHERE v.tenant_id = r.tenant_id
              AND v.user_id IS NULL
          );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        SELECT 1;
    """
