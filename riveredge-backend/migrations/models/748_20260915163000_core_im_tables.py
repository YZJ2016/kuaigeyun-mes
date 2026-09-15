"""IM 会话与消息表（与 MessageLog 分层）。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "core_im_conversations" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "kind" VARCHAR(20) NOT NULL,
            "title" VARCHAR(200),
            "last_message_at" TIMESTAMPTZ,
            "last_message_preview" VARCHAR(500),
            "created_by_id" INT,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_core_im_conv_tenant_last"
            ON "core_im_conversations" ("tenant_id", "last_message_at");
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_im_conversations_uuid"
            ON "core_im_conversations" ("uuid");

        CREATE TABLE IF NOT EXISTS "core_im_conversation_members" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "conversation_id" INT NOT NULL,
            "user_id" INT NOT NULL,
            "role" VARCHAR(20) NOT NULL DEFAULT 'member',
            "last_read_at" TIMESTAMPTZ,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_im_conv_members_tcu"
            ON "core_im_conversation_members" ("tenant_id", "conversation_id", "user_id");
        CREATE INDEX IF NOT EXISTS "idx_core_im_conv_members_user"
            ON "core_im_conversation_members" ("tenant_id", "user_id");

        CREATE TABLE IF NOT EXISTS "core_im_messages" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "conversation_id" INT NOT NULL,
            "sender_id" INT NOT NULL,
            "body" TEXT NOT NULL,
            "kind" VARCHAR(20) NOT NULL DEFAULT 'text',
            "ref_type" VARCHAR(50),
            "ref_id" VARCHAR(64),
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS "idx_core_im_msg_conv_created"
            ON "core_im_messages" ("tenant_id", "conversation_id", "created_at");
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_im_messages_uuid"
            ON "core_im_messages" ("uuid");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "core_im_messages";
        DROP TABLE IF EXISTS "core_im_conversation_members";
        DROP TABLE IF EXISTS "core_im_conversations";
    """
