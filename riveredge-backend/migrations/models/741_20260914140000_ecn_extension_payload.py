"""ECN 头表与物料行 extension_payload（行业溢出字段唯一落点）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_engineering_changes"
            ADD COLUMN IF NOT EXISTS "extension_payload" JSONB;
        COMMENT ON COLUMN "apps_kuaiplm_engineering_changes"."extension_payload"
            IS '行业扩展载荷（header_option_flags 等）';

        ALTER TABLE "apps_kuaiplm_ecn_material_lines"
            ADD COLUMN IF NOT EXISTS "extension_payload" JSONB;
        COMMENT ON COLUMN "apps_kuaiplm_ecn_material_lines"."extension_payload"
            IS '行业扩展载荷（profile 列溢出字段）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_ecn_material_lines"
            DROP COLUMN IF EXISTS "extension_payload";
        ALTER TABLE "apps_kuaiplm_engineering_changes"
            DROP COLUMN IF EXISTS "extension_payload";
    """
