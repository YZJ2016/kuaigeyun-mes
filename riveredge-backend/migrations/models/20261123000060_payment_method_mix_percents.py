from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_customers"
        ADD COLUMN IF NOT EXISTS "default_payment_wire_percent" DECIMAL(5,2);
        ALTER TABLE "apps_master_data_customers"
        ADD COLUMN IF NOT EXISTS "default_payment_acceptance_percent" DECIMAL(5,2);

        ALTER TABLE "apps_master_data_suppliers"
        ADD COLUMN IF NOT EXISTS "default_payment_wire_percent" DECIMAL(5,2);
        ALTER TABLE "apps_master_data_suppliers"
        ADD COLUMN IF NOT EXISTS "default_payment_acceptance_percent" DECIMAL(5,2);

        ALTER TABLE "apps_kuaizhizao_sales_orders"
        ADD COLUMN IF NOT EXISTS "payment_wire_percent" DECIMAL(5,2);
        ALTER TABLE "apps_kuaizhizao_sales_orders"
        ADD COLUMN IF NOT EXISTS "payment_acceptance_percent" DECIMAL(5,2);

        ALTER TABLE "apps_kuaizhizao_purchase_orders"
        ADD COLUMN IF NOT EXISTS "payment_wire_percent" DECIMAL(5,2);
        ALTER TABLE "apps_kuaizhizao_purchase_orders"
        ADD COLUMN IF NOT EXISTS "payment_acceptance_percent" DECIMAL(5,2);

        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
        ADD COLUMN IF NOT EXISTS "payment_method_code" VARCHAR(50);
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
        ADD COLUMN IF NOT EXISTS "payment_wire_percent" DECIMAL(5,2);
        ALTER TABLE "apps_kuaizhizao_sales_deliveries"
        ADD COLUMN IF NOT EXISTS "payment_acceptance_percent" DECIMAL(5,2);

        ALTER TABLE "apps_kuaicaiwu_receivables"
        ADD COLUMN IF NOT EXISTS "payment_method_code" VARCHAR(50);
        ALTER TABLE "apps_kuaicaiwu_receivables"
        ADD COLUMN IF NOT EXISTS "payment_wire_percent" DECIMAL(5,2);
        ALTER TABLE "apps_kuaicaiwu_receivables"
        ADD COLUMN IF NOT EXISTS "payment_acceptance_percent" DECIMAL(5,2);

        ALTER TABLE "apps_kuaicaiwu_payables"
        ADD COLUMN IF NOT EXISTS "payment_method_code" VARCHAR(50);
        ALTER TABLE "apps_kuaicaiwu_payables"
        ADD COLUMN IF NOT EXISTS "payment_wire_percent" DECIMAL(5,2);
        ALTER TABLE "apps_kuaicaiwu_payables"
        ADD COLUMN IF NOT EXISTS "payment_acceptance_percent" DECIMAL(5,2);
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaicaiwu_payables" DROP COLUMN IF EXISTS "payment_acceptance_percent";
        ALTER TABLE "apps_kuaicaiwu_payables" DROP COLUMN IF EXISTS "payment_wire_percent";
        ALTER TABLE "apps_kuaicaiwu_payables" DROP COLUMN IF EXISTS "payment_method_code";
        ALTER TABLE "apps_kuaicaiwu_receivables" DROP COLUMN IF EXISTS "payment_acceptance_percent";
        ALTER TABLE "apps_kuaicaiwu_receivables" DROP COLUMN IF EXISTS "payment_wire_percent";
        ALTER TABLE "apps_kuaicaiwu_receivables" DROP COLUMN IF EXISTS "payment_method_code";
        ALTER TABLE "apps_kuaizhizao_sales_deliveries" DROP COLUMN IF EXISTS "payment_acceptance_percent";
        ALTER TABLE "apps_kuaizhizao_sales_deliveries" DROP COLUMN IF EXISTS "payment_wire_percent";
        ALTER TABLE "apps_kuaizhizao_sales_deliveries" DROP COLUMN IF EXISTS "payment_method_code";
        ALTER TABLE "apps_kuaizhizao_purchase_orders" DROP COLUMN IF EXISTS "payment_acceptance_percent";
        ALTER TABLE "apps_kuaizhizao_purchase_orders" DROP COLUMN IF EXISTS "payment_wire_percent";
        ALTER TABLE "apps_kuaizhizao_sales_orders" DROP COLUMN IF EXISTS "payment_acceptance_percent";
        ALTER TABLE "apps_kuaizhizao_sales_orders" DROP COLUMN IF EXISTS "payment_wire_percent";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "default_payment_acceptance_percent";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "default_payment_wire_percent";
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "default_payment_acceptance_percent";
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "default_payment_wire_percent";
    """