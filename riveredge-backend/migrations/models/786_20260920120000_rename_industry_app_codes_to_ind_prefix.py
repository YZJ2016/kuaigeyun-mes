"""
行业免费应用编码规范化：kuaielectronics → ind-electronics，industry-mold → ind-mold。

同步应用注册、权限、菜单路径、租户配置键与模具插件表名。
新旧权限/应用并存时合并角色授权并下线旧码，避免 unique (tenant_id, code) 冲突。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 1) 应用注册：新旧并存 → 合并安装态，删旧行；仅旧 code → 原地改码
        UPDATE core_applications AS newer
        SET
            is_installed = (newer.is_installed OR older.is_installed),
            is_active = CASE
                WHEN newer.is_installed THEN newer.is_active
                WHEN older.is_installed THEN older.is_active
                ELSE newer.is_active
            END,
            entry_point = COALESCE(NULLIF(newer.entry_point, ''), '../apps/ind-electronics/index.tsx'),
            route_path = COALESCE(NULLIF(newer.route_path, ''), '/apps/ind-electronics'),
            updated_at = NOW()
        FROM core_applications AS older
        WHERE newer.code = 'ind-electronics'
          AND older.code = 'kuaielectronics'
          AND newer.tenant_id = older.tenant_id
          AND newer.deleted_at IS NULL
          AND older.deleted_at IS NULL;

        UPDATE core_applications AS old_row
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE old_row.code = 'kuaielectronics'
          AND old_row.deleted_at IS NULL
          AND EXISTS (
            SELECT 1 FROM core_applications AS newer
            WHERE newer.tenant_id = old_row.tenant_id
              AND newer.code = 'ind-electronics'
              AND newer.deleted_at IS NULL
          );

        UPDATE core_applications
        SET
            code = 'ind-electronics',
            entry_point = '../apps/ind-electronics/index.tsx',
            route_path = '/apps/ind-electronics',
            updated_at = NOW()
        WHERE code = 'kuaielectronics'
          AND deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM core_applications AS newer
            WHERE newer.tenant_id = core_applications.tenant_id
              AND newer.code = 'ind-electronics'
              AND newer.deleted_at IS NULL
          );

        UPDATE core_applications AS newer
        SET
            is_installed = (newer.is_installed OR older.is_installed),
            is_active = CASE
                WHEN newer.is_installed THEN newer.is_active
                WHEN older.is_installed THEN older.is_active
                ELSE newer.is_active
            END,
            entry_point = COALESCE(NULLIF(newer.entry_point, ''), '../apps/ind-mold/index.tsx'),
            route_path = COALESCE(NULLIF(newer.route_path, ''), '/apps/ind-mold'),
            updated_at = NOW()
        FROM core_applications AS older
        WHERE newer.code = 'ind-mold'
          AND older.code = 'industry-mold'
          AND newer.tenant_id = older.tenant_id
          AND newer.deleted_at IS NULL
          AND older.deleted_at IS NULL;

        UPDATE core_applications AS old_row
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE old_row.code = 'industry-mold'
          AND old_row.deleted_at IS NULL
          AND EXISTS (
            SELECT 1 FROM core_applications AS newer
            WHERE newer.tenant_id = old_row.tenant_id
              AND newer.code = 'ind-mold'
              AND newer.deleted_at IS NULL
          );

        UPDATE core_applications
        SET
            code = 'ind-mold',
            entry_point = '../apps/ind-mold/index.tsx',
            route_path = '/apps/ind-mold',
            updated_at = NOW()
        WHERE code = 'industry-mold'
          AND deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM core_applications AS newer
            WHERE newer.tenant_id = core_applications.tenant_id
              AND newer.code = 'ind-mold'
              AND newer.deleted_at IS NULL
          );

        -- 2) 权限码：无 ind 对端则原地改前缀；对端已存在则迁角色授权后下线旧码
        UPDATE core_permissions
        SET
            code = REPLACE(code, 'kuaielectronics:', 'ind-electronics:'),
            resource = REPLACE(resource, 'kuaielectronics:', 'ind-electronics:'),
            description = REPLACE(COALESCE(description, ''), 'kuaielectronics:', 'ind-electronics:'),
            source_app = CASE WHEN source_app = 'kuaielectronics' THEN 'ind-electronics' ELSE source_app END,
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'kuaielectronics:%'
          AND NOT EXISTS (
            SELECT 1 FROM core_permissions AS newer
            WHERE newer.tenant_id = core_permissions.tenant_id
              AND newer.deleted_at IS NULL
              AND newer.code = REPLACE(core_permissions.code, 'kuaielectronics:', 'ind-electronics:')
          );

        INSERT INTO core_role_permissions (role_id, permission_id, created_at)
        SELECT rp.role_id, newer.id, NOW()
        FROM core_permissions AS old
        JOIN core_permissions AS newer
          ON newer.tenant_id = old.tenant_id
         AND newer.deleted_at IS NULL
         AND newer.code = REPLACE(old.code, 'kuaielectronics:', 'ind-electronics:')
        JOIN core_role_permissions AS rp
          ON rp.permission_id = old.id
        WHERE old.deleted_at IS NULL
          AND old.code LIKE 'kuaielectronics:%'
          AND NOT EXISTS (
            SELECT 1 FROM core_role_permissions AS rp2
            WHERE rp2.role_id = rp.role_id
              AND rp2.permission_id = newer.id
          );

        UPDATE core_permissions
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'kuaielectronics:%';

        UPDATE core_permissions
        SET source_app = 'ind-electronics', updated_at = NOW()
        WHERE source_app = 'kuaielectronics';

        UPDATE core_permissions
        SET
            code = REPLACE(code, 'industry-mold:', 'ind-mold:'),
            resource = REPLACE(resource, 'industry-mold:', 'ind-mold:'),
            description = REPLACE(COALESCE(description, ''), 'industry-mold:', 'ind-mold:'),
            source_app = CASE WHEN source_app = 'industry-mold' THEN 'ind-mold' ELSE source_app END,
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'industry-mold:%'
          AND NOT EXISTS (
            SELECT 1 FROM core_permissions AS newer
            WHERE newer.tenant_id = core_permissions.tenant_id
              AND newer.deleted_at IS NULL
              AND newer.code = REPLACE(core_permissions.code, 'industry-mold:', 'ind-mold:')
          );

        INSERT INTO core_role_permissions (role_id, permission_id, created_at)
        SELECT rp.role_id, newer.id, NOW()
        FROM core_permissions AS old
        JOIN core_permissions AS newer
          ON newer.tenant_id = old.tenant_id
         AND newer.deleted_at IS NULL
         AND newer.code = REPLACE(old.code, 'industry-mold:', 'ind-mold:')
        JOIN core_role_permissions AS rp
          ON rp.permission_id = old.id
        WHERE old.deleted_at IS NULL
          AND old.code LIKE 'industry-mold:%'
          AND NOT EXISTS (
            SELECT 1 FROM core_role_permissions AS rp2
            WHERE rp2.role_id = rp.role_id
              AND rp2.permission_id = newer.id
          );

        UPDATE core_permissions
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'industry-mold:%';

        UPDATE core_permissions
        SET source_app = 'ind-mold', updated_at = NOW()
        WHERE source_app = 'industry-mold';

        -- 3) 数据权限策略
        UPDATE core_data_permission_policies
        SET
            resource = REPLACE(resource, 'kuaielectronics:', 'ind-electronics:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND resource LIKE '%kuaielectronics:%';

        UPDATE core_data_permission_policies
        SET
            resource = REPLACE(resource, 'industry-mold:', 'ind-mold:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND resource LIKE '%industry-mold:%';

        -- 4) 菜单 path / permission
        UPDATE core_menus
        SET
            path = REPLACE(path, '/apps/kuaielectronics', '/apps/ind-electronics'),
            permission_code = REPLACE(permission_code, 'kuaielectronics:', 'ind-electronics:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND (
            path LIKE '/apps/kuaielectronics%'
            OR permission_code LIKE 'kuaielectronics:%'
          );

        UPDATE core_menus
        SET
            path = REPLACE(path, '/apps/industry-mold', '/apps/ind-mold'),
            permission_code = REPLACE(permission_code, 'industry-mold:', 'ind-mold:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND (
            path LIKE '/apps/industry-mold%'
            OR permission_code LIKE 'industry-mold:%'
          );

        -- 5) 租户配置键（ESD / profile）
        UPDATE infra_tenant_configs
        SET
            config_key = 'industry.ext.electronics.esd',
            updated_at = NOW()
        WHERE config_key = 'industry.ext.kuaielectronics.esd';

        UPDATE infra_tenant_configs
        SET
            config_key = 'ind-electronics.label_oem',
            updated_at = NOW()
        WHERE config_key = 'kuaielectronics.label_oem';

        -- 6) 模具插件表名（781 历史表名 → ind_mold）
        ALTER TABLE IF EXISTS "apps_industry_mold_program_sheets"
            RENAME TO "apps_ind_mold_program_sheets";
        ALTER TABLE IF EXISTS "apps_industry_mold_material_arrivals"
            RENAME TO "apps_ind_mold_material_arrivals";
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE IF EXISTS "apps_ind_mold_program_sheets"
            RENAME TO "apps_industry_mold_program_sheets";
        ALTER TABLE IF EXISTS "apps_ind_mold_material_arrivals"
            RENAME TO "apps_industry_mold_material_arrivals";

        UPDATE infra_tenant_configs
        SET config_key = 'industry.ext.kuaielectronics.esd', updated_at = NOW()
        WHERE config_key = 'industry.ext.electronics.esd';

        UPDATE infra_tenant_configs
        SET config_key = 'kuaielectronics.label_oem', updated_at = NOW()
        WHERE config_key = 'ind-electronics.label_oem';

        UPDATE core_menus
        SET
            path = REPLACE(path, '/apps/ind-electronics', '/apps/kuaielectronics'),
            permission_code = REPLACE(permission_code, 'ind-electronics:', 'kuaielectronics:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND path LIKE '/apps/ind-electronics%';

        UPDATE core_menus
        SET
            path = REPLACE(path, '/apps/ind-mold', '/apps/industry-mold'),
            permission_code = REPLACE(permission_code, 'ind-mold:', 'industry-mold:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND path LIKE '/apps/ind-mold%';

        UPDATE core_data_permission_policies
        SET resource = REPLACE(resource, 'ind-electronics:', 'kuaielectronics:'), updated_at = NOW()
        WHERE deleted_at IS NULL AND resource LIKE '%ind-electronics:%';

        UPDATE core_data_permission_policies
        SET resource = REPLACE(resource, 'ind-mold:', 'industry-mold:'), updated_at = NOW()
        WHERE deleted_at IS NULL AND resource LIKE '%ind-mold:%';

        UPDATE core_permissions
        SET
            code = REPLACE(code, 'ind-electronics:', 'kuaielectronics:'),
            resource = REPLACE(resource, 'ind-electronics:', 'kuaielectronics:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL AND code LIKE 'ind-electronics:%';

        UPDATE core_permissions
        SET
            code = REPLACE(code, 'ind-mold:', 'industry-mold:'),
            resource = REPLACE(resource, 'ind-mold:', 'industry-mold:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL AND code LIKE 'ind-mold:%';

        UPDATE core_applications
        SET
            code = 'kuaielectronics',
            entry_point = '../apps/kuaielectronics/index.tsx',
            route_path = '/apps/kuaielectronics',
            updated_at = NOW()
        WHERE code = 'ind-electronics' AND deleted_at IS NULL;

        UPDATE core_applications
        SET
            code = 'industry-mold',
            entry_point = '../apps/industry-mold/index.tsx',
            route_path = '/apps/industry-mold',
            updated_at = NOW()
        WHERE code = 'ind-mold' AND deleted_at IS NULL;
    """
