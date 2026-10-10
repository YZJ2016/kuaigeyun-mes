"""轻办公奖励登记：绩效得分（nullable，定制页展示）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaioa_reward_records"
    ADD COLUMN IF NOT EXISTS "performance_score" NUMERIC(10,2);
COMMENT ON COLUMN "apps_kuaioa_reward_records"."performance_score"
    IS '绩效得分（定制页录入）';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaioa_reward_records"
    DROP COLUMN IF EXISTS "performance_score";
"""
