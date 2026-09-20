"""
行业免费应用编码规范化：kuaielectronics → ind-electronics，industry-mold → ind-mold。

同步应用注册、权限、菜单路径、租户配置键与模具插件表名。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 1) 应用注册
        UPDATE core_applications
        SET
            code = 'ind-electronics',
            entry_point = '../apps/ind-electronics/index.tsx',
            route_path = '/apps/ind-electronics',
            updated_at = NOW()
        WHERE code = 'kuaielectronics' AND deleted_at IS NULL;

        UPDATE core_applications
        SET
            code = 'ind-mold',
            entry_point = '../apps/ind-mold/index.tsx',
            route_path = '/apps/ind-mold',
            updated_at = NOW()
        WHERE code = 'industry-mold' AND deleted_at IS NULL;

        -- 2) 权限码
        UPDATE core_permissions
        SET
            code = REPLACE(code, 'kuaielectronics:', 'ind-electronics:'),
            resource = REPLACE(resource, 'kuaielectronics:', 'ind-electronics:'),
            description = REPLACE(COALESCE(description, ''), 'kuaielectronics:', 'ind-electronics:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'kuaielectronics:%';

        UPDATE core_permissions
        SET
            code = REPLACE(code, 'industry-mold:', 'ind-mold:'),
            resource = REPLACE(resource, 'industry-mold:', 'ind-mold:'),
            description = REPLACE(COALESCE(description, ''), 'industry-mold:', 'ind-mold:'),
            updated_at = NOW()
        WHERE deleted_at IS NULL
          AND code LIKE 'industry-mold:%';

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
