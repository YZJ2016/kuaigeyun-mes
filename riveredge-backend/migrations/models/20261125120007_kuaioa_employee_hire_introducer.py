"""员工档案：入职介绍人（手填姓名，不关联系统用户）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_employee_profiles"
            ADD COLUMN IF NOT EXISTS "hire_introducer" VARCHAR(100);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_employee_profiles"
            DROP COLUMN IF EXISTS "hire_introducer";
    """
