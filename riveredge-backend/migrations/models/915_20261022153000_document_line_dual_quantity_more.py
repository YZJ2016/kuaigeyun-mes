"""单据行主/副数量：询价、调拨、订单评审等明细表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_TABLES = (
    "apps_kuaizhizao_purchase_inquiry_items",
    "apps_kuaizhizao_inventory_transfer_items",
    "apps_kuaizhizao_sales_review_items",
    "apps_kuaizhizao_material_call_request_items",
    "apps_kuaizhizao_after_sales_ticket_items",
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
