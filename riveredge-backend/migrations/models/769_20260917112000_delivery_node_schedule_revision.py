"""交付项目节点计划编辑历史。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_delivery_project_node_schedule_revisions" (
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "id" SERIAL PRIMARY KEY,
    "project_id" INT NOT NULL,
    "node_id" INT NOT NULL,
    "edit_reason" TEXT NOT NULL,
    "changes_json" JSONB NOT NULL,
    "edited_by_id" INT,
    "edited_by_name" VARCHAR(100),
    "edited_at" TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kz_delivery_node_sched_rev_uuid"
    ON "apps_kuaizhizao_delivery_project_node_schedule_revisions" ("uuid");
CREATE INDEX IF NOT EXISTS "idx_kz_delivery_node_sched_rev_node"
    ON "apps_kuaizhizao_delivery_project_node_schedule_revisions" ("tenant_id", "project_id", "node_id");
CREATE INDEX IF NOT EXISTS "idx_kz_delivery_node_sched_rev_time"
    ON "apps_kuaizhizao_delivery_project_node_schedule_revisions" ("tenant_id", "edited_at");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS "apps_kuaizhizao_delivery_project_node_schedule_revisions";
"""
