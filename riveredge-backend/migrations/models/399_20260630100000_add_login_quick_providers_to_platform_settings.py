"""
登录页快捷登录分渠道开关（平台设置 JSON）
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings"
        ADD COLUMN IF NOT EXISTS "login_quick_providers" JSONB NOT NULL DEFAULT '{}'::jsonb;

        COMMENT ON COLUMN "infra_platform_settings"."login_quick_providers" IS '快捷登录分渠道开关（wechat/qq/wechat_work/dingtalk/feishu）';
        """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "infra_platform_settings" DROP COLUMN IF EXISTS "login_quick_providers";
        """
