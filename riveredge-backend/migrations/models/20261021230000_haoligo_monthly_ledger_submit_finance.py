"""月度工厂台账：提交财务（接收人 + 提交状态）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haolisales_monthly_factory_ledger"
            ADD COLUMN IF NOT EXISTS "finance_submitted" BOOL NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS "finance_submitted_at" TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS "finance_submitted_by" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "finance_recipient_user_ids" JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS "finance_recipient_user_names" VARCHAR(500);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haolisales_monthly_factory_ledger"
            DROP COLUMN IF EXISTS "finance_recipient_user_names",
            DROP COLUMN IF EXISTS "finance_recipient_user_ids",
            DROP COLUMN IF EXISTS "finance_submitted_by",
            DROP COLUMN IF EXISTS "finance_submitted_at",
            DROP COLUMN IF EXISTS "finance_submitted";
    """
