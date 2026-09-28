"""消息记录增加可选附件列。不传附件时这两列为空。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_message_logs"
            ADD COLUMN IF NOT EXISTS "attachment_name" VARCHAR(255);
        ALTER TABLE "core_message_logs"
            ADD COLUMN IF NOT EXISTS "attachment_content" BYTEA;
        COMMENT ON COLUMN "core_message_logs"."attachment_name" IS '可选附件文件名';
        COMMENT ON COLUMN "core_message_logs"."attachment_content" IS '可选附件内容';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "core_message_logs" DROP COLUMN IF EXISTS "attachment_content";
        ALTER TABLE "core_message_logs" DROP COLUMN IF EXISTS "attachment_name";
    """
