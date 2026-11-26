from tortoise import BaseDBAsyncClient

# 与 master_data/config/partner_settlement_codes.py PARTNER_PAYMENT_METHOD_CODES 保持一致
_PAYMENT_CODES = (
    "cash",
    "bank_transfer",
    "bank_acceptance",
    "bank_transfer_and_acceptance",
    "commercial_acceptance",
    "employee_advance",
    "other",
)

# 与 partner_settlement_codes.PARTNER_SETTLEMENT_TERMS_CODES | _LEGACY_PERIOD_SETTLEMENT_TERMS 对齐
_TERMS_CODES = (
    "prepaid",
    "pay_before_ship",
    "spot",
    "cod",
    "net_terms",
    "installment",
    "progress",
    "pay_on_invoice",
    "monthly",
    "bimonthly",
    "quarterly",
)

# 与 partner_settlement_codes._SETTLEMENT_TERMS_CN_ALIASES 对齐（migration 不能 import 应用模块）
_CN_TERMS_ALIASES = {
    "月结": "net_terms",
    "双月结": "net_terms",
    "季结": "net_terms",
    "季度结": "net_terms",
    "预付款": "prepaid",
    "预付": "prepaid",
    "款到发货": "pay_before_ship",
    "先款后货": "pay_before_ship",
    "现款现货": "spot",
    "货到付款": "cod",
    "账期结算": "net_terms",
    "账期": "net_terms",
    "分期付款": "installment",
    "分期": "installment",
    "进度款": "progress",
    "按进度": "progress",
    "票到付款": "pay_on_invoice",
    "见票付款": "pay_on_invoice",
    "票到付": "pay_on_invoice",
}


def _cn_terms_update(table: str) -> str:
    cases = "\n            ".join(f"WHEN '{k}' THEN '{v}'" for k, v in _CN_TERMS_ALIASES.items())
    keys_in = ", ".join(f"'{k}'" for k in _CN_TERMS_ALIASES)
    return f"""
        UPDATE "{table}"
        SET "settlement_terms_code" = CASE "settlement_method_code"
            {cases}
            ELSE "settlement_terms_code"
        END
        WHERE "settlement_method_code" IN ({keys_in});
    """


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
        {_cn_terms_update("apps_master_data_customers")}

        UPDATE "apps_master_data_customers"
        SET "settlement_terms_code" = "settlement_method_code"
        WHERE "settlement_method_code" IN ({terms_in});

        UPDATE "apps_master_data_suppliers"
        SET "default_payment_method_code" = "settlement_method_code"
        WHERE "settlement_method_code" IN ({payment_in});
        {_cn_terms_update("apps_master_data_suppliers")}

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
