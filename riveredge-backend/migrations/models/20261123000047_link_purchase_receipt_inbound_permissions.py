"""
采购入库单与入库管理共用同一组功能权限。

历史租户的采购管理入口可能仍绑定旧资源权限，导致角色矩阵中“采购入库单”
与“入库管理”的勾选状态彼此独立。迁移现有角色授权后，将两个菜单入口统一
绑定到 kuaizhizao:inbound:read。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TEMP TABLE _purchase_receipt_inbound_permission_map ON COMMIT DROP AS
        SELECT DISTINCT
            m.tenant_id,
            LOWER(BTRIM(m.permission_code)) AS old_read_code,
            REGEXP_REPLACE(
                LOWER(BTRIM(m.permission_code)),
                ':[^:]+$',
                ''
            ) AS old_prefix
        FROM core_menus m
        WHERE m.deleted_at IS NULL
          AND m.path IN (
              '/apps/kuaizhizao/purchase-management/inbound',
              '/apps/kuaizhizao/warehouse-management/inbound'
          )
          AND COALESCE(BTRIM(m.permission_code), '') <> ''
          AND LOWER(BTRIM(m.permission_code)) <> 'kuaizhizao:inbound:read';

        INSERT INTO core_role_permissions (role_id, permission_id, created_at)
        SELECT DISTINCT
            rp.role_id,
            target_permission.id,
            NOW()
        FROM _purchase_receipt_inbound_permission_map mapping
        JOIN core_permissions old_permission
          ON old_permission.tenant_id = mapping.tenant_id
         AND old_permission.deleted_at IS NULL
         AND LOWER(BTRIM(old_permission.code)) LIKE mapping.old_prefix || ':%'
        JOIN core_role_permissions rp
          ON rp.permission_id = old_permission.id
        JOIN core_permissions target_permission
          ON target_permission.tenant_id = mapping.tenant_id
         AND target_permission.deleted_at IS NULL
         AND LOWER(BTRIM(target_permission.code)) =
             'kuaizhizao:inbound:' || LOWER(BTRIM(old_permission.action))
        WHERE NOT EXISTS (
            SELECT 1
            FROM core_role_permissions existing
            WHERE existing.role_id = rp.role_id
              AND existing.permission_id = target_permission.id
        );

        UPDATE core_menus
        SET permission_code = 'kuaizhizao:inbound:read',
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND path IN (
              '/apps/kuaizhizao/purchase-management/inbound',
              '/apps/kuaizhizao/warehouse-management/inbound'
          )
          AND LOWER(BTRIM(COALESCE(permission_code, '')))
              <> 'kuaizhizao:inbound:read';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    """历史权限来源不唯一，无法可靠反推，降级保持 no-op。"""
    return "-- purchase receipt and inbound permission link: no-op downgrade"
