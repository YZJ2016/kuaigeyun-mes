"""
apps_kuaizhizao_document_relations.target_id：INT4 → BIGINT。

金蝶云苍穹等外部系统单据内码为雪花 ID（>int32），外推成功后写关联会溢出。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_document_relations"
    ALTER COLUMN "target_id" TYPE BIGINT
    USING "target_id"::bigint;
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaizhizao_document_relations"
    ALTER COLUMN "target_id" TYPE INTEGER
    USING "target_id"::integer;
"""
