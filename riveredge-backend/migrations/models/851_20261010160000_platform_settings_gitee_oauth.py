"""
平台设置：Gitee OAuth Client ID / Secret（快捷登录）
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings"
        ADD COLUMN IF NOT EXISTS "gitee_oauth_client_id" VARCHAR(200);

        ALTER TABLE "infra_platform_settings"
        ADD COLUMN IF NOT EXISTS "gitee_oauth_client_secret" VARCHAR(200);

        COMMENT ON COLUMN "infra_platform_settings"."gitee_oauth_client_id"
        IS 'Gitee OAuth 应用 Client ID（平台级）';

        COMMENT ON COLUMN "infra_platform_settings"."gitee_oauth_client_secret"
        IS 'Gitee OAuth 应用 Client Secret（平台级，勿对公开接口下发）';
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings" DROP COLUMN IF EXISTS "gitee_oauth_client_id";
        ALTER TABLE "infra_platform_settings" DROP COLUMN IF EXISTS "gitee_oauth_client_secret";
        """
