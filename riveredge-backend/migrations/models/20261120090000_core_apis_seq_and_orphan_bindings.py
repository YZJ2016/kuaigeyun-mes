"""校准 core_apis 序列；清空指向已不存在接口的同步绑定 api_uuid（禁止读侧猜绑）。

997 已补主键/唯一约束；本机序列曾未对齐到 max(id)，新建会撞号。
德盛客户绑定等残留失效 uuid 一律置空，由用户在来源设置重选。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        SELECT setval(
            'core_apis_id_seq',
            GREATEST((SELECT COALESCE(MAX(id), 1) FROM "core_apis"), 1),
            true
        );

        -- 主数据 / 单据：顶层 api_uuid 失效则置空（sources JSON 由用户在界面重配）
        UPDATE apps_master_data_customer_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL
          AND api_uuid <> ''
          AND NOT EXISTS (
            SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid
          );

        UPDATE apps_master_data_supplier_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_master_data_material_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_master_data_material_unit_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_master_data_material_group_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_master_data_warehouse_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_master_data_engineering_bom_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_master_data_operation_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_kuaizhizao_sales_order_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_kuaizhizao_purchase_order_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_kuaizhizao_work_order_sync_binding b
        SET api_uuid = CASE
              WHEN api_uuid IS NOT NULL AND api_uuid <> ''
                AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid)
              THEN NULL
              ELSE api_uuid
            END,
            push_save_api_uuid = CASE
              WHEN push_save_api_uuid IS NOT NULL AND push_save_api_uuid <> ''
                AND NOT EXISTS (
                  SELECT 1 FROM core_apis a WHERE a.uuid::text = b.push_save_api_uuid
                )
              THEN NULL
              ELSE push_save_api_uuid
            END
        WHERE (
          api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid)
        ) OR (
          push_save_api_uuid IS NOT NULL AND push_save_api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.push_save_api_uuid)
        );

        UPDATE apps_kuaizhizao_inventory_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

        UPDATE apps_kuaizhizao_reporting_sync_binding b
        SET api_uuid = NULL
        WHERE api_uuid IS NOT NULL AND api_uuid <> ''
          AND NOT EXISTS (SELECT 1 FROM core_apis a WHERE a.uuid::text = b.api_uuid);

    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 序列与失效 uuid 清理不可逆
        SELECT 1;
    """
