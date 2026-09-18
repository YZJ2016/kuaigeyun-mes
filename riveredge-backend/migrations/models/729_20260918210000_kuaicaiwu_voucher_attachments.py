"""
总账凭证原始凭证附件字段。

Author: AI Assistant
Date: 2026-09-18
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_vouchers"
        ADD COLUMN IF NOT EXISTS "attachments" JSONB;
    """
