"""
销售跟踪 haolisales — 指定人、账期到期日、未开票总数字段。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haolisales_monthly_factory_ledger"
            RENAME COLUMN "invoice_qty" TO "uninvoiced_qty";

        ALTER TABLE "haolisales_order_tracking"
            ADD COLUMN IF NOT EXISTS "designated_user_id" INT,
            ADD COLUMN IF NOT EXISTS "designated_user_name" VARCHAR(100),
            ADD COLUMN IF NOT EXISTS "payment_due_date" DATE,
            ADD COLUMN IF NOT EXISTS "payment_due_reminder_sent_at" TIMESTAMPTZ;

        CREATE INDEX IF NOT EXISTS "idx_haolisales_ot_designated"
            ON "haolisales_order_tracking" ("designated_user_id");
        CREATE INDEX IF NOT EXISTS "idx_haolisales_ot_payment_due"
            ON "haolisales_order_tracking" ("payment_due_date");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "haolisales_monthly_factory_ledger"
            RENAME COLUMN "uninvoiced_qty" TO "invoice_qty";

        ALTER TABLE "haolisales_order_tracking"
            DROP COLUMN IF EXISTS "payment_due_reminder_sent_at",
            DROP COLUMN IF EXISTS "payment_due_date",
            DROP COLUMN IF EXISTS "designated_user_name",
            DROP COLUMN IF EXISTS "designated_user_id";

        DROP INDEX IF EXISTS "idx_haolisales_ot_payment_due";
        DROP INDEX IF EXISTS "idx_haolisales_ot_designated";
    """
