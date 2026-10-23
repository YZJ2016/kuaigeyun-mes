"""KU-AI HITL checkpointer 表（spec 192 / SC-D8）

1. apps_kuaiai_agent_checkpoints：LangGraph checkpoint 主表
   （checkpoint/metadata 以 (type, bytes) 落 bytea；uuid6 checkpoint_id 字典序即时间序）
2. apps_kuaiai_agent_checkpoint_writes：pending writes 表
   （idx >=0 常规写入序号；<0 为 ERROR/SCHEDULED/INTERRUPT/RESUME 特殊写入）

只存执行现场（HITL 中断/续跑），非审计或会话历史真源；不进任何对外接口。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiai_agent_checkpoints" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "thread_id" VARCHAR(255) NOT NULL,
            "checkpoint_ns" VARCHAR(255) NOT NULL DEFAULT '',
            "checkpoint_id" VARCHAR(64) NOT NULL,
            "parent_checkpoint_id" VARCHAR(64),
            "checkpoint_type" VARCHAR(64) NOT NULL,
            "checkpoint_blob" BYTEA NOT NULL,
            "metadata_type" VARCHAR(64) NOT NULL,
            "metadata_blob" BYTEA NOT NULL,
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_agent_ckpt_tenant_thread_ns_id"
            ON "apps_kuaiai_agent_checkpoints" ("tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id");
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_agent_ckpt_created"
            ON "apps_kuaiai_agent_checkpoints" ("created_at");

        COMMENT ON TABLE "apps_kuaiai_agent_checkpoints" IS 'KU-AI Agent 执行现场 checkpoint（非审计真源）';

        CREATE TABLE IF NOT EXISTS "apps_kuaiai_agent_checkpoint_writes" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "thread_id" VARCHAR(255) NOT NULL,
            "checkpoint_ns" VARCHAR(255) NOT NULL DEFAULT '',
            "checkpoint_id" VARCHAR(64) NOT NULL,
            "task_id" VARCHAR(255) NOT NULL,
            "idx" INT NOT NULL,
            "channel" VARCHAR(255) NOT NULL,
            "value_type" VARCHAR(64) NOT NULL,
            "value_blob" BYTEA NOT NULL,
            "task_path" VARCHAR(255) NOT NULL DEFAULT '',
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_agent_ckptw_tenant_thread_ns_id_task_idx"
            ON "apps_kuaiai_agent_checkpoint_writes" ("tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx");
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_agent_ckptw_tenant_thread_ns_id"
            ON "apps_kuaiai_agent_checkpoint_writes" ("tenant_id", "thread_id", "checkpoint_ns", "checkpoint_id");
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_agent_ckptw_created"
            ON "apps_kuaiai_agent_checkpoint_writes" ("created_at");

        COMMENT ON TABLE "apps_kuaiai_agent_checkpoint_writes" IS 'KU-AI Agent 执行现场 pending writes（非审计真源）';
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "apps_kuaiai_agent_checkpoint_writes" CASCADE;
        DROP TABLE IF EXISTS "apps_kuaiai_agent_checkpoints" CASCADE;
    """
