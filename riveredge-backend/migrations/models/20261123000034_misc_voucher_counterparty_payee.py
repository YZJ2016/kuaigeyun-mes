"""其他费用支出：对方收款户名、开户行、账号。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            ADD COLUMN IF NOT EXISTS "counterparty_account_name" VARCHAR(200);
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            ADD COLUMN IF NOT EXISTS "counterparty_bank_name" VARCHAR(200);
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            ADD COLUMN IF NOT EXISTS "counterparty_bank_account" VARCHAR(64);
        COMMENT ON COLUMN "apps_kuaicaiwu_other_expenses"."counterparty_account_name" IS '对方收款户名';
        COMMENT ON COLUMN "apps_kuaicaiwu_other_expenses"."counterparty_bank_name" IS '对方收款开户行';
        COMMENT ON COLUMN "apps_kuaicaiwu_other_expenses"."counterparty_bank_account" IS '对方收款账号';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            DROP COLUMN IF EXISTS "counterparty_bank_account";
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            DROP COLUMN IF EXISTS "counterparty_bank_name";
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            DROP COLUMN IF EXISTS "counterparty_account_name";
    """
