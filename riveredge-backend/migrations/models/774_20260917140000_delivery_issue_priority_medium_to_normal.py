"""交付问题优先级历史值 medium 回填为 normal。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaizhizao_delivery_issues"
SET "priority" = 'normal'
WHERE "priority" = 'medium';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
UPDATE "apps_kuaizhizao_delivery_issues"
SET "priority" = 'medium'
WHERE "priority" = 'normal'
  AND "deleted_at" IS NULL;
"""
