"""
KU-AI 重建 S3 Phase 1 — 知识库数据面（KR-D12）

1. 新建 apps_kuaiai_knowledge_bases（知识库父表）：
   name / description / embedding_model_id / chunk_size / chunk_overlap /
   expand_enabled / status（闭集 启用|停用）。
   - embedding_model_id 挂 apps_kuaiai_llm_models 的 embed 行，不写 DB 级 FK，
     同租户 + model_type='embed' + 启用由服务层校验；
   - chunk_size / chunk_overlap / expand_enabled 可空，NULL=回落租户可运营
     配置（site_settings/参数机制，不新写 yml）；
   - (tenant_id, name) 为 deleted_at IS NULL 部分唯一索引（软删可重建同名），
     与迁移 20260925100000_kuaiai_catalog_agent_tables 的既有惯例一致。
2. apps_kuaiai_knowledge_documents 增 knowledge_id（挂库）：
   不加 FK 约束（该表既有风格无 FK，归属由服务层复核），
   补 (tenant_id, knowledge_id) 索引。

chunks 表（apps_kuaiai_knowledge_chunks，迁移 395/517 已建）不动，
embedding_vector vector(768) + HNSW 沿用；training_samples/FAQ 不接产品。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "apps_kuaiai_knowledge_bases" (
            "id" SERIAL PRIMARY KEY,
            "uuid" VARCHAR(36) NOT NULL,
            "tenant_id" INT NOT NULL,
            "name" VARCHAR(200) NOT NULL,
            "description" TEXT,
            "embedding_model_id" INT,
            "chunk_size" INT,
            "chunk_overlap" INT,
            "expand_enabled" BOOL,
            "status" VARCHAR(20) NOT NULL DEFAULT '启用',
            "created_by" INT,
            "created_by_name" VARCHAR(100),
            "updated_by" INT,
            "updated_by_name" VARCHAR(100),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "deleted_at" TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_kb_tenant_uuid"
            ON "apps_kuaiai_knowledge_bases" ("tenant_id", "uuid");
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_kb_tenant_name"
            ON "apps_kuaiai_knowledge_bases" ("tenant_id", "name")
            WHERE "deleted_at" IS NULL;
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_kb_tenant"
            ON "apps_kuaiai_knowledge_bases" ("tenant_id");

        COMMENT ON TABLE "apps_kuaiai_knowledge_bases" IS 'KU-AI 知识库';
        COMMENT ON COLUMN "apps_kuaiai_knowledge_bases"."embedding_model_id" IS 'apps_kuaiai_llm_models.id，须本租户 model_type=embed 启用行；空=回落本租户第一条启用 embed；服务层校验，无 DB FK';
        COMMENT ON COLUMN "apps_kuaiai_knowledge_bases"."chunk_size" IS '切块大小；NULL=回落租户可运营配置';
        COMMENT ON COLUMN "apps_kuaiai_knowledge_bases"."chunk_overlap" IS '切块重叠；NULL=回落租户配置；约束 overlap>0 且 <chunk_size（服务层）';
        COMMENT ON COLUMN "apps_kuaiai_knowledge_bases"."expand_enabled" IS '检索前有限展开开关；NULL=回落租户配置（默认开）';
        COMMENT ON COLUMN "apps_kuaiai_knowledge_bases"."status" IS '启用|停用';

        ALTER TABLE "apps_kuaiai_knowledge_documents"
            ADD COLUMN IF NOT EXISTS "knowledge_id" INT;
        COMMENT ON COLUMN "apps_kuaiai_knowledge_documents"."knowledge_id" IS '所属知识库 apps_kuaiai_knowledge_bases.id；无 DB FK，服务层复核归属';
        CREATE INDEX IF NOT EXISTS "idx_kuaiai_kdoc_tenant_kb"
            ON "apps_kuaiai_knowledge_documents" ("tenant_id", "knowledge_id");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_kuaiai_kdoc_tenant_kb";
        ALTER TABLE "apps_kuaiai_knowledge_documents"
            DROP COLUMN IF EXISTS "knowledge_id";
        DROP TABLE IF EXISTS "apps_kuaiai_knowledge_bases" CASCADE;
    """
