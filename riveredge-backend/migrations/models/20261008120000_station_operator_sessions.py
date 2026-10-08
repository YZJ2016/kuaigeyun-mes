"""
工位操作员会话表：数据库会话 + 凭据哈希（spec 180 T4）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaizhizao_station_operator_sessions" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "terminal_user_id" INT NOT NULL,
            "workstation_id" INT,
            "workstation_name" VARCHAR(200),
            "operator_employee_id" INT NOT NULL,
            "operator_user_id" INT NOT NULL,
            "operator_name" VARCHAR(100) NOT NULL,
            "confirm_method" VARCHAR(20) NOT NULL,
            "credential_hash" VARCHAR(64) NOT NULL,
            "status" VARCHAR(20) NOT NULL DEFAULT 'active',
            "issued_at" TIMESTAMPTZ NOT NULL,
            "last_seen_at" TIMESTAMPTZ NOT NULL,
            "closed_at" TIMESTAMPTZ,
            "close_reason" VARCHAR(32),
            "deleted_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100)
        );
        CREATE INDEX IF NOT EXISTS "idx_station_opsess_tenant_terminal_status"
            ON "apps_kuaizhizao_station_operator_sessions" ("tenant_id", "terminal_user_id", "status");
        CREATE INDEX IF NOT EXISTS "idx_station_opsess_tenant_credhash"
            ON "apps_kuaizhizao_station_operator_sessions" ("tenant_id", "credential_hash");
        CREATE INDEX IF NOT EXISTS "idx_station_opsess_tenant_ws"
            ON "apps_kuaizhizao_station_operator_sessions" ("tenant_id", "workstation_id");
        -- 并发双会话兜底：同租户 + 同终端账号只允许一条 active 会话（PG 部分唯一索引）
        CREATE UNIQUE INDEX IF NOT EXISTS "uq_station_opsess_tenant_terminal_active"
            ON "apps_kuaizhizao_station_operator_sessions" ("tenant_id", "terminal_user_id")
            WHERE "status" = 'active';
        COMMENT ON TABLE "apps_kuaizhizao_station_operator_sessions" IS '快格轻制造 - 工位操作员会话';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uq_station_opsess_tenant_terminal_active";
        DROP TABLE IF EXISTS "apps_kuaizhizao_station_operator_sessions";
    """
