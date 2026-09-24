"""
KU-AI 重建 S2 — 模型目录与 Agent 档案/授权表（数据与管理面）

1. apps_kuaiai_llm_providers / apps_kuaiai_llm_models（KR-D5 目录语义：
   厂商/模型自由配置，provider_type 仅模板标签、非闭集；
   api_key 列按 IntegrationConfig 口径存写、出参打码，密文不回前端）
2. apps_kuaiai_agent_profiles / apps_kuaiai_agent_grants（KR-D8/D9：
   grant_mode ROLE|USER 互斥；授权为档案上的数据名单）
3. 业务键唯一索引均为 deleted_at IS NULL 部分索引（软删后可重建同名行），
   与迁移 282/425 的既有惯例一致。

无应用种子（S1 迁移 20260924130000_kuaiai_chat_tables 已种 kuaiai 应用与权限码）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiai_llm_providers" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "code" VARCHAR(64) NOT NULL,
            "name" VARCHAR(100) NOT NULL,
            "base_url" VARCHAR(500) NOT NULL,
            "api_key" VARCHAR(500),
            "provider_type" VARCHAR(50),
            "status" VARCHAR(20) NOT NULL DEFAULT '启用',
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_llm_provider_tenant_uuid"
            ON "apps_kuaiai_llm_providers" ("tenant_id", "uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_llm_provider_tenant_code"
            ON "apps_kuaiai_llm_providers" ("tenant_id", "code")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_llm_provider_tenant"
            ON "apps_kuaiai_llm_providers" ("tenant_id");

        COMMENT ON TABLE "apps_kuaiai_llm_providers" IS 'KU-AI LLM 厂商目录';
        COMMENT ON COLUMN "apps_kuaiai_llm_providers"."api_key" IS '服务端解析用，出参打码不回明文';
        COMMENT ON COLUMN "apps_kuaiai_llm_providers"."provider_type" IS '可选模板标签，非闭集枚举';
        COMMENT ON COLUMN "apps_kuaiai_llm_providers"."status" IS '启用|停用';

        CREATE TABLE IF NOT EXISTS "apps_kuaiai_llm_models" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "provider_id" INT NOT NULL,
            "model_name" VARCHAR(200) NOT NULL,
            "model_type" VARCHAR(20) NOT NULL,
            "status" VARCHAR(20) NOT NULL DEFAULT '启用',
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_llm_model_tenant_uuid"
            ON "apps_kuaiai_llm_models" ("tenant_id", "uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_llm_model_tenant_provider_name"
            ON "apps_kuaiai_llm_models" ("tenant_id", "provider_id", "model_name")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_llm_model_tenant_provider"
            ON "apps_kuaiai_llm_models" ("tenant_id", "provider_id");

        COMMENT ON TABLE "apps_kuaiai_llm_models" IS 'KU-AI LLM 模型目录';
        COMMENT ON COLUMN "apps_kuaiai_llm_models"."model_type" IS 'chat|embed|vision';
        COMMENT ON COLUMN "apps_kuaiai_llm_models"."status" IS '启用|停用';

        CREATE TABLE IF NOT EXISTS "apps_kuaiai_agent_profiles" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "name" VARCHAR(100) NOT NULL,
            "description" TEXT,
            "system_prompt" TEXT,
            "default_model_id" INT,
            "knowledge_ids" JSONB NOT NULL DEFAULT '[]',
            "enabled_tools" JSONB NOT NULL DEFAULT '[]',
            "mcp_server_ids" JSONB NOT NULL DEFAULT '[]',
            "status" VARCHAR(20) NOT NULL DEFAULT '停用',
            "grant_mode" VARCHAR(10) NOT NULL,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_agent_profile_tenant_uuid"
            ON "apps_kuaiai_agent_profiles" ("tenant_id", "uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_agent_profile_tenant_name"
            ON "apps_kuaiai_agent_profiles" ("tenant_id", "name")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_agent_profile_tenant"
            ON "apps_kuaiai_agent_profiles" ("tenant_id");

        COMMENT ON TABLE "apps_kuaiai_agent_profiles" IS 'KU-AI Agent 档案';
        COMMENT ON COLUMN "apps_kuaiai_agent_profiles"."knowledge_ids" IS '知识库 id 列表（库表属 S3，本期仅存）';
        COMMENT ON COLUMN "apps_kuaiai_agent_profiles"."enabled_tools" IS 'Tool 五值闭集子集';
        COMMENT ON COLUMN "apps_kuaiai_agent_profiles"."mcp_server_ids" IS 'MCP 白名单 id 列表（表属 S4，本期仅存）';
        COMMENT ON COLUMN "apps_kuaiai_agent_profiles"."status" IS '启用|停用';
        COMMENT ON COLUMN "apps_kuaiai_agent_profiles"."grant_mode" IS 'ROLE|USER（互斥）';

        CREATE TABLE IF NOT EXISTS "apps_kuaiai_agent_grants" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "agent_id" INT NOT NULL,
            "target_type" VARCHAR(10) NOT NULL,
            "target_id" INT NOT NULL,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_agent_grant_tenant_uuid"
            ON "apps_kuaiai_agent_grants" ("tenant_id", "uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_agent_grant_target"
            ON "apps_kuaiai_agent_grants" ("tenant_id", "agent_id", "target_type", "target_id")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_agent_grant_tenant_agent"
            ON "apps_kuaiai_agent_grants" ("tenant_id", "agent_id");

        COMMENT ON TABLE "apps_kuaiai_agent_grants" IS 'KU-AI Agent 档案使用授权名单';
        COMMENT ON COLUMN "apps_kuaiai_agent_grants"."target_type" IS 'role|user';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiai_agent_grants" CASCADE;
        DROP TABLE IF EXISTS "apps_kuaiai_agent_profiles" CASCADE;
        DROP TABLE IF EXISTS "apps_kuaiai_llm_models" CASCADE;
        DROP TABLE IF EXISTS "apps_kuaiai_llm_providers" CASCADE;
    """
