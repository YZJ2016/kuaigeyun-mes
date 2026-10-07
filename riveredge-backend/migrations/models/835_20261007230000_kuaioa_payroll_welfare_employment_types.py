"""工资结算单 / 节日福利发放单：用工类型多选。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_payroll_settlements"
            ADD COLUMN IF NOT EXISTS "employment_types" JSONB NOT NULL DEFAULT '[]'::jsonb;

        ALTER TABLE "apps_kuaioa_welfare_batches"
            ADD COLUMN IF NOT EXISTS "employment_types" JSONB NOT NULL DEFAULT '[]'::jsonb;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaioa_payroll_settlements"
            DROP COLUMN IF EXISTS "employment_types";

        ALTER TABLE "apps_kuaioa_welfare_batches"
            DROP COLUMN IF EXISTS "employment_types";
    """
