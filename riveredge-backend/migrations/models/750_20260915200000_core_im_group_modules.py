"""
IM 群聊：公共群标记 + 模块绑定表。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_im_conversations"
    ADD COLUMN IF NOT EXISTS "is_public" BOOL NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS "idx_core_im_conv_tenant_public"
    ON "core_im_conversations" ("tenant_id", "is_public");

CREATE TABLE IF NOT EXISTS "core_im_conversation_modules" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "uuid" VARCHAR(36) NOT NULL,
    "tenant_id" INT NOT NULL,
    "conversation_id" INT NOT NULL,
    "module_code" VARCHAR(64) NOT NULL,
    "created_by" INT,
    "created_by_name" VARCHAR(100),
    "updated_by" INT,
    "updated_by_name" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_im_conv_modules_uuid"
    ON "core_im_conversation_modules" ("uuid");
CREATE UNIQUE INDEX IF NOT EXISTS "uid_core_im_conv_modules_tcm"
    ON "core_im_conversation_modules" ("tenant_id", "conversation_id", "module_code");
CREATE INDEX IF NOT EXISTS "idx_core_im_conv_modules_module"
    ON "core_im_conversation_modules" ("tenant_id", "module_code");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP TABLE IF EXISTS "core_im_conversation_modules";
ALTER TABLE "core_im_conversations" DROP COLUMN IF EXISTS "is_public";
"""
