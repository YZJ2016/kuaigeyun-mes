"""
套餐 allow_pro_apps 与内置档位对齐。

专业/旗舰必须允许 PRO；体验/基础不允许。修复历史库中「专业版套餐 allow_pro=false」
导致组织升档后应用中心仍提示需升级专业版的问题。
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "infra_packages"
SET
    "allow_pro_apps" = TRUE,
    "updated_at" = NOW()
WHERE "plan" IN ('professional', 'enterprise')
  AND "allow_pro_apps" IS DISTINCT FROM TRUE;

UPDATE "infra_packages"
SET
    "allow_pro_apps" = FALSE,
    "updated_at" = NOW()
WHERE "plan" IN ('trial', 'basic')
  AND "allow_pro_apps" IS DISTINCT FROM FALSE;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
-- 不可安全回滚历史 allow_pro_apps 值
SELECT 1;
    """
