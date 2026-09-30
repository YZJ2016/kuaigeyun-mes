"""模具维修单增加紧急程度列，前端已发送该字段此前被静默丢弃。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_mold_repairs"
            ADD COLUMN IF NOT EXISTS "urgency" VARCHAR(32);
        COMMENT ON COLUMN "apps_kuaizhizao_mold_repairs"."urgency" IS '紧急程度';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_mold_repairs" DROP COLUMN IF EXISTS "urgency";
    """
