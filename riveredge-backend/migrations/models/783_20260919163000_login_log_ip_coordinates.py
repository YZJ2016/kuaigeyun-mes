"""登录日志增加 IP 解析经纬度字段（登录写入真源，地图视图直读）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_login_logs"
            ADD COLUMN IF NOT EXISTS "login_latitude" DECIMAL(10, 6) NULL,
            ADD COLUMN IF NOT EXISTS "login_longitude" DECIMAL(10, 6) NULL;

        COMMENT ON COLUMN "core_login_logs"."login_latitude" IS '登录 IP 纬度（登录时解析写入）';
        COMMENT ON COLUMN "core_login_logs"."login_longitude" IS '登录 IP 经度（登录时解析写入）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_login_logs"
            DROP COLUMN IF EXISTS "login_longitude",
            DROP COLUMN IF EXISTS "login_latitude";
    """
