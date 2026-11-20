"""单据税率字段统一非空；0 表示零税率。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE apps_kuaizhizao_purchase_receipt_items
        SET tax_rate = 0
        WHERE tax_rate IS NULL;

        ALTER TABLE apps_kuaizhizao_purchase_receipt_items
            ALTER COLUMN tax_rate SET DEFAULT 0,
            ALTER COLUMN tax_rate SET NOT NULL;

        UPDATE apps_kuaizhizao_purchase_inquiries
        SET tax_rate = 0
        WHERE tax_rate IS NULL;

        ALTER TABLE apps_kuaizhizao_purchase_inquiries
            ALTER COLUMN tax_rate SET DEFAULT 0,
            ALTER COLUMN tax_rate SET NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE apps_kuaizhizao_purchase_receipt_items
            ALTER COLUMN tax_rate DROP NOT NULL;
        ALTER TABLE apps_kuaizhizao_purchase_inquiries
            ALTER COLUMN tax_rate DROP NOT NULL;
    """
