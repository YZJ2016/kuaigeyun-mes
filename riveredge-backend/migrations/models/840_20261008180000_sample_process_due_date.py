"""样品加工（L36）：期望交期独立字段 due_date。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_sample_process_applications"
    ADD COLUMN IF NOT EXISTS "due_date" DATE;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_sample_process_applications"
    DROP COLUMN IF EXISTS "due_date";
"""
