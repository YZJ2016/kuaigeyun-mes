from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
        ADD COLUMN IF NOT EXISTS "machine_session_state" VARCHAR(20) NOT NULL DEFAULT 'none';
        COMMENT ON COLUMN "apps_kuaizhizao_work_order_operations"."machine_session_state"
            IS '上下机状态 none/on_machine/off_machine';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaizhizao_work_order_operations"
        DROP COLUMN IF EXISTS "machine_session_state";
    """
