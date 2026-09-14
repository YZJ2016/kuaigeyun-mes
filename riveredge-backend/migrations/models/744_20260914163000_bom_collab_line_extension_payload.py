"""BOM 协同明细行 extension_payload（行业 profile 溢出字段）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_bom_collaboration_lines"
            ADD COLUMN IF NOT EXISTS "extension_payload" JSONB;
        COMMENT ON COLUMN "apps_kuaiplm_bom_collaboration_lines"."extension_payload"
            IS 'BOM 协同行行业扩展载荷';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_bom_collaboration_lines"
            DROP COLUMN IF EXISTS "extension_payload";
    """
