"""交付节点计划编辑历史表补齐 BaseModel 列。

769 建表漏 uuid / created_at / updated_at 及审计人名列，列表查询 500。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_delivery_project_node_schedule_revisions"
    ADD COLUMN IF NOT EXISTS "uuid" VARCHAR(36),
    ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS "created_by" INT,
    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
    ADD COLUMN IF NOT EXISTS "updated_by" INT,
    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);

UPDATE "apps_kuaizhizao_delivery_project_node_schedule_revisions"
SET
    "uuid" = gen_random_uuid()::text,
    "created_at" = COALESCE("created_at", "edited_at", NOW()),
    "updated_at" = COALESCE("updated_at", "edited_at", NOW())
WHERE "uuid" IS NULL OR "created_at" IS NULL OR "updated_at" IS NULL;

ALTER TABLE "apps_kuaizhizao_delivery_project_node_schedule_revisions"
    ALTER COLUMN "uuid" SET NOT NULL,
    ALTER COLUMN "created_at" SET NOT NULL,
    ALTER COLUMN "updated_at" SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kz_delivery_node_sched_rev_uuid"
    ON "apps_kuaizhizao_delivery_project_node_schedule_revisions" ("uuid");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX IF EXISTS "uidx_kz_delivery_node_sched_rev_uuid";
ALTER TABLE "apps_kuaizhizao_delivery_project_node_schedule_revisions"
    DROP COLUMN IF EXISTS "updated_by_name",
    DROP COLUMN IF EXISTS "updated_by",
    DROP COLUMN IF EXISTS "created_by_name",
    DROP COLUMN IF EXISTS "created_by",
    DROP COLUMN IF EXISTS "updated_at",
    DROP COLUMN IF EXISTS "created_at",
    DROP COLUMN IF EXISTS "uuid";
"""
