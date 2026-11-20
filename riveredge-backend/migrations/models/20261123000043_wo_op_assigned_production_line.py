"""工单工序增加产线指派字段（上游 1044）（自动化产线 APS 排程真源）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            ADD COLUMN IF NOT EXISTS "assigned_production_line_id" INT NULL;
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            ADD COLUMN IF NOT EXISTS "assigned_production_line_code" VARCHAR(50) NULL;
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            ADD COLUMN IF NOT EXISTS "assigned_production_line_name" VARCHAR(200) NULL;
        CREATE INDEX IF NOT EXISTS "idx_wo_op_assigned_pline"
            ON "apps_kuaizhizao_work_order_operations" ("tenant_id", "assigned_production_line_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_wo_op_assigned_pline";
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            DROP COLUMN IF EXISTS "assigned_production_line_id";
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            DROP COLUMN IF EXISTS "assigned_production_line_code";
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            DROP COLUMN IF EXISTS "assigned_production_line_name";
    """
