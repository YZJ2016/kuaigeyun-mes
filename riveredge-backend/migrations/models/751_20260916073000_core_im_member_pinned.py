"""
IM 成员会话置顶：is_pinned；公共群历史成员默认置顶。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_im_conversation_members"
    ADD COLUMN IF NOT EXISTS "is_pinned" BOOL NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS "idx_core_im_member_tenant_user_pinned"
    ON "core_im_conversation_members" ("tenant_id", "user_id", "is_pinned");

UPDATE "core_im_conversation_members" AS m
SET "is_pinned" = TRUE
FROM "core_im_conversations" AS c
WHERE m."conversation_id" = c."id"
  AND m."tenant_id" = c."tenant_id"
  AND c."is_public" = TRUE
  AND m."deleted_at" IS NULL
  AND c."deleted_at" IS NULL;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX IF EXISTS "idx_core_im_member_tenant_user_pinned";
ALTER TABLE "core_im_conversation_members" DROP COLUMN IF EXISTS "is_pinned";
"""
