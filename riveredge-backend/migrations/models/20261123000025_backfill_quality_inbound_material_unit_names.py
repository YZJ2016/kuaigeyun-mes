"""
质检 / 入库等单据 material_unit：编码 → 单位目录名称。

876 只回填了部分制造快照表；质检、采购入库、其他入出库、销采明细等仍可能存单位编码。
展示层禁止 code→name 映射，须在真源字段回填为名称。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

# 有 soft-delete 的表
_SNAPSHOT_TABLES_WITH_DELETED = (
    "apps_kuaizhizao_incoming_inspections",
    "apps_kuaizhizao_process_inspections",
    "apps_kuaizhizao_finished_goods_inspections",
    "apps_kuaizhizao_outsource_inspections",
    "apps_kuaizhizao_oqc_inspections",
    "apps_kuaizhizao_quality_patrols",
    "apps_kuaizhizao_purchase_receipt_items",
    "apps_kuaizhizao_inventory_transfer_items",
    "apps_kuaizhizao_stocktaking_items",
    "apps_kuaizhizao_sales_order_items",
    "apps_kuaizhizao_sales_delivery_items",
    "apps_kuaizhizao_customer_material_registration_items",
)

# 无 deleted_at 的明细表
_SNAPSHOT_TABLES_NO_DELETED = (
    "apps_kuaizhizao_purchase_return_items",
    "apps_kuaizhizao_other_inbound_items",
    "apps_kuaizhizao_other_outbound_items",
    "apps_kuaizhizao_material_return_items",
    "apps_kuaizhizao_material_borrow_items",
    "apps_kuaizhizao_sales_return_items",
    "apps_kuaizhizao_quotation_items",
    "apps_kuaizhizao_shipment_notice_items",
    "apps_kuaizhizao_delivery_notice_items",
    "apps_kuaizhizao_receipt_notice_items",
    "apps_kuaizhizao_sales_contract_items",
    "apps_kuaizhizao_sales_forecast_items",
    "apps_kuaizhizao_sales_review_items",
    "apps_kuaizhizao_demand_items",
    "apps_kuaizhizao_demand_computation_items",
    "apps_kuaizhizao_after_sales_ticket_items",
)


async def _backfill_material_unit(db: BaseDBAsyncClient, table: str, *, has_deleted: bool) -> None:
    deleted_clause = 'AND t."deleted_at" IS NULL' if has_deleted else ""
    await db.execute_script(
        f"""
        UPDATE "{table}" AS t
        SET "material_unit" = u."name"
        FROM "apps_master_data_units" AS u
        WHERE u."deleted_at" IS NULL
          {deleted_clause}
          AND t."tenant_id" = u."tenant_id"
          AND t."material_unit" = u."code"
          AND u."code" IS DISTINCT FROM u."name"
          AND COALESCE(btrim(u."name"), '') <> '';
        """
    )


async def upgrade(db: BaseDBAsyncClient) -> str:
    # 物料 base_unit 再补一轮（同步可能再次写入编码）
    await db.execute_script(
        """
        UPDATE "apps_master_data_materials" AS m
        SET "base_unit" = u."name"
        FROM "apps_master_data_units" AS u
        WHERE m."deleted_at" IS NULL
          AND u."deleted_at" IS NULL
          AND m."tenant_id" = u."tenant_id"
          AND m."base_unit" = u."code"
          AND u."code" IS DISTINCT FROM u."name"
          AND COALESCE(btrim(u."name"), '') <> '';
        """
    )

    for table in _SNAPSHOT_TABLES_WITH_DELETED:
        await _backfill_material_unit(db, table, has_deleted=True)
    for table in _SNAPSHOT_TABLES_NO_DELETED:
        await _backfill_material_unit(db, table, has_deleted=False)

    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "SELECT 1;"
