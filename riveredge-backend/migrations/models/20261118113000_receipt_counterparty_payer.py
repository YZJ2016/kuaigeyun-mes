"""收款单：对方付款户名、开户行、账号（客户资料带入）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_receipts"
            ADD COLUMN IF NOT EXISTS "counterparty_account_name" VARCHAR(200);
        ALTER TABLE "apps_kuaicaiwu_receipts"
            ADD COLUMN IF NOT EXISTS "counterparty_bank_name" VARCHAR(200);
        ALTER TABLE "apps_kuaicaiwu_receipts"
            ADD COLUMN IF NOT EXISTS "counterparty_bank_account" VARCHAR(64);
        COMMENT ON COLUMN "apps_kuaicaiwu_receipts"."counterparty_account_name" IS '对方付款户名';
        COMMENT ON COLUMN "apps_kuaicaiwu_receipts"."counterparty_bank_name" IS '对方付款开户行';
        COMMENT ON COLUMN "apps_kuaicaiwu_receipts"."counterparty_bank_account" IS '对方付款账号';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_receipts"
            DROP COLUMN IF EXISTS "counterparty_bank_account";
        ALTER TABLE "apps_kuaicaiwu_receipts"
            DROP COLUMN IF EXISTS "counterparty_bank_name";
        ALTER TABLE "apps_kuaicaiwu_receipts"
            DROP COLUMN IF EXISTS "counterparty_account_name";
    """
