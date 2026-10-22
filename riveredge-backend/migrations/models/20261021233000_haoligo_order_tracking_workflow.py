"""订单跟踪：排产/完成拆分、生产/财务接收人、发货备注。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haolisales_order_tracking"
            ADD COLUMN IF NOT EXISTS "completion_status" VARCHAR(32) NOT NULL DEFAULT 'open',
            ADD COLUMN IF NOT EXISTS "production_recipient_user_ids" JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS "production_recipient_user_names" VARCHAR(500),
            ADD COLUMN IF NOT EXISTS "finance_submitted" BOOL NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS "finance_submitted_at" TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS "finance_submitted_by" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "finance_recipient_user_ids" JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS "finance_recipient_user_names" VARCHAR(500);

        ALTER TABLE "haolisales_order_tracking_delivery"
            ADD COLUMN IF NOT EXISTS "remarks" VARCHAR(500);

        -- 历史「已完成」从排产状态拆到完成情况；排产回落为已排产
        UPDATE "haolisales_order_tracking"
        SET "completion_status" = 'completed',
            "order_status" = 'scheduled'
        WHERE "order_status" = 'completed'
          AND ("deleted_at" IS NULL);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "haolisales_order_tracking"
        SET "order_status" = 'completed'
        WHERE "completion_status" = 'completed'
          AND ("deleted_at" IS NULL);

        ALTER TABLE "haolisales_order_tracking_delivery"
            DROP COLUMN IF EXISTS "remarks";

        ALTER TABLE "haolisales_order_tracking"
            DROP COLUMN IF EXISTS "finance_recipient_user_names",
            DROP COLUMN IF EXISTS "finance_recipient_user_ids",
            DROP COLUMN IF EXISTS "finance_submitted_by",
            DROP COLUMN IF EXISTS "finance_submitted_at",
            DROP COLUMN IF EXISTS "finance_submitted",
            DROP COLUMN IF EXISTS "production_recipient_user_names",
            DROP COLUMN IF EXISTS "production_recipient_user_ids",
            DROP COLUMN IF EXISTS "completion_status";
    """
