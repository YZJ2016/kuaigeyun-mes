"""交付节点子任务与模板预置任务增加核心任务字段。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    ADD COLUMN IF NOT EXISTS "core_task" VARCHAR(500);

ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    ADD COLUMN IF NOT EXISTS "core_task" VARCHAR(500);
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    DROP COLUMN IF EXISTS "core_task";

ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    DROP COLUMN IF EXISTS "core_task";
"""
