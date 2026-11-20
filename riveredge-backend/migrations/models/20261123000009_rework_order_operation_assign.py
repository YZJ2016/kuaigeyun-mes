"""返工工序行增加指派人员/班组字段（对齐工单工序派工）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_rework_order_operations"
            ADD COLUMN IF NOT EXISTS "assigned_worker_id" INT,
            ADD COLUMN IF NOT EXISTS "assigned_worker_name" VARCHAR(500),
            ADD COLUMN IF NOT EXISTS "assigned_worker_ids" JSONB DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS "assigned_team_id" INT,
            ADD COLUMN IF NOT EXISTS "assigned_team_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "assigned_at" TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS "assigned_by" INT,
            ADD COLUMN IF NOT EXISTS "assigned_by_name" VARCHAR(100);
        CREATE INDEX IF NOT EXISTS "idx_rework_op_assigned_worker"
            ON "apps_kuaizhizao_rework_order_operations" ("tenant_id", "assigned_worker_id");
        CREATE INDEX IF NOT EXISTS "idx_rework_op_assigned_team"
            ON "apps_kuaizhizao_rework_order_operations" ("tenant_id", "assigned_team_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_rework_op_assigned_team";
        DROP INDEX IF EXISTS "idx_rework_op_assigned_worker";
        ALTER TABLE "apps_kuaizhizao_rework_order_operations"
            DROP COLUMN IF EXISTS "assigned_by_name",
            DROP COLUMN IF EXISTS "assigned_by",
            DROP COLUMN IF EXISTS "assigned_at",
            DROP COLUMN IF EXISTS "assigned_team_name",
            DROP COLUMN IF EXISTS "assigned_team_id",
            DROP COLUMN IF EXISTS "assigned_worker_ids",
            DROP COLUMN IF EXISTS "assigned_worker_name",
            DROP COLUMN IF EXISTS "assigned_worker_id";
    """
