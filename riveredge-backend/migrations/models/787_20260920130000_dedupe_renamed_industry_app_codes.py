"""
合并行业应用改编码产生的双份 core_applications 行。

场景：786 未跑或「扫描应用」在新 manifest 入库后又留下 kuaielectronics / industry-mold 旧行。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- ind-electronics：新旧并存 → 合并安装态，删旧行
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

        -- 仅旧 code → 原地改码
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

        -- ind-mold：新旧并存
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
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 不可逆：已软删除的旧 code 行不恢复
        SELECT 1;
    """
