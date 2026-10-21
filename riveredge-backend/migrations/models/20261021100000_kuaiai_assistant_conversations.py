"""KU-AI 助手对话历史表。"""
from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS core_kuaiai_assistant_conversations (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(36) NOT NULL,
            tenant_id INT,
            user_id INT NOT NULL,
            title VARCHAR(200) NOT NULL,
            messages JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by INT NULL,
            created_by_name VARCHAR(100) NULL,
            updated_by INT NULL,
            updated_by_name VARCHAR(100) NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_kuaiai_conv_tenant_user_uuid
            ON core_kuaiai_assistant_conversations (tenant_id, user_id, uuid);

        CREATE INDEX IF NOT EXISTS idx_kuaiai_conv_tenant_user_updated
            ON core_kuaiai_assistant_conversations (tenant_id, user_id, updated_at DESC);

        COMMENT ON TABLE core_kuaiai_assistant_conversations IS 'KU-AI 标签页助手会话历史';
        COMMENT ON COLUMN core_kuaiai_assistant_conversations.messages IS 'OpenAI 风格消息 JSON 数组';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS core_kuaiai_assistant_conversations;
    """
