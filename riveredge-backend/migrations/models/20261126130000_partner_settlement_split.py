from tortoise import BaseDBAsyncClient

_PAYMENT_CODES = ("cash", "bank_transfer", "bank_acceptance", "commercial_acceptance", "other")
_TERMS_CODES = ("monthly", "prepaid")


async def upgrade(db: BaseDBAsyncClient) -> str:
    payment_in = ", ".join(f"'{c}'" for c in _PAYMENT_CODES)
    terms_in = ", ".join(f"'{c}'" for c in _TERMS_CODES)
    return f"""
        ALTER TABLE "apps_master_data_customers"
        ADD COLUMN IF NOT EXISTS "default_payment_method_code" VARCHAR(50);
        ALTER TABLE "apps_master_data_customers"
        ADD COLUMN IF NOT EXISTS "settlement_terms_code" VARCHAR(50);
        ALTER TABLE "apps_master_data_suppliers"
        ADD COLUMN IF NOT EXISTS "default_payment_method_code" VARCHAR(50);
        ALTER TABLE "apps_master_data_suppliers"
        ADD COLUMN IF NOT EXISTS "settlement_terms_code" VARCHAR(50);

        UPDATE "apps_master_data_customers"
        SET "default_payment_method_code" = "settlement_method_code"
        WHERE "settlement_method_code" IN ({payment_in});

        UPDATE "apps_master_data_customers"
        SET "settlement_terms_code" = 'monthly'
        WHERE "settlement_method_code" = '月结';

        UPDATE "apps_master_data_customers"
        SET "settlement_terms_code" = "settlement_method_code"
        WHERE "settlement_method_code" IN ({terms_in});

        UPDATE "apps_master_data_suppliers"
        SET "default_payment_method_code" = "settlement_method_code"
        WHERE "settlement_method_code" IN ({payment_in});

        UPDATE "apps_master_data_suppliers"
        SET "settlement_terms_code" = 'monthly'
        WHERE "settlement_method_code" = '月结';

        UPDATE "apps_master_data_suppliers"
        SET "settlement_terms_code" = "settlement_method_code"
        WHERE "settlement_method_code" IN ({terms_in});

        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "settlement_method_code";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "settlement_method_code";
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_master_data_customers" ADD COLUMN IF NOT EXISTS "settlement_method_code" VARCHAR(50);
        ALTER TABLE "apps_master_data_suppliers" ADD COLUMN IF NOT EXISTS "settlement_method_code" VARCHAR(50);

        UPDATE "apps_master_data_customers"
        SET "settlement_method_code" = COALESCE("settlement_terms_code", "default_payment_method_code");

        UPDATE "apps_master_data_suppliers"
        SET "settlement_method_code" = COALESCE("settlement_terms_code", "default_payment_method_code");

        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "default_payment_method_code";
        ALTER TABLE "apps_master_data_customers" DROP COLUMN IF EXISTS "settlement_terms_code";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "default_payment_method_code";
        ALTER TABLE "apps_master_data_suppliers" DROP COLUMN IF EXISTS "settlement_terms_code";
    """

# 对应上游 918_20261022180000_partner_settlement_split.py
