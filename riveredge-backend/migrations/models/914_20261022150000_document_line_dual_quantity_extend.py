"""单据行主/副数量：报价、发货通知、预测、合同、退换货、请购等明细表。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_TABLES = (
    "apps_kuaizhizao_quotation_items",
    "apps_kuaizhizao_shipment_notice_items",
    "apps_kuaizhizao_sales_forecast_items",
    "apps_kuaizhizao_sales_contract_items",
    "apps_kuaizhizao_sales_return_items",
    "apps_kuaizhizao_purchase_return_items",
    "apps_kuaizhizao_purchase_requisition_items",
    "apps_kuaizhizao_delivery_notice_items",
    "apps_kuaizhizao_receipt_notice_items",
    "apps_kuaizhizao_finished_goods_receipt_items",
    "apps_kuaizhizao_semi_finished_goods_receipt_items",
    "apps_kuaizhizao_production_picking_items",
    "apps_kuaizhizao_production_return_items",
    "apps_kuaizhizao_material_return_items",
    "apps_kuaizhizao_material_borrow_items",
    "apps_kuaizhizao_demand_items",
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
