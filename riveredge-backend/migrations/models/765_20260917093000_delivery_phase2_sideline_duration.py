"""交付项目 Phase2：规格档位工期、旁线主从、工单回写所需字段。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_process_template_nodes"
    ADD COLUMN IF NOT EXISTS "duration_rules" JSONB;

ALTER TABLE "apps_kuaizhizao_delivery_projects"
    ADD COLUMN IF NOT EXISTS "parent_project_id" INT,
    ADD COLUMN IF NOT EXISTS "parent_sync_task_key" VARCHAR(50),
    ADD COLUMN IF NOT EXISTS "line_role" VARCHAR(20) NOT NULL DEFAULT 'main';
CREATE INDEX IF NOT EXISTS "idx_kz_delivery_proj_parent"
    ON "apps_kuaizhizao_delivery_projects" ("tenant_id", "parent_project_id");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX IF EXISTS "idx_kz_delivery_proj_parent";
ALTER TABLE "apps_kuaizhizao_delivery_projects"
    DROP COLUMN IF EXISTS "line_role",
    DROP COLUMN IF EXISTS "parent_sync_task_key",
    DROP COLUMN IF EXISTS "parent_project_id";

ALTER TABLE "apps_kuaizhizao_delivery_process_template_nodes"
    DROP COLUMN IF EXISTS "duration_rules";
"""
