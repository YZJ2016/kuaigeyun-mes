"""工资结算行新增手工「高温补贴」列（与各项补贴 heat_subsidy 分离）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_payroll_settlement_lines"
            ADD COLUMN IF NOT EXISTS "high_temp_subsidy" NUMERIC(12,2) NOT NULL DEFAULT 0;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_payroll_settlement_lines"
            DROP COLUMN IF EXISTS "high_temp_subsidy";
    """

# 对应上游 994_20261105030000_payroll_line_high_temp_subsidy.py
