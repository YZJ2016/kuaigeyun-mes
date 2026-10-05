"""
质量体系条款 M2M 关联表补齐 BaseModel 审计列（created_by_name 等）。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True

_LINK_TABLES = (
    "apps_kuaizhizao_qms_document_clauses",
    "apps_kuaizhizao_qms_audit_clauses",
    "apps_kuaizhizao_qms_review_standards",
)


def _alter_block(table: str) -> str:
    return f"""
ALTER TABLE "{table}"
    ADD COLUMN IF NOT EXISTS "created_by" INT,
    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
    ADD COLUMN IF NOT EXISTS "updated_by" INT,
    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
"""


async def upgrade(db: BaseDBAsyncClient) -> str:
    return "".join(_alter_block(t) for t in _LINK_TABLES)


async def downgrade(db: BaseDBAsyncClient) -> str:
    parts = []
    for table in _LINK_TABLES:
        parts.append(
            f"""
ALTER TABLE "{table}"
    DROP COLUMN IF EXISTS "updated_by_name",
    DROP COLUMN IF EXISTS "updated_by",
    DROP COLUMN IF EXISTS "created_by_name",
    DROP COLUMN IF EXISTS "created_by";
"""
        )
    return "".join(parts)
