"""回填菜单管理手工停用标记 meta.tenant_disabled。

应用仍启用、菜单已停用、且非接管/行业包/定制壳抑制的行，视为租户在菜单管理中的停用意图。
应用启用与接管恢复将跳过带此标记的菜单。

上游同步：1049_20261118090000_menu_tenant_disabled_meta
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE core_menus AS m
           SET meta = COALESCE(m.meta, '{}'::jsonb) || '{"tenant_disabled": true}'::jsonb,
               updated_at = NOW()
          FROM core_applications AS a
         WHERE m.tenant_id = a.tenant_id
           AND m.application_uuid = a.uuid
           AND m.deleted_at IS NULL
           AND a.deleted_at IS NULL
           AND a.is_installed = TRUE
           AND a.is_active = TRUE
           AND m.is_active = FALSE
           AND COALESCE(m.meta->>'tenant_disabled', 'false') <> 'true'
           AND COALESCE(m.meta->>'suppressed_by_takeover', '') = ''
           AND COALESCE(m.meta->>'suppressed_by_industry_pack', '') = ''
           AND COALESCE(m.meta->>'suppressed_by_dedicated_shell', '') = '';

        UPDATE core_menus
           SET meta = COALESCE(meta, '{}'::jsonb) || '{"tenant_disabled": true}'::jsonb,
               updated_at = NOW()
         WHERE deleted_at IS NULL
           AND application_uuid IS NULL
           AND is_active = FALSE
           AND COALESCE(meta->>'tenant_disabled', 'false') <> 'true'
           AND COALESCE(meta->>'suppressed_by_takeover', '') = ''
           AND COALESCE(meta->>'suppressed_by_industry_pack', '') = ''
           AND COALESCE(meta->>'suppressed_by_dedicated_shell', '') = '';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE core_menus
           SET meta = meta - 'tenant_disabled',
               updated_at = NOW()
         WHERE meta ? 'tenant_disabled';
    """
