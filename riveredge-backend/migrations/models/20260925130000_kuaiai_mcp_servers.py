"""
KU-AI 重建 S4 — MCP 白名单数据面（KR-D11）

新建 apps_kuaiai_mcp_servers（租户 MCP 服务器白名单，≈ ktg-ai ai_mcp_server）：
- code / name / transport / endpoint / token / allowed_tools / status；
- transport 仅放行 http（映射 langchain-mcp-adapters streamable_http），
  stdio/sse/websocket 由服务层守卫拒绝（不落库）；
- endpoint 为 http/https 出站地址，localhost/metadata/回环/链路本地/组播/
  云元数据地址由 services/mcp_guard 在保存与建连两侧复核（失败关闭）；
- token 列存，出参打码（"****" + token_configured），口径同
  llm_providers.api_key（KR-D5 惯例），不回明文；
- allowed_tools 为允许工具名 CSV（必填非空；SQL 类工具名守卫拒绝）；
- (tenant_id, code) 为 deleted_at IS NULL 部分唯一索引（软删可重建同名），
  与迁移 20260925110000_kuaiai_knowledge_base 的既有惯例一致。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiai_mcp_servers" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "code" VARCHAR(64) NOT NULL,
            "name" VARCHAR(100) NOT NULL,
            "transport" VARCHAR(20) NOT NULL DEFAULT 'http',
            "endpoint" VARCHAR(500) NOT NULL,
            "token" TEXT,
            "allowed_tools" TEXT NOT NULL,
            "status" VARCHAR(20) NOT NULL DEFAULT '启用',
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_mcp_tenant_uuid"
            ON "apps_kuaiai_mcp_servers" ("tenant_id", "uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_mcp_tenant_code"
            ON "apps_kuaiai_mcp_servers" ("tenant_id", "code")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_mcp_tenant"
            ON "apps_kuaiai_mcp_servers" ("tenant_id");

        COMMENT ON TABLE "apps_kuaiai_mcp_servers" IS 'KU-AI MCP 白名单';
        COMMENT ON COLUMN "apps_kuaiai_mcp_servers"."code" IS '服务器代码（组织内唯一，软删可重建同名）';
        COMMENT ON COLUMN "apps_kuaiai_mcp_servers"."transport" IS '传输类型（仅 http，映射 streamable_http；服务层守卫拒绝其它值）';
        COMMENT ON COLUMN "apps_kuaiai_mcp_servers"."endpoint" IS 'MCP 服务端点 URL（http/https；服务层守卫禁 localhost/metadata/回环/链路本地/组播/云元数据）';
        COMMENT ON COLUMN "apps_kuaiai_mcp_servers"."token" IS 'Bearer Token（列存；出参打码不回明文，口径同 llm_providers.api_key）';
        COMMENT ON COLUMN "apps_kuaiai_mcp_servers"."allowed_tools" IS '允许工具名 CSV（必填非空；SQL 类工具名守卫拒绝）';
        COMMENT ON COLUMN "apps_kuaiai_mcp_servers"."status" IS '启用|停用';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiai_mcp_servers" CASCADE;
    """
