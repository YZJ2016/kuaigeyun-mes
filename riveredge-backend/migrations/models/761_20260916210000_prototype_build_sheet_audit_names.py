"""样机制作书补齐 BaseModel 审计姓名列。

758 建表时漏了 created_by_name / updated_by_name，列表查询会报 column does not exist。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_prototype_build_sheets"
    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_prototype_build_sheets"
    DROP COLUMN IF EXISTS "updated_by_name",
    DROP COLUMN IF EXISTS "created_by_name";
"""
