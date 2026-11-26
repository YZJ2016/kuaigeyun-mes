"""其他费用收入/支出单据补立账策略列（上游同款）。

OtherIncome.revenue_recognition 默认 on_shipment；
OtherExpense.payable_recognition 默认 on_receipt。
存量行按非空默认值回填，与上游模型 default 一致。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_incomes"
            ADD COLUMN IF NOT EXISTS "revenue_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_shipment';
        ALTER TABLE "apps_kuaicaiwu_other_expenses"
            ADD COLUMN IF NOT EXISTS "payable_recognition" VARCHAR(32) NOT NULL DEFAULT 'on_receipt';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_other_incomes" DROP COLUMN IF EXISTS "revenue_recognition";
        ALTER TABLE "apps_kuaicaiwu_other_expenses" DROP COLUMN IF EXISTS "payable_recognition";
    """
