"""下发对象 grant 表补齐 BaseModel 审计列（交付物 / 会签申请）。

843/844 建表时漏了 created_by / updated_by 等，列表查询 SELECT 审计字段会 500。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


_AUDIT_COLS = """
    ADD COLUMN IF NOT EXISTS "created_by" INT,
    ADD COLUMN IF NOT EXISTS "created_by_name" VARCHAR(100),
    ADD COLUMN IF NOT EXISTS "updated_by" INT,
    ADD COLUMN IF NOT EXISTS "updated_by_name" VARCHAR(100)
"""


async def upgrade(db: BaseDBAsyncClient) -> str:
    return f"""
ALTER TABLE "apps_kuaiplm_rd_project_deliverable_issue_grants"
{_AUDIT_COLS};
ALTER TABLE "apps_kuaioa_form_request_issue_grants"
{_AUDIT_COLS};
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
ALTER TABLE "apps_kuaiplm_rd_project_deliverable_issue_grants"
    DROP COLUMN IF EXISTS "updated_by_name",
    DROP COLUMN IF EXISTS "updated_by",
    DROP COLUMN IF EXISTS "created_by_name",
    DROP COLUMN IF EXISTS "created_by";
ALTER TABLE "apps_kuaioa_form_request_issue_grants"
    DROP COLUMN IF EXISTS "updated_by_name",
    DROP COLUMN IF EXISTS "updated_by",
    DROP COLUMN IF EXISTS "created_by_name",
    DROP COLUMN IF EXISTS "created_by";
"""
