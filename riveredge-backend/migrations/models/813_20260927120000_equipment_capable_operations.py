"""
设备台账：可加工关联工序

apps_kuaizhizao_equipment 增加：
- capable_operation_ids（JSON 工序 ID 列表）
- capable_operations（JSON 工序快照 [{id, code, name}]）
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DO $migration$
        DECLARE
            tbl_name TEXT;
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'apps_kuaizhizao_equipment'
            ) THEN
                tbl_name := 'apps_kuaizhizao_equipment';
            ELSIF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'core_equipment'
            ) THEN
                tbl_name := 'core_equipment';
            ELSE
                RETURN;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = tbl_name AND column_name = 'capable_operation_ids'
            ) THEN
                EXECUTE format(
                    'ALTER TABLE %I ADD COLUMN "capable_operation_ids" JSONB NULL',
                    tbl_name
                );
                EXECUTE format(
                    'COMMENT ON COLUMN %I."capable_operation_ids" IS ''可加工工序ID列表''',
                    tbl_name
                );
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = tbl_name AND column_name = 'capable_operations'
            ) THEN
                EXECUTE format(
                    'ALTER TABLE %I ADD COLUMN "capable_operations" JSONB NULL',
                    tbl_name
                );
                EXECUTE format(
                    'COMMENT ON COLUMN %I."capable_operations" IS ''可加工工序快照 [{id, code, name}]''',
                    tbl_name
                );
            END IF;
        END $migration$;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DO $migration$
        DECLARE
            tbl_name TEXT;
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'apps_kuaizhizao_equipment'
            ) THEN
                tbl_name := 'apps_kuaizhizao_equipment';
            ELSIF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'core_equipment'
            ) THEN
                tbl_name := 'core_equipment';
            ELSE
                RETURN;
            END IF;

            EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS "capable_operations"', tbl_name);
            EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS "capable_operation_ids"', tbl_name);
        END $migration$;
    """
