"""
平台设置：微信开放平台网站应用 AppID / AppSecret（快捷登录扫码）
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings"
        ADD COLUMN IF NOT EXISTS "wechat_oauth_app_id" VARCHAR(200);

        ALTER TABLE "infra_platform_settings"
        ADD COLUMN IF NOT EXISTS "wechat_oauth_app_secret" VARCHAR(200);

        COMMENT ON COLUMN "infra_platform_settings"."wechat_oauth_app_id"
        IS '微信开放平台网站应用 AppID（平台级）';

        COMMENT ON COLUMN "infra_platform_settings"."wechat_oauth_app_secret"
        IS '微信开放平台网站应用 AppSecret（平台级，勿对公开接口下发）';
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings" DROP COLUMN IF EXISTS "wechat_oauth_app_id";
        ALTER TABLE "infra_platform_settings" DROP COLUMN IF EXISTS "wechat_oauth_app_secret";
        """
