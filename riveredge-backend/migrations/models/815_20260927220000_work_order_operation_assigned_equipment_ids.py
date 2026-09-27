from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            ADD COLUMN IF NOT EXISTS "assigned_equipment_ids" JSONB NOT NULL DEFAULT '[]';

        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            ALTER COLUMN "assigned_equipment_name" TYPE VARCHAR(500);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            DROP COLUMN IF EXISTS "assigned_equipment_ids";

        ALTER TABLE "apps_kuaizhizao_work_order_operations"
            ALTER COLUMN "assigned_equipment_name" TYPE VARCHAR(100);
    """
