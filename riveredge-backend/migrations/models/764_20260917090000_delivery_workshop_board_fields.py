"""交付项目：机台配置、台账分段、任务齐套跟踪。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_projects"
    ADD COLUMN IF NOT EXISTS "config_attrs" JSONB,
    ADD COLUMN IF NOT EXISTS "board_section" VARCHAR(30) NOT NULL DEFAULT 'active';
CREATE INDEX IF NOT EXISTS "idx_kz_delivery_proj_board_section"
    ON "apps_kuaizhizao_delivery_projects" ("tenant_id", "board_section");

ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    ADD COLUMN IF NOT EXISTS "track_mode" VARCHAR(20) NOT NULL DEFAULT 'progress',
    ADD COLUMN IF NOT EXISTS "kit_status" VARCHAR(20) NOT NULL DEFAULT 'none';

ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    ADD COLUMN IF NOT EXISTS "track_mode" VARCHAR(20) NOT NULL DEFAULT 'progress';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_process_template_node_tasks"
    DROP COLUMN IF EXISTS "track_mode";

ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
    DROP COLUMN IF EXISTS "kit_status",
    DROP COLUMN IF EXISTS "track_mode";

DROP INDEX IF EXISTS "idx_kz_delivery_proj_board_section";
ALTER TABLE "apps_kuaizhizao_delivery_projects"
    DROP COLUMN IF EXISTS "board_section",
    DROP COLUMN IF EXISTS "config_attrs";
"""
