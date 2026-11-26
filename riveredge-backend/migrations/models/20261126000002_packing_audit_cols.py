"""装箱绑定明细 / 箱规表补齐 BaseModel 审计列（created_by / updated_by 等）。

20261125120015 建表时只写了 created_at/updated_at，详情查 PackingBindingLine 会因 SELECT updated_by 失败。
对应上游 1016_20261109143000_packing_binding_lines_audit_cols.py。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DO $$
        BEGIN
            IF to_regclass('public.apps_kuaizhizao_packing_binding_lines') IS NOT NULL THEN
                ALTER TABLE "apps_kuaizhizao_packing_binding_lines"
                    ADD COLUMN IF NOT EXISTS "created_by" INT,
                    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS "updated_by" INT,
                    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
            END IF;
            IF to_regclass('public.apps_kuaizhizao_packing_profiles') IS NOT NULL THEN
                ALTER TABLE "apps_kuaizhizao_packing_profiles"
                    ADD COLUMN IF NOT EXISTS "created_by" INT,
                    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS "updated_by" INT,
                    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
            END IF;
        END $$;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_packing_binding_lines"
            DROP COLUMN IF EXISTS "created_by",
            DROP COLUMN IF EXISTS "created_by_name",
            DROP COLUMN IF EXISTS "updated_by",
            DROP COLUMN IF EXISTS "updated_by_name";
        ALTER TABLE "apps_kuaizhizao_packing_profiles"
            DROP COLUMN IF EXISTS "created_by",
            DROP COLUMN IF EXISTS "created_by_name",
            DROP COLUMN IF EXISTS "updated_by",
            DROP COLUMN IF EXISTS "updated_by_name";
    """
