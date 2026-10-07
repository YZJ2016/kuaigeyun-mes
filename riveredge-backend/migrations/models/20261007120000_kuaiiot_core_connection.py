"""数采关联公共连接；系统未上线，不迁移或合并存量配置。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiiot_connections" ADD COLUMN "integration_id" INT;
        ALTER TABLE "apps_kuaiiot_connections"
            ADD CONSTRAINT "fk_kuaiiot_connection_integration"
            FOREIGN KEY ("integration_id") REFERENCES "core_integration_configs" ("id") ON DELETE RESTRICT;
        CREATE INDEX "idx_kuaiiot_connection_integration"
            ON "apps_kuaiiot_connections" ("integration_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX "idx_kuaiiot_connection_integration";
        ALTER TABLE "apps_kuaiiot_connections" DROP CONSTRAINT "fk_kuaiiot_connection_integration";
        ALTER TABLE "apps_kuaiiot_connections" DROP COLUMN "integration_id";
    """
