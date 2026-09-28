"""把 core_scheduled_tasks.type 加长到 64，以容纳 kuaireport_report_subscription。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_scheduled_tasks"
    ALTER COLUMN "type" TYPE VARCHAR(64);
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_scheduled_tasks"
    ALTER COLUMN "type" TYPE VARCHAR(20);
"""
