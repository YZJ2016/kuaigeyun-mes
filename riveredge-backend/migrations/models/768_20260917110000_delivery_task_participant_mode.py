"""交付节点任务：协作方式与关联人员操作记录。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    ADD COLUMN IF NOT EXISTS "participant_mode" VARCHAR(20) NOT NULL DEFAULT 'solo';

ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    ADD COLUMN IF NOT EXISTS "participant_mode" VARCHAR(20) NOT NULL DEFAULT 'solo',
    ADD COLUMN IF NOT EXISTS "participant_actions_json" JSONB;

UPDATE "apps_kuaizhizao_delivery_process_template_node_tasks"
SET "participant_mode" = 'signoff_all'
WHERE "task_key" = 'review_confirm';

UPDATE "apps_kuaizhizao_delivery_project_node_tasks"
SET "participant_mode" = 'signoff_all'
WHERE "task_key" = 'review_confirm'
  AND "participant_mode" = 'solo';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    DROP COLUMN IF EXISTS "participant_actions_json",
    DROP COLUMN IF EXISTS "participant_mode";

ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    DROP COLUMN IF EXISTS "participant_mode";
"""
