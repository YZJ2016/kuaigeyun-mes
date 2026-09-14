"""质量投诉 extension_payload（R-11 模板对齐扩展字段唯一落点）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_quality_complaints"
            ADD COLUMN IF NOT EXISTS "extension_payload" JSONB;
        COMMENT ON COLUMN "apps_kuaizhizao_quality_complaints"."extension_payload"
            IS '质量投诉扩展载荷（检验数量/不良/根因对策等）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_quality_complaints"
            DROP COLUMN IF EXISTS "extension_payload";
    """
