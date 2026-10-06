"""校准车间表自增主键序列。

造数/导入若写入显式 id 而未 setval，后续新建会撞 pkey，
却被误报成「车间编码已存在」。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DO $migration$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'S'
                  AND c.relname = 'apps_master_data_workshops_id_seq'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'apps_master_data_workshops'
            ) THEN
                PERFORM setval(
                    'apps_master_data_workshops_id_seq',
                    COALESCE((SELECT MAX(id) FROM apps_master_data_workshops), 1),
                    EXISTS (SELECT 1 FROM apps_master_data_workshops)
                );
            END IF;
        END
        $migration$;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        SELECT 1;
    """
