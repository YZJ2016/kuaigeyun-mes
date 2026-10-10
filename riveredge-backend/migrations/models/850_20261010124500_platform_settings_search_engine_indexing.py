"""平台设置：是否接受被搜索引擎收录。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "infra_platform_settings"
    ADD COLUMN IF NOT EXISTS "search_engine_indexing_enabled" BOOLEAN DEFAULT TRUE;
COMMENT ON COLUMN "infra_platform_settings"."search_engine_indexing_enabled"
    IS '是否接受被搜索引擎收录；关闭时 robots.txt 与页面 meta 拒绝爬取';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "infra_platform_settings"
    DROP COLUMN IF EXISTS "search_engine_indexing_enabled";
"""
