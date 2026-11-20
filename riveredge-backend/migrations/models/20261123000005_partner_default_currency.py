"""客户/供应商默认币种与汇率（单据表头带出）。"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_suppliers"
            ADD COLUMN IF NOT EXISTS "default_currency_code" VARCHAR(10);
        ALTER TABLE "apps_master_data_suppliers"
            ADD COLUMN IF NOT EXISTS "default_exchange_rate" DECIMAL(18,6);
        ALTER TABLE "apps_master_data_customers"
            ADD COLUMN IF NOT EXISTS "default_currency_code" VARCHAR(10);
        ALTER TABLE "apps_master_data_customers"
            ADD COLUMN IF NOT EXISTS "default_exchange_rate" DECIMAL(18,6);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "default_exchange_rate";
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "default_currency_code";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "default_exchange_rate";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "default_currency_code";
    """
