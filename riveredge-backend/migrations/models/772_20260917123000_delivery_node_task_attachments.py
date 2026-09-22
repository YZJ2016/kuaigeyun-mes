"""交付项目节点子任务附件列。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    ADD COLUMN IF NOT EXISTS "attachments" JSONB;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    DROP COLUMN IF EXISTS "attachments";
"""
