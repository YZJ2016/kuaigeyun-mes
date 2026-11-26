"""
返工会签行：唯一约束改为仅对未删除行生效，避免软删后无法重建同部门节点。
"""

from tortoise import BaseDBAsyncClient


RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uidx_kz_rework_signoff_dept";
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kz_rework_signoff_dept"
            ON "apps_kuaizhizao_rework_order_signoffs" ("tenant_id", "rework_order_id", "dept_code")
            WHERE "deleted_at" IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uidx_kz_rework_signoff_dept";
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_kz_rework_signoff_dept"
            ON "apps_kuaizhizao_rework_order_signoffs" ("tenant_id", "rework_order_id", "dept_code");
    """

# 对应上游 1026_20261111093000_rework_signoff_partial_unique.py
