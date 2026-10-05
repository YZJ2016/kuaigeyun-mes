"""交付任务增加子阶段，关联单据可挂到具体任务。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
            ADD COLUMN IF NOT EXISTS "parent_task_id" INT,
            ADD COLUMN IF NOT EXISTS "task_layer" VARCHAR(20);

        UPDATE "apps_kuaizhizao_delivery_project_node_tasks"
            SET "task_layer" = 'task'
            WHERE "task_layer" IS NULL;

        ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
            ALTER COLUMN "task_layer" SET NOT NULL;

        INSERT INTO "apps_kuaizhizao_delivery_project_node_tasks" (
            "uuid", "tenant_id", "project_id", "node_id", "task_key", "task_name",
            "sort_order", "status", "planned_start_date", "planned_end_date",
            "progress_percent", "task_layer", "created_at", "updated_at"
        )
        SELECT
            gen_random_uuid()::text,
            n.tenant_id,
            n.project_id,
            n.id,
            'substage-' || n.id::text,
            n.node_name,
            0,
            'todo',
            n.planned_start_date,
            n.planned_end_date,
            0,
            'substage',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM "apps_kuaizhizao_delivery_project_nodes" n
        WHERE EXISTS (
            SELECT 1
            FROM "apps_kuaizhizao_delivery_project_node_tasks" t
            WHERE t.tenant_id = n.tenant_id
              AND t.node_id = n.id
              AND t.deleted_at IS NULL
              AND t.task_layer = 'task'
              AND t.parent_task_id IS NULL
        )
        AND NOT EXISTS (
            SELECT 1
            FROM "apps_kuaizhizao_delivery_project_node_tasks" s
            WHERE s.tenant_id = n.tenant_id
              AND s.node_id = n.id
              AND s.deleted_at IS NULL
              AND s.task_layer = 'substage'
        );

        UPDATE "apps_kuaizhizao_delivery_project_node_tasks" t
        SET "parent_task_id" = s.id
        FROM "apps_kuaizhizao_delivery_project_node_tasks" s
        WHERE t.task_layer = 'task'
          AND t.parent_task_id IS NULL
          AND t.deleted_at IS NULL
          AND s.task_layer = 'substage'
          AND s.deleted_at IS NULL
          AND s.tenant_id = t.tenant_id
          AND s.node_id = t.node_id
          AND s.task_key = 'substage-' || t.node_id::text;

        CREATE INDEX IF NOT EXISTS "idx_dp_node_tasks_tenant_parent"
            ON "apps_kuaizhizao_delivery_project_node_tasks" ("tenant_id", "parent_task_id");

        ALTER TABLE "apps_kuaizhizao_delivery_project_node_documents"
            ADD COLUMN IF NOT EXISTS "task_id" INT;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_delivery_project_node_documents"
            DROP COLUMN IF EXISTS "task_id";
        DROP INDEX IF EXISTS "idx_dp_node_tasks_tenant_parent";
        DELETE FROM "apps_kuaizhizao_delivery_project_node_tasks"
            WHERE "task_layer" = 'substage' AND "task_key" LIKE 'substage-%';
        ALTER TABLE "apps_kuaizhizao_delivery_project_node_tasks"
            DROP COLUMN IF EXISTS "parent_task_id",
            DROP COLUMN IF EXISTS "task_layer";
    """
