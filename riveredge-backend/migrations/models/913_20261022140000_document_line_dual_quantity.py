"""单据行：副数量、副单位、行换算率（主/副单位与浮动换算）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_TABLES = (
    "apps_kuaizhizao_other_inbound_items",
    "apps_kuaizhizao_other_outbound_items",
    "apps_kuaizhizao_purchase_receipt_items",
    "apps_kuaizhizao_purchase_order_items",
    "apps_kuaizhizao_sales_order_items",
    "apps_kuaizhizao_sales_delivery_items",
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    parts = []
    for table in _TABLES:
        parts.append(
            f'''
        ALTER TABLE "{table}"
            ADD COLUMN IF NOT EXISTS "aux_quantity" DECIMAL(18,4),
            ADD COLUMN IF NOT EXISTS "aux_unit" VARCHAR(20),
            ADD COLUMN IF NOT EXISTS "unit_conversion_rate" DECIMAL(18,8);
        '''
        )
    return "\n".join(parts)


async def downgrade(db: BaseDBAsyncClient) -> str:
    parts = []
    for table in _TABLES:
        parts.append(
            f'''
        ALTER TABLE "{table}"
            DROP COLUMN IF EXISTS "aux_quantity",
            DROP COLUMN IF EXISTS "aux_unit",
            DROP COLUMN IF EXISTS "unit_conversion_rate";
        '''
        )
    return "\n".join(parts)
