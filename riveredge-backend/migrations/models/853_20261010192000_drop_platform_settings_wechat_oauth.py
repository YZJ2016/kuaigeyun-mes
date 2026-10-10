"""
平台设置：移除微信开放平台网站应用 AppID / AppSecret（已下线个人微信快捷登录）
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings" DROP COLUMN IF EXISTS "wechat_oauth_app_id";
        ALTER TABLE "infra_platform_settings" DROP COLUMN IF EXISTS "wechat_oauth_app_secret";
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings"
        ADD COLUMN IF NOT EXISTS "wechat_oauth_app_id" VARCHAR(200);

        ALTER TABLE "infra_platform_settings"
        ADD COLUMN IF NOT EXISTS "wechat_oauth_app_secret" VARCHAR(200);
        """
