"""
单据行：伙伴料号/品名 + 型号快照字段（销售/采购/成品入库）。
"""
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_LINE_TABLES = (
    "apps_kuaizhizao_quotation_items",
    "apps_kuaizhizao_sales_order_items",
    "apps_kuaizhizao_sales_order_change_items",
    "apps_kuaizhizao_sales_contract_items",
    "apps_kuaizhizao_sales_forecast_items",
    "apps_kuaizhizao_sales_review_items",
    "apps_kuaizhizao_shipment_notice_items",
    "apps_kuaizhizao_sales_delivery_items",
    "apps_kuaizhizao_delivery_notice_items",
    "apps_kuaizhizao_sales_return_items",
    "apps_kuaizhizao_purchase_inquiry_items",
    "apps_kuaizhizao_purchase_requisition_items",
    "apps_kuaizhizao_purchase_order_items",
    "apps_kuaizhizao_purchase_order_change_items",
    "apps_kuaizhizao_receipt_notice_items",
    "apps_kuaizhizao_purchase_receipt_items",
    "apps_kuaizhizao_purchase_return_items",
    "apps_kuaizhizao_finished_goods_receipt_items",
)


def _add_columns_sql() -> str:
    parts = []
    for table in _LINE_TABLES:
        parts.append(
            f"""
        ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS partner_material_code VARCHAR(100) NULL,
            ADD COLUMN IF NOT EXISTS partner_material_name VARCHAR(200) NULL,
            ADD COLUMN IF NOT EXISTS material_model VARCHAR(200) NULL;
        """
        )
    return "\n".join(parts)


async def upgrade(db: BaseDBAsyncClient) -> str:
    return (
        _add_columns_sql()
        + """
        UPDATE apps_kuaizhizao_sales_order_items li
        SET material_model = NULLIF(TRIM(m.model), '')
        FROM apps_master_data_materials m
        WHERE m.id = li.material_id AND li.material_model IS NULL;

        UPDATE apps_kuaizhizao_sales_order_items li
        SET
            partner_material_code = a.code,
            partner_material_name = a.name
        FROM apps_kuaizhizao_sales_orders so,
             apps_master_data_material_code_aliases a
        WHERE so.id = li.sales_order_id
          AND a.tenant_id = li.tenant_id
          AND a.material_id = li.material_id
          AND a.code_type = 'CUSTOMER'
          AND a.external_entity_type = 'customer'
          AND a.external_entity_id = so.customer_id
          AND a.deleted_at IS NULL
          AND li.partner_material_code IS NULL;

        UPDATE apps_kuaizhizao_purchase_order_items li
        SET material_model = NULLIF(TRIM(m.model), '')
        FROM apps_master_data_materials m
        WHERE m.id = li.material_id AND li.material_model IS NULL;

        UPDATE apps_kuaizhizao_purchase_order_items li
        SET
            partner_material_code = a.code,
            partner_material_name = a.name
        FROM apps_kuaizhizao_purchase_orders po,
             apps_master_data_material_code_aliases a
        WHERE po.id = li.order_id
          AND a.tenant_id = li.tenant_id
          AND a.material_id = li.material_id
          AND a.code_type = 'SUPPLIER'
          AND a.external_entity_type = 'supplier'
          AND a.external_entity_id = po.supplier_id
          AND a.deleted_at IS NULL
          AND li.partner_material_code IS NULL;

        UPDATE apps_kuaizhizao_finished_goods_receipt_items li
        SET material_model = NULLIF(TRIM(m.model), '')
        FROM apps_master_data_materials m
        WHERE m.id = li.material_id AND li.material_model IS NULL;

        UPDATE apps_kuaizhizao_finished_goods_receipt_items li
        SET
            partner_material_code = a.code,
            partner_material_name = a.name
        FROM apps_kuaizhizao_finished_goods_receipts fg,
             apps_kuaizhizao_sales_orders so,
             apps_master_data_material_code_aliases a
        WHERE fg.id = li.receipt_id
          AND so.id = fg.sales_order_id
          AND a.tenant_id = li.tenant_id
          AND a.material_id = li.material_id
          AND a.code_type = 'CUSTOMER'
          AND a.external_entity_type = 'customer'
          AND a.external_entity_id = so.customer_id
          AND a.deleted_at IS NULL
          AND li.partner_material_code IS NULL;
        """
    )


async def downgrade(db: BaseDBAsyncClient) -> str:
    parts = []
    for table in _LINE_TABLES:
        parts.append(
            f"""
        ALTER TABLE {table}
            DROP COLUMN IF EXISTS partner_material_code,
            DROP COLUMN IF EXISTS partner_material_name,
            DROP COLUMN IF EXISTS material_model;
        """
        )
    return "\n".join(parts)
