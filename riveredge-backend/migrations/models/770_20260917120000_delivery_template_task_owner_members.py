"""交付流程模板预置子任务支持负责人与成员。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    ADD COLUMN IF NOT EXISTS "owner_id" INT,
    ADD COLUMN IF NOT EXISTS "owner_name" VARCHAR(100),
    ADD COLUMN IF NOT EXISTS "members_json" JSONB;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    DROP COLUMN IF EXISTS "members_json",
    DROP COLUMN IF EXISTS "owner_name",
    DROP COLUMN IF EXISTS "owner_id";
"""
