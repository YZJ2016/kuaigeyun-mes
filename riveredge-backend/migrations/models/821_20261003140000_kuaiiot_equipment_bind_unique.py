"""
快数采：同一租户下未删除设备的 equipment_uuid 唯一绑定。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- 历史重复绑定：保留最小 id，其余解绑
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, equipment_uuid
                       ORDER BY id
                   ) AS rn
            FROM "apps_kuaiiot_devices"
            WHERE deleted_at IS NULL
              AND equipment_uuid IS NOT NULL
              AND btrim(equipment_uuid) <> ''
        )
        UPDATE "apps_kuaiiot_devices" AS d
        SET equipment_uuid = NULL,
            updated_at = CURRENT_TIMESTAMP
        FROM ranked AS r
        WHERE d.id = r.id
          AND r.rn > 1;

        CREATE UNIQUE INDEX IF NOT EXISTS "uq_kuaiiot_devices_tenant_equipment_active"
            ON "apps_kuaiiot_devices" ("tenant_id", "equipment_uuid")
            WHERE deleted_at IS NULL
              AND equipment_uuid IS NOT NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uq_kuaiiot_devices_tenant_equipment_active";
    """
