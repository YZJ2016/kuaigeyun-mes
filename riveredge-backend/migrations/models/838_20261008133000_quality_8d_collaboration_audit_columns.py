"""8D 协同表补齐 BaseModel 审计列，uuid 对齐 VARCHAR(36)。

824 建 stage_assignments / action_items 时未含 created_by* / updated_by*，
且 uuid 为 PG UUID；列表 enrich 查询指派/行动项时 SELECT updated_by_name 会 500。
对齐迁移 664（stage_revisions 审计列）与 502/837（uuid varchar）。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


_TABLES = (
    "apps_kuaizhizao_quality_8d_stage_assignments",
    "apps_kuaizhizao_quality_8d_action_items",
)


async def upgrade(db: BaseDBAsyncClient) -> str:
    parts: list[str] = []
    for table in _TABLES:
        parts.append(
            f"""
ALTER TABLE "{table}"
    ADD COLUMN IF NOT EXISTS "created_by" INT,
    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
    ADD COLUMN IF NOT EXISTS "updated_by" INT,
    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
ALTER TABLE "{table}"
    ALTER COLUMN "uuid" TYPE VARCHAR(36) USING "uuid"::text;
"""
        )
    return "\n".join(parts)


async def downgrade(db: BaseDBAsyncClient) -> str:
    parts: list[str] = []
    for table in _TABLES:
        parts.append(
            f"""
ALTER TABLE "{table}"
    ALTER COLUMN "uuid" TYPE UUID USING "uuid"::uuid;
ALTER TABLE "{table}"
    DROP COLUMN IF EXISTS "updated_by_name",
    DROP COLUMN IF EXISTS "updated_by",
    DROP COLUMN IF EXISTS "created_by_name",
    DROP COLUMN IF EXISTS "created_by";
"""
        )
    return "\n".join(parts)
