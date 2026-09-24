"""
KU-AI S3 review 修复 — 切块幂等唯一索引（M1）

apps_kuaiai_knowledge_chunks 补 (tenant_id, document_id, chunk_index) 的
deleted_at IS NULL 部分唯一索引：index_document 并发重入/重解析时，行锁
（select_for_update）之外的意外双写由 DB 兜底拒绝；软删行不占唯一键，
与迁移 20260925110000_kuaiai_knowledge_base 的部分唯一索引惯例一致。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kuaiai_kchunk_doc_chunk"
            ON "apps_kuaiai_knowledge_chunks" ("tenant_id", "document_id", "chunk_index")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uidx_kuaiai_kchunk_doc_chunk";
    """
