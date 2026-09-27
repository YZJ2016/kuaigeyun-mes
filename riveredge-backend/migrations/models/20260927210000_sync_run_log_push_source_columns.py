"""SyncRunLog 外推源单据维度：source_type / source_id（spec 142 金蝶失败可见未推送）。

推送失败也必须能按单据查到「未推送/失败」态：DocumentPushPipeline 每次正式推送
（成功或失败）都写 core_sync_run_logs，补上源单据维度后按
(tenant_id, entity_type=document_push, source_type, source_id) 即可查询。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_sync_run_logs"
    ADD COLUMN IF NOT EXISTS "source_type" VARCHAR(50);
ALTER TABLE "core_sync_run_logs"
    ADD COLUMN IF NOT EXISTS "source_id" INT;
COMMENT ON COLUMN "core_sync_run_logs"."source_type" IS '外推源单据类型（entity_type=document_push 时写入）';
COMMENT ON COLUMN "core_sync_run_logs"."source_id" IS '外推源单据ID（entity_type=document_push 时写入）';
CREATE INDEX IF NOT EXISTS "idx_sync_run_logs_push_source"
    ON "core_sync_run_logs" ("tenant_id", "entity_type", "source_type", "source_id");
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
DROP INDEX IF EXISTS "idx_sync_run_logs_push_source";
ALTER TABLE "core_sync_run_logs" DROP COLUMN IF EXISTS "source_id";
ALTER TABLE "core_sync_run_logs" DROP COLUMN IF EXISTS "source_type";
"""
