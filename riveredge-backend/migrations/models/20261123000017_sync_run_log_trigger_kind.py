"""core_sync_run_logs 增加触发方式：manual / trigger / scheduled。"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_sync_run_logs"
    ADD COLUMN IF NOT EXISTS "trigger_kind" VARCHAR(20) NOT NULL DEFAULT 'manual';
COMMENT ON COLUMN "core_sync_run_logs"."trigger_kind" IS '触发方式：manual 手动 / trigger 链式触发 / scheduled 定时';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "core_sync_run_logs" DROP COLUMN IF EXISTS "trigger_kind";
"""
