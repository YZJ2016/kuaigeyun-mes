"""月结/双月结/季结并入账期结算，具体天数由 payment_terms_days 表达。"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_master_data_customers"
        SET "settlement_terms_code" = 'net_terms'
        WHERE "settlement_terms_code" IN ('monthly', 'bimonthly', 'quarterly');

        UPDATE "apps_master_data_suppliers"
        SET "settlement_terms_code" = 'net_terms'
        WHERE "settlement_terms_code" IN ('monthly', 'bimonthly', 'quarterly');
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 无法还原原月结/双月结/季结区分， downgrade 不改动
        SELECT 1;
    """

# 对应上游 919_20261022190000_partner_settlement_period_to_net_terms.py
