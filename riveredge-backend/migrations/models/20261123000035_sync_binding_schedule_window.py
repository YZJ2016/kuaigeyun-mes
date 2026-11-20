"""入站/单据同步绑定：定时允许时段（HH:mm）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_SYNC_BINDING_TABLES = (
    "apps_master_data_customer_sync_binding",
    "apps_master_data_supplier_sync_binding",
    "apps_master_data_warehouse_sync_binding",
    "apps_master_data_storage_location_sync_binding",
    "apps_master_data_warehouse_location_ref_sync_binding",
    "apps_master_data_material_sync_binding",
    "apps_master_data_material_multi_unit_sync_binding",
    "apps_master_data_material_batch_manage_sync_binding",
    "apps_master_data_material_unit_sync_binding",
    "apps_master_data_material_group_sync_binding",
    "apps_master_data_engineering_bom_sync_binding",
    "apps_master_data_operation_sync_binding",
    "apps_kuaizhizao_inventory_sync_binding",
    "apps_kuaizhizao_work_order_sync_binding",
    "apps_kuaizhizao_sales_order_sync_binding",
    "apps_kuaizhizao_purchase_order_sync_binding",
    "apps_kuaizhizao_reporting_sync_binding",
    "apps_kuaizhizao_sales_delivery_sync_binding",
    "apps_kuaizhizao_production_picking_sync_binding",
    "apps_kuaizhizao_finished_goods_receipt_sync_binding",
    "apps_kuaizhizao_other_inbound_sync_binding",
    "apps_kuaizhizao_other_outbound_sync_binding",
    "apps_kuaizhizao_purchase_receipt_sync_binding",
)


def _alter_blocks(direction: str) -> str:
    blocks: list[str] = ["DO $$\nBEGIN"]
    for table in _SYNC_BINDING_TABLES:
        if direction == "upgrade":
            blocks.append(
                f"""
            IF to_regclass('public.{table}') IS NOT NULL THEN
                ALTER TABLE "{table}"
                    ADD COLUMN IF NOT EXISTS "schedule_window_start" VARCHAR(5),
                    ADD COLUMN IF NOT EXISTS "schedule_window_end" VARCHAR(5);
            END IF;"""
            )
        else:
            blocks.append(
                f"""
            IF to_regclass('public.{table}') IS NOT NULL THEN
                ALTER TABLE "{table}"
                    DROP COLUMN IF EXISTS "schedule_window_start",
                    DROP COLUMN IF EXISTS "schedule_window_end";
            END IF;"""
            )
    blocks.append("END $$;")
    return "\n".join(blocks)


async def upgrade(db: BaseDBAsyncClient) -> str:
    return _alter_blocks("upgrade")


async def downgrade(db: BaseDBAsyncClient) -> str:
    return _alter_blocks("downgrade")
