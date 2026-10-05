"""
快数采：连接源 MQTT 最近报文表（跨 API/Worker 进程展示消息体）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiiot_connection_messages" (
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
            "topic" VARCHAR(255) NOT NULL,
            "qos" INT NOT NULL DEFAULT 0,
            "retained" BOOL NOT NULL DEFAULT False,
            "payload" JSONB,
            "payload_format" VARCHAR(30) NOT NULL DEFAULT 'unknown',
            "ingest_summary" JSONB,
            "error_message" TEXT,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_kuaiiot_conn_msg_tenant_conn_created"
            ON "apps_kuaiiot_connection_messages" ("tenant_id", "connection_id", "created_at");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiiot_connection_messages";
    """
