"""汇率设置表补齐 BaseModel 审计列。

807 建表漏 created_by / created_by_name / updated_by / updated_by_name，
INSERT/SELECT 会报 column created_by does not exist。
"""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaicaiwu_gl_exchange_rates"
    ADD COLUMN IF NOT EXISTS "created_by" INT,
    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
    ADD COLUMN IF NOT EXISTS "updated_by" INT,
    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100);
COMMENT ON TABLE "apps_kuaicaiwu_gl_exchange_rates" IS '管理会计 - 汇率设置';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaicaiwu_gl_exchange_rates"
    DROP COLUMN IF EXISTS "updated_by_name",
    DROP COLUMN IF EXISTS "updated_by",
    DROP COLUMN IF EXISTS "created_by_name",
    DROP COLUMN IF EXISTS "created_by";
COMMENT ON TABLE "apps_kuaicaiwu_gl_exchange_rates" IS '管理会计 - 汇率表';
"""
