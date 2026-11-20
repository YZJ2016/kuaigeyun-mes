"""多账户登录默认组织：core_users.is_login_default。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_users"
            ADD COLUMN IF NOT EXISTS "is_login_default" BOOLEAN NOT NULL DEFAULT FALSE;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_users"
            DROP COLUMN IF EXISTS "is_login_default";
    """
