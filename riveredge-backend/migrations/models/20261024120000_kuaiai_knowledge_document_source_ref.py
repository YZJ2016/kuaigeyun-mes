"""
KU-AI spec 200（S3-a）— 知识文档外部来源列

apps_kuaiai_knowledge_documents 新增可空列 source_ref_type / source_ref_id：
SOP 同步等外部来源写 ("sop", sop.id)，一列对一可追溯、可重建。
(tenant_id, source_ref_type, source_ref_id) 在 deleted_at IS NULL 上建
部分唯一索引：同一来源行只对应一条未删文档；两列均为 NULL 的普通文档
不占唯一键（PostgreSQL 唯一索引中 NULL 互不相等）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "apps_kuaiai_knowledge_documents"
            ADD COLUMN IF NOT EXISTS "source_ref_type" varchar(50) NULL;
        ALTER TABLE "apps_kuaiai_knowledge_documents"
            ADD COLUMN IF NOT EXISTS "source_ref_id" int NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_kdoc_source_ref"
            ON "apps_kuaiai_knowledge_documents" ("tenant_id", "source_ref_type", "source_ref_id")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uidx_kuaiai_kdoc_source_ref";
        ALTER TABLE "apps_kuaiai_knowledge_documents"
            DROP COLUMN IF EXISTS "source_ref_id";
        ALTER TABLE "apps_kuaiai_knowledge_documents"
            DROP COLUMN IF EXISTS "source_ref_type";
    """
