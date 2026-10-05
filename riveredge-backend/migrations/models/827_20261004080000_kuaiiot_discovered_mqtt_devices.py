"""
快数采：MQTT 现场设备名录（从完整报文抽出，供新建设备下拉）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiiot_discovered_mqtt_devices" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "deleted_by" INT,
            "deleted_by_name" VARCHAR(100),
            "connection_id" INT NOT NULL,
            "external_device_id" VARCHAR(100) NOT NULL,
            "device_name" VARCHAR(100),
            "device_key" VARCHAR(100),
            "line_name" VARCHAR(100),
            "line_code" VARCHAR(50),
            "workshop_name" VARCHAR(100),
            "workshop_code" VARCHAR(50),
            "status" VARCHAR(30),
            "topic" VARCHAR(255),
            "last_seen_at" TIMESTAMPTZ,
            "deleted_at" TIMESTAMPTZ,
            CONSTRAINT "uid_kuaiiot_disc_mqtt_tenant_conn_ext"
                UNIQUE ("tenant_id", "connection_id", "external_device_id")
        );
        CREATE INDEX IF NOT EXISTS "idx_kuaiiot_disc_mqtt_tenant_conn"
            ON "apps_kuaiiot_discovered_mqtt_devices" ("tenant_id", "connection_id");
        CREATE INDEX IF NOT EXISTS "idx_kuaiiot_disc_mqtt_tenant_ext"
            ON "apps_kuaiiot_discovered_mqtt_devices" ("tenant_id", "external_device_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiiot_discovered_mqtt_devices";
    """
