"""员工档案入离职登记：人员接收人（通知对象）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_employee_profiles"
            ADD COLUMN IF NOT EXISTS "hire_recipient_user_id" INT,
            ADD COLUMN IF NOT EXISTS "hire_recipient_user_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "leave_recipient_user_id" INT,
            ADD COLUMN IF NOT EXISTS "leave_recipient_user_name" VARCHAR(100);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_employee_profiles"
            DROP COLUMN IF EXISTS "leave_recipient_user_name",
            DROP COLUMN IF EXISTS "leave_recipient_user_id",
            DROP COLUMN IF EXISTS "hire_recipient_user_name",
            DROP COLUMN IF EXISTS "hire_recipient_user_id";
    """
