"""
生产领料 / 采购申请等：单位编码 → 目录名称。

991 已覆盖质检与入出库；领料明细、请购明细（unit 字段）仍可能残留编码。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_MATERIAL_UNIT_TABLES = (
    "apps_kuaizhizao_production_picking_items",
    "apps_kuaizhizao_material_call_request_items",
    "apps_kuaizhizao_finished_goods_receipt_items",
    "apps_kuaizhizao_semi_finished_goods_receipt_items",
)


async def _backfill_column(
    db: BaseDBAsyncClient, table: str, column: str
) -> None:
    await db.execute_script(
        f"""
        UPDATE "{table}" AS t
        SET "{column}" = u."name"
        FROM "apps_master_data_units" AS u
        WHERE u."deleted_at" IS NULL
          AND t."tenant_id" = u."tenant_id"
          AND t."{column}" = u."code"
          AND u."code" IS DISTINCT FROM u."name"
          AND COALESCE(btrim(u."name"), '') <> '';
        """
    )


async def upgrade(db: BaseDBAsyncClient) -> str:
    for table in _MATERIAL_UNIT_TABLES:
        await _backfill_column(db, table, "material_unit")
    await _backfill_column(db, "apps_kuaizhizao_purchase_requisition_items", "unit")
    await _backfill_column(db, "apps_kuaizhizao_purchase_order_items", "unit")
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "SELECT 1;"
