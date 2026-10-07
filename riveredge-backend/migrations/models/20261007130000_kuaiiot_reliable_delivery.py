from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
    CREATE TABLE apps_kuaiiot_deliveries (
        id SERIAL PRIMARY KEY, uuid VARCHAR(36) NOT NULL, tenant_id INT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_by INT, created_by_name VARCHAR(100), updated_by INT, updated_by_name VARCHAR(100),
        kind VARCHAR(20) NOT NULL, delivery_key VARCHAR(128) NOT NULL, payload JSONB NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending', attempts INT NOT NULL DEFAULT 0,
        next_attempt_at TIMESTAMPTZ, last_error VARCHAR(200), UNIQUE(tenant_id, delivery_key)
    );
    CREATE INDEX idx_kuaiiot_delivery_due ON apps_kuaiiot_deliveries(status,next_attempt_at);
    CREATE INDEX idx_kuaiiot_delivery_tenant ON apps_kuaiiot_deliveries(tenant_id);
    ALTER TABLE apps_kuaiiot_alerts ADD COLUMN recovered_at TIMESTAMPTZ;
    ALTER TABLE apps_kuaiiot_alerts ADD COLUMN closed_at TIMESTAMPTZ;
    ALTER TABLE apps_kuaiiot_alerts ADD COLUMN closed_by INT;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
    ALTER TABLE apps_kuaiiot_alerts DROP COLUMN recovered_at, DROP COLUMN closed_at, DROP COLUMN closed_by;
    DROP TABLE apps_kuaiiot_deliveries;
    """
