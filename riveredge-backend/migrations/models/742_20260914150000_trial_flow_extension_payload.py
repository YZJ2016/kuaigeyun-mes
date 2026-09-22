"""试流单 extension_payload（profile 头字段溢出唯一落点）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_trial_flows"
            ADD COLUMN IF NOT EXISTS "extension_payload" JSONB;
        COMMENT ON COLUMN "apps_kuaiplm_trial_flows"."extension_payload"
            IS '行业扩展载荷（header_fields 等）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiplm_trial_flows"
            DROP COLUMN IF EXISTS "extension_payload";
    """
