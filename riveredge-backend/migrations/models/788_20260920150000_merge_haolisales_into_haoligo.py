"""
销售跟踪并入好力 GO：权限码 haolisales:* → haoligo:*，退役独立应用注册。

表名 haolisales_* 不变。禁止新旧权限码并存。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 1) 权限码：无 haoligo 对端则原地改前缀
        UPDATE core_permissions
        SET
            code = REPLACE(code, 'haolisales:', 'haoligo:'),
            resource = REPLACE(resource, 'haolisales:', 'haoligo:'),
            description = REPLACE(COALESCE(description, ''), 'haolisales:', 'haoligo:'),
            source_app = CASE WHEN source_app = 'haolisales' THEN 'haoligo' ELSE source_app END,
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'haolisales:%'
          AND NOT EXISTS (
            SELECT 1 FROM core_permissions AS newer
            WHERE newer.tenant_id = core_permissions.tenant_id
              AND newer.deleted_at IS NULL
              AND newer.code = REPLACE(core_permissions.code, 'haolisales:', 'haoligo:')
          );

        -- 2) 对端已存在：把角色授权迁到 haoligo 码，再下线旧码
        INSERT INTO core_role_permissions (role_id, permission_id, created_at)
        SELECT rp.role_id, newer.id, NOW()
        FROM core_permissions AS old
        JOIN core_permissions AS newer
          ON newer.tenant_id = old.tenant_id
         AND newer.deleted_at IS NULL
         AND newer.code = REPLACE(old.code, 'haolisales:', 'haoligo:')
        JOIN core_role_permissions AS rp
          ON rp.permission_id = old.id
        WHERE old.deleted_at IS NULL
          AND old.code LIKE 'haolisales:%'
          AND NOT EXISTS (
            SELECT 1 FROM core_role_permissions AS rp2
            WHERE rp2.role_id = rp.role_id
              AND rp2.permission_id = newer.id
          );

        UPDATE core_permissions
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'haolisales:%';

        UPDATE core_permissions
        SET source_app = 'haoligo', updated_at = NOW()
        WHERE source_app = 'haolisales';

        -- 3) 数据权限策略
        UPDATE core_data_permission_policies
        SET
            resource = REPLACE(resource, 'haolisales:', 'haoligo:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND resource LIKE '%haolisales:%';

        -- 4) 旧销售跟踪菜单下线（新菜单由 haoligo manifest 同步）
        UPDATE core_menus AS m
        SET deleted_at = NOW(), updated_at = NOW()
        FROM core_applications AS a
        WHERE m.application_uuid = a.uuid
          AND a.code = 'haolisales'
          AND m.deleted_at IS NULL;

        UPDATE core_menus
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE deleted_at IS NULL
          AND (
            path LIKE '/apps/haolisales%'
            OR permission_code LIKE 'haolisales:%'
          );

        -- 5) 退役独立应用
        UPDATE core_applications
        SET
            is_active = FALSE,
            is_installed = FALSE,
            deleted_at = NOW(),
            updated_at = NOW()
        WHERE code = 'haolisales'
          AND deleted_at IS NULL;

        DELETE FROM core_application_dedicated_bindings
        WHERE app_code = 'haolisales';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 销售跟踪已并入 haoligo，禁止把独立应用还原回来。
        SELECT 1;
    """
