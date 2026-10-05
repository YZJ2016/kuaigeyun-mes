"""
设备编码唯一约束改为未删除行部分索引，并回填空设备性质为通用设备。

软删行仍占用 (tenant_id, code) 全表唯一时，台账列表空白、导入却报「编码已存在」。
未填性质的设备被「通用设备」页签精确过滤，同样看不见。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DO $migration$
        DECLARE
            r RECORD;
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'apps_kuaizhizao_equipment'
            ) THEN
                RETURN;
            END IF;

            FOR r IN
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = 'apps_kuaizhizao_equipment'
                  AND c.contype = 'u'
                  AND pg_get_constraintdef(c.oid) LIKE '%tenant_id%'
                  AND pg_get_constraintdef(c.oid) LIKE '%code%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE apps_kuaizhizao_equipment DROP CONSTRAINT IF EXISTS %I',
                    r.conname
                );
            END LOOP;

            FOR r IN
                SELECT i.relname AS idx_name
                FROM pg_index x
                JOIN pg_class t ON t.oid = x.indrelid
                JOIN pg_class i ON i.oid = x.indexrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = 'apps_kuaizhizao_equipment'
                  AND x.indisunique
                  AND NOT x.indisprimary
                  AND x.indpred IS NULL
                  AND x.indnkeyatts = 2
                  AND EXISTS (
                      SELECT 1 FROM pg_attribute a
                      WHERE a.attrelid = t.oid AND a.attnum = x.indkey[0] AND a.attname = 'tenant_id'
                  )
                  AND EXISTS (
                      SELECT 1 FROM pg_attribute a
                      WHERE a.attrelid = t.oid AND a.attnum = x.indkey[1] AND a.attname = 'code'
                  )
            LOOP
                EXECUTE format('DROP INDEX IF EXISTS %I', r.idx_name);
            END LOOP;
        END
        $migration$;

        CREATE UNIQUE INDEX IF NOT EXISTS "uid_kuaizhizao_equipment_code_active"
            ON "apps_kuaizhizao_equipment" ("tenant_id", "code")
            WHERE "deleted_at" IS NULL;

        UPDATE "apps_kuaizhizao_equipment"
        SET "equipment_nature" = '通用设备',
            "updated_at" = NOW()
        WHERE "deleted_at" IS NULL
          AND ("equipment_nature" IS NULL OR btrim("equipment_nature") = '');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_kuaizhizao_equipment_code_active";
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_apps_kuaizh_tenant__equipment_code"
            ON "apps_kuaizhizao_equipment" ("tenant_id", "code");
    """
