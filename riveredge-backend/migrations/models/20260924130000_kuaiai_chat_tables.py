"""
KU-AI 重建 S1 — 会话与消息表（apps/kuaiai 骨架）

1. apps_kuaiai_chat_sessions / apps_kuaiai_chat_messages（含 tool 列，全宽历史预留）
2. 各租户补齐 kuaiai 应用记录（未安装，应用中心可发现后手动安装；
   已存在的历史行仅更新展示元数据，不动 is_installed）
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiai_chat_sessions" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "user_id" INT NOT NULL,
            "title" VARCHAR(300) NOT NULL DEFAULT '',
            "agent_id" INT,
            "model" VARCHAR(100),
            "last_message_at" TIMESTAMPTZ,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_chat_session_tenant_uuid"
            ON "apps_kuaiai_chat_sessions" ("tenant_id", "uuid");
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_chat_session_tenant_user"
            ON "apps_kuaiai_chat_sessions" ("tenant_id", "user_id");
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_chat_session_tenant_last_msg"
            ON "apps_kuaiai_chat_sessions" ("tenant_id", "last_message_at");

        COMMENT ON TABLE "apps_kuaiai_chat_sessions" IS 'KU-AI 对话会话';

        CREATE TABLE IF NOT EXISTS "apps_kuaiai_chat_messages" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "session_id" INT NOT NULL,
            "seq" INT NOT NULL,
            "role" VARCHAR(20) NOT NULL,
            "content" TEXT,
            "tool_calls" JSONB,
            "tool_call_id" VARCHAR(100),
            "tool_name" VARCHAR(100),
            "prompt_tokens" INT,
            "completion_tokens" INT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_chat_msg_tenant_session_seq"
            ON "apps_kuaiai_chat_messages" ("tenant_id", "session_id", "seq");
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_chat_msg_tenant_session"
            ON "apps_kuaiai_chat_messages" ("tenant_id", "session_id");

        COMMENT ON TABLE "apps_kuaiai_chat_messages" IS 'KU-AI 会话消息（含工具轨迹列）';
        COMMENT ON COLUMN "apps_kuaiai_chat_messages"."role" IS 'user|assistant|tool';

        INSERT INTO core_applications (
            uuid, tenant_id, code, name, description, version,
            entry_point, route_path, sort_order,
            is_system, is_active, is_installed,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            t.id,
            'kuaiai',
            'KU-AI',
            '嵌入业务场景的 AI 智能辅助引擎：全宽对话、顶栏助手、Agent 档案、知识库与 MCP 白名单',
            '2.0.0',
            '../apps/kuaiai/index.tsx',
            '/apps/kuaiai',
            350,
            FALSE, TRUE, FALSE,
            NOW(), NOW()
        FROM infra_tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM core_applications
            WHERE code = 'kuaiai' AND tenant_id = t.id AND deleted_at IS NULL
        );

        UPDATE core_applications
        SET sort_order = 350,
            name = 'KU-AI',
            description = '嵌入业务场景的 AI 智能辅助引擎：全宽对话、顶栏助手、Agent 档案、知识库与 MCP 白名单',
            entry_point = '../apps/kuaiai/index.tsx',
            route_path = '/apps/kuaiai',
            updated_at = NOW()
        WHERE code = 'kuaiai' AND deleted_at IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE FROM core_applications
        WHERE code = 'kuaiai' AND is_installed = FALSE AND deleted_at IS NULL;
        DROP TABLE IF EXISTS "apps_kuaiai_chat_messages" CASCADE;
        DROP TABLE IF EXISTS "apps_kuaiai_chat_sessions" CASCADE;
    """
